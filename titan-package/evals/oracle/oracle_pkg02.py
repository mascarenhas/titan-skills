#!/usr/bin/env python3
"""Independent Stage-B oracle for package-02-provider-bundling-dso-compat-and-uninstall."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/verify/oracle")
from setup_rock_tree import setup_rock_tree


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


def main() -> None:
    work = Path.cwd()
    for rel in (
        "helper.h",
        "helper.c",
        "base-rock/titan-tagfmt-0.1.0-1.rockspec",
        "v1/titan-bundle-1.0.0-1.rockspec",
        "v1/src/bundle/hash.titan",
        "v1/src/bundle/report.titan",
        "v2/titan-bundle-2.0.0-1.rockspec",
        "v2/src/bundle/hash.titan",
        "v2/src/bundle/report.titan",
    ):
        if not (work / rel).is_file():
            fail(f"missing expected deliverable: {rel}")

    # Verify v1/v2 do NOT use explicit .titan import across installed source-only boundary
    for rel in ("v1/src/bundle/report.titan", "v2/src/bundle/report.titan"):
        txt = (work / rel).read_text("utf-8")
        if 'tagfmt.titan' in txt:
            fail(f"{rel} must use ordinary import \"tagfmt\", never explicit .titan import across installed source boundary")

    rock_tree = setup_rock_tree("/verify/rock-tree")
    rt_bin = rock_tree / "bin"
    env = os.environ.copy()
    env["PATH"] = f"{rt_bin}:{env.get('PATH', '')}"
    for v in ("TITAN_ROOT", "TITAN_PATH", "TITAN_PATH_0_6", "LUA_PATH", "LUA_CPATH", "LUA_PATH_5_5", "LUA_CPATH_5_5"):
        env.pop(v, None)

    # Verify all 3 rockspecs load cleanly in empty _ENV and obey format 3.0 & no --static & no include/titan/
    for rs_path in (
        "base-rock/titan-tagfmt-0.1.0-1.rockspec",
        "v1/titan-bundle-1.0.0-1.rockspec",
        "v2/titan-bundle-2.0.0-1.rockspec",
    ):
        check_lua = f'''
local env = {{}}
local fn, err = loadfile({rs_path!r}, "t", env)
assert(fn, "loadfile failed: " .. tostring(err))
local ok, rerr = pcall(fn)
assert(ok, "exec failed in empty _ENV: " .. tostring(rerr))
assert(env.rockspec_format == "3.0", "rockspec_format must be 3.0")
if env.build and env.build.build_command then
  assert(not env.build.build_command:find("--static", 1, true), "library rockspec must NOT use --static")
end
assert(env.hooks and env.hooks.post_install and env.hooks.post_install:find("titan-install", 1, true),
  "rockspec must invoke titan-install in hooks.post_install")
'''
        r_chk = run([str(rt_bin / "lua"), "-e", check_lua], env=env)
        if r_chk.returncode != 0:
            fail(f"rockspec audit failed for {rs_path}:\n{r_chk.stdout}")

    # 1. Install source-only dependency rock titan-tagfmt
    r_base = run(
        [str(rt_bin / "luarocks"), "--tree", str(rock_tree), "make", "titan-tagfmt-0.1.0-1.rockspec"],
        env=env,
        cwd=work / "base-rock",
    )
    if r_base.returncode != 0:
        fail(f"installing titan-tagfmt failed:\n{r_base.stdout}")
    if not (rock_tree / "lib/titan/0.6/tagfmt.titan").is_file():
        fail("titan-tagfmt did not publish lib/titan/0.6/tagfmt.titan")

    # 2. Install compiled multi-module provider rock v1 (with -X helper.o and dist/include/bundle/helper.h)
    r_v1 = run(
        [str(rt_bin / "luarocks"), "--tree", str(rock_tree), "make", "titan-bundle-1.0.0-1.rockspec"],
        env=env,
        cwd=work / "v1",
    )
    if r_v1.returncode != 0:
        fail(f"installing titan-bundle v1 failed:\n{r_v1.stdout}")

    for pub in ("lib/titan/0.6/bundle.so", "lib/titan/0.6/bundle.a", "include/bundle/helper.h"):
        if not (rock_tree / pub).is_file():
            fail(f"v1 install missing published file {pub}")
    if (rock_tree / "include/titan/helper.h").exists():
        fail("package must NOT publish into reserved include/titan/")

    # 3. Build outside dynamic & --static consumers against v1 (consumer does NOT import tagfmt directly;
    #    -o is required so installed source tagfmt.titan compiles once under consumer ownership)
    with tempfile.TemporaryDirectory(prefix="pkg02_outside_") as td:
        out_dir = Path(td)
        shutil.copy2("/verify/oracle/oracle_bundle_consumer.titan", out_dir / "oracle_bundle_consumer.titan")

        r_dyn_b = run(
            [str(rt_bin / "titanc"), "-q", "-o", "build-dyn", "--exe", "build-dyn/consumer", "oracle_bundle_consumer"],
            env=env,
            cwd=out_dir,
        )
        if r_dyn_b.returncode != 0:
            fail(f"outside v1 dynamic consumer build failed:\n{r_dyn_b.stdout}")
        r_dyn_v1 = run(["./build-dyn/consumer"], env=env, cwd=out_dir)
        if r_dyn_v1.returncode != 0 or r_dyn_v1.stdout.strip() != "[h1]:33":
            fail(f"v1 dynamic consumer output mismatch: rc={r_dyn_v1.returncode} out={r_dyn_v1.stdout!r}")

        r_st_b = run(
            [str(rt_bin / "titanc"), "-q", "--static", "-o", "build-static", "--exe", "build-static/consumer", "oracle_bundle_consumer"],
            env=env,
            cwd=out_dir,
        )
        if r_st_b.returncode != 0:
            fail(f"outside v1 --static consumer build failed (check -X helper.o in bundle.a):\n{r_st_b.stdout}")
        r_st_v1 = run(["./build-static/consumer"], env=env, cwd=out_dir)
        if r_st_v1.returncode != 0 or r_st_v1.stdout.strip() != "[h1]:33":
            fail(f"v1 --static consumer output mismatch: rc={r_st_v1.returncode} out={r_st_v1.stdout!r}")

        # 4. Upgrade to v2 (ABI-compatible DSO replacement) WITHOUT rebuilding ./build-dyn/consumer!
        r_v2 = run(
            [str(rt_bin / "luarocks"), "--tree", str(rock_tree), "make", "titan-bundle-2.0.0-1.rockspec"],
            env=env,
            cwd=work / "v2",
        )
        if r_v2.returncode != 0:
            fail(f"installing titan-bundle v2 failed:\n{r_v2.stdout}")

        # Unrebuilt dynamic consumer MUST load v2 bundle.so seamlessly and emit v2 output!
        r_dyn_v2 = run(["./build-dyn/consumer"], env=env, cwd=out_dir)
        if r_dyn_v2.returncode != 0 or r_dyn_v2.stdout.strip() != "[h2]:1033":
            fail(
                f"unrebuilt dynamic consumer failed DSO ABI hot-swap to v2: "
                f"rc={r_dyn_v2.returncode} out={r_dyn_v2.stdout!r}"
            )

        # Already-linked --static consumer MUST stay pinned at v1 output!
        r_st_after = run(["./build-static/consumer"], env=env, cwd=out_dir)
        if r_st_after.returncode != 0 or r_st_after.stdout.strip() != "[h1]:33":
            fail(f"static consumer changed unexpectedly after .so swap: out={r_st_after.stdout!r}")

        # New unused export release_tag() in v2 is callable from Lua
        r_lua_v2 = run([
            str(rt_bin / "lua"), "-e",
            'require "titan"; local h = require("bundle.hash"); assert(h.release_tag() == "v2"); print(h.release_tag())'
        ], env=env, cwd=out_dir)
        if r_lua_v2.returncode != 0 or r_lua_v2.stdout.strip() != "v2":
            fail(f"v2 release_tag() Lua check failed: rc={r_lua_v2.returncode} out={r_lua_v2.stdout!r}")

    # 5. titan-uninstall lifecycle & physical ownership teardown in /verify/rock-tree
    # (a) Removing titan-tagfmt while titan-bundle depends on it MUST fail and preserve tagfmt.titan
    r_dep_fail = run([str(rt_bin / "titan-uninstall"), "titan-tagfmt"], env=env)
    if r_dep_fail.returncode == 0:
        fail("titan-uninstall titan-tagfmt should fail while titan-bundle still depends on it")
    if not (rock_tree / "lib/titan/0.6/tagfmt.titan").is_file():
        fail("failed dependency check must preserve published lib/titan/0.6/tagfmt.titan")

    # (b) Removing inactive older version titan-bundle 1.0.0-1 keeps active 2.0.0-1 files intact
    r_old = run([str(rt_bin / "titan-uninstall"), "titan-bundle", "1.0.0-1"], env=env)
    if r_old.returncode != 0:
        fail(f"titan-uninstall titan-bundle 1.0.0-1 failed:\n{r_old.stdout}")
    for pub in ("lib/titan/0.6/bundle.so", "lib/titan/0.6/bundle.a", "include/bundle/helper.h"):
        if not (rock_tree / pub).is_file():
            fail(f"removing inactive 1.0.0-1 must keep active {pub} intact")

    # (c) Removing active titan-bundle cleans all published bundle files
    r_act = run([str(rt_bin / "titan-uninstall"), "titan-bundle"], env=env)
    if r_act.returncode != 0:
        fail(f"titan-uninstall titan-bundle failed:\n{r_act.stdout}")
    for pub in ("lib/titan/0.6/bundle.so", "lib/titan/0.6/bundle.a", "include/bundle/helper.h"):
        if (rock_tree / pub).exists():
            fail(f"titan-uninstall titan-bundle left behind {pub}")

    # (d) Now removing titan-tagfmt succeeds and deletes tagfmt.titan
    r_tag = run([str(rt_bin / "titan-uninstall"), "titan-tagfmt"], env=env)
    if r_tag.returncode != 0:
        fail(f"titan-uninstall titan-tagfmt failed:\n{r_tag.stdout}")
    if (rock_tree / "lib/titan/0.6/tagfmt.titan").exists():
        fail("titan-uninstall titan-tagfmt left behind lib/titan/0.6/tagfmt.titan")

    # (e) Absent-rock uninstall is a clean no-op
    r_noop = run([str(rt_bin / "titan-uninstall"), "titan-bundle"], env=env)
    if r_noop.returncode != 0:
        fail(f"absent-rock titan-uninstall must be a clean no-op:\n{r_noop.stdout}")

    print("ORACLE PASS: source-only dep, -X C object, v1->v2 unrebuilt DSO hot-swap, and titan-uninstall teardown verified")


if __name__ == "__main__":
    main()
