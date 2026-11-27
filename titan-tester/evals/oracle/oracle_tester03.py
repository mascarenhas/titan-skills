#!/usr/bin/env python3
"""Independent Stage-B oracle for tester-03-ref-titan-repo-validation-suites."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_CLEAN_ENV = {
    "ROCKS_TREE",
    "TITAN_ROOT",
    "TITANC",
    "TITAN_PATH_0_6",
    "TITAN_PATH",
    "TITAN_EXTRA_CPPFLAGS",
    "TITAN_TARGET",
    "TITAN_NO_LINE_DIRECTIVES",
    "LUA_PATH",
    "LUA_CPATH",
    "LUA_PATH_5_5",
    "LUA_CPATH_5_5",
}

REQUIRED_TIMING_GUARDED = {"timer", "net", "ssl", "http", "websocket", "os"}


def fail(msg: str) -> None:
    print(f"ORACLE FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd, env=None):
    return subprocess.run(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def main() -> None:
    work = Path.cwd()
    plan_path = work / "validation-plan.json"
    script_path = work / "validation-commands.sh"
    if not plan_path.is_file():
        fail("missing validation-plan.json")
    if not script_path.is_file():
        fail("missing validation-commands.sh")

    try:
        plan = json.loads(plan_path.read_text("utf-8"))
    except Exception as exc:
        fail(f"invalid JSON in validation-plan.json: {exc}")

    # 1. Validate regression layer placement
    layers = plan.get("regression_layers")
    if not isinstance(layers, dict):
        fail("validation-plan.json missing regression_layers object")

    checker = layers.get("compiler_checker", {})
    if "spec/checker" not in str(checker.get("owning_layer", "")):
        fail(f"compiler_checker owning_layer must reference spec/checker: {checker}")
    if "run_checker" not in str(checker.get("helper_or_contract", "")):
        fail(f"compiler_checker helper_or_contract must mention helpers.run_checker: {checker}")
    if checker.get("in_luacov") is not True:
        fail("compiler_checker must have in_luacov=true")

    stdlib_api = layers.get("stdlib_public_api", {})
    if "spec/stdlib/titan" not in str(stdlib_api.get("owning_layer", "")):
        fail(f"stdlib_public_api owning_layer must reference spec/stdlib/titan: {stdlib_api}")
    if "TITAN_STDLIB_TEST_ROOTS" not in str(stdlib_api.get("manifest_var", "")):
        fail(f"stdlib_public_api manifest_var must be TITAN_STDLIB_TEST_ROOTS: {stdlib_api}")
    if stdlib_api.get("in_luacov") is not False:
        fail("stdlib_public_api must stay outside LuaCov (in_luacov=false)")

    browser_shim = layers.get("browser_stdlib_shim", {})
    if "TITAN_STDLIB_BROWSER_TEST_ROOTS" not in str(browser_shim.get("manifest_var", "")):
        fail(f"browser_stdlib_shim manifest_var must be TITAN_STDLIB_BROWSER_TEST_ROOTS: {browser_shim}")
    if ".browser.titan" not in str(browser_shim.get("variant_contract", "")):
        fail(f"browser_stdlib_shim variant_contract must reference .browser.titan contributors: {browser_shim}")

    new_spec = layers.get("new_compiler_spec_registration", {})
    if "spec/support/ci_compiler_test_groups.txt" not in str(new_spec.get("timing_file", "")):
        fail(f"new_compiler_spec_registration must reference spec/support/ci_compiler_test_groups.txt: {new_spec}")

    ci_jobs = set(plan.get("affected_linux_ci_jobs", []))
    for req_job in ("test-linux-compiler", "native-coverage", "browser-stdlib", "browser-playwright"):
        if req_job not in ci_jobs:
            fail(f"affected_linux_ci_jobs missing {req_job}: {sorted(ci_jobs)}")

    # 2. Validate clean-env list & SDK policy
    clean_unset = set(plan.get("clean_env_unset", []))
    missing_env = REQUIRED_CLEAN_ENV - clean_unset
    if missing_env:
        fail(f"clean_env_unset missing required vars: {sorted(missing_env)}")

    sdk = plan.get("sdk_policy", {})
    if sdk.get("lua_version") != "5.5.1":
        fail(f"sdk_policy.lua_version must be '5.5.1', got {sdk.get('lua_version')!r}")
    if sdk.get("repo_test_profile") != "validation":
        fail(f"sdk_policy.repo_test_profile must be 'validation', got {sdk.get('repo_test_profile')!r}")
    if sdk.get("default_profile") != "production":
        fail(f"sdk_policy.default_profile must be 'production', got {sdk.get('default_profile')!r}")
    if sdk.get("rocks_tree_equals_prefix") is not True:
        fail("sdk_policy.rocks_tree_equals_prefix must be true")
    if sdk.get("separate_profile_prefixes") is not True:
        fail("sdk_policy.separate_profile_prefixes must be true")
    if "worktree" not in str(sdk.get("concurrent_build_isolation", "")).lower():
        fail(f"sdk_policy.concurrent_build_isolation must specify separate worktrees: {sdk}")

    # 3. Validate native aggregate conventions & skip prefixes
    agg = plan.get("native_aggregate_rules", {})
    if agg.get("uv_bootstrap_flag") != "--no-uv-bootstrap":
        fail(f"native_aggregate_rules.uv_bootstrap_flag must be '--no-uv-bootstrap': {agg}")
    if agg.get("async_wrapper") != "support.runtime.run":
        fail(f"native_aggregate_rules.async_wrapper must be 'support.runtime.run': {agg}")
    helpers_set = set(agg.get("runtime_cleanup_helpers", []))
    if not {"support.runtime.cleanup", "support.async.cleanup_task"}.issubset(helpers_set):
        fail(f"native_aggregate_rules.runtime_cleanup_helpers incomplete: {helpers_set}")
    if agg.get("parallel_rejects_titan_filter") is not True:
        fail("native_aggregate_rules.parallel_rejects_titan_filter must be true")
    if set(agg.get("timing_guarded_owners", [])) != REQUIRED_TIMING_GUARDED:
        fail(f"timing_guarded_owners mismatch: got {agg.get('timing_guarded_owners')}, want {sorted(REQUIRED_TIMING_GUARDED)}")

    skips = agg.get("skip_prefixes", {})
    if (
        skips.get("platform") != "allowed"
        or skips.get("capability") != "allowed"
        or skips.get("unsupported") != "allowed"
        or skips.get("portability") != "fails_validation"
    ):
        fail(f"skip_prefixes mismatch (portability must fail validation): {skips}")

    # 4. Validate browser & platform gates
    gates = plan.get("browser_and_platform_gates", {})
    if gates.get("require_toolchain_env") != "TITAN_REQUIRE_BROWSER_TOOLCHAIN":
        fail(f"require_toolchain_env mismatch: {gates}")
    if gates.get("require_deployment_env") != "TITAN_REQUIRE_BROWSER_DEPLOYMENT":
        fail(f"require_deployment_env mismatch: {gates}")
    req_tools = set(gates.get("required_tool_envs", []))
    if not {"WASI_SDK_PATH", "BINARYEN_ROOT", "TITAN_NODE", "TITAN_CHROME"}.issubset(req_tools):
        fail(f"required_tool_envs incomplete: {req_tools}")
    if gates.get("macos_manual_full_requires_maintainer_approval") is not True:
        fail("macos_manual_full_requires_maintainer_approval must be true")
    if gates.get("windows_makefile") != "Makefile.win":
        fail(f"windows_makefile must be 'Makefile.win': {gates}")
    if gates.get("windows_local_ntfs_required") is not True:
        fail("windows_local_ntfs_required must be true")

    # 5. Syntax-check and execute validation-commands.sh under poisoned environment
    r_syn = run(["sh", "-n", str(script_path)])
    if r_syn.returncode != 0:
        fail(f"sh -n validation-commands.sh failed:\n{r_syn.stdout}")

    poisoned = os.environ.copy()
    for var in REQUIRED_CLEAN_ENV:
        poisoned[var] = f"POISON_{var}"
    sdk_root = run(["titanc", "--print-root"]).stdout.strip()
    if not sdk_root:
        fail("could not resolve SDK root via titanc --print-root")
    poisoned["PREFIX"] = sdk_root

    r_env = run(["sh", str(script_path), "--print-clean-env"], env=poisoned)
    if r_env.returncode != 0:
        fail(f"validation-commands.sh --print-clean-env failed:\n{r_env.stdout}")
    for var in REQUIRED_CLEAN_ENV:
        if f"POISON_{var}" in r_env.stdout or re.search(rf"^{var}=", r_env.stdout, re.M):
            fail(f"--print-clean-env failed to clear poisoned variable {var}:\n{r_env.stdout}")

    r_cmds = run(["sh", str(script_path), "--emit-commands"], env=poisoned)
    if r_cmds.returncode != 0:
        fail(f"validation-commands.sh --emit-commands failed:\n{r_cmds.stdout}")
    cmds_out = r_cmds.stdout

    # Verify required repo validation commands in emitted plan
    checks = [
        ("checkout busted with TITAN_ROOT & TITAN_PROBE_CACHE_DISABLE=1",
         r"TITAN_ROOT=.*TITAN_PROBE_CACHE_DISABLE=1.*busted\s+--run=checkout.*spec/checker/method_call_spec\.lua"),
        ("installed busted filter",
         r"make\s+busted-test\s+.*BUSTED_FILTER="),
        ("filtered native stdlib aggregate with escaped Lua pattern",
         r"make\s+titan-stdlib-test-run\s+.*TITAN_FILTER=['\"]?\^url\[\.\]tests\[\.\]"),
        ("fail-closed browser stdlib gate",
         r"TITAN_REQUIRE_BROWSER_TOOLCHAIN=1.*make\s+titan-stdlib-browser-test"),
        ("serial native coverage lane",
         r"make\s+titan-native-coverage\b"),
        ("canonical reinstall + full mixed suite",
         r"make\s+test\b"),
    ]
    for desc, pat in checks:
        if not re.search(pat, cmds_out):
            fail(f"--emit-commands missing {desc} (pattern {pat!r}):\n{cmds_out}")

    # Must NOT pair titan-stdlib-test-run-parallel with TITAN_FILTER
    if re.search(r"titan-stdlib-test-run-parallel[^\n]*TITAN_FILTER|TITAN_FILTER[^\n]*titan-stdlib-test-run-parallel", cmds_out):
        fail(f"must not pass TITAN_FILTER to titan-stdlib-test-run-parallel:\n{cmds_out}")

    # Must NOT pass -j to make titan-native-coverage
    if re.search(r"make[^\n]*-j[^\n]*titan-native-coverage|titan-native-coverage[^\n]*-j", cmds_out):
        fail(f"titan-native-coverage must run serially without -j:\n{cmds_out}")

    print("ORACLE PASS: validation-plan.json + validation-commands.sh verified cleanly")


if __name__ == "__main__":
    main()
