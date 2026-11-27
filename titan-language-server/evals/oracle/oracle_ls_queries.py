#!/usr/bin/env python3
"""Independent Stage-B oracle for ls-01-multiroot-config-and-stdio-queries."""
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def find_symbol_pos(path: Path, symbol: str, occurrence: int = 1) -> tuple[int, int]:
    """Return 0-based (line, utf16_col) for the Nth identifier occurrence."""
    count = 0
    for idx, line in enumerate(path.read_text("utf-8").splitlines()):
        start = 0
        while True:
            pos = line.find(symbol, start)
            if pos < 0:
                break
            before_ok = pos == 0 or not (line[pos - 1].isalnum() or line[pos - 1] == "_")
            after_pos = pos + len(symbol)
            after_ok = after_pos == len(line) or not (line[after_pos].isalnum() or line[after_pos] == "_")
            if before_ok and after_ok:
                count += 1
                if count == occurrence:
                    utf16_col = len(line[:pos].encode("utf-16-le")) // 2
                    return idx, utf16_col
            start = pos + 1
    fail(f"symbol {symbol!r} (occurrence {occurrence}) not found in {path}")
    raise AssertionError


def make_spy_server(tmp_dir: Path, real_bin: str, log_file: Path) -> Path:
    spy = tmp_dir / "spy_ls_wrapper.py"
    spy.write_text(
        f"""#!/usr/bin/env python3
import json, os, subprocess, sys, threading

real_bin = {real_bin!r}
log_file = {str(log_file)!r}
proc = subprocess.Popen([real_bin] + sys.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr)

def pump_in():
    buf = b""
    stdin_fd = sys.stdin.buffer
    with open(log_file, "a", encoding="utf-8") as lf:
        while True:
            chunk = stdin_fd.read1(4096) if hasattr(stdin_fd, "read1") else stdin_fd.read(1)
            if not chunk:
                break
            proc.stdin.write(chunk)
            proc.stdin.flush()
            buf += chunk
            while True:
                sep = buf.find(b"\\r\\n\\r\\n")
                if sep < 0:
                    break
                hdr = buf[:sep].decode("ascii", errors="replace")
                cl = None
                for hline in hdr.split("\\r\\n"):
                    if hline.lower().startswith("content-length:"):
                        cl = int(hline.split(":", 1)[1].strip())
                if cl is None or len(buf) < sep + 4 + cl:
                    break
                body = buf[sep + 4 : sep + 4 + cl]
                buf = buf[sep + 4 + cl :]
                try:
                    msg = json.loads(body.decode("utf-8"))
                    if "method" in msg:
                        lf.write(msg["method"] + "\\n")
                        lf.flush()
                except Exception:
                    pass
    try:
        proc.stdin.close()
    except Exception:
        pass

def pump_out():
    while True:
        chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(1)
        if not chunk:
            break
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()

t1 = threading.Thread(target=pump_in, daemon=True)
t2 = threading.Thread(target=pump_out, daemon=True)
t1.start(); t2.start()
proc.wait()
t1.join(timeout=2); t2.join(timeout=2)
sys.exit(proc.returncode)
""",
        encoding="utf-8",
    )
    spy.chmod(spy.stat().st_mode | stat.S_IXUSR)
    return spy


