#!/usr/bin/env python3
"""Independent Stage-B oracle for package-01-multi-module-rockspec-and-install."""
import os
import re
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
        "titan-metric-0.1.0-1.rockspec",
        "src/metric/core/core.titan",
        "src/metric/core/math_contrib.titan",
        "src/metric/format.titan",
        "tests/metric_test.titan",
    ):
        if not (work / rel).is_file():
            fail(f"missing expected deliverable: {rel}")

    rock_tree = setup_rock_tree("/verify/rock-tree")
    rt_bin = rock_tree / "bin"
    env = os.environ.copy()
    env["PATH"] = f"{rt_bin}:{env.get('PATH', '')}"
    for v in ("TITAN_ROOT", "TITAN_PATH", "TITAN_PATH_0_6", "LUA_PATH", "LUA_CPATH", "LUA_PATH_5_5", "LUA_CPATH_5_5"):
        env.pop(v, None)

    # 1. Verify rockspec loads cleanly in empty _ENV, is format 3.0, no --static, has Windows overrides & titan-install hook
    lua_audit = r'''
local env = {}
local fn, err = loadfile("titan-metric-0.1.0-1.rockspec", "t", env)
assert(fn, "rockspec load failed in empty _ENV: " .. tostring(err))
local ok, rerr = pcall(fn)
assert(ok, "rockspec exec failed in empty _ENV: " .. tostring(rerr))
assert(env.rockspec_format == "3.0", "rockspec_format must be 3.0")
assert(env.package == "titan-metric", "package must be titan-metric")
assert(env.version == "0.1.0-1", "version must be 0.1.0-1")
assert(type(env.dependencies) == "table", "missing dependencies")
local has_lua, has_titan = false, false
for _, d in ipairs(env.dependencies) do
  if d:match("^lua") then has_lua = true end
  if d:match("^titan") then has_titan = true end
end
assert(has_lua and has_titan, "dependencies must declare lua and titan")
assert(type(env.build) == "table" and env.build.type == "command", "build.type must be command")
assert(type(env.build.build_command) == "string", "missing build_command")
assert(not env.build.build_command:find("--static", 1, true), "library build_command must NOT pass --static")
assert(type(env.build.install_command) == "string" and env.build.install_command:find("$(PREFIX)/dist/modules", 1, true),
  "install_command must stage into $(PREFIX)/dist/modules")
assert(type(env.build.platforms) == "table" and type(env.build.platforms.windows) == "table",
  "missing build.platforms.windows overrides")
assert(type(env.build.platforms.windows.build_command) == "string" and env.build.platforms.windows.build_command:find("titanc.exe", 1, true),
  "Windows build_command must invoke titanc.exe")
assert(type(env.build.platforms.windows.install_command) == "string" and env.build.platforms.windows.install_command:find("metric.dll", 1, true),
  "Windows install_command must stage metric.dll")
assert(type(env.hooks) == "table" and type(env.hooks.post_install) == "string", "missing hooks.post_install")
assert(env.hooks.post_install:find("titan-install", 1, true) and env.hooks.post_install:find('--path "$(PREFIX)"', 1, true),
  'hooks.post_install must invoke titan-install --path "$(PREFIX)"')
assert(type(env.hooks.platforms) == "table" and type(env.hooks.platforms.windows) == "table"
  and env.hooks.platforms.windows.post_install:find("titan-install.bat", 1, true),
  "missing Windows hooks.platforms.windows.post_install titan-install.bat")
print("ROCKSPEC AUDIT OK")
'''
    r_rs = run([str(rt_bin / "lua"), "-e", lua_audit], env=env)
    if r_rs.returncode != 0 or "ROCKSPEC AUDIT OK" not in r_rs.stdout:
        fail(f"rockspec empty-_ENV audit failed:\n{r_rs.stdout}")

    # 2. Run native package tests
    r_tb = run([
        str(rt_bin / "titanc"), "-q", "--incremental", "--test",
        "--tree", "src;tests", "--test-dir", "tests",
        "-o", "build_tests", "--exe", "build_tests/metric_tests",
    ], env=env)
    if r_tb.returncode != 0:
        fail(f"native package test build failed:\n{r_tb.stdout}")
    r_tr = run(["./build_tests/metric_tests"], env=env)
    if r_tr.returncode != 0:
        fail(f"native package tests failed:\n{r_tr.stdout}")
    m_ran = re.search(r"\[==========\]\s+(\d+)\s+tests?\s+ran\.", r_tr.stdout)
    if not m_ran or int(m_ran.group(1)) <= 0:
        fail(f"expected > 0 package tests to run:\n{r_tr.stdout}")

    # 3. Install via luarocks --tree /verify/rock-tree make
    r_mk = run([
        str(rt_bin / "luarocks"), "--tree", str(rock_tree),
        "make", "titan-metric-0.1.0-1.rockspec",
    ], env=env)
    if r_mk.returncode != 0:
        fail(f"luarocks --tree /verify/rock-tree make failed:\n{r_mk.stdout}")

    # 4. Audit staged dist/ and published files in /verify/rock-tree
    staged_dist = rock_tree / "lib/luarocks/rocks-5.5/titan-metric/0.1.0-1/dist"
    if not staged_dist.is_dir():
        fail(f"missing staged dist/ dir: {staged_dist}")
    staged_files = []
    for root, dirs, files in os.walk(staged_dist):
        for name in dirs + files:
            p = Path(root) / name
            if p.is_symlink():
                fail(f"symlink forbidden in staged dist/: {p}")
        for name in files:
            p = Path(root) / name
            staged_files.append(str(p.relative_to(staged_dist)))
    if sorted(staged_files) != ["modules/metric.a", "modules/metric.so"]:
        fail(f"staged dist/ must contain ONLY modules/metric.so and modules/metric.a, got {sorted(staged_files)}")

    for pub in ("lib/titan/0.6/metric.so", "lib/titan/0.6/metric.a"):
        if not (rock_tree / pub).is_file():
            fail(f"missing published provider {pub} in /verify/rock-tree")

    # 5. Outside consumer verification (NO --tree, NO TITAN_PATH_0_6): dynamic, --static, and bare Lua
    with tempfile.TemporaryDirectory(prefix="pkg01_outside_") as td:
        out_dir = Path(td)
        shutil.copy2("/verify/oracle/oracle_consumer.titan", out_dir / "oracle_consumer.titan")

        r_dyn_b = run([str(rt_bin / "titanc"), "-q", "-o", "build-dyn", "--exe", "build-dyn/demo", "oracle_consumer"], env=env, cwd=out_dir)
        if r_dyn_b.returncode != 0:
            fail(f"outside dynamic consumer compile failed:\n{r_dyn_b.stdout}")
        r_dyn_r = run(["./build-dyn/demo"], env=env, cwd=out_dir)
        if r_dyn_r.returncode != 0 or r_dyn_r.stdout.strip() != "cpu=21":
            fail(f"outside dynamic consumer run failed: rc={r_dyn_r.returncode} out={r_dyn_r.stdout!r}")

        r_st_b = run([str(rt_bin / "titanc"), "-q", "--static", "-o", "build-static", "--exe", "build-static/demo", "oracle_consumer"], env=env, cwd=out_dir)
        if r_st_b.returncode != 0:
            fail(f"outside --static consumer compile failed:\n{r_st_b.stdout}")
        r_st_r = run(["./build-static/demo"], env=env, cwd=out_dir)
        if r_st_r.returncode != 0 or r_st_r.stdout.strip() != "cpu=21":
            fail(f"outside --static consumer run failed: rc={r_st_r.returncode} out={r_st_r.stdout!r}")

        r_lua = run([
            str(rt_bin / "lua"), "-e",
            'require "titan"; local c = require("metric.core"); local f = require("metric.format"); '
            'local out = f.render(c.make_sample("cpu", 7), 3); assert(out == "cpu=21", out); print(out)'
        ], env=env, cwd=out_dir)
        if r_lua.returncode != 0 or r_lua.stdout.strip() != "cpu=21":
            fail(f"bare Lua consumer failed: rc={r_lua.returncode} out={r_lua.stdout!r}")

        # Negative check: folder contributor math_contrib must NOT be importable directly
        (out_dir / "bad_contrib.titan").write_text(
            'local m = import "metric.core.math_contrib"\nfunction main(_: {string}): integer return 0 end\n',
            "utf-8",
        )
        r_neg = run([str(rt_bin / "titanc"), "-q", "-o", "build-neg", "--exe", "build-neg/bad", "bad_contrib"], env=env, cwd=out_dir)
        if r_neg.returncode == 0:
            fail("folder contributor metric.core.math_contrib must NOT be directly importable")

    print("ORACLE PASS: rockspec, tests, luarocks make, dist/ staging, outside dynamic/--static/Lua, and contributor privacy verified")


if __name__ == "__main__":
    main()
