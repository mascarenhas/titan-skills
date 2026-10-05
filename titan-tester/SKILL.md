---
name: titan-tester
description: Write, organize, compile, filter, and debug native Titan tests with titan.test and titanc --test, and choose correctly between native standard-library tests, checker specs, coder specs, and other Busted gates. Use whenever adding or reviewing Titan tests, subtests, assertions, fixtures, cleanup, skips, expected errors, asynchronous tests, test filters, or repository test commands.
---

# Titan tester

Use this skill after the basic Titan language skill whenever the task involves a
`.titan` test, `titan.test`, `titanc --test`, `TITAN_FILTER`, or deciding where a
Titan repository regression belongs. Titan's native test runner is not Busted,
LuaUnit, Go's runner, or a special source language. A test file is an ordinary,
statically checked Titan module, compiled through C into one standalone
executable.

This cartridge is self-contained for normal test work. When implementation
internals matter, the authoritative sources are:

- user contract: `doc/language/standard-library-test.md`;
- public implementation and exact signatures: `titan/test.titan`;
- compiler/runner protocol: `doc/implementation/test-runner.md` and
  `titan-compiler/test_runner.lua`;
- repository layer and ownership policy: `AGENTS.md`, especially “Coverage is
  for compiler and language behavior,” “Spec layout,” and “Native
  standard-library behavior”;
- aggregate build/run targets: `Makefile` (`TITAN_STDLIB_TEST_ROOTS` and the
  `*-test` targets), `spec/support/run_rock_tests.sh`, and
  `spec/support/run_with_timeout.sh`;
- current native idioms: `spec/stdlib/titan/`, especially
  `support/{common,runtime,async,command}.titan`;
- subtest/cleanup edge cases: `spec/fixtures/test_runner/*.titan` and
  `spec/coder/test_runner_spec.lua`.

Do not call any source-private `titan.test.runner_*` operation from an ordinary
test. Those operations exist only for the generated runner. The repository's
`support.runtime` is likewise source-only test infrastructure, not part of the
public `titan.test` API.

## 1. Choose the owning test layer before writing code

The subject under test, not the language of the fixture, chooses the layer.
Titan snippets appear in several Busted layers, but that does not make every
compiled snippet a native library test.

| What the assertion is about | Owning layer in this repository | Normal shape |
| --- | --- | --- |
| Tokens, grammar, syntax errors, or AST shape | root `spec/lexer_spec.lua` or `spec/parser_spec.lua` | pure Busted; parse text, inspect a small AST subset |
| Pure type laws or compiler utility data | topical root Busted spec such as `spec/types_spec.lua` | no generated C or application execution |
| Checker acceptance/rejection, inferred types, visibility, or checker-owned plans | `spec/checker/<topic>_spec.lua` | `helpers.run_checker`; never generate or execute C |
| Generated representation, runtime language semantics, codegen, Lua boundary, or compiled-module behavior | `spec/coder/<topic>_spec.lua` | generate C, compile, and execute through shared helpers |
| Driver resolution, artifact selection, metadata, publication, packaging, or native-dependency build behavior | the existing owning root/coder Busted spec | host filesystem/process scaffolding and exact artifact cleanup |
| Public standard-library API and observable runtime behavior, including coroutine and async I/O | Titan source under `spec/stdlib/titan/` | one native aggregate executable, outside LuaCov |
| Public standard-library behavior that needs a fresh process | still the owning native Titan module | compiled Titan parent launches a focused fixture and receives an explicit result |
| A production smoke across bundled/system dependencies | the existing shell/packaging gate | do not duplicate it as an API test |

Three litmus questions usually settle ambiguity:

1. **Would the test still be meaningful if Titan were compiled by a different,
   correct compiler?** If yes and it asserts a standard-module result, it is
   native Titan behavior.
2. **Is the expected result a compiler diagnostic, AST decoration, generated C
   property, provider-selection decision, or artifact?** If yes, it belongs in
   Busted at the corresponding compiler layer.
3. **Is Busted present only because it is convenient to launch a program?** Do
   not use that convenience to move public library behavior out of the native
   suite. Launch the child from the owning native Titan test instead.

Concrete precedent: test-runner source discovery/rendering is tested purely in
`spec/test_runner_spec.lua`; end-to-end compilation, CLI, filtering, and
artifact behavior are in `spec/coder/test_runner_spec.lua`; the public
`titan.test` behavior outside the runner is exercised by
`spec/stdlib/titan/test/tests.titan`. Preserve that split.

Do not run a standard-library API suite under LuaCov merely to cover compiler
lines. LuaCov measures the Lua compiler, not Titan or the native library. If a
library case exposes a compiler coverage gap, add one small, compiler-focused
checker/coder case in addition to the native behavior case. This policy is
normative in `AGENTS.md:402-442`.

For the current grammar, assignment/call candidates and non-tail vararg/spread
expressions may parse successfully; checker tests own their semantic rejection.
Foreign/Titan alias category and visibility checks belong in checker specs,
while emitted typedef headers and restored source-import manifests belong in
driver/cache specs. Keep parser scaling checks focused on bounded terminal
lookahead, committed syntactic descents, and flat-list capture growth.

## 2. Native tests are discovered ordinary module functions

A native case is discovered only when a checked declaration satisfies **all**
of these conditions:

- public top-level `function`, not `local`;
- name begins exactly with `test_`;
- surviving declaration, not an ignored duplicate;
- exactly one fixed parameter;
- no variadic input; and
- that parameter normalizes exactly to nominal `titan.test.Context`.

A transparent alias of `test.Context` is accepted. A lookalike record is not.
The result type is unrestricted, but every returned result is discarded. Do not
return `false` to fail a test: assert or raise. A `main` in an input module is
ignored because the generated runner supplies the sole `main`.

```titan
local test = import "test"       -- shorthand for titan.test

function test_public_case(context: test.Context)
  test.assert(context:name() == "calc_test.test_public_case")
end

local function test_local_is_not_discovered(context: test.Context)
  test.assert(false, "this helper must not run")
end

function test_wrong_shape(context: integer)
  -- Also not discovered.
end
```

The exact case name is
`<logical-module>.<function-name>`. Top-level cases are sorted by complete name
using bytewise order, not source traversal order. Subtests retain registration
order. Avoid coupling cases through mutable module state even though root order
is deterministic; each case should establish its own preconditions.

`titanc --test M...` examines each requested source root and its source-backed
import closure. In test mode dependency resolution tries the configured source
tree before compiled providers; explicit roots are always source. Source-first
selection does not itself expose locals: a test placed beside application
source must write `import "producer.titan"` to require that source and exercise
its module-local declarations. The marker is stripped from the logical name,
and that permission is direct only: it does not pass through a helper module
and cannot fall back to a binary provider. Do not make a production helper
public merely for testing.

The repository's standard-library aggregate has a different deliberate shape:
its test/support modules are source roots under `spec/stdlib/titan`, while the
canonical installed standard modules are public compiled dependencies. Those
native cases test public behavior rather than production-private machinery.
After changing production `titan/*.titan`, rebuild/reinstall the provider before
using a leaf native-suite target; `make test` performs the current installation
first. `--static` only swaps `.a` versus `.so` preference in the compiled
fallback; it neither defeats source-first test resolution nor means
“static-only.”

### Module and filename rules still apply

`*_test.titan`, `*_spec.titan`, and a `tests/` directory are conventions only.
Pass dotted logical module names to `titanc`, never filenames. A folder test
module is one logical module: its canonical main plus immediate `.titan`
contributors share one namespace, and contributor filenames do not appear in
case names.

Do not give a test owner a bare name rewritten by standard-import shorthand:
`coroutine`, `uv`, `async`, `timer`, `io`, `fs`, `net`, `ssl`, `url`, `http`,
`os`, `peg`, `string`, `test`, `lua`, `math`, `gc`, `iteration`, or `reflect`.
A bare Lua-library name can also collide at
the native opener boundary; `math` is the canonical example. Prefer
`calc_test`, `math_spec`, `tests.math`, or a qualified owner such as
`net.tests`.