def main() -> None:
    work = Path.cwd()
    sdk_root = subprocess.check_output(["titanc", "--print-root"], text=True).strip()
    real_ls_bin = os.environ.get("TITAN_LS_BIN")
    check(bool(real_ls_bin and Path(real_ls_bin).is_file()), "TITAN_LS_BIN must point to staged LS binary")

    required = [
        "native_app/titan-config.lua",
        "native_app/titan-config.local.lua",
        "native_app/src/counts.titan",
        "browser_app/titan-config.lua",
        "browser_app/src/ok.titan",
        "browser_app/src/broken.titan",
        "probe_ls.py",
    ]
    for rel in required:
        check((work / rel).is_file(), f"missing required deliverable: {rel}")

    # Load subject's probe_ls.py module.
    spec = importlib.util.spec_from_file_location("probe_ls", work / "probe_ls.py")
    check(spec is not None and spec.loader is not None, "could not load probe_ls.py")
    probe_ls = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe_ls)

    # 1. Verify build_launcher_config hygiene.
    check(hasattr(probe_ls, "build_launcher_config"), "probe_ls missing build_launcher_config")
    cfg = probe_ls.build_launcher_config(sdk_root, real_ls_bin, ["/tmp/trust_a"])
    check(isinstance(cfg, dict) and "servers" in cfg and "titan" in cfg["servers"],
          "build_launcher_config must return {'servers': {'titan': ...}}")
    srv_cfg = cfg["servers"]["titan"]
    check("env" not in srv_cfg, "ServerConfig must NOT contain an 'env' field")
    check(srv_cfg.get("command") == "/usr/bin/env", "launcher command must be '/usr/bin/env'")
    args = srv_cfg.get("args", [])
    check(isinstance(args, list) and len(args) > 0, "launcher args must be a non-empty list")

    unset_vars = set()
    env_assigns = {}
    i = 0
    while i < len(args):
        if args[i] == "-u" and i + 1 < len(args):
            unset_vars.add(args[i + 1])
            i += 2
        elif "=" in args[i] and not args[i].startswith("/"):
            k, v = args[i].split("=", 1)
            env_assigns[k] = v
            i += 1
        else:
            i += 1

    must_unset = {
        "TITAN_PREFIX", "TITAN_PATH_0_6", "TITAN_PATH", "TITAN_SOURCE_PATH",
        "LUA_PATH", "LUA_CPATH", "LUA_PATH_5_5", "LUA_CPATH_5_5",
    }
    missing_unsets = must_unset - unset_vars
    check(not missing_unsets, f"launcher must unset {sorted(missing_unsets)}")
    check(env_assigns.get("TITAN_ROOT") == sdk_root, "launcher must set TITAN_ROOT=<sdk_root>")
    ls_lua_path = env_assigns.get("TITAN_LS_LUA_PATH", "")
    ls_lua_cpath = env_assigns.get("TITAN_LS_LUA_CPATH", "")
    check(f"{sdk_root}/share/lua/5.5/?.lua" in ls_lua_path and ";;" not in ls_lua_path,
          f"invalid verbatim TITAN_LS_LUA_PATH: {ls_lua_path!r}")
    check(f"{sdk_root}/lib/lua/5.5/?.so" in ls_lua_cpath and ";;" not in ls_lua_cpath,
          f"invalid verbatim TITAN_LS_LUA_CPATH: {ls_lua_cpath!r}")
    check(args[-1] == real_ls_bin, "launcher args must end with server_bin")
    root_markers = srv_cfg.get("rootMarkers", [])
    check("." not in root_markers, "rootMarkers must NOT contain '.'")
    check("titan-config.lua" in root_markers and "titan-config.local.lua" in root_markers,
          "rootMarkers must include titan-config.lua and titan-config.local.lua")
    init_opts = srv_cfg.get("initOptions", {})
    check(init_opts.get("trustedRoots") == ["/tmp/trust_a"],
          "initOptions.trustedRoots must forward trusted_roots")

    # 2. Verify counts.titan and browser ok.titan compile cleanly; broken.titan fails checking.
    with tempfile.TemporaryDirectory(prefix="ls01_oracle_") as td:
        tmp = Path(os.path.realpath(td))
        ws_native = tmp / "native_app"
        ws_browser = tmp / "browser_app"
        shutil.copytree(work / "native_app", ws_native)
        shutil.copytree(work / "browser_app", ws_browser)
        # Runtime temp symlink for relative compiler_root = "./local-sdk"
        os.symlink(sdk_root, ws_native / "local-sdk")

        # Verify native counts.titan compiles cleanly
        r_nat = subprocess.run(
            ["titanc", "-q", "-c", "--tree", str(ws_native / "src"), "-o", str(tmp / "build_nat"), "counts"],
            capture_output=True, text=True,
        )
        check(r_nat.returncode == 0, f"counts.titan failed titanc -c: {r_nat.stderr}")

        # Verify browser ok.titan compiles under --target browser -c and broken.titan fails
        env_br = dict(os.environ, TITAN_BUILD_PROFILE="validation")
        r_ok = subprocess.run(
            ["titanc", "-q", "--target", "browser", "-c", "--tree", str(ws_browser / "src"),
             "-o", str(tmp / "build_ok"), "ok"],
            capture_output=True, text=True, env=env_br,
        )
        check(r_ok.returncode == 0, f"browser ok.titan failed --target browser -c: {r_ok.stderr}")
        r_bad = subprocess.run(
            ["titanc", "-q", "--target", "browser", "-c", "--tree", str(ws_browser / "src"),
             "-o", str(tmp / "build_bad"), "broken"],
            capture_output=True, text=True, env=env_br,
        )
        check(r_bad.returncode != 0, "browser broken.titan must contain a real static type error")

        # Verify titan-config.local.lua contains ONLY compiler_root (checked live below too)
        local_cfg_text = (ws_native / "titan-config.local.lua").read_text("utf-8")
        check("compiler_root" in local_cfg_text, "native_app/titan-config.local.lua must set compiler_root")
        native_cfg_text = (ws_native / "titan-config.lua").read_text("utf-8")
        check("compiler_root" not in native_cfg_text, "tracked titan-config.lua must NOT set compiler_root")

        spy_log = tmp / "spy_methods.log"
        spy_bin = make_spy_server(tmp, real_ls_bin, spy_log)

        # Pollute ambient env to prove launcher /usr/bin/env -u strips hostile overrides!
        saved_env = {k: os.environ.get(k) for k in ("TITAN_PREFIX", "LUA_PATH", "TITAN_PATH_0_6")}
        os.environ["TITAN_PREFIX"] = "/nonexistent/polluted/prefix"
        os.environ["LUA_PATH"] = "/nonexistent/?.lua"
        os.environ["TITAN_PATH_0_6"] = "/nonexistent/lib"

        try:
            counts_path = ws_native / "src" / "counts.titan"
            ok_path = ws_browser / "src" / "ok.titan"
            broken_path = ws_browser / "src" / "broken.titan"
            counts_sha_before = hashlib.sha256(counts_path.read_bytes()).hexdigest()

            step_line, step_col = find_symbol_pos(counts_path, "step", 1)
            ok_fn_line, ok_fn_col = find_symbol_pos(ok_path, "format_count", 1)
            bad_fn_line, bad_fn_col = find_symbol_pos(broken_path, "bad", 1)

            # Run 1: Both roots trusted.
            with probe_ls.TitanLspClient(
                sdk_root=sdk_root,
                workspace_folders=[str(ws_native), str(ws_browser)],
                trusted_roots=[str(ws_native), str(ws_browser)],
                server_bin=str(spy_bin),
            ) as client:
                status = client.workspace_status()
                roots = {r["root"]: r for r in status.get("roots", [])}
                check(str(ws_native) in roots, f"native_app root missing from workspaceStatus: {roots}")
                check(str(ws_browser) in roots, f"browser_app root missing from workspaceStatus: {roots}")

                r_nat_st = roots[str(ws_native)]
                check(r_nat_st.get("state") == "ready", f"native_app not ready: {r_nat_st}")
                check(r_nat_st.get("trusted") is True, f"native_app not trusted: {r_nat_st}")
                check(str(r_nat_st.get("compilerRoot", "")).endswith("/local-sdk"),
                      f"native_app compilerRoot not resolved: {r_nat_st}")
                check(str(r_nat_st.get("probePrefix", "")).endswith("/.titan-ls"),
                      f"native_app probePrefix unexpected: {r_nat_st}")

                r_br_st = roots[str(ws_browser)]
                check(r_br_st.get("state") == "ready", f"browser_app not ready: {r_br_st}")
                check(r_br_st.get("target") == "browser", f"browser_app target != 'browser': {r_br_st}")

                # Pull diagnostics with previousResultId -> unchanged!
                d1 = client.pull_diagnostics(str(counts_path))
                check(d1.get("ok") is True, f"counts.titan diagnostics failed: {d1}")
                d1_res = d1["result"]
                check(d1_res.get("kind") == "full" and d1_res.get("items") == [],
                      f"expected clean full diagnostic report on counts.titan, got {d1_res}")
                rid = d1_res.get("resultId")
                check(isinstance(rid, str) and len(rid) > 0, f"missing resultId: {d1_res}")

                d2 = client.pull_diagnostics(str(counts_path), previous_result_id=rid)
                check(d2.get("ok") is True and d2["result"].get("kind") == "unchanged",
                      f"expected unchanged diagnostic report with previousResultId, got {d2}")

                # LDoc hover on step and Counter.label
                h_step = client.hover(str(counts_path), step_line, step_col)
                check(isinstance(h_step, str) and "step" in h_step and ("Parameter" in h_step or "Returns" in h_step),
                      f"expected LDoc hover markdown on step, got: {h_step!r}")
                # Find the field declaration line of `label` (contains `const label`)
                field_line, field_col = None, None
                for lno, text in enumerate(counts_path.read_text("utf-8").splitlines()):
                    if "const label" in text or ("label" in text and ": string" in text):
                        field_line = lno
                        field_col = len(text[:text.index("label")].encode("utf-16-le")) // 2
                        break
                check(field_line is not None, "could not locate label field in counts.titan")
                h_field = client.hover(str(counts_path), field_line, field_col)
                check(isinstance(h_field, str) and "string" in h_field and len(h_field.splitlines()) >= 3,
                      f"expected LDoc @field hover markdown on Counter.label, got: {h_field!r}")

                # Read-only rename preview: returns >= 2 edits and leaves disk file untouched.
                ren = client.preview_rename(str(counts_path), step_line, step_col, "advance_counter")
                changes = ren.get("changes", {}) if isinstance(ren, dict) else {}
                edits = changes.get("file://" + str(counts_path), [])
                check(len(edits) >= 2, f"expected >= 2 rename edits for step (def + call), got {ren}")
                check(all(e.get("newText") == "advance_counter" for e in edits),
                      f"unexpected rename edit text: {edits}")
                counts_sha_after = hashlib.sha256(counts_path.read_bytes()).hexdigest()
                check(counts_sha_after == counts_sha_before,
                      "preview_rename MUST be read-only and never modify files on disk")

                # Failed browser module emits diagnostics and null hover while valid sibling answers!
                d_bad = client.pull_diagnostics(str(broken_path))
                check(d_bad.get("ok") is True and len(d_bad["result"].get("items", [])) >= 1,
                      f"expected diagnostic item on broken.titan, got {d_bad}")
                h_bad = client.hover(str(broken_path), bad_fn_line, bad_fn_col)
                check(h_bad is None, f"failed module must return null hover, got {h_bad!r}")
                h_ok = client.hover(str(ok_path), ok_fn_line, ok_fn_col)
                check(isinstance(h_ok, str) and "format_count" in h_ok,
                      f"valid sibling ok.titan must still answer hover, got {h_ok!r}")

                # Unimplemented methods must be classified as -32601 unsupported, never empty/ok.
                unsup = client.probe_unsupported(str(counts_path), step_line, step_col)
                for m in (
                    "textDocument/documentSymbol",
                    "textDocument/typeDefinition",
                    "textDocument/implementation",
                    "textDocument/codeAction",
                ):
                    entry = unsup.get(m)
                    check(isinstance(entry, dict) and entry.get("status") == "unsupported"
                          and entry.get("code") == -32601,
                          f"method {m} must be classified unsupported/-32601, got {entry!r}")

            # Run 2: native_app NOT trusted -> state="failed", trusted=False, titanRoot=None, diag error -32803.
            with probe_ls.TitanLspClient(
                sdk_root=sdk_root,
                workspace_folders=[str(ws_native), str(ws_browser)],
                trusted_roots=[str(ws_browser)],
                server_bin=str(spy_bin),
            ) as client2:
                st2 = client2.workspace_status()
                roots2 = {r["root"]: r for r in st2.get("roots", [])}
                r_un = roots2.get(str(ws_native), {})
                check(r_un.get("trusted") is False and r_un.get("state") == "failed",
                      f"untrusted compiler_root must fail without fallback: {r_un}")
                check(r_un.get("titanRoot") is None and r_un.get("workerPid") is None,
                      f"untrusted root must not fall back to default SDK: {r_un}")
                d_un = client2.pull_diagnostics(str(counts_path))
                check(d_un.get("ok") is False and d_un.get("error", {}).get("code") == -32803,
                      f"untrusted root diagnostics must surface -32803 error, got {d_un}")

            # Verify live RPC traffic via spy log (defeats hardcoded stubs).
            seen = set(spy_log.read_text("utf-8").splitlines()) if spy_log.is_file() else set()
            expected_methods = {
                "initialize",
                "initialized",
                "titan/workspaceStatus",
                "textDocument/diagnostic",
                "textDocument/hover",
                "textDocument/rename",
                "textDocument/documentSymbol",
                "textDocument/typeDefinition",
                "textDocument/implementation",
                "textDocument/codeAction",
                "shutdown",
                "exit",
            }
            missing_rpc = expected_methods - seen
            check(not missing_rpc, f"live language server did not receive expected JSON-RPC methods: {sorted(missing_rpc)}")
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    print("oracle_ls_queries PASS")


if __name__ == "__main__":
    main()
