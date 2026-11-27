#!/usr/bin/env python3
"""Independent Stage-B oracle for tester-02-test-dir-filtering-and-coverage."""
import os
import re
import subprocess
import sys
from pathlib import Path


def run(cmd, env=None):
    return subprocess.run(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def fail(msg: str) -> None:
    print(f"ORACLE FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_ran_count(output: str) -> int:
    m = re.search(r"\[==========\]\s+(\d+)\s+tests?\s+ran\.", output)
    return int(m.group(1)) if m else -1


def parse_titan_gcov(gcov_path: Path) -> dict[str, tuple[int, int]]:
    """Return {source_path: (executed_lines, total_executable_lines)} for .titan sources."""
    blocks: dict[str, tuple[int, int]] = {}
    current = None
    for line in gcov_path.read_text("utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*-:\s*0:Source:(.+)$", line)
        if m:
            src = m.group(1).strip()
            current = src if src.endswith(".titan") else None
            if current and current not in blocks:
                blocks[current] = (0, 0)
            continue
        if current is None:
            continue
        m_exec = re.match(r"^\s*([0-9]+|#+):\s*(\d+):", line)
        if m_exec:
            count_tok = m_exec.group(1)
            lineno = int(m_exec.group(2))
            if lineno == 0:
                continue
            hit, total = blocks[current]
            total += 1
            if not count_tok.startswith("#") and int(count_tok) > 0:
                hit += 1
            blocks[current] = (hit, total)
    return blocks


def main() -> None:
    work = Path.cwd()
    for rel in (
        "src/mathx/stats.titan",
        "src/mathx/fmt.titan",
        "tests/stats_test.titan",
        "tests/fmt_test.titan",
        "tests/slow_spec.titan",
        "run_tests.sh",
    ):
        if not (work / rel).is_file():
            fail(f"missing expected deliverable: {rel}")

    # 1. Verify tests/slow_spec.titan genuinely fails if compiled & run without exclusion
    r_slow_build = run([
        "titanc", "-q", "--test", "--tree", "src;tests",
        "-o", "build_slow_probe", "--exe", "build_slow_probe/slow", "slow_spec",
    ])
    if r_slow_build.returncode != 0:
        fail(f"tests/slow_spec.titan must be a valid compilable test module:\n{r_slow_build.stdout}")
    r_slow_run = run(["./build_slow_probe/slow"])
    if r_slow_run.returncode == 0 or parse_ran_count(r_slow_run.stdout) <= 0:
        fail(f"tests/slow_spec.titan must contain a failing test_* case when not excluded:\n{r_slow_run.stdout}")

    # 2. Full unfiltered run via run_tests.sh
    clean_env = os.environ.copy()
    clean_env.pop("TITAN_FILTER", None)
    r_full = run(["sh", "run_tests.sh"], env=clean_env)
    if r_full.returncode != 0:
        fail(f"sh run_tests.sh failed (rc={r_full.returncode}):\n{r_full.stdout}")
    total_ran = parse_ran_count(r_full.stdout)
    if total_ran < 6:
        fail(f"expected >= 6 tests/subtests in full run, got {total_ran}:\n{r_full.stdout}")
    if "slow_spec" in r_full.stdout:
        fail(f"slow_spec must be excluded from run_tests.sh:\n{r_full.stdout}")
    if "stats_test." not in r_full.stdout or "fmt_test.test_bands" not in r_full.stdout:
        fail(f"expected stats_test.* and fmt_test.test_bands in output:\n{r_full.stdout}")

    # 3. Filtered run via TITAN_FILTER forwarded to standalone binary --filter
    filt_env = clean_env.copy()
    filt_env["TITAN_FILTER"] = "^fmt_test[.]test_bands"
    r_filt = run(["sh", "run_tests.sh"], env=filt_env)
    if r_filt.returncode != 0:
        fail(f"filtered run_tests.sh failed (rc={r_filt.returncode}):\n{r_filt.stdout}")
    filt_ran = parse_ran_count(r_filt.stdout)
    if not (4 <= filt_ran < total_ran):
        fail(f"expected filtered count in [4, {total_ran - 1}], got {filt_ran}:\n{r_filt.stdout}")
    if "stats_test." in r_filt.stdout:
        fail(f"stats_test should not run under TITAN_FILTER='^fmt_test[.]test_bands':\n{r_filt.stdout}")
    for sub in ("low", "ok", "high"):
        if f"fmt_test.test_bands.{sub}" not in r_filt.stdout:
            fail(f"missing subtest fmt_test.test_bands.{sub} under filtered run:\n{r_filt.stdout}")

    # 4. Native --coverage run via run_tests.sh --coverage
    r_cov = run(["sh", "run_tests.sh", "--coverage"], env=clean_env)
    if r_cov.returncode != 0:
        fail(f"sh run_tests.sh --coverage failed (rc={r_cov.returncode}):\n{r_cov.stdout}")
    if "Titan executable lines:" not in r_cov.stdout:
        fail(f"coverage run did not print Titan executable lines summary:\n{r_cov.stdout}")

    gcov_path = work / "build-cov/.coverage/report/coverage.gcov"
    if not gcov_path.is_file():
        fail(f"missing coverage report at {gcov_path}")

    blocks = parse_titan_gcov(gcov_path)
    if not blocks:
        fail("no .titan source blocks found in coverage.gcov")

    # Confirm production modules instrumented & hit, and zero test modules instrumented
    stats_key = next((k for k in blocks if k.endswith("mathx/stats.titan")), None)
    fmt_key = next((k for k in blocks if k.endswith("mathx/fmt.titan")), None)
    if not stats_key or not fmt_key:
        fail(f"missing production modules in coverage.gcov; found keys={sorted(blocks)}")

    for name, key in (("stats", stats_key), ("fmt", fmt_key)):
        hit, tot = blocks[key]
        if tot == 0 or (hit / tot) < 0.80:
            fail(f"production module {name} ({key}) has insufficient coverage {hit}/{tot}")

    for key in blocks:
        base = Path(key).name
        if base.endswith("_test.titan") or base.endswith("_spec.titan"):
            fail(f"test module must NOT be instrumented in coverage.gcov: {key}")

    print(
        f"ORACLE PASS: full={total_ran}, filtered={filt_ran}, "
        f"cov_stats={blocks[stats_key]}, cov_fmt={blocks[fmt_key]}"
    )


if __name__ == "__main__":
    main()