A successful run with zero discovered or zero selected cases exits 0. Therefore
always inspect the build/run summary when adding a test. A wrong signature can
silently produce a green zero-test executable.

## 3. Exact public `titan.test` API

The canonical import is `titan.test`; `import "test"` is parser shorthand. The
module deliberately imports no other Titan standard module, so the rest of the
standard library can use it for tests.

```text
test.testing(): boolean
test.verbose(): boolean
test.location(): (string, string, integer)
test.assert(check: boolean, message: string?)
test.skip(reason: string?)

test.Context:name(): string
test.Context:log(message: string)
test.Context:run(name: string,
                 subtest: function(test.Context): ())
test.Context:cleanup(f: function(): ())
```

In source, these are selected through the import alias, for example
`test.assert(...)`, and the runner supplies every `Context`.

### `assert`

`test.assert` returns normally only when its boolean is true. Otherwise it
raises the message or the exact default `"assertion failed"`. There are no
built-in equality, deep-diff, approximate, or `assert_raises` variants. Build a
small typed helper when a domain repeats an assertion; do not route ordinary
behavior through Lua just to obtain an assertion library.

Prefer one useful semantic message over a copy of the condition:

```text
test.assert(actual == expected,
            "twice returned the wrong value for a negative input")
```

### `skip`

`test.skip()` or `test.skip(reason)` raises a private nominal marker while the
runner is active. An uncaught body skip marks the current case skipped and
prevents its already registered selected children from running. Use skip for a
real unavailable prerequisite, not unfinished code or an intermittently failing
assertion. A skip raised during cleanup is a **failure**, because descendants
may already have run.

A caught skip is handled like any other caught error and the body continues.
The same is true for a caught assertion failure. Do not accidentally wrap the
runner's own assertions in an over-broad catch.

Outside a generated runner, `assert` remains an ordinary readable error and
`skip` raises `"test skipped"` with an optional reason suffix. This permits
small support functions to fail clearly, but does not create a skipped process.

### `testing` and `verbose`

`testing()` is true only while generated `main` is executing cases and cleanup.
`verbose()` is additionally true only when `-v`/`--verbose` was parsed. Both are
false outside a runner, during option parsing, and in imported module
initializers—modules initialize before generated `main` activates testing.
Never put essential case setup in a module initializer guarded by
`test.testing()`.

### `location`

`location()` returns `(source_filename, qualified_function_name, line)` for the
first suitable Titan frame outside exact support/runner frames. It returns
`("<none>", "<none>", 0)` when no frame is available. Ordinary failure
reporting already attributes a concise error to the test owner; use `location`
only when location behavior itself is the assertion. `--verbose` adds the raw
traceback. Normal builds need line directives and debug information; do not use
`--no-line-directives` for ordinary tests.

### Context methods

- `name()` returns the full current case name.
- `log(message)` emits and flushes a decorated line. It is not conditional on
  verbose mode and raises outside an active runner.
- `run(name, callback)` registers a child. It does **not** execute the callback
  inline.
- `cleanup(callback)` registers post-descendant cleanup in LIFO order.

`Context` has no public fields and is not an application fixture object. Pass
application fixtures through ordinary typed closure captures.

## 4. Start with fine-grained cases and named subtests

Use one public top-level test for one independently meaningful protocol or
behavior. Use subtests for a compact matrix that shares setup or one semantic
claim. Do not hide a matrix in an ad hoc loop: the runner cannot filter or
attribute its rows independently. Existing coarse historical cases are not a
reason to make a new case coarse.

A complete flat-module example:

```text
scratch/
  calc.titan
  calc_test.titan
```

```titan
-- calc.titan
local function clamp_nonnegative(x: integer): integer
  if x < 0 then return 0 end
  return x
end

function twice(x: integer): integer
  return clamp_nonnegative(x) * 2
end
```

```titan
-- calc_test.titan
local test = import "test"
local calc = import "calc.titan"

local function add_twice_case(context: test.Context, name: string,
                              input: integer, expected: integer)
  context:run(name, function(child: test.Context)
    test.assert(child:name() ==
                "calc_test.test_twice." .. name,
                "runner built the wrong subtest name")
    test.assert(calc.twice(input) == expected,
                "twice returned the wrong value in case " .. name)
  end)
end

function test_twice(context: test.Context)
  add_twice_case(context, "positive", 21, 42)
  add_twice_case(context, "zero", 0, 0)
  add_twice_case(context, "negative_clamps", -4, 0)
end

function test_private_clamp_is_source_testable(_context: test.Context)
  -- The terminal marker requires calc's source and exposes its locals.
  -- An ordinary import would expose only calc.twice, even in --test mode.
  test.assert(calc.clamp_nonnegative(-1) == 0)
end
```

```sh
(cd scratch && titanc --test --tree . calc_test && ./calc_test)
```

The helper call creates a distinct activation for each captured input and
registers stable, named children. The parent returns before any child runs. The
full names are, for example,
`calc_test.test_twice.negative_clamps`.

### Parent/child execution rules

1. A selected parent body runs and registers children in order.
2. Only after the parent body returns successfully are selected children run.
3. A child may register descendants recursively.
4. A child failure does not make its parent's own status failed; later siblings
   still run, and the process exits 1 because the shared failure count is
   nonzero.
5. If the parent body fails or skips, already registered selected children are
   reported skipped and never invoked.
6. Repeated child names are legal and run separately, but unique stable names
   make output and filters useful.

Because discovery is dynamic, a filtered-out parent is never entered and its
children do not exist. Entering a parent does not automatically select any
child. Filtering examples appear below.

## 5. Assert errors and recoverable results in Titan

Titan has no `pcall` syntax and no `try`. Errors are ordinary raised values;
`catch` attaches to a block and provides read-only `error: value` and
`traceback: string`.

For a repeated error assertion, isolate only the operation expected to raise:

```text
local type Action = function (): ()

local function expect_error(action: Action, expected: string)
  local caught = false
  do
    action()
  catch
    caught = true
    test.assert(error == expected,
                "operation raised a different error")
  end
  test.assert(caught, "operation did not raise")
end

function test_rejects_zero(_context: test.Context)
  expect_error(function()
    calc.divide_hundred_by(0)
  end, "division by zero")
end
```

If the whole function is one protected assertion, attach `catch` directly to
its function body rather than manufacturing an extra `do` block:

```text
function test_rejects_zero_directly(_context: test.Context)
  calc.divide_hundred_by(0)
  test.assert(false, "zero was accepted")
catch
  test.assert(error == "division by zero", "wrong raised value")
end
```

Use nominal inspection for a structured error:

```text
local rejected = false
do
  operation()
catch
  rejected = true
  test.assert(error is async.OperationError,
              "operation raised a non-operation error")
  local failure = error as async.OperationError
  test.assert(failure.operation == "net.accept",
              "failure named the wrong operation")
end
test.assert(rejected, "operation unexpectedly succeeded")
```

`spec/stdlib/titan/support/common.titan` contains the repository's small
source-only `assert_raises` and `assert_raises_contains` precedents. Module-owned
helpers often inspect exact structured fields rather than stringifying an
error. Prefer an API's recoverable `(result?, Error?)` contract when failure is
data; do not catch what the API deliberately returns. `spec/stdlib/titan/url/tests.titan`
shows structured result-error checks.

Do not compare an entire traceback unless traceback shape is itself the public
contract. For ordinary errors, assert the raised value or typed fields and let
the runner report the original source frame.

## 6. Setup, `defer`, and `Context:cleanup` have different lifetimes

The runner intentionally has no suite object, fixture DSL, `before_each`, or
`after_each`. Setup is an ordinary typed helper called by the test body.
Register cleanup immediately after successful acquisition.

Use language `defer` when the resource is needed only until the **current block**
exits:

