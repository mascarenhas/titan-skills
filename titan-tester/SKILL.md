---
name: titan-tester
description: Use for native/browser Titan tests: test_*, titan.test, titanc --test/--test-dir, TITAN_FILTER, --coverage. Covers unit/integration suites, assertions, subtests, defer vs cleanup, skips, async tests, titan-browser-run, gcov coverage, and Titan repo Make/Busted lanes; use titan-application for app builds and titan-async for Task APIs.
---

# Titan testing and coverage

Write, compile, run, filter, and measure line coverage for native and browser `.titan` tests with `titan.test` (`local test = import "test"`; imports no other stdlib module, complete on native and `--target browser`). Pair with `skill://titan-programmer` for `.titan` syntax/types, `skill://titan-async` for Tasks, `skill://titan-application` for `-o`/`--incremental`/`--tree`/browser SDKs, and `skill://titan-ffi` for C/`titan.browser` fixtures.

## Non-negotiable invariants

1. **Discovery signature & naming:** `titanc --test` discovers ONLY **public** (non-`local`, non-ignored) top-level `function test_*(context: test.Context)`—one fixed parameter normalizing to nominal `titan.test.Context`, no `...` vararg (transparent aliases pass; lookalike records are ignored). Return values are **discarded** (`return false` passes—fail via `test.assert` or `raise`). Any input `main` is ignored (`titan.test.runner` supplies `main`). Never use a bare stdlib shorthand (`string`, `test`, `url`, `math`, etc.) as a test owner; use `calc_test`, `tests.calc`, or a folder module.
2. **Build AND execute:** `titanc --test` only compiles/links; you **must run** the output (`./out/suite` or `"$PREFIX/lib/titan-browser/0.6/titan-browser-run" out/suite.mjs`). Zero discovered or filtered cases exits `0`—always confirm `[==========] N tests ran.` has `N > 0`.
3. **Source-first vs `local` visibility:** `--test` resolves dependencies source-first under `--tree`, yet ordinary `import "app.calc"` still hides `local`s. White-box test `local` helpers with direct `import "app.calc.titan"` (never falls back to binary providers) instead of making helpers public.
4. **Deferred subtests & cleanup:** `context:run(name, fn)` runs children **after** the parent returns (not inline). Use `defer` for block-local resources (runs **before** subtests); use `context:cleanup(fn)` (LIFO, runs **after** all descendants) for shared parent fixtures. Never call `test.skip` in cleanup (fails the case).
5. **Assertions, `catch`, & runner state:** `test.assert(check, msg?)` is the sole assertion (raises `msg or "assertion failed"`). `test.skip(reason?)` raises nominal `test.Skip` (`const reason: string?`) in `test.run`. Do not swallow assertions/skips in a broad `catch`. `test.testing()`/`test.verbose()` are `false` in module `do ... end` initializers.
6. **Async bootstrap vs `--no-uv-bootstrap`:** Importing `async` (or any async stdlib module) runs the generated runner inside one standalone async Task—suspend directly in bodies, subtests, and `context:cleanup`; **never** call `async.loop()`. Only under `--no-uv-bootstrap` must tests drive their own `async.run`/`async.loop()`.
7. **Browser `--test` & native `--coverage`:** Build browser tests with `titanc --target browser --test -o out --exe out/suite.mjs <roots>` (`--exe` ends in `.mjs`; `--coverage` unsupported) and run via `"$PREFIX/lib/titan-browser/0.6/titan-browser-run"` (not in `bin/`). Native `--coverage` uses `.coverage/` dirs, writes `coverage.gcov` on pass, and must run serially per `-o`.
8. **Titan compiler repo suites:** **MUST read `skill://titan-tester/references/titan-repo-suites.md` when** testing inside the Titan compiler/stdlib repo (`make test`, `make titan-stdlib-test`, `make titan-stdlib-browser-test`, `make titan-native-coverage`, `TITAN_FILTER` vs `BUSTED_FILTER`, `busted --run=checkout`, `support.runtime`, layer placement, skip tags, CI lanes).

