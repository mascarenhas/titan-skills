#!/usr/bin/env python3
"""Independent Stage-B oracle for ls-02-unsaved-completion-hover-and-ffi-limits."""
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


def make_spy_server(tmp_dir: Path, real_bin: str, log_file: Path) -> Path:
    spy = tmp_dir / "spy_ls_wrapper.py"
    spy.write_text(
        f"""#!/usr/bin/env python3
import json, subprocess, sys, threading

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
        "sensor.h",
        "ws_main/titan-config.lua",
        "ws_main/src/editor.titan",
        "ws_ffi/titan-config.lua",
        "ws_ffi/src/bridge.titan",
        "ls_unsaved_audit.py",
    ]
    for rel in required:
        check((work / rel).is_file(), f"missing required deliverable: {rel}")

    spec = importlib.util.spec_from_file_location("ls_unsaved_audit", work / "ls_unsaved_audit.py")
    check(spec is not None and spec.loader is not None, "could not load ls_unsaved_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(hasattr(mod, "run_audit"), "ls_unsaved_audit.py must export run_audit")

    with tempfile.TemporaryDirectory(prefix="ls02_oracle_") as td:
        tmp = Path(os.path.realpath(td))
        shutil.copy2(work / "sensor.h", tmp / "sensor.h")
        ws_main = tmp / "ws_main"
        ws_ffi = tmp / "ws_ffi"
        shutil.copytree(work / "ws_main", ws_main)
        shutil.copytree(work / "ws_ffi", ws_ffi)

        # Verify both Titan modules compile cleanly with titanc -c.
        r1 = subprocess.run(
            ["titanc", "-q", "-c", "--tree", str(ws_main / "src"), "-o", str(tmp / "b_main"), "editor"],
            capture_output=True, text=True,
        )
        check(r1.returncode == 0, f"ws_main/src/editor.titan failed titanc -c: {r1.stderr}")

        r2 = subprocess.run(
            ["titanc", "-q", "-c", "--tree", str(ws_ffi / "src"), "-I", str(tmp),
             "-o", str(tmp / "b_ffi"), "bridge"],
            capture_output=True, text=True,
        )
        check(r2.returncode == 0, f"ws_ffi/src/bridge.titan failed titanc -c: {r2.stderr}")

        editor_path = ws_main / "src" / "editor.titan"
        editor_bytes_before = editor_path.read_bytes()
        check(b"UnsavedDraft" not in editor_bytes_before,
              "UnsavedDraft must NOT be saved in editor.titan on disk")
        editor_sha_before = hashlib.sha256(editor_bytes_before).hexdigest()

        spy_log = tmp / "spy_methods.log"
        spy_bin = make_spy_server(tmp, real_ls_bin, spy_log)

        saved_env = {k: os.environ.get(k) for k in ("TITAN_PREFIX", "LUA_PATH", "TITAN_PATH_0_6")}
        os.environ["TITAN_PREFIX"] = "/nonexistent/polluted/prefix"
        os.environ["LUA_PATH"] = "/nonexistent/?.lua"
        os.environ["TITAN_PATH_0_6"] = "/nonexistent/lib"

        try:
            report = mod.run_audit(str(spy_bin), sdk_root, str(ws_main), str(ws_ffi))
        finally:
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        check(isinstance(report, dict), f"run_audit must return a dict, got {type(report)}")
        check(report.get("saved_diag_count") == 0,
              f"expected saved_diag_count == 0, got {report.get('saved_diag_count')!r}")

        labels = report.get("unsaved_completion_labels", [])
        check(isinstance(labels, list) and "tag" in labels,
              f"expected 'tag' in unsaved_completion_labels, got {labels!r}")
        check(isinstance(report.get("unsaved_completion_incomplete"), bool),
              f"unsaved_completion_incomplete must be bool, got {report.get('unsaved_completion_incomplete')!r}")

        unsaved_hover = report.get("unsaved_hover_markdown", "")
        check(isinstance(unsaved_hover, str) and "UnsavedDraft" in unsaved_hover and "tag" in unsaved_hover,
              f"unsaved hover must describe UnsavedDraft after unsaved completion, got {unsaved_hover!r}")

        editor_sha_after = hashlib.sha256(editor_path.read_bytes()).hexdigest()
        check(editor_sha_after == editor_sha_before and report.get("saved_file_unchanged") is True,
              "unsaved audit must NOT modify ws_main/src/editor.titan on disk")

        ffi_hover = report.get("ffi_hover_markdown", "")
        check(isinstance(ffi_hover, str) and "sensor_scale" in ffi_hover and "foreign int" in ffi_hover,
              f"expected FFI hover signature for sensor_scale, got {ffi_hover!r}")
        check(report.get("ffi_definition_is_null") is True,
              f"FFI foreign import definition must be null, got {report.get('ffi_definition_is_null')!r}")
        ref_count = report.get("ffi_reference_count", 0)
        check(isinstance(ref_count, int) and ref_count >= 2,
              f"expected >= 2 in-module FFI references to sensor_scale, got {ref_count!r}")

        check(report.get("initial_ffi_origin") == "folder",
              f"expected initial_ffi_origin == 'folder', got {report.get('initial_ffi_origin')!r}")
        pid1 = report.get("initial_ffi_worker_pid")
        pid2 = report.get("released_ffi_worker_pid")
        check(isinstance(pid1, int) and pid1 > 0, f"invalid initial_ffi_worker_pid: {pid1!r}")
        check(report.get("released_ffi_origin") == "released",
              f"expected released_ffi_origin == 'released', got {report.get('released_ffi_origin')!r}")
        check(report.get("released_ffi_state") == "ready",
              f"expected released_ffi_state == 'ready', got {report.get('released_ffi_state')!r}")
        check(pid2 == pid1,
              f"released sibling root must reuse warm workerPid ({pid1} != {pid2})")
        check(report.get("post_release_ffi_hover_ok") is True,
              "hover on released sibling root must continue succeeding on warm worker")

        seen = set(spy_log.read_text("utf-8").splitlines()) if spy_log.is_file() else set()
        required_rpc = {
            "initialize",
            "initialized",
            "titan/workspaceStatus",
            "textDocument/diagnostic",
            "textDocument/didOpen",
            "textDocument/completion",
            "textDocument/hover",
            "textDocument/definition",
            "textDocument/references",
            "workspace/didChangeWorkspaceFolders",
            "shutdown",
            "exit",
        }
        missing = required_rpc - seen
        check(not missing, f"live language server missing required JSON-RPC calls: {sorted(missing)}")

    print("oracle_ls_unsaved PASS")


if __name__ == "__main__":
    main()