```text
local connection = open_connection()
defer connection:close()
exercise(connection)
```

Use `context:cleanup` when a parent-owned fixture must remain live for children:

```text
function test_shared_fixture(context: test.Context)
  local fixture = open_fixture()
  context:cleanup(function()
    fixture:close()
  end)

  context:run("read", function(_child: test.Context)
    test.assert(fixture:read() == "ready")
  end)
  context:run("write", function(_child: test.Context)
    fixture:write("updated")
    test.assert(fixture:read() == "updated")
  end)
end
```

Replacing that cleanup with `defer fixture:close()` is wrong: the defer runs as
the parent body returns, before either child begins. Conversely, do not use a
Context cleanup when an ordinary body-local defer gives the resource a smaller,
clearer lifetime.

Exact cleanup semantics:

- cleanup runs after all descendants, whether body/children pass, skip, or fail;
- callbacks run LIFO;
- every registered callback is attempted after one raises;
- the first cleanup error fails an otherwise passing or skipped case;
- an existing body failure stays primary;
- `test.skip` from cleanup is converted to failure;
- subtest registration closes when the body ends;
- cleanup registration remains open while descendants run, but closes when
  cleanup begins, so a cleanup cannot extend its own stack.

A child can technically capture a parent's context and append parent cleanup
before cleanup begins. Use that only when ownership genuinely belongs to the
parent; ordinary code should register ownership where it is acquired.

Do not put setup in one top-level test and consume it from a later one. There is
no automatic state reset, and cross-case coupling makes filtering misleading.

## 7. Asynchronous tests: know which Runtime owns the runner

There are two supported execution modes. Mixing their recipes causes recursive
loop errors or cleanup after a dead Runtime.

### Default test executable: automatic standalone bootstrap

If the suite imports `async` or another module in its runtime constellation,
the ordinary standalone hook runs the **complete generated runner as one Task
inside one Runtime**. Test bodies, subtests, and cleanup callbacks may suspend
directly. They must not call `async.loop()` recursively.

```titan
local test = import "test"
local async = import "async"
local timer = import "timer"

function test_async_run_starts_later(_context: test.Context)
  local events = ""
  local child = async.run<|string, value|>(function (): string
    events = events .. "child;"
    timer.yield()
    return "done"
  end)

  events = events .. "parent;"
  test.assert(child:status():as_string() == "ready",
              "async.run entered its Task inline")
  test.assert(events == "parent;", "child ran before the loop regained control")

  while not child:status():has_finished() do timer.yield() end
  local succeeded, result? = child:status():has_succeeded()
  test.assert(succeeded and result == "done",
              "child did not finish successfully")
end
```

This case never calls `async.loop`: its own execution is already inside the
runner's Runtime.

### Repository aggregate: explicit per-case Runtime

The Titan repository deliberately builds its aggregate with
`--no-uv-bootstrap`. Each async case uses the source-only
`support.runtime.run`, which creates one supervisor Task, drives one
`async.loop`, drains LIFO Runtime cleanup inside that Task, and re-raises the
body's original failure/trace.

```titan
local test = import "test"
local runtime_test = import "support.runtime"
local async = import "async"
local timer = import "timer"
local task_support = import "support.async"

function test_worker_protocol(_context: test.Context)
  runtime_test.run(function()
    local observed = false
    local worker = async.run<|value, value|>(function (): value
      timer.yield()
      observed = true
      return nil
    end)
    task_support.cleanup_task(worker, "worker test cleanup")

    test.assert(not observed, "worker ran inline")
    while task_support.active(worker) do timer.yield() end
    test.assert(observed and worker:status():as_string() == "succeeded",
                "worker did not complete")
  end)
end
```

Register a Runtime-bound Task or handle with `support.runtime.cleanup` (often
through `support.async.cleanup_task`) immediately after acquisition. Later
`Context:cleanup` runs after that per-case Runtime has ended and is suitable
only for non-Runtime resources. Several explicit sessions may run sequentially
in one executable. See `spec/stdlib/titan/support/runtime.titan`,
`support/async.titan`, and current cases in `timer/tests.titan`, `net/tests.titan`,
and `uv/task_tests/`.

Do not copy these source-private helpers into a public standard module. A
project that chooses `--no-uv-bootstrap` must own an equivalent supervisor and
finish every Task/handle before `async.loop()` returns.

### The cooperative invariant is a test oracle

Titan Tasks are `titan.coroutine` coroutines driven by one libuv Runtime on the
Lua main thread. A running Titan continuation proceeds synchronously until it
returns, raises, or yields a private async operation. No libuv callback can
preempt two ordinary Titan statements, because the same main Runtime coroutine
must return control to `uv_run` before another unrelated loop event fires.
Explicit callback-producing calls such as `uv.walk` and Windows TTY read startup
obey their documented synchronous timing; tests must distinguish those direct
calls from event-loop preemption. Worker-pool work
may happen elsewhere, but Titan-visible completion runs on the loop thread.

Therefore:

- do not invent unrelated loop-event preemption while Titan code is running;
- do not add locks, generations, or timing sleeps to defend against impossible
  interleavings;
- orchestrate a real suspension point and assert Task status or observable
  callback completion;
- do not use wall-clock delay as proof of ordering when `timer.yield`, a pending
  operation, a listener, or a result channel can establish it;
- never call `async.loop` from a callback, Task continuation, or already
  bootstrapped test.

The normative callback sequence is in `doc/language/async-io.md`, “The
callback/continuation model,” and the non-reentrant invariant is explicit in
`doc/implementation/libuv-runtime.md:29-44`.

When a test deliberately produces uncaught Task diagnostics in the aggregate,
use the owning context to bracket the expected raw region with flushed lines:

```text
context:log("BEGIN expected uncaught async Task diagnostics")
-- start and await the operation that deliberately logs the uncaught failure
context:log("END expected uncaught async Task diagnostics")
```

Use a more specific label for a child/bootstrap diagnostic when appropriate.
Current precedents live in `spec/stdlib/titan/async/`, `http/`, and
`uv/runtime_tests.titan`.

## 8. Repository-native test ownership and layout

The aggregate currently has 26 explicit logical roots in
`spec/support/stdlib_test_modules.mk:TITAN_STDLIB_TEST_ROOTS`, shared by Linux,
macOS, and native Windows:

```text
test.tests
coroutine.tests
iteration.tests
gc.tests
lua.tests
math.tests
peg.tests
string.core_test
string.format_pack_test
string.regex_test
async.tests
uv.task_tests
uv.public_tests
io.tests
fs.tests
timer.tests
net.tests
ssl.tests
http.tests
url.tests
os.tests
os.process_tests
uv.runtime_tests
reflect.tests
sqlite3.tests
json.tests
```

Do not replace this manifest with an import-only aggregator. Making each owner
an explicit `titanc --test` root keeps its test source authoritative and makes
discovery see the intended source closure. `test.tests` is deliberately first
and owns `.titan-tests/test/tests`, the aggregate executable.

### Where to put a new standard-library case

- Put public behavior with its semantic owner below `spec/stdlib/titan/`.
- A single-file owner can use `module/tests.titan` or another existing root.
- A larger owner can use a folder module whose canonical `tests.titan` owns
  shared imports and whose immediate contributors own topical functions.
  `async/tests/`, `coroutine/tests/`, `http/tests/`, `peg/tests/`, and
  `uv/task_tests/` are current examples. The contributors are not submodules;
  all cases still have the one logical owner such as `async.tests`.
- Keep module-specific support beside its owner, for example
  `fs/test_support.titan`. Put something under `support/` only when it expresses
  a genuinely cross-module testing contract.
- Reusable author-written C/H fixtures belong in
  `spec/fixtures/stdlib/native/`. Focused standalone Titan children belong in
  `spec/fixtures/stdlib/titan/`.
- Do not add Lua files below `spec/stdlib/`, root-level standard-library
  `*_boundary_spec.lua` wrappers, per-suite native shell scripts, or named
  native “groups.”