## Choosing test structure, lifetime, and build mode

| Need | Choice | Rule |
| --- | --- | --- |
| Independent case | Public `test_*(context: test.Context)` | Runs bytewise by `<module>.<fn>`. |
| Shared setup / matrix | `context:run("name", function(child) ... end)` | Runs in registration order after parent returns. |
| Test `local` helpers | `import "pkg.mod.titan"` | Direct source visibility; keep helpers `local`. |
| Block-local resource | `defer res:close()` | Runs on block exit—**before** subtests. |
| Shared parent fixture | `context:cleanup(function() ... end)` | Runs LIFO **after** all descendants finish. |
| Native project suite | `titanc -q --incremental --test -o build --tree . --exe build/suite ... && ./build/suite` | Dotted roots or `--test-dir DIR`. |
| Browser suite | `titanc -q --target browser --test -o out-web --exe out-web/suite.mjs ...` | Run via `"$PREFIX/lib/titan-browser/0.6/titan-browser-run"`. |
| Line coverage | `titanc -q -o out --test --coverage ... && ./out/suite` | Native only (`gcc-gcov` GCC 14+ Unix; `llvm-gcov` Win). |

## API, subtests, errors, and cleanup

```text
record Skip  const reason: string?  end
function assert(check: boolean, message: string?)
function skip(reason: string?)
function testing(): boolean
function verbose(): boolean
function location(): (string, string, integer)
record Context
  :name(): string | :log(msg: string) | :run(name: string, fn: function(Context)) | :cleanup(f: function())
record Case
function Case.new(full_name: string, owner_module: string, body: function(Context)): Case
function run(args: {string}, cases: {Case}): integer
```

- **Subtests & isolation:** `context:name()` returns `<module>.<fn>` or `<parent>.<subtest>`. `context:log(msg)` prints/flushes immediately (raises outside `test.run`). Parent failure/skip marks already-registered matching children skipped (`0.00 ms`). A child failure does **not** fail its parent; siblings continue and exit status is `1`.
- **Registration & cleanup windows:** Subtest registration closes when the body returns; cleanup stays open during descendants (children may append to a captured parent) and closes when cleanup starts. All cleanups run even if one raises; the first cleanup error fails a passing/skipped case without overriding an earlier body error.
- **Outside runner, traces & errors:** Outside `test.run`, `skip` raises `"test skipped"` (`": <reason>"` if given); nested `test.run` raises. `location()` returns `(file, qualified_fn, line)` for the first frame outside `titan.test`/`titan.test.runner` or `("<none>", "<none>", 0)`. Concise failures attribute to the test owner (`-v` adds raw traceback; avoid `--no-line-directives`). Assert errors by isolating only the raising call in `do ... catch`, asserting `caught`, and checking nominal types (`error is MyError`) or exact values.

```titan
-- file: calc.titan
local function clamp_nonnegative(n: integer): integer
  if n < 0 then return 0 end
  return n
end

function twice(n: integer): integer
  return clamp_nonnegative(n) * 2
end

function divide_checked(a: integer, b: integer): integer
  if b == 0 then raise "division by zero" end
  return a // b
end

-- file: calc_test.titan
local test = import "test"
local calc = import "calc.titan"

local record AuditLog
  const label: string
  const entries: {string}
  closed: boolean
end

local function expect_error(action: function(), expected: string)
  local caught = false
  do
    action()
  catch
    caught = true
    test.assert(error == expected, "unexpected error value")
  end
  test.assert(caught, "expected error was not raised")
end

function test_twice_matrix(context: test.Context)
  local log = AuditLog("twice", {}, false)
  context:cleanup(function() log.closed = true end)

  context:run("positive", function(child)
    test.assert(not log.closed, "fixture closed before child")
    log.entries[#log.entries + 1] = child:name()
    test.assert(calc.twice(21) == 42, "positive input must double")
  end)

  context:run("negative_clamps", function(child)
    log.entries[#log.entries + 1] = child:name()
    test.assert(calc.twice(-4) == 0, "negative input must clamp")
  end)
end

function test_private_and_errors(_: test.Context)
  test.assert(calc.clamp_nonnegative(-3) == 0, "private helper clamp")
  expect_error(function() calc.divide_checked(10, 0) end, "division by zero")
end
```

