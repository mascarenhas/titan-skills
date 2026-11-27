import { pathToFileURL } from "node:url";
import { mkdtempSync, copyFileSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";

function assert(cond, msg) {
  if (!cond) {
    console.error("LOADER ORACLE FAIL:", msg);
    process.exit(1);
  }
}

const loaderPath = resolve("web/loader_client.mjs");
const siteAppPath = resolve("site/app.mjs");
const { runApp } = await import(pathToFileURL(loaderPath).href);
assert(typeof runApp === "function", "web/loader_client.mjs must export async function runApp");

// 1. Happy path with args
const okRes = await runApp(pathToFileURL(siteAppPath).href, ["x", "y"]);
assert(okRes && okRes.kind === "returned", `expected kind='returned', got ${JSON.stringify(okRes)}`);
assert(okRes.status === 0, `expected status=0, got ${okRes.status}`);
assert(
  typeof okRes.stdout === "string" && okRes.stdout.trim() === "target=browser;count=2;joined=x,y",
  `unexpected browser stdout: ${JSON.stringify(okRes.stdout)}`
);

// 2. Failure path with --fail must produce non-empty traceback text
const failRes = await runApp(pathToFileURL(siteAppPath).href, ["--fail"]);
assert(failRes && failRes.kind === "failed", `expected kind='failed' for --fail, got ${JSON.stringify(failRes)}`);
assert(failRes.status !== 0, `expected non-zero status for --fail, got ${failRes.status}`);
assert(
  typeof failRes.traceText === "string" && failRes.traceText.includes("main.titan"),
  `expected Titan trace frames in traceText, got: ${JSON.stringify(failRes.traceText)}`
);

// 3. Missing .wasm.trace MUST fail because loader enforces requireTrace: true
const tmpDir = mkdtempSync(join(tmpdir(), "app01_notrace_"));
try {
  copyFileSync(resolve("site/app.mjs"), join(tmpDir, "app.mjs"));
  copyFileSync(resolve("site/app.wasm"), join(tmpDir, "app.wasm"));
  let failedAsExpected = false;
  try {
    const degraded = await runApp(pathToFileURL(join(tmpDir, "app.mjs")).href, ["z"]);
    if (degraded && degraded.kind === "failed" && degraded.status !== 0) {
      failedAsExpected = true;
    }
  } catch (_err) {
    failedAsExpected = true;
  }
  assert(
    failedAsExpected,
    "runApp succeeded without site/app.wasm.trace — loader must set requireTrace: true"
  );
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}

console.log("BROWSER LOADER ORACLE PASS");