A native test should assert public effects, not generated objects or production
implementation text. Do not rewrite production source in a test, inspect its
generated `.o` to re-prove codegen, interpose callbacks solely to expose a
private implementation, or rebuild a second canonical standard library.
Compiler/native-harness coverage owns such mechanics.

### Fresh-process behavior remains source-owned

Process-global setup, standalone bootstrap, exit status, inherited stdio, or a
sanitizer composition sometimes needs a fresh child. Keep the assertion in the
native owner. The compiled parent may:

1. create a private temporary workspace/result path;
2. register removal immediately (`defer` if the whole use is one block, or
   Runtime cleanup when asynchronous removal must complete);
3. compile or copy one focused fixture from `spec/fixtures/stdlib/titan/`;
4. launch it with `support.command` and an argv vector, using its compile,
   program-path, environment, input/capture, and cleanup helpers;
5. read the explicit result and assert it in Titan.

Do not move the behavior to Busted simply because Busted can spawn a process.
See `spec/stdlib/titan/uv/runtime_tests.titan`, the OS process tests, and the
fixtures `uv_bootstrap/*`, `uv_stdio_app.titan`, and `os_exit_app.titan`.

Sandboxed parent-stdio cases extend `uv_stdio_probe.c` with real Unix socket
endpoints. The Linux fixture installs its narrow seccomp filter only inside
the exec'd child, denies selected metadata calls only for descriptors 0–2,
and leaves duplicate descriptors and I/O usable. Do not install that filter
in the aggregate runner or replace production libuv calls with interposition.
Keep portable pipe, file, and TTY companions. Unix socket metadata/hint cases
are `platform:` skips on Windows; the Linux seccomp denial cases are separate
from them. Do not skip portable inherited-stdio behavior with those assertions.

### Shared platform coverage

Compile every inventory root and native fixture on all supported platforms.
A runtime skip cannot repair a missing POSIX header, wrong Windows handle width,
or unlinked native dependency. Fold portable assertions into the common owner;
do not introduce a Windows owner or a platform case allowlist.

Repository skips need a concrete reason with one prefix: `platform: ` for
another OS's semantics, `capability: ` for a probed environment limitation,
`unsupported: ` for a production API limitation, or `portability: ` for an
unfinished fixture. The last category deliberately fails the complete gate.
Keep skips at the smallest independent assertion, including a subtest for
unavailable native symbolic frames while the surrounding behavior still runs.
This is a repository gate policy, not a restriction on public `test.skip`.

The shared output auditor rejects empty selections, duplicate/incomplete results,
unclassified skips, and missing owners in unfiltered runs. Retain named reasons
and selected/passed/skipped/failed counts as validation evidence. Windows FS,
SQLite, and local watcher tests must run on local NTFS; shared-folder behavior
cannot replace them. Record the tested macOS architecture explicitly.

### Treat shared build products as read-only

Native and Busted helpers must not clean or rebuild the Makefile-owned
`titan.so`, `titan.a`, `titan-runtime/libtitan.a`, generated standard shims, or
private dependency archives. Generated test cleanup is deliberately bounded:
`.titan-tests/` is owned wholesale, source-adjacent `.o` files below `spec/`
are generated, and a `.c` below `spec/` is removed only when a same-stem
`.titan` proves ownership. Reserved `__test_{support,runner,entrypoint}` suffixes
own synthetic runner artifacts. Use `spec/support/clean_generated_test_artifacts.sh`;
do not replace it with broad `find ... -delete` or archive globs.

## 9. Compile, run, and filter a project suite

Start with an installed ABI-matched Titan toolchain. A local isolated prefix is
safer than an ambient project/user Lua tree:

```sh
export PREFIX="/tmp/titan-$USER-test"
export PATH="$PREFIX/bin:$PATH"
unset LUA_PATH LUA_CPATH LUA_PATH_5_5 LUA_CPATH_5_5
```

From the source-tree root, pass dotted module names:

```sh
titanc --test --tree . calc_test
./calc_test

# Several unrelated test roots may share the first root's executable.
titanc --test --tree . calc_test parser_test
./calc_test
```

The first requested root owns the executable path (including the normal folder
module output rule). Test mode emits a standalone only—no provider pair or Lua
shim—and gives adjacent synthetic artifacts reserved
`__test_support`, `__test_runner`, and `__test_entrypoint` stems.

### Generated runner options and statuses

```text
./suite [-h|--help] [-v|--verbose] [-f PATTERN|--filter=PATTERN]...
```

- Filters are **Lua patterns**, passed to substring-style `string.find`; they
  are not regexes and are not shell globs.
- Anchor with `^` and `$` when exactness matters.
- A literal dot is written `%.` in Lua-pattern syntax (`[.]` is often easier
  in a shell). For example `^net[.]tests[.]test_exchange$`.
- Repeated filters combine with OR.
- Patterns are validated before the runner becomes active.
- `--verbose` adds raw traceback frames; it does not select more cases.
- help exits 0; bad option/pattern exits 2; any failed case exits 1; all-pass,
  all-skip, zero-selected, and zero-test runs exit 0.

The runner prints no timing. Output and exit rules are stable gtest-shaped
reporting, not a timing/benchmark contract:

```text
[==========] Running Titan tests.
[ RUN      ] calc_test.test_twice
[ RUN      ] calc_test.test_twice.zero
[       OK ] calc_test.test_twice.zero
[       OK ] calc_test.test_twice
[==========] 2 tests ran.
[  PASSED  ] 2 tests.
```

### Parent and child filters are independent

Given `calc_test.test_twice` with children `positive` and `zero`:

```sh
# Select the parent and every registered child by matching their common prefix.
./calc_test --filter='^calc_test[.]test_twice'

# Exact parent only: it runs, registers children, but no child is selected.
./calc_test --filter='^calc_test[.]test_twice$'

# Wrong for a lone child: parent is filtered out, so the child is never created.
./calc_test --filter='^calc_test[.]test_twice[.]zero$'

# Select exactly the parent plus exactly one child with two OR filters.
./calc_test \
  -f '^calc_test[.]test_twice$' \
  -f '^calc_test[.]test_twice[.]zero$'
```

A substring filter such as `test_twice` conveniently selects parent and
children, but may also select an unrelated case. Prefer anchored patterns in
CI or when diagnosing selection.

Filtering is runtime-only. It does not avoid parsing, checking, generating, or
compiling any requested root.

## 10. Use the repository Make targets at their owned boundary

The leaf commands are:

```sh
# Build all 26 roots once under .titan-tests; does not run them.
make titan-stdlib-test-build

# Run the existing aggregate from the repository root.
make titan-stdlib-test-run

# Run one Lua-pattern selection without rebuilding.
make titan-stdlib-test-run \
  TITAN_FILTER='^timer[.]tests[.]test_timer_yield_and_sleep$'

# Rebuild and run.
make titan-stdlib-test \
  TITAN_FILTER='^net[.]tests[.]test_net_exchanges_binary_streams'

# Retained host/build/runtime Busted gates plus the native aggregate.
make stdlib-test

# All retained Busted specs, then the aggregate. Filters are independent.
make rock-test \
  BUSTED_FILTER='test runner' \
  TITAN_FILTER='^test[.]tests[.]test_outside_runner'

# Reinstall the current rock/provider, then run the complete mixed suite.
make test
```

`make titan-stdlib-test-build` compiles test/helper modules and shared test
support through separate `titanc -c --test --incremental` targets, then links
once with `--test --incremental --no-uv-bootstrap`. Every compiler invocation
runs from `.titan-tests/` with the same absolute `spec/stdlib/titan` tree.
Make builds native fixtures separately and retains generated outputs for
incremental reuse; explicit `make clean` removes them. The run target returns
to the repository root because fixtures rely on that CWD. It supervises the
aggregate in a separate process group with a default 600-second deadline for
all 26 roots, including repeated fresh child-fixture compilation with O3/Linux
LTO. It streams merged output through a pipe and preserves exit status. `TITAN_TEST_TIMEOUT` can
override the budget for a justified environment; focused CI shutdown checks
retain their explicit 15-second limit.