```sh
titanc -q --incremental --test -o out --tree . --exe out/calc_test calc_test
./out/calc_test
```

## Asynchronous tests (native and browser)

- **Automatic bootstrap:** Importing `async` (or `timer`, `fs`, `net`, `http`, `websocket`, `os`, `sqlite3`) runs the generated runner in one standalone async Task; suspend directly in bodies, subtests, and `context:cleanup`—never call `async.loop()`.
- **Cooperative oracles:** No callback preempts non-yielding Titan statements. Use `async.yield()`, `timer.yield()`, `async.join*`, or `async.channel` instead of sleep races, and cancel unwanted `race*`/`any*` losers (`skill://titan-async`).
- **`--no-uv-bootstrap`:** Runs `main` directly; each async test drives its own `async.run` + `async.loop()` and retires all Runtime-bound Tasks/handles before `async.loop()` returns (`context:cleanup` runs after the loop closes: non-Runtime resources only).

```titan
-- file: async_worker_test.titan
local async = import "async"
local test = import "test"
local timer = import "timer"

function test_async_worker(context: test.Context)
  local send, receive, close = async.channel<|string|>(1)
  context:cleanup(function()
    timer.sleep(1)
    close()
  end)

  context:run("roundtrip", function(_: test.Context)
    local worker = async.run(function(): string
      timer.sleep(5)
      send("ready")
      return "done"
    end)
    local msg = receive()
    local status = async.join(worker)
    local ok, result? = status:has_succeeded()
    test.assert(msg == "ready", "channel delivery failed")
    test.assert(ok and result == "done", "worker did not succeed")
  end)
end
```

Runs identically natively (`titanc -q --test -o out --tree . --exe out/async_worker_test async_worker_test && ./out/async_worker_test`) and on browser (`--target browser`, `--exe out-web/async_worker_test.mjs`, executed via `titan-browser-run`).

## Discovery (`--test-dir`), filtering, browser runs, and `--coverage`

### Automatic root discovery (`--test-dir` / `--test-exclude`)

```sh
titanc -q --incremental --test -o build --tree 'src;tests' \
  --test-dir tests --test-exclude windows_only_test --exe build/suite
./build/suite
```

- **Containment & prefix:** Repeatable `--test-dir DIR` must lie inside a `--tree` root; the **first** containing `--tree` root sets the logical prefix (`--tree . --test-dir tests` -> `tests.*`; `--tree tests --test-dir tests` -> top-level). Positional roots and `--test-dir` resolve only from `--tree`, never the installed SDK fallback.
- **Selection & variants:** Recursively selects flat files or folder mains whose final component is `test`, `tests`, `spec`, `specs`, or ends in `_test`, `_tests`, `_spec`, or `_specs` (skipping `.` hidden entries, folder contributors, nested dir symlinks; explicit symlink `--test-dir` is traversed). Target variants (`foo_test.<label>.titan`) select active labels and skip others; stacked/mis-cased labels error.
- **Ordering & `-c`:** Explicit roots precede bytewise-sorted discovered roots and override `--test-exclude`; the first root owns the default exe path without `--exe`. Shadowing, cross-dir ambiguity, or empty roots (`no test modules found`) error; a selected root with zero `test_*` is valid. `-c --test` compiles test owners with `-fno-optimize-sibling-calls` (plus `-fno-inline` on browser `production`) without linking.

### Runner CLI, Lua-pattern filtering, and exit codes

```sh
./build/suite [-h|--help] [-v|--verbose] [-f PATTERN|--filter=PATTERN]...
```

