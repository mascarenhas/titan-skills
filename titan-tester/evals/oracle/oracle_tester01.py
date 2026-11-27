#!/usr/bin/env python3
"""Independent Stage-B oracle for tester-01-native-subtests-cleanup-and-async."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(cmd, cwd=None, env=None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def parse_ran_count(output: str) -> int:
    m = re.search(r"\[==========\]\s+(\d+)\s+tests?\s+ran\.", output)
    return int(m.group(1)) if m else -1


def fail(msg: str) -> None:
    print(f"ORACLE FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    work = Path.cwd()
    test_file = work / "queue_test.titan"
    if not test_file.is_file():
        fail("missing queue_test.titan")

    src = test_file.read_text("utf-8")
    if re.search(r'\bimport\s+["\']queue_under_test\.titan["\']', src) is None:
        fail("queue_test.titan must white-box import \"queue_under_test.titan\" directly")
    if "async.loop(" in src:
        fail("queue_test.titan must not call async.loop() under default async bootstrap")

    # 1. Build and run natively against valid queue_under_test.titan
    r = run([
        "titanc", "-q", "--incremental", "--test", "--tree", ".",
        "-o", "build_valid", "--exe", "build_valid/queue_test", "queue_test",
    ])
    if r.returncode != 0:
        fail(f"native --test build failed:\n{r.stdout}")

    r = run(["./build_valid/queue_test", "-v"])
    if r.returncode != 0:
        fail(f"native test binary failed (rc={r.returncode}):\n{r.stdout}")

    ran_total = parse_ran_count(r.stdout)
    if ran_total < 6:
        fail(f"expected >= 6 tests/subtests to run, got {ran_total}:\n{r.stdout}")

    for req_case in (
        "queue_test.test_whitebox_and_errors",
        "queue_test.test_subtests_and_cleanup_order",
        "queue_test.test_async_drain",
        "queue_test.test_skip_mechanism",
    ):
        if f"[       OK ] {req_case}" not in r.stdout:
            fail(f"missing passing test case {req_case}:\n{r.stdout}")

    subtests = re.findall(
        r"\[       OK \] queue_test\.test_subtests_and_cleanup_order\.([A-Za-z0-9_]+)",
        r.stdout,
    )
    if len(subtests) < 3:
        fail(f"expected >= 3 passing subtests under test_subtests_and_cleanup_order, found {subtests}:\n{r.stdout}")

    if "[  SKIPPED ]" not in r.stdout:
        fail(f"expected at least one SKIPPED subtest in test_skip_mechanism:\n{r.stdout}")

    # 2. Verify Lua-pattern parent+child filtering works
    rf = run(["./build_valid/queue_test", "-f", "^queue_test[.]test_subtests_and_cleanup_order"])
    if rf.returncode != 0:
        fail(f"filtered native run failed:\n{rf.stdout}")
    ran_filtered = parse_ran_count(rf.stdout)
    if not (4 <= ran_filtered < ran_total):
        fail(f"filtered run count {ran_filtered} invalid vs total {ran_total}:\n{rf.stdout}")

    # 3. Verify browser --test portability via titan-browser-run
    sdk_root = run(["titanc", "--print-root"]).stdout.strip()
    browser_env = os.environ.copy()
    browser_env["TITAN_BUILD_PROFILE"] = "validation"
    rb = run([
        "titanc", "-q", "--target", "browser", "--test", "--tree", ".",
        "-o", "build_browser", "--exe", "build_browser/queue_test.mjs", "queue_test",
    ], env=browser_env)
    if rb.returncode != 0:
        fail(f"browser --test build failed:\n{rb.stdout}")

    browser_run = Path(sdk_root) / "lib/titan-browser/0.6/titan-browser-run"
    rr = run([str(browser_run), "build_browser/queue_test.mjs"], env=browser_env)
    if rr.returncode != 0:
        fail(f"titan-browser-run failed (rc={rr.returncode}):\n{rr.stdout}")
    ran_browser = parse_ran_count(rr.stdout)
    if ran_browser != ran_total:
        fail(f"browser test count {ran_browser} != native count {ran_total}:\n{rr.stdout}")

    # 4. Mutant-kill checks: test suite MUST fail against seeded buggy implementations
    for label, mutant_path in (
        ("fifo_and_whitebox_mutant", Path("/verify/oracle/mutant_queue_fifo.titan")),
        ("async_drain_mutant", Path("/verify/oracle/mutant_queue_async.titan")),
    ):
        with tempfile.TemporaryDirectory(prefix=f"t01_{label}_") as td:
            tdir = Path(td)
            shutil.copy2(test_file, tdir / "queue_test.titan")
            shutil.copy2(mutant_path, tdir / "queue_under_test.titan")
            mb = run([
                "titanc", "-q", "--test", "--tree", ".",
                "-o", "build", "--exe", "build/queue_test", "queue_test",
            ], cwd=tdir)
            if mb.returncode != 0:
                fail(f"mutant build unexpectedly failed for {label}:\n{mb.stdout}")
            mr = run(["./build/queue_test"], cwd=tdir)
            if mr.returncode == 0:
                fail(f"test suite FAILED TO KILL {label} (exited 0!):\n{mr.stdout}")

    print(f"ORACLE PASS: native={ran_total}, filtered={ran_filtered}, browser={ran_browser}, 2/2 mutants killed")


if __name__ == "__main__":
    main()