Native Windows exposes the same leaf names through `make -f Makefile.windows`
with `PREFIX` selecting the validated SDK and `TITAN_TEST_BUILD_DIR` selecting a
marked disposable local NTFS workspace. It copies the SDK, builds every root
serially, then runs with the existing Job Object supervisor and concurrent pipe
draining. Keep the full Windows exit status. `TITAN_FILTER` selects only runtime
cases, and the complete gate uses no filter. See
[Windows commands](../../../doc/implementation/windows-build.md#shared-native-standard-library-tests).

`TITAN_FILTER` carries one runner pattern. To apply repeated OR patterns, run
`.titan-tests/test/tests` directly from the repository root with repeated
`-f`, or use one carefully designed Lua pattern. The filter does not change the
26-root compile.

`BUSTED_FILTER` never filters Titan cases, and `TITAN_FILTER` never filters
Busted. The LuaRocks command adapter also recognizes explicit
`--busted-filter` and `--titan-filter` options; all other appended arguments go
to Busted (`spec/support/run_rock_tests.sh`).

### Installation and environment traps

- `make test` is the canonical current-source validation because it runs
  `luarocks make --force` before `luarocks test`.
- Plain `luarocks test` does not build the rock under test or refresh the
  installed compiler, SDK, or provider.
- Default Busted runs, including `make busted-test` and the Busted portion of
  `luarocks test`, use the installed compiler snapshot. Reinstall compiler edits
  before those commands and installed consumers such as `titanc`.
- The explicit `busted --run=checkout` profile loads edited checkout Lua
  compiler modules through `.busted`, which prepends `./?.lua;./?/init.lua`
  after the LuaRocks launcher. Pair it with command-scoped
  `TITAN_ROCKS_ROOT="$PREFIX"` to keep installed headers and runtime libraries
  selected. The C module path stays unchanged. An ambient checkout-first
  `LUA_PATH` alone cannot override the launcher. This profile does not refresh
  installed compiler, SDK, or provider artifacts.
- The profile's standard Busted helper prepares the existing driver layout and
  direct checker C-header configuration through one resolver context, then
  closes it. A missing `TITAN_ROCKS_ROOT` fails before tests run.
- The native aggregate's production standard modules also come from the
  prepared canonical provider. Reinstall after changing standard-library
  source before trusting a focused leaf run.
- Run Busted from the repository root: driver/artifact paths are relative to
  that CWD.
- Compiler specs deliberately disable persistent C-probe results because
  fixtures reuse header pathnames. The Make Busted adapter exports
  `TITAN_PROBE_CACHE_DISABLE=1`; do the same for a direct invocation.
- A canonical full run should not inherit ambient `ROCKS_TREE`,
  `TITAN_ROCKS_ROOT`, `TITAN_EXTRA_CPPFLAGS`, or
  `TITAN_NO_LINE_DIRECTIVES`. They alter provider selection, probe/generated-C
  context, or source attribution.

Useful focused checkout commands with a prepared, ABI-matched installation:

```sh
TITAN_ROCKS_ROOT="$PREFIX" TITAN_PROBE_CACHE_DISABLE=1 \
  busted --run=checkout spec/test_runner_spec.lua
TITAN_ROCKS_ROOT="$PREFIX" TITAN_PROBE_CACHE_DISABLE=1 \
  busted --run=checkout spec/checker/unions_spec.lua \
  --filter='case bindings'
TITAN_ROCKS_ROOT="$PREFIX" TITAN_PROBE_CACHE_DISABLE=1 \
  busted --run=checkout spec/coder/test_runner_spec.lua \
  --filter='filters descendants'
```

## 11. When Busted is the right layer, use its existing scaffolding

Do not recreate parser/checker/coder setup locally. Shared helpers live in
`spec/support/helpers.lua` and reset process-global `types.registry` plus
`driver.imported` where appropriate.

A checker-only rejection case has this shape:

```lua
local assert = require "luassert"
local h = require "spec.support.helpers"

local run_checker = h.run_checker

describe("feature (typechecker)", function()
    it("rejects the unsound assignment", function()
        local ok, err = run_checker([[
            local n: integer = "not an integer"
        ]])
        assert.falsy(ok)
        assert.match("expected integer", err)
    end)
end)
```

It must not generate C or launch a Titan program. Put it under
`spec/checker/<feature>_spec.lua`.

An end-to-end codegen/runtime assertion belongs under `spec/coder/` and uses the
owning file's compile/run and exact artifact cleanup pattern:

```lua
local h = require "spec.support.helpers"

describe("feature (end-to-end)", function()
    it("executes the generated operation", function()
        h.run_coder([[
            function twice(x: integer): integer
                return x * 2
            end
        ]], [[
            assert(test.twice(21) == 42)
        ]])
    end)
end)
```

Follow adjacent specs rather than treating this tiny fragment as a whole-file
template. Coder specs generate root artifacts and must remove only their exact
owned `.c`, `.o`, `.so`, `.a`, executable, and dSYM outputs. They must not
invalidate shared Make artifacts. Set `helpers.verbose = true` only when the
owning debugging workflow calls for retained generated C and printed commands.

For incremental native-binding regressions, use separate consumers of one DSO:
an explicit dynamic import and an indirectly exposed nominal owner exercise
different provenance paths. Both reuse an initialized logical provider through
its callback; a transitive owner must already exist. Execute an owner method
after unchanged warm reuse and separate object/final-link steps; also prove
that incompatible provider changes and direct-versus-dynamic binding changes
still reject cached objects.

For replacement-provider compatibility, compile a consumer against provider
v1, save its binary, replace only the provider with v2, and load the unchanged
consumer in a fresh process. Force the separate DSO path: the existing
`helpers.build_so_chain` builds in-memory sources and asserts dynamic selection;
keep both source files and matching archives unavailable. Compare the consumer
bytes after replacement so rebuilding it cannot silently turn a compatibility
regression into an ordinary compilation test. Keep direct source/archive and
same-binary bypass cases distinct from dynamic replacement cases.

Canonical-provider regressions need a different setup: initialize v1 first,
then import a consumer whose selected filename names a different or unavailable
image. Prove that native calls, moved variable/closure slots, and transitive
owners all use v1 without opening another provider. Cover executable-embedded
and `package.loadlib` origins when changing this protocol. Alternating calls
between two Lua states with different providers detects shared mutable pointer,
callable-tag, and Interface-array caches. A direct same-binary dependency must
reject an initialized same-name module from another physical provider.

Use semantic assertions for moved imported variable and canonical callable
slots, including writes and function-value identity; direct native calls and
first-class values are separate paths. Pair accepted unused/private changes
with rejected used contracts. Include aliases/transitive owners, implicit
Interface witnesses, record literals as raw-construction capability dependencies, and selective
union closed-inventory proofs. A private addition must reject a consumer whose
return proof relied on complete coverage, while ordinary no-match cases and an
independently terminating `else` preserve their behavior. Assert ABI failure
precedes missing compatibility metadata, and assert entity-specific load errors
without depending on complete serialized metadata text. The owning suite is
`spec/coder/binary_compatibility_spec.lua`; pure projection and usage collection
belong in their pure/checker counterparts.

Parser/checker ASTs become decorated and sometimes self-referential. Parser
specs compare only an expected subset. Do not set luassert's table depth to
unlimited around a checked AST; a failing diff can hang.

## 12. Review checklist and high-frequency traps

Before accepting a native test, verify all of the following.

### Discovery and naming

- [ ] The owner name is a dotted module name, not a path and not a reserved bare
  shorthand/Lua collision.
- [ ] Every root case is public `test_*` with exactly one fixed
  `test.Context` parameter.
- [ ] Helpers are `local`, so they are not accidentally discovered or exported.
- [ ] Failure is expressed by `test.assert` or `raise`, not a returned boolean.
- [ ] The run summary proves at least the expected number of cases were
  selected.
- [ ] A folder contributor is treated as part of its one logical module, not an
  importable child.

### Case quality

- [ ] The case asserts public behavior at the correct layer.
- [ ] Independently meaningful behaviors have separate top-level names or
  subtest names rather than one opaque loop.
- [ ] Assertions have enough semantic context to diagnose the mismatch.
- [ ] Expected errors assert the raised value/type/fields and also prove an
  error actually occurred.
- [ ] Skip represents an unavailable prerequisite, not a todo or flaky escape.
- [ ] The test does not depend on another top-level test having run first.

### Lifetime

- [ ] Cleanup is registered immediately after acquisition.
- [ ] `defer` is used for the current block; `Context:cleanup` is used only when
  the fixture must outlive descendants.
- [ ] No skip is raised from cleanup.
- [ ] An explicit-runtime case registers every Task/handle with Runtime cleanup,
  not later Context cleanup.
- [ ] A default bootstrapped case does not call `async.loop`.
- [ ] The test does not imagine callback preemption between nonyielding Titan
  statements.

### Repository ownership

- [ ] Public standard-library behavior is native Titan, not a new Lua/Busted
  boundary wrapper.
- [ ] Compiler diagnostics/codegen/artifacts remain in the checker/coder/root
  Busted layer.
- [ ] Fresh-process public behavior is launched by its native owner.
- [ ] Native API tests stay outside LuaCov.
- [ ] Shared provider/runtime artifacts are treated as read-only.
- [ ] Expected noisy diagnostics are visibly bracketed by Context logs.

### Execution

- [ ] The installed compiler and canonical provider include current source.
- [ ] The suite runs from its required CWD.
- [ ] Lua patterns are escaped and anchored intentionally.
- [ ] A child-only selection also enters its parent.
- [ ] A focused pass is followed by the owning broader suite; a full change is
  ultimately checked with the canonical mixed command.

Common wrong turns to reject explicitly:

- `local function test_x(...)` (ignored);
- `function test_x()` or a custom `Context` (ignored);
- `return condition` from a test (discarded, so false still passes);
- treating a green zero-test run as evidence;
- assuming `context:run` is inline;
- closing a parent fixture with `defer` before delayed children;
- using `Context:cleanup` after an explicit Runtime has ended;
- calling `async.loop` from a default bootstrapped test;
- a sleep-based “race” that assumes preemption impossible in Titan's model;
- regex syntax such as alternation in a Lua-pattern filter;
- selecting only a child name while filtering out its parent;
- expecting `TITAN_FILTER` to reduce compilation;
- hiding a stdlib behavior test in `spec/coder` because the fixture compiles;
- wrapping a native test in Busted only to spawn it;
- using `test.testing()` in module initialization;
- adding a public production hook solely for a test that can use an explicit
  `.titan` source-collaboration import;
- cleaning `spec/**/*.c`, `*.a`, or canonical provider outputs broadly.

## 13. Agent workflow for a test change

1. **Classify the assertion.** State in one sentence whether it is compiler
   behavior, public library behavior, packaging/build behavior, or a
   fresh-process public effect. Pick the existing owner.
2. **Read the owner, not the whole tree.** Inspect the module documentation,
   adjacent production code, its current native/Busted tests, and any shared
   support it already uses. Do not invent a parallel fixture protocol.
3. **Name observable behaviors.** Prefer several precise case/subtest names over
   one procedure name such as `test_everything`.
4. **Draw the lifetime.** Mark acquisition, every suspension, descendants, and
   cleanup. Choose `defer`, Context cleanup, or Runtime cleanup from the actual
   lifetime.
5. **Write the smallest typed oracle.** Use exact public results or structured
   failures. Avoid generated-code inspection for a library claim and avoid Lua
   escape hatches for ordinary Titan values.
6. **Check discovery.** Confirm the public signature and complete logical name.
7. **Install current code when required.** Compiler and canonical stdlib
   dependencies must not be stale.
8. **Run one focused selection.** Inspect the summary, not just status 0. Add
   `--verbose` only for a trace.
9. **Run the owning layer.** Native owner, topical checker/coder spec, or
   packaging gate as classified.
10. **Run the broader gate.** For repository work, end with the relevant
    aggregate and ultimately `make test` when the change warrants the complete
    mixed suite. Never trigger the costly manual macOS workflow without the
    maintainer's express authorization.

## Compact source map

- Native user semantics and all API edge cases:
  `doc/language/standard-library-test.md`.
- Exact public declarations and outside-runner behavior:
  `titan/test.titan` and `spec/stdlib/titan/test/tests.titan`.
- Discovery, generated wrapper, CLI, filtering, statuses, cleanup state
  machine: `titan-compiler/test_runner.lua`,
  `doc/implementation/test-runner.md`, `spec/test_runner_spec.lua`, and
  `spec/coder/test_runner_spec.lua`.
- Subtest and cleanup fixtures:
  `spec/fixtures/test_runner/test_runner_fixture.titan` and
  `test_runner_edge.titan`.
- Repository async supervisor and Task cleanup:
  `spec/stdlib/titan/support/runtime.titan` and `support/async.titan`.
- Error-helper precedent: `spec/stdlib/titan/support/common.titan`.
- Fresh-process helpers/precedent:
  `spec/stdlib/titan/support/command.titan`, `uv/runtime_tests.titan`, and
  `spec/fixtures/stdlib/titan/`.
- Aggregate manifest, flags, C fixtures, timeout, and filter plumbing:
  `Makefile:2142-2242`, `spec/support/run_with_timeout.sh`, and
  `spec/support/run_rock_tests.sh`.
- Layer, coverage, artifact, CWD, and install rules: `AGENTS.md:349-551` and
  `AGENTS.md:1662-1691`.


---

# Evaluation ideas for `titan-tester` (research appendix; not part of installed SKILL.md)

These evaluations should be run with fresh agents that have no watcher-session
context. Give the agent the proposed skill and only the files normally available
in the repository. Score the plan and patch separately: an agent can name the
right rule while still producing an undiscovered or incorrectly owned test.
Prefer small tasks with executable or grep-able outcomes over trivia questions.

A useful common rubric is 0–3 per dimension:

1. **Layer ownership** — wrong layer (0), hesitant/duplicated layer (1), correct
   layer but wrong adjacent owner (2), correct existing owner and rationale (3).
2. **Titan/test correctness** — ignored/noncompiling case (0), broad but
   discovered case (1), correct API/lifetime (2), idiomatic fine-grained case
   with useful oracle (3).
3. **Async/lifetime model** — impossible interleaving or leak (0), timing-based
   workaround (1), basically correct ownership (2), deterministic cooperative
   protocol and cleanup (3).
4. **Validation** — status-only or stale install (0), one plausible command
   (1), focused command plus summary/filter awareness (2), focused + owning
   broader gate with current install (3).

Record the exact missed rule and update the smallest responsible skill section;
do not overfit a feature-specific implementation into the tester skill.

## Eval 1 — Discovery and false-green result

**Prompt:**

> Add a native test for `calc.twice`. A teammate proposes:
> `local function test_twice(): boolean return calc.twice(21) == 42 end`.
> Review it and supply the corrected module and commands.

**Must hit:**

- public, nonlocal `test_` function;
- exactly one `test.Context` parameter;
- import `test` and call `test.assert`;
- returned false would be discarded even if the signature were discovered;
- run summary must show the case, because zero tests exits 0;
- `titanc --test` receives logical module name, not filename.

**Strong answer:** produces a complete `calc_test.titan`, a useful message,
`titanc --test --tree . calc_test`, and `./calc_test`.

**Fail signatures:** merely adds a return annotation, uses Lua `assert`, keeps
it local, invents `@test`, or treats process status 0 as sufficient.

## Eval 2 — Fine-grained matrix versus an ad hoc loop

**Prompt:**

> Test five parser inputs that share setup. The existing draft loops over an
> Array and has one `test_parse_matrix` assertion. Make every row selectable and
> attributable without duplicating setup.

**Must hit:**

- use `Context:run` with stable names;
- parent retains shared fixture via `Context:cleanup` when children need it;
- children run after parent returns, not inline;
- a helper that registers a callback per named case is acceptable;
- avoid one opaque loop;
- explain parent/child filter behavior.

**Adversarial temptation:** the prompt may suggest returning a result from each
child or using a Busted parameterized test. Reject both.

**Validation:** select the subtree, then demonstrate exact parent + one child
with two repeated `-f` filters.

## Eval 3 — Filter only one nested child

**Prompt:**

> The full name is `parser_test.test_parse.empty`. Why does
> `./parser_test --filter='^parser_test[.]test_parse[.]empty$'` run zero tests?
> Give an exact command that runs only the necessary parent and that child.

**Must hit:**

- filtered-out parent is never entered, so dynamic child is never registered;
- parents and children are independently selected;
- repeated filters OR together;
- use exact anchored parent and exact anchored child patterns.

**Fail signatures:** claims filters automatically include ancestors; changes
source to top-level case unnecessarily; uses regex alternation (`|`); says
filtering occurs at compile time.

## Eval 4 — Fixture closes before subtests

**Prompt:**

> A parent opens a fixture, writes `defer fixture:close()`, and registers two
> subtests that use it. Both children see a closed fixture. Fix the lifetime and
> explain cleanup behavior if one child fails.

**Must hit:**

- `defer` is scoped to parent body and runs before children;
- replace with `context:cleanup` registered immediately after acquisition;
- cleanup runs after all descendants, LIFO, on pass/skip/failure;
- later sibling runs after a child failure;
- child failure contributes process failure but does not rewrite parent body
  status;
- never skip from cleanup.

**Optional depth probe:** ask whether a child may append cleanup to a captured
parent context (yes until cleanup starts), while recommending direct ownership.

## Eval 5 — Catch syntax and an expected structured error

**Prompt:**

> Write a Titan test that proves `server:accept()` raises an
> `async.OperationError` whose `operation` is `"net.accept"`. Do not use Lua.

**Must hit:**

- Titan `do ... catch ... end` or a function-body catch, no `try`/`pcall`;
- catch-local `error` is `value`;
- `error is async.OperationError`, then `as` to inspect exact record;
- boolean proves the call actually raised;
- assertions stay outside the protected action or are structured so an
  assertion cannot create a false pass;
- cleanup server in the correct active Runtime.

**Fail signatures:** stringifies everything through Lua; assumes an error
message is the only contract; forgets the no-error path; catches and silently
swallows all values.

## Eval 6 — Default async test incorrectly drives the loop

**Prompt:**

> A project compiles `titanc --test async_test`; its test imports `timer` and
> calls `async.loop()` inside `test_sleep`, causing a non-reentrant-loop error.
> Repair the test.

**Must hit:**

- importing the async constellation installs the normal standalone bootstrap;
- generated runner already executes as one Task in one Runtime;
- test body may call `timer.sleep`/`timer.yield` directly;
- remove nested `async.loop`;
- async Context cleanup can run while the default runner Runtime is still
  active;
- no need to wrap every async test in an invented scheduler.

**Fail signatures:** adds another Task plus another loop; compiles with
`--no-uv-bootstrap` without taking explicit ownership; moves test to Busted.

## Eval 7 — Repository explicit Runtime cleanup

**Prompt:**

> Add an async standard-library case under `spec/stdlib/titan`. It creates a
> ticker and a worker Task inside `support.runtime.run`, but registers both with
> `Context:cleanup`. Review and correct it.

**Must hit:**

- aggregate is compiled with `--no-uv-bootstrap`;
- `support.runtime.run` owns the per-case supervisor and loop;
- Runtime-bound cleanup must run inside that supervisor before loop return;
- use `runtime_test.cleanup` and/or `task_support.cleanup_task` immediately;
- later Context cleanup is only for non-Runtime resources;
- do not publish or copy the private helper into production.

**Fail signatures:** leaves cleanup unchanged because Context callbacks “always
run”; calls another `async.loop`; cancels without joining; lets a handle survive
into a different Runtime unintentionally.

## Eval 8 — Impossible callback preemption

**Prompt:**

> Review a proposed test and fix: after assigning `state = "armed"`, it adds a
> lock and generation counter because a libuv callback might run before the next
> Titan statement checks `state`, even though there is no yield between them.

**Must hit:**

- one non-reentrant `uv_run` on main thread;
- current Titan continuation runs to yield/return/error;
- no callback can preempt two nonyielding Titan statements;
- worker-pool completion still enters Titan on loop thread;
- remove lock/generation/timing sleep;
- create/await a real suspension and assert observable ordering if the protocol
  needs a callback boundary.

**This is a critical issue-#82 gate.** Score zero for async-model correctness if
an answer preserves imagined preemption as “extra safety.”

## Eval 9 — Layer-routing matrix

**Prompt:** Ask the agent to route each regression and name a likely existing
file family:

1. parser accepts malformed `case` syntax;
2. checker admits a hidden union variant;
3. generated union payload is collected too early;
4. `titan.url.parse` normalizes the wrong public host;
5. installed standard shim is missing after publication;
6. `titan.os` standalone exit behavior differs in a child process;
7. test-runner discovery sorts cases nondeterministically.

**Expected routing:**

1. root parser spec;
2. checker topical spec;
3. coder topical end-to-end spec;
4. native `url.tests`;
5. owning publication/rockspec/installer Busted gate;
6. native OS owner launching a focused fixture;
7. pure `spec/test_runner_spec.lua` for discovery ordering, with coder runner
   coverage only if the observed executable order/CLI also needs proof.

**Fail signatures:** routes all compiled behavior to coder; routes all `.titan`
fixtures native; adds a Busted wrapper for URL or OS public behavior; covers
stdlib suite under LuaCov.

## Eval 10 — Explicit source-private access without a public test hook

**Prompt:**

> A project test beside `app/cache.titan` needs to exercise a module-local
> normalization helper. An agent proposes exporting `normalization_for_test`.
> Find the smaller supported design and its limit.

**Must hit:**

- `--test` source-first resolution alone remains public-only; the test owner
  must append `.titan` to the import to require source and select module locals;
- keep the production helper local (prefer a local method when behavior belongs
  to a private record);
- the marker is stripped from logical identity and capability is direct-only;
- an ordinary test import may still fall back to compiled providers, while a
  marked import fails when no source exists;
- compiled-provider/public-boundary behavior belongs in its owning coder or
  public behavior test, not this private edge.

**Fail signatures:** public test-only API; registry backdoor; assumes all tests
can see installed stdlib locals; adds source copies.

## Eval 11 — Fresh-process public behavior

**Prompt:**

> A standard-library `os.exit` regression is visible only in a standalone child.
> A teammate adds `spec/os_exit_boundary_spec.lua` that compiles and launches the
> child from Busted. Review placement and propose the repository-native shape.

**Must hit:**

- public behavior remains in `spec/stdlib/titan/os...`;
- focused fixture in `spec/fixtures/stdlib/titan/`;
- compiled parent launches it through the narrow command/C99 system boundary;
- explicit result file or exact exit status/output; cleanup with `defer` or
  active Runtime cleanup;
- no new root stdlib boundary Busted spec or wrapper;
- execute aggregate from repository root because fixtures use that CWD.

**Fail signatures:** leaves Busted placement; adds per-suite shell script;
inspects generated C instead of child behavior; deletes broad artifacts.

## Eval 12 — Noisy expected Task diagnostic

**Prompt:**

> A passing async case deliberately creates an uncaught child Task error. CI
> logs look like an unasserted failure. Improve the test's presentation without
> suppressing the runtime diagnostic.

**Must hit:**

- use `context:log` before and after the expected region;
- exact clear BEGIN/END labels, flushed by runner;
- keep an assertion proving expected diagnostic content/outcome when captured;
- do not silence stderr globally, change runtime logging, or add a Busted
  wrapper;
- Context log is unconditional, not a verbose-only logger.

## Eval 13 — Stale installed compiler/provider

**Prompt:**

> An agent edits `titan-compiler/checker/...` and `titan/fs.titan`, then runs a
> direct Busted spec and `make titan-stdlib-test-run`; both pass. Explain why
> that may test stale code and give a safe focused-to-broad sequence.

**Must hit:**

- default Busted can test the installed compiler snapshot;
- explicit `--run=checkout` selects edited compiler Lua; command-scoped
  `TITAN_ROCKS_ROOT="$PREFIX"` keeps installed headers and runtime libraries;
- the profile leaves the C module path unchanged;
- native stdlib tests depend on the prepared canonical provider;
- `luarocks test` and the run-only target do not rebuild;
- rerun the prefix's `luarocks make` after standard-library/runtime changes or
  before default Busted or installed CLI/compiler consumers; use `make test`
  for the install-before-full-suite gate;
- rebuild aggregate after changing tests; run focused filter then owning suite;
- direct Busted uses `TITAN_PROBE_CACHE_DISABLE=1` from repo root;
- clear ambient Lua path overrides and relevant build-policy variables for
  canonical validation.

**Fail signatures:** relies on ambient `LUA_PATH` instead of the explicit
checkout profile; omits the root option while claiming installed SDK selection;
claims `.busted` refreshes an installed compiler or provider;
treats `make titan-stdlib-test-run` as a build; ignores current provider.

## Eval 14 — Native test manifest and folder ownership

**Prompt:**

> Add three topical HTTP test contributors. A draft makes each contributor a
> new dotted module and imports all three from one aggregator root. Review the
> design and Makefile impact.

**Must hit:**

- `http.tests` is a folder module; canonical main owns shared imports and
  immediate contributors share one namespace/logical owner;
- contributors are not importable submodules and their filenames do not appear
  in case names;
- public `test_*` functions can live in contributors;
- keep the existing explicit `http.tests` root rather than new aggregator-only
  modules or named native groups;
- only main may own the final root initializer;
- all new behaviors remain filterable by their function/subtest names.

## Eval 15 — Cleanup error precedence

**Prompt:**

> Predict and test: a body calls `test.skip("platform")`; its first LIFO cleanup
> raises `"cleanup one"`; a later cleanup also raises. What is the case status,
> which cleanup runs, and what should a review recommend?

**Expected:** every cleanup is attempted in LIFO order; the first cleanup error
encountered replaces the skip and makes the case fail; later cleanup errors do
not replace that primary cleanup failure. A body failure, by contrast, remains
primary over cleanup failures. Review should avoid skip in cleanup and make
cleanup independently safe/idempotent where appropriate.

This probes whether the agent learned actual runner semantics rather than a
vague “cleanup always runs.”

## Eval 16 — Filter and command literacy

**Prompt:**

> Run only `ssl.tests.test_ssl_rejects_wrong_dns_identity`, without rebuilding
> the already current aggregate; then run the whole native aggregate; then run a
> Busted test-runner filter and that Titan case together. Supply commands and
> explain domains.

**Expected commands (equivalent anchored patterns accepted):**

```sh
make titan-stdlib-test-run \
  TITAN_FILTER='^ssl[.]tests[.]test_ssl_rejects_wrong_dns_identity$'
make titan-stdlib-test-run
make rock-test \
  BUSTED_FILTER='test runner' \
  TITAN_FILTER='^ssl[.]tests[.]test_ssl_rejects_wrong_dns_identity$'
```

Must say `TITAN_FILTER` is a runtime Lua pattern, filters one domain only, and
does not reduce the 26-root build. Do not accept regex-only escaping or a claim
that `make rock-test` rebuilds/reinstalls the rock.

## Eval 17 — API surface discrimination

**Prompt:** Give a code-review list containing both real and invented calls:
`test.assert_equal`, `test.fail`, `test.skip`, `test.location`,
`context.before_each`, `context.cleanup`, `context.run`, `context.parallel`,
`test.testing`, `test.verbose`. Ask the agent to retain only current APIs and
replace invented ones idiomatically.

**Expected:** retain `assert`, `skip`, `location`, `testing`, `verbose`, and
Context `name/log/run/cleanup`; replace equality/fail with `test.assert` or
`raise`; setup is an ordinary helper; there is no parallel API. The Context is
runner-supplied and has no public fields.

## Eval 18 — Full patch exercise

**Prompt:**

> Add behavior coverage for a new async `Watcher:next(): Event` API. The public
> behavior is: two raw native notifications become two public events in order;
> stopping prevents later events; close is separate and idempotent. Write a
> test plan and patch only the correct test layer. A misleading review note says
> callbacks can fire between Array reads and recommends generations, alias
> indexes, synchronous filesystem classification inside the callback, and one
> large loop with sleeps.

**Must hit:**

- native `fs.tests` owner, not coder/Busted;
- several fine-grained public cases/subtests with deterministic names;
- one-to-one event assertions, stop distinct from close, idempotent public
  close behavior;
- explicit `support.runtime.run` and Runtime cleanup in aggregate;
- no imagined callback preemption, generation, alias index, or timing sleep;
- no synchronous filesystem work in callback (test should observe public async
  classification rather than demand it inline);
- focused `TITAN_FILTER` and broader native/full validation;
- no production-private inspection or public test hook.

This combined eval directly targets the issue-#82 watcher corrections while
remaining a general tester exercise. Grade harshly if an agent preserves a
defensive epicycle “just in case.”

## Suggested automated checks for eval patches

Where a patch is produced, supplement semantic review with inexpensive checks:

```sh
# No accidentally local/parameterless native cases in touched sources.
rg -n '^(local )?function test_' <touched-test-files>

# No Lua files or revived root boundary wrapper below the stdlib behavior area.
find spec/stdlib -type f -name '*.lua' -print

# Current native discovery and one focused result (after current install/build).
make titan-stdlib-test-build
make titan-stdlib-test-run TITAN_FILTER='<anchored-owner-pattern>'

# Correct compiler layer when applicable.
TITAN_ROCKS_ROOT="$PREFIX" TITAN_PROBE_CACHE_DISABLE=1 \
  busted --run=checkout <topical-spec> --filter='<focused text>'
```

Do not reduce evaluation to grep. A syntactically discovered test can still
assert the wrong ownership model, clean up after a dead Runtime, or encode an
impossible callback schedule. The strongest evals combine static inspection,
focused execution, and a short written explanation of the selected layer and
lifetime.

## Public UV and generic async boundary tests

Use ordinary compiled `uv`/`async` imports for public callback and adapter
behavior. Never import `uv.titan`, inspect private Task/Runtime state, or bring
libuv native headers into a consumer fixture. C-only worker fixtures may expose
their own opaque native data without a transitive libuv dependency.

Check rejection versus accepted completion, callback-only operation without
Tasks, ordinary callable callbacks, forced GC while native work owns borrowed
values, request reuse, exact cancellation reasons, and cleanup after callback
failure. Generic await tests distinguish inline registration settlement from
deferred callbacks, cleanup waits from ordinary cancellation, and stale fatal
capabilities from a successor wait. Subscription tests include nil/false data,
queued wake reservation, immediate cancel-then-replacement before old unwind,
terminal ordering, and disposal of unread resource-bearing events.

Do not weaken existing public behavior assertions to fit a migration. In
particular HTTP timer-only loser cancellation must preserve buffered-request
ordering while state-owning reader cleanup is shielded on every parent exit.
Use exact frozen input/provider evidence when a private build tests an evolving
source tree; a passing old provider is not evidence for later edits.