- Repeatable `-f`/`--filter` uses **Lua patterns** (escape dots as `[.]` or `%.`; no regex `|` alternation), combined with **OR**. Filtered cases are omitted from counts (not skipped).
- **Parent/child trap:** Parents and children (`mod.test_x.sub`) match independently; filtering out a parent prevents children from registering. Select one child with a shared prefix (`-f '^mod[.]test_x'`) or two OR filters (`-f '^mod[.]test_x$' -f '^mod[.]test_x[.]sub$'`).
- **Exit codes:** `0` = pass, all-skip, zero-selected/zero-test, or `--help`; `1` = case/cleanup failure; `2` = bad flag/pattern. (`TITAN_FILTER` is a Titan-repo Make variable; standalone binaries take `-f`/`--filter`.)

### Browser `--test` execution (`titan-browser-run`)

```sh
titanc -q --target browser --incremental --test -o out-web --tree . \
  --exe out-web/suite.mjs calc_test
"$PREFIX/lib/titan-browser/0.6/titan-browser-run" out-web/suite.mjs \
  -- --filter='^calc_test[.]' -v
"$PREFIX/lib/titan-browser/0.6/titan-browser-run" --engine chromium out-web/suite.mjs
```

- Pass runner args after `--`. Flags: `--engine node|chromium` (default `node`, Node 26+ JSPI via `TITAN_NODE`/`PATH`), `--timeout MS` (30000), `--grace MS` (1500), `--chrome PATH`, `--cdp pipe|port`, `--root DIR`, `--imports FILE` (`create({ imports })`), `--allow-degraded-trace`, `--probe`. Set `TITAN_BROWSER_ROOT_NO_SANDBOX=1` only for `root` Chromium in containers.
- Exit codes: `0`/`1`/`2` from `test.run`, `70` abort, `71` trap, `72` timeout, `73` grace trap/abort, `74` unhandled rejection, `75` runner/env error, `76` sink error.

### Native source coverage (`--coverage`, native only)

```sh
CC=gcc-14 GCOV=gcov-14 titanc -q -o out --test --coverage --tree . calc_test && ./out/calc_test
CC=clang titanc -q -o out --test --coverage --coverage-backend llvm-gcov --coverage-gcov 'llvm-cov gcov' --tree . calc_test && ./out/calc_test
```

- **Backends:** `gcc-gcov` (Unix default: GCC 14+ & matching `gcov`, rejects Apple Clang `gcc`, rejected on Windows) or `llvm-gcov` (Windows default: Clang & `llvm-cov gcov`). Needs `#line`; unsupported on browser.
- **Selection:** Auto-instruments authored build-graph sources with **no** top-level `test_*` (excludes SDK fallback, providers, and test modules; import untested authored modules from a test root to include them). Repeatable `--coverage-module GLOB` (`*`/`?`, matches dots; quote from shell) replaces auto-selection and can opt in installed fallback sources; empty match errors.
- **Artifacts & reports:** Outputs live in `.coverage/` dirs. Startup resets `.gcda` (keep `.gcno`/artifacts; run serially per `-o`). Passing runs write `<out>/.coverage/report/coverage.gcov` without Python/`gcovr`. Optional `--coverage-format html|lcov|cobertura` (`--coverage-output`, `--coverage-root`, `--coverage-gcovr`) needs `gcovr` 8.4; reports Titan executable lines only (no denominator exclusions).

## Pre-delivery verification checklist

1. Public `test_*(context: test.Context)` only (helpers `local`), fail via `test.assert`/`raise` (never `return false`), no bare stdlib shorthand names.
2. Match cleanup lifetime: `defer` for block-local, `context:cleanup` for shared fixtures, no `test.skip` in cleanup, no `async.loop()` under default bootstrap.
3. Build **and** execute the binary (or `titan-browser-run` for browser) and confirm `[==========] N tests ran.` shows `N > 0`.
4. Escape Lua-pattern dots (`[.]`) in filters and match the parent alongside any target subtest.
5. Coverage uses matching `gcc-14`/`gcov-14` or `clang`/`llvm-cov gcov`, runs serially per `-o`, and writes `coverage.gcov`. Inside the Titan repo, read `skill://titan-tester/references/titan-repo-suites.md`.
