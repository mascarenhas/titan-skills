#!/usr/bin/env python3
"""Independent Stage-B oracle for application-01-multi-target-app-layout-and-profiles."""
import os
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


def main() -> None:
    work = Path.cwd()
    for rel in (
        "src/platform.native.titan",
        "src/platform.browser.titan",
        "src/app/greeter.titan",
        "src/main.titan",
        ".gitignore",
        "web/loader_client.mjs",
        "build_targets.sh",
    ):
        if not (work / rel).is_file():
            fail(f"missing expected deliverable: {rel}")

    # Verify loader_client.mjs calls dispose()
    loader_src = (work / "web/loader_client.mjs").read_text("utf-8")
    if "dispose" not in loader_src:
        fail("web/loader_client.mjs must call instance.dispose()")
    if "requireTrace" not in loader_src:
        fail("web/loader_client.mjs must explicitly enable requireTrace: true")

    # 1. Build both targets into separate -o dirs via build_targets.sh
    env = os.environ.copy()
    env["TITAN_BUILD_PROFILE"] = "validation"
    r_build = run(["sh", "build_targets.sh"], env=env)
    if r_build.returncode != 0:
        fail(f"build_targets.sh failed (rc={r_build.returncode}):\n{r_build.stdout}")

    # Verify separate -o isolation & .titan-target marker
    if not (work / "build-native/bin/app").is_file():
        fail("missing native executable build-native/bin/app")
    if (work / "build-native/.titan-target").exists():
        fail("build-native must not contain browser .titan-target marker")
    marker = work / "build-browser/.titan-target"
    if not marker.is_file() or marker.read_text("utf-8").strip() != "browser":
        fail("build-browser/.titan-target missing or not 'browser'")

    for art in ("app.mjs", "app.wasm", "app.wasm.trace"):
        if not (work / "site" / art).is_file():
            fail(f"site/ missing matched browser artifact: {art}")
    if (work / "site/.titan-target").exists():
        fail("site/ must not contain compiler-internal .titan-target marker")

    # 2. Native binary functional checks
    rn1 = run(["./build-native/bin/app", "alpha", "beta"], env=env)
    if rn1.returncode != 0 or rn1.stdout.strip() != "target=native;count=2;joined=alpha,beta":
        fail(f"native run with args failed: rc={rn1.returncode} out={rn1.stdout!r}")

    rn0 = run(["./build-native/bin/app"], env=env)
    if rn0.returncode != 0 or rn0.stdout.strip() != "target=native;count=0;joined=none":
        fail(f"native run with 0 args failed: rc={rn0.returncode} out={rn0.stdout!r}")

    rnf = run(["./build-native/bin/app", "--fail"], env=env)
    if rnf.returncode == 0 or "intentional failure" not in rnf.stdout:
        fail(f"native --fail must exit non-zero with error message: rc={rnf.returncode} out={rnf.stdout!r}")

    # 3. Browser CLI runner check via titan-browser-run
    sdk_root = run(["titanc", "--print-root"], env=env).stdout.strip()
    browser_run = Path(sdk_root) / "lib/titan-browser/0.6/titan-browser-run"
    rb1 = run([str(browser_run), "site/app.mjs", "--", "alpha", "beta"], env=env)
    if rb1.returncode != 0 or rb1.stdout.strip() != "target=browser;count=2;joined=alpha,beta":
        fail(f"titan-browser-run failed: rc={rb1.returncode} out={rb1.stdout!r}")

    # 4. Node loader API check (requireTrace: true, stdout capture, trace frames, dispose)
    titan_node = env.get("TITAN_NODE", "node")
    r_node = run([titan_node, "/verify/oracle/check_browser_loader.mjs"], env=env)
    if r_node.returncode != 0 or "BROWSER LOADER ORACLE PASS" not in r_node.stdout:
        fail(f"browser loader check failed (rc={r_node.returncode}):\n{r_node.stdout}")

    # 5. Narrow .gitignore verification via git check-ignore --no-index
    r_git_init = run(["git", "init", "-q"], env=env)
    if r_git_init.returncode != 0:
        fail(f"git init failed:\n{r_git_init.stdout}")

    must_ignore = [
        "build-native/main.c",
        "build-browser/app.wasm",
        "dist/app",
        "site/app.mjs",
        ".titan-ls/cache",
        ".env",
        ".env.local",
    ]
    must_track = [
        ".env.example",
        ".env.prod.example",
        "src/main.titan",
        "native/helper.c",
        "native/helper.h",
        "scripts/tool.lua",
        "tests/fixtures/sample.sqlite3",
        "config/defaults.json",
        "fixtures/sample.log",
    ]
    for p in must_ignore:
        rc = run(["git", "check-ignore", "--no-index", "-q", p], env=env).returncode
        if rc != 0:
            fail(f".gitignore failed to ignore {p!r}")
    for p in must_track:
        rc = run(["git", "check-ignore", "--no-index", "-q", p], env=env).returncode
        if rc == 0:
            fail(f".gitignore overly broad — must NOT ignore authored file {p!r}")

    print("ORACLE PASS: native + browser target variants, requireTrace loader, and narrow .gitignore verified")


if __name__ == "__main__":
    main()
