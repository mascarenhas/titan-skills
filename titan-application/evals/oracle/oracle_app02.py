#!/usr/bin/env python3
"""Independent Stage-B oracle for application-02-incremental-provider-and-windows."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(cmd, env=None, cwd=None):
    return subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def fail(msg: str) -> None:
    print(f"ORACLE FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def find_single(root: Path, suffix: str) -> Path:
    matches = [p for p in root.rglob("*") if p.is_file() and str(p).endswith(suffix)]
    if not matches:
        fail(f"expected file ending with {suffix!r} under {root}")
    return matches[0]


def main() -> None:
    work = Path.cwd()
    for rel in (
        "lib/calc/core.titan",
        "app/main.titan",
        "build_app.sh",
        "run_stock_lua.sh",
        "Makefile",
        "deploy-windows.bat",
    ):
        if not (work / rel).is_file():
            fail(f"missing expected deliverable: {rel}")

    # 1. Pass 1: clean build via build_app.sh
    r1 = run(["sh", "build_app.sh"])
    if r1.returncode != 0:
        fail(f"Pass 1 build_app.sh failed (rc={r1.returncode}):\n{r1.stdout}")

    for art in (
        "build-dyn/app",
        "build-static/app",
        "dist/bin/app",
        "build-prov/calc/core.so",
        "build-prov/calc/core.a",
    ):
        if not (work / art).is_file():
            fail(f"missing expected build output: {art}")

    # Confirm incremental digest cache, link record, build lock, and embedded .titan.source sections
    if not (work / "build-static/.titan-build.lock").is_file():
        fail("expected build-static/.titan-build.lock from incremental build")
    if not (work / "build-static/.titan/digests").is_file():
        fail("expected build-static/.titan/digests persistent digest cache")
    link_records = list((work / "build-static/.titan-links").rglob("record"))
    if not link_records:
        fail("expected final-link certificate under build-static/.titan-links/*/record")

    core_obj = find_single(work / "build-static", "calc/core.o")
    main_obj = find_single(work / "build-static", "main.o")
    if b".titan.source" not in core_obj.read_bytes() or b".titan.source" not in main_obj.read_bytes():
        fail("expected embedded .titan.source certificate sections inside incremental .o files")
    core_stat_1 = (core_obj.stat().st_mtime_ns, core_obj.stat().st_ino)
    main_stat_1 = (main_obj.stat().st_mtime_ns, main_obj.stat().st_ino)

    # Verify executable outputs after Pass 1
    for bin_path in ("./build-dyn/app", "./build-static/app"):
        ro = run([bin_path])
        if ro.returncode != 0 or ro.stdout.strip() != "run:v1:73":
            fail(f"{bin_path} unexpected output: rc={ro.returncode} out={ro.stdout!r}")
        rs = run([bin_path, "--self-test"])
        if rs.returncode != 0 or rs.stdout.strip() != "self-test:v1:42":
            fail(f"{bin_path} --self-test unexpected output: rc={rs.returncode} out={rs.stdout!r}")

    # 2. Pass 2: unchanged rebuild must reuse BOTH .o objects (zero recompile)
    time.sleep(0.05)
    r2 = run(["sh", "build_app.sh"])
    if r2.returncode != 0:
        fail(f"Pass 2 build_app.sh failed:\n{r2.stdout}")
    core_stat_2 = (core_obj.stat().st_mtime_ns, core_obj.stat().st_ino)
    main_stat_2 = (main_obj.stat().st_mtime_ns, main_obj.stat().st_ino)
    if core_stat_2 != core_stat_1 or main_stat_2 != main_stat_1:
        fail(
            f"Pass 2 incremental build failed to reuse unchanged objects: "
            f"core={core_stat_1}->{core_stat_2}, main={main_stat_1}->{main_stat_2}\n{r2.stdout}"
        )

    # 3. Pass 3: edit ONLY app/main.titan; calc/core.o MUST stay untouched while main rebuilds
    main_titan = work / "app/main.titan"
    orig_main = main_titan.read_text("utf-8")
    if '"run:"' not in orig_main:
        fail('app/main.titan must output "run:" prefix on default invocation')
    time.sleep(0.05)
    main_titan.write_text(orig_main.replace('"run:"', '"run2:"', 1), "utf-8")
    try:
        r3 = run(["sh", "build_app.sh"])
        if r3.returncode != 0:
            fail(f"Pass 3 build_app.sh failed:\n{r3.stdout}")
        core_stat_3 = (core_obj.stat().st_mtime_ns, core_obj.stat().st_ino)
        if core_stat_3 != core_stat_1:
            fail(f"Pass 3 unnecessarily recompiled unchanged calc/core.o: {core_stat_1} -> {core_stat_3}")
        ro3 = run(["./build-static/app"])
        if ro3.returncode != 0 or ro3.stdout.strip() != "run2:v1:73":
            fail(f"Pass 3 binary did not reflect updated app/main.titan: rc={ro3.returncode} out={ro3.stdout!r}")
    finally:
        main_titan.write_text(orig_main, "utf-8")

    # 4. Relocated env -i delivery check (both subject script and independent oracle check)
    rcd = run(["sh", "build_app.sh", "--check-delivery"])
    if rcd.returncode != 0:
        fail(f"build_app.sh --check-delivery failed (rc={rcd.returncode}):\n{rcd.stdout}")
    with tempfile.TemporaryDirectory(prefix="app02_delivery_") as td:
        tdir = Path(td)
        shutil.copytree(work / "dist", tdir / "dist")
        clean_run = run(
            ["env", "-i", f"HOME={tdir}", "PATH=/usr/bin:/bin", str(tdir / "dist/bin/app"), "--self-test"],
            cwd=tdir,
        )
        if clean_run.returncode != 0 or clean_run.stdout.strip() != "self-test:v1:42":
            fail(
                f"relocated env -i delivery binary failed: rc={clean_run.returncode} out={clean_run.stdout!r}"
            )

    # 5. Stock Lua 5.5 hosting check (must NOT put provider dir on LUA_CPATH/package.cpath)
    stock_src = (work / "run_stock_lua.sh").read_text("utf-8")
    if re.search(r"LUA_CPATH[^\n]*(?:build-prov|lib/titan/0\.6)|package\.cpath[^\n]*(?:build-prov|lib/titan/0\.6)", stock_src):
        fail("run_stock_lua.sh must NOT add Titan provider dirs to LUA_CPATH or package.cpath")
    if "TITAN_PATH_0_6" not in stock_src or "LUA_CPATH_5_5" not in stock_src:
        fail("run_stock_lua.sh must configure LUA_CPATH_5_5 and TITAN_PATH_0_6")
    r_lua = run(["sh", "run_stock_lua.sh"])
    if r_lua.returncode != 0 or r_lua.stdout.strip() != "v1:56":
        fail(f"run_stock_lua.sh failed: rc={r_lua.returncode} out={r_lua.stdout!r}")

    # 6. Makefile audit: compiler-owned incremental build with + jobserver prefix, zero %.o rules
    mk_src = (work / "Makefile").read_text("utf-8")
    if re.search(r"^[^#]*%\.o\s*:", mk_src, re.M):
        fail("Makefile must NOT define hand-written per-module %.o rules")
    if not re.search(r"^\t\+", mk_src, re.M):
        fail("Makefile must use '+' recipe prefix to share Make jobserver with titanc")
    if "--incremental" not in mk_src:
        fail("Makefile must invoke titanc --incremental")
    if not re.search(r"^check-delivery\s*:\s*$", mk_src, re.M):
        fail("Makefile check-delivery target must be prerequisite-free")

    # 7. Windows .bat deployment audit: DLL-only (no --static), full payload layout
    bat_src = (work / "deploy-windows.bat").read_text("utf-8")
    if "--static" in bat_src:
        fail("deploy-windows.bat must NOT pass --static (Windows is DLL-only)")
    for req_win in (
        "titanc.exe",
        "app.exe",
        "lua55.dll",
        "libuv-1.dll",
        "libllhttp-9.4.dll",
        "libsqlite3-0.dll",
        "libcrypto",
        "libssl",
        "titan.dll",
        "main.dll",
    ):
        if req_win.lower() not in bat_src.lower():
            fail(f"deploy-windows.bat missing required Windows payload item: {req_win}")

    print("ORACLE PASS: 3-pass incremental reuse, env -i delivery, stock Lua, Makefile, and Windows layout verified")


if __name__ == "__main__":
    main()
