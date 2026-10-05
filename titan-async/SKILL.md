---
name: titan-async
description: Write, review, and test Titan asynchronous code with async Tasks, timers, channels, cancellation, terminal listeners, fixed-arity combinators, and the cooperative libuv continuation runtime. Use when working on Titan async.run/loop, suspend/resume, Task status or cancellation, join/any/race/all, timer.sleep/Ticker, low-level coroutine interaction, or public titan.uv callbacks, generic await/subscriptions, and native ownership code.
---

# Titan async

Use this skill for Titan Task code, Task-aware standard-library code, and reviews
of the public callback-based libuv layer and its async adapters. Titan is not Go, JavaScript, Lua with
annotations, or a preemptive threaded runtime. Read the project-local
`titan-programmer` skill first for general Titan syntax, types, options,
`defer`, `catch`, tests, and build commands; this cartridge supplies the async
mental model and current API in one place.

## Start with the one scheduling invariant

Titan async is **cooperative, single-loop continuation execution**:

- `async.Task` is implemented with `titan.coroutine` and a private tagged yield.
- Async owns its loop: top-level `async.loop()` or the generated standalone
  bootstrap drives it on the Lua main thread. Callback-only code may own a
  separate `uv.loop_t` and call `uv.run` without any Tasks. Never drive a loop
  recursively, including a different loop from a callback.
- A Task runs synchronously until it yields an async operation, returns, or
  raises. Libuv does not preempt that continuation with unrelated loop events,
  and another Task cannot preempt it. Explicit low-level calls with synchronous
  callbacks, such as `uv.walk` and Windows TTY read startup, follow their stated
  callback timing; they are not event-loop preemption.
- Once libuv enters an operation callback, that callback may resume its one
  suspended continuation directly. The Task can run through immediate outcomes
  until it submits the next callback-bearing operation, returns, or raises;
  then the callback returns to libuv.
- Filesystem, DNS, and explicit `async.run_foreign` work may execute in libuv
  worker threads, but only the loop-thread completion callback enters Titan.
  Worker threads never read or mutate Titan records; `run_foreign` performs
  exactly its supplied C function-pointer call over native data.
- CPU-bound Titan code that does not finish or yield blocks every Task and the
  event loop. Call `async.yield()` or `timer.yield()` deliberately in such a
  loop.

Therefore this interleaving is impossible:

```text
Task A reads Titan state
  [unrelated libuv callback runs and mutates that state]
Task A writes Titan state
```

Task A must first yield, return, or raise. In particular, no callback can run
between a combinator's initial status scan, listener registrations, and its
`async.suspend(token)`. Do not add locks, atomics, extra callback fences,
`uv_check_t`, `uv_idle_t`, polling passes, or snapshot rollback to defend against
imagined preemption. The existing Runtime queue and suspension epochs handle
real deferred handoffs and stale operation identity across continuations.

This does **not** remove ownership rules across a real yield. Native work and
borrowed values must remain alive through the callback libuv promised, and a
multi-shot source needs exactly the buffering/waiter state promised by its
public semantics.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, `titan/async.titan`, and issue #82.

## Choose the public layer

Applications normally import `async`, `timer`, `fs`, `net`, `io`, `os`, `ssl`,
or `http`. Library authors and callback-only programs may also use:

```titan
local uv = import "uv"
local async = import "async"
```

These are ordinary compiled imports of `titan.uv` and `titan.async`. Only the
implementation of `titan.uv` imports `uv.h`, libuv native types, or native libuv
helpers, including transitive header dependencies. Do not use `uv.titan` to
reach private declarations. Unrelated OpenSSL, SQLite, llhttp, and platform FFI
remain separate boundaries.

`uv` exposes explicit libuv status, cleanup, ownership, and ordinary Titan
callback values; it does not create Tasks or convert statuses to exceptions.
Use [the public uv manual](../../../doc/language/standard-library-uv.md) and
its family tables for exact signatures, parameter roles, callback cardinality,
borrowed memory, cleanup, and platform support. Titan uses its pinned, patched
bundled libuv 1.52.1. System libuv is not a supported build mode. OpenSSL retains
its separate preferred-system and explicit-bundled modes.

`coroutine` is also public and low-level. It transfers control; it is not a
scheduler. Runtime records, generic operation state, `ASYNC_TAG`, driver
helpers, and UV's native callback bridges remain private.

## Exact public `async` surface

`async` declares and owns `Error`, `OperationError`, `CancellationReason`,
`TaskStatus`, `Task`, and `ResumeToken`. These are not aliases to `uv` types.
Their existing names, constructors, and generic parameters remain available
through `async`; rebuild compiled consumers after this prerelease owner change.
`SuspendCancelAction` is the function type `function (): ()`.

The underlying public data is:

```text
record Error
  error: value
  traceback: string
end

record OperationError
  code: integer
  name: string
  message: string
  operation: string
end

record ResumeToken
  const source: string?
end

union CancellationReason<|B|>
  simple(string)
  complex(B)
end

union TaskStatus<|A, B|>
  ready()
  running()
  waiting()
  succeeded(A)
  failed(Error)
  cancelled(CancellationReason<|B|>)
end
```

`Task<|A, B|>` means success payload `A` and complex-cancellation payload `B`.
A bare `Task`, `TaskStatus`, or `CancellationReason` is exactly the all-`value`
application. There is no public `cancelling` status.

The exact Task/status methods are:

```text
function Task:cancel(reason: CancellationReason<|B|>?)
function Task:status(): TaskStatus<|A, B|>
function Task:add_terminal_listener(
    listener: function (TaskStatus<|A, B|>): ()): function (): ()
function Task:resume(token: ResumeToken)

function TaskStatus:as_string(): string
function TaskStatus:has_finished(): boolean
function TaskStatus:has_succeeded(): (boolean, A?)
function TaskStatus:has_failed(): (boolean, Error?)
function TaskStatus:has_cancelled(): (boolean, CancellationReason<|B|>?)
```

The exact top-level scheduling API is:

```text
function run<|A, B|>(func: function (): (A)): Task<|A, B|>
function run_foreign(f: foreign function (*void): void, arg: foreign *void)
function loop()
function yield()
function running(): Task<|value, value|>
function current_loop(): uv.loop_t
function is_closing(): boolean
function checkpoint()
function request_exit(code: integer)
function suspend(token: ResumeToken,
                 cancel_action: SuspendCancelAction?)
function version(): string
```

`ResumeToken` is nominal. Only the exact record passed to the current
`suspend` may be passed to `resume`; its optional `source` is diagnostic only.
It authorizes this public explicit-suspension wake, never a native operation or
persistent-source completion.

Both type arguments to `run` are all-or-none. `B` appears only in the result,
so a result context may choose it; otherwise the generic final-carrier rule
chooses `value`. Prefer an explicit full pair when the Task crosses an API
boundary:

```text
local task = async.run<|string, value|>(function (): string
  return "done"
end)
```

Do not write a partial `async.run<|string|>(...)`. `async.running()` deliberately
returns `Task<|value, value|>`, but it is a view of the same Task userdata and may
be compared with a precisely typed view. The Runtime stores success and complex
cancellation payloads through the all-`value` carrier; the exact `A`/`B` guard
occurs only when a typed view projects that payload. Identity comparison,
`status():as_string()`, and tag-only status inspection do not project it.
`async.version()` returns libuv's version string.

Evidence: `titan/async.titan`, `titan/async.titan`, and
`doc/language/async-io.md`.

### Generic operations: registration, completion, and cleanup

```text
union Result<|T, E|>
  success(T)
  error(E)
end
union CancellableResult<|T, E|>
  success(T)
  error(E)
  cancelled(CancellationReason<|value|>)
end

record Completion<|C, T, E|> -- opaque; constructed only by async
function Completion:context(number: integer): C
function Completion:resolve(number: integer, result: T)
function Completion:reject(number: integer, error: E)
function Completion:fatal(number: integer, error: value, trace: string)
function await_with<|C, T, E|>(context: C,
  start: function (Completion<|C, T, E|>, integer): (uv.req_t?)): Result<|T, E|>
function await_cleanup_with<|C, T, E|>(context: C,
  start: function (Completion<|C, T, E|>, integer): (uv.req_t?)): Result<|T, E|>
function await_cancellable_with<|C, T, E|>(context: C,
  start: function (Completion<|C, T, E|>, integer): (uv.req_t?)):
  CancellableResult<|T, E|>

function await<|T, E|>(op: function (
  function (T): (), function (E): (), function (value, string): ()): ()):
  Result<|T, E|>
function await_cleanup<|T, E|>(op: function (
  function (T): (), function (E): (), function (value, string): ()): ()):
  Result<|T, E|>
function await_cancellable<|T, E|>(op: function (
  function (T): (), function (E): (), function (value, string): ()):
  (uv.req_t?)): CancellableResult<|T, E|>
```

Prefer `_with` with a named module registrar. Its nominal Completion argument
avoids a concrete-context callable adapter; do not take a bound completion
method just to recreate a capability closure. All three registrar forms return
`uv.req_t?`: ordinary/cleanup may return nil and never implicitly cancel a
returned request; cancellable requires the accepted request unless settled
inline. Create any required request view before native acceptance.

Completion storage is reused per Task. Save the integer supplied to `start`
with that exact Completion and pass it to every method. `context`, `resolve`,
and `reject` reject a stale number; duplicate settlement raises. Checked Task
suspension numbers never wrap. Context access ends at operation retirement,
which clears context/registrar/request/payload before continuation or terminal
Task publication. Save context in callback locals or independently retained
rollback state before settlement or registration failure. Native ownership
lasts until actual terminal callback/close regardless of wait retirement.
Detach an exclusively owned UV data slot before settlement so old cleanup
cannot clear its successor. Concurrent requests require independent context
and captured-number storage; count new context/ticket records and upvalues.

An old `done:fatal(number, error, traceback)` still reports Runtime failure but
must never retire a successor as the old completed request. The callback must
protect terminal conversion/cleanup/settlement and then bare rethrow; preserve
the original error/trace. Normal shutdown cancellation still applies to the
successor and cannot substitute for its native completion.

The callback-triple APIs remain convenience facades over this same core and
retain their closure costs. All forms require a running Task. Triple registrar
arguments are `resolve`, `reject`, and `fatal`.
Registration runs synchronously without a current Task;
it must not yield. Inline resolve/reject is allowed, but the Task continues only
after registration returns. Immediate completion chains use bounded stack.
Exactly one settlement is allowed; duplicate or stale settlements raise.

Allocate callbacks, request views, actions, and anything else that may fail
before native acceptance. Registration owns rollback until it returns. A
rejected native submission has no promised callback; settle rejection inline.
An accepted request and its borrowed arguments survive until the promised
callback, even after cancellation. Copy callback-only results and perform
required native cleanup before settlement; a continuation can immediately
reuse the request or release domain state.

Ordinary `await_with` / `await` skips registration when cancellation is already pending and
raises its nominal reason. After acceptance it waits for completion before
injecting cancellation. `await_cancellable_with` / `await_cancellable` returns `cancelled(reason)` instead;
its registration returns the exact accepted `uv.req_t` or returns nil after
inline settlement. Nil without settlement is an error. Cancellation requests
`uv.cancel` for a supported request and still waits for the terminal callback;
a successful cancel request is not completion. High-level adapters translate
the tagged result into their established cancellation behavior.

`await_cleanup_with` / `await_cleanup` permits registration and completion despite pending cancellation
or Runtime shutdown. Use it for ownership retirement, not ordinary new work.
Cancellation remains sticky and still determines the Task's final status. A
parent already unwinding from cancellation cannot rely on ordinary `join` to
drain a child; await its terminal listener under `await_cleanup`, with an
idempotent listener remover registered in `defer`.

The third capability is for a consumed terminal callback that fails before it
can settle normally. Its catch calls `fatal(error, traceback)` and then `raise`
so the public UV boundary retains the original loop failure. It marks exactly
that operation consumed, allows lexical cleanup to finish, and preserves the
first Runtime failure. It must run outside a Task. A late capability cannot
complete a successor operation; it reports the Runtime failure instead. Never
use `fatal` for a callback belonging to a still-pending accepted native request,
or translate unexpected callback/conversion failures into ordinary `reject`.

`checkpoint()` is a synchronous cancellation boundary for a running Task: it
checks Task context, the first sticky cancellation reason, then Runtime failure.
It does not yield, register a wait, construct a result, or change Task status.
Use it at existing buffered-resource admission positions while preserving
validation, reader contention and lazy-start precedence. It is not a fairness
yield and does not belong on shielded ownership-cleanup paths.

`current_loop()` and `is_closing()` require an active Runtime but not a running
Task, so registration and loop callbacks may use them. Neither creates a
Runtime, yields, nor checks Task cancellation. The loop is borrowed: adapters
manage their own handles, while async owns driving, final loop close and its
internal wake handle. Do not stop, close or unreference Runtime-owned handles
found by a walk. A domain method whose established
contract requires a Task must separately call `running()`. `request_exit(code)`
is the Task-aware exit path used by `os.exit`; cleanup completes before exit.

### Persistent sources: subscriptions own delivery, domains own resources

`CoalescingSubscription<|T, E|>` retains the latest unread value;
`BufferedSubscription<|T, E|>` retains every event in order. Their `.new`
constructor takes a producer called once with these capabilities:

```text
publish: function (T): boolean
fail: function (E): boolean
finish: function (): boolean
```

The producer returns `SubscriptionActions<|T|>` with `stop: function (): ()`
and `close: function (function (): (SubscriptionBatch<|T|>)): ()`. Prebuild
actions before accepting resources. A partially failed producer must roll back
its own accepted resources. A false `publish` means ownership was not accepted;
the producer must dispose of any resource in that event. If publication raises,
the producer also retains ownership. Do not leak an accepted socket after a
closed subscription rejects it.

Coalescing publication can replace an unread value without a destructor. Its
payload must therefore be safely discardable. Use BufferedSubscription for
accepted sockets, descriptors, or other values requiring explicit disposal.

Both expose `next`, `has_waiter`, `stop`, and `close`. `next()` returns
`SubscriptionResult<|T, E|>`: `item(T)`, `error(E)`, `ended()`, or `closed()`.
Errors/end are terminal and follow buffered items; recoverable errors belong
inside `T`. Nil and false are real payloads, never absence sentinels.

Buffered sources additionally expose `next_batch()` returning
`SubscriptionBatchResult<|T, E|>` with `batch(SubscriptionBatch<|T|>)`,
`error(E)`, `ended()`, or `closed()`. A batch has explicit `count` and
one-based `get(index)`; never use Array length or truthiness for nullable data.
`drain_pending()` synchronously transfers the complete unread batch.
`drain_if(predicate)` transfers the complete batch if any item matches, otherwise
nil. `wake_batch()` wakes only a blocked batch reader; it can produce an empty
batch for a domain-specific stop condition. These three are producer/domain
control operations, not a second reader queue.

The `drain_if` predicate must not yield or mutate the subscription. Domain code
must not drain the only outcome promised to an already-notified `next()` reader
and leave it live but empty. Stop/close supplies a terminal outcome; batch readers
may deliberately receive an empty batch through the separate batch contract.

There is one reader reservation across `next` and `next_batch`. A queued wake
keeps it reserved until delivery; cancellation detaches it synchronously before
the canceled Task unwinds. `has_waiter()` queries this exact reservation. Do not
mirror it with a domain boolean cleared only in `defer`, which would prevent
immediate cancel-then-replacement. An old wait's scope cleanup cannot detach its
successor. Wait cancellation leaves the producer alive and queued items intact.

`stop()` is synchronous and idempotent: stop production, retain queued events,
then expose the terminal outcome. `close()` requires a Task for its first call,
blocks ordinary delivery immediately, invokes stop and producer cleanup, and
discards remaining events. Repeated close initiates no second cleanup, including
while the first is suspended. Producer cleanup may use `await_cleanup`; its
supplied drain callback transfers unread resource-bearing events for disposal
before domain handles are closed. One subscription need not own one handle.

Evidence: `titan/async.titan`, `doc/language/async-io.md`, and the native async
subscription/await tests. For domain admission checks, preserve established
error and cancellation precedence before querying a shared reservation.

### Foreign blocking work is a narrow C-only boundary

`async.run_foreign(f, arg)` submits exactly `f(arg)` to libuv's process-wide
worker pool and suspends the current Task until the after-work callback returns
to the event-loop thread. Use it only for a blocking call into an external C
library. The callback is a restricted source `foreign function` or a compatible
C function pointer—not a Titan closure—and the argument points at native
storage that remains alive until completion. Load `titan-ffi` when designing
that boundary.

The worker must not inspect Titan or Lua values, enter an ordinary Titan
function or closure, call a Titan runtime helper or the Lua API, allocate
through Titan, raise, resume a Task, or touch `TValue`/`Udata`/GC state. A
restricted source `foreign function` is the deliberate exception: the compiler
emits it as an exact C callback whose body must itself obey this raw-C boundary.
The suspended caller must retain every owner and must not concurrently access
bytes the worker may read or write. Submission failure raises immediately. Once
accepted, cancellation does not stop the C call or release its state early:
completion stays authoritative, then the Task receives its pending
cancellation. The pool is shared with filesystem and DNS requests, so long or
numerous jobs can delay unrelated I/O.

The portable raw-pointer signature is statically callable across compiled Titan
modules. It does not create a dynamic Lua coercion for raw pointers or foreign
function pointers.

### Exact fixed-arity combinator signatures

Every named operand has an independent success/cancellation pair. Parameter
order is interleaved `(A1, B1, A2, B2, ...)`:

```text
function any_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>):
    AnyTwoResult<|A1, A2|>
function any_three<|A1, B1, A2, B2, A3, B3|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>):
    AnyThreeResult<|A1, A2, A3|>
function any_four<|A1, B1, A2, B2, A3, B3, A4, B4|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>):
    AnyFourResult<|A1, A2, A3, A4|>
function any_five<|A1, B1, A2, B2, A3, B3, A4, B4, A5, B5|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>,
    fifth: Task<|A5, B5|>):
    AnyFiveResult<|A1, A2, A3, A4, A5|>

function race_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>):
    RaceTwoResult<|A1, B1, A2, B2|>
function race_three<|A1, B1, A2, B2, A3, B3|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>):
    RaceThreeResult<|A1, B1, A2, B2, A3, B3|>
function race_four<|A1, B1, A2, B2, A3, B3, A4, B4|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>):
    RaceFourResult<|A1, B1, A2, B2, A3, B3, A4, B4|>
function race_five<|A1, B1, A2, B2, A3, B3, A4, B4, A5, B5|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>,
    fifth: Task<|A5, B5|>):
    RaceFiveResult<|A1, B1, A2, B2, A3, B3, A4, B4, A5, B5|>

function all_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>): (A1, A2)
function all_three<|A1, B1, A2, B2, A3, B3|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>): (A1, A2, A3)
function all_four<|A1, B1, A2, B2, A3, B3, A4, B4|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>):
    (A1, A2, A3, A4)
function all_five<|A1, B1, A2, B2, A3, B3, A4, B4, A5, B5|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>,
    fifth: Task<|A5, B5|>): (A1, A2, A3, A4, A5)

function join<|A, B|>(task: Task<|A, B|>): TaskStatus<|A, B|>
function join_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>):
    (TaskStatus<|A1, B1|>, TaskStatus<|A2, B2|>)
function join_three<|A1, B1, A2, B2, A3, B3|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>):
    (TaskStatus<|A1, B1|>, TaskStatus<|A2, B2|>, TaskStatus<|A3, B3|>)
function join_four<|A1, B1, A2, B2, A3, B3, A4, B4|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>):
    (TaskStatus<|A1, B1|>, TaskStatus<|A2, B2|>,
     TaskStatus<|A3, B3|>, TaskStatus<|A4, B4|>)
function join_five<|A1, B1, A2, B2, A3, B3, A4, B4, A5, B5|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>,
    third: Task<|A3, B3|>, fourth: Task<|A4, B4|>,
    fifth: Task<|A5, B5|>):
    (TaskStatus<|A1, B1|>, TaskStatus<|A2, B2|>,
     TaskStatus<|A3, B3|>, TaskStatus<|A4, B4|>, TaskStatus<|A5, B5|>)
```

The exact result/error owners follow one positional pattern:

| Family | Owners | Variants |
| --- | --- | --- |
| `any_*` | `AnyTwoResult<\|A1, A2\|>` through `AnyFiveResult<\|A1,...,A5\|>` | `first(A1)`, `second(A2)`, then payload variants `third`, `fourth`, `fifth` as applicable, plus `none()` |
| `race_*` | `RaceTwoResult<\|A1, B1, A2, B2\|>` through `RaceFiveResult<\|...\|>` | positional variants carrying the corresponding `TaskStatus<\|Ai, Bi\|>`; no `none` |
| `all_*` errors | `AllTwoError<\|A1, B1, A2, B2\|>` through `AllFiveError<\|...\|>` | positional variants carrying the corresponding `TaskStatus<\|Ai, Bi\|>`; no success variant |

Only `join` has a unary form. There is intentionally no unary `any`, `race`,
or `all`, and no variadic or Array-taking form.

Evidence: `titan/async.titan` and `doc/language/async-io.md`.

### Exact channel surface

Channels are public Task-to-Task coordination built entirely on `running` and
private token-bearing `suspend`/`resume`, not native Runtime queues:

```text
function channel<|T|>(size: integer?):
    (function (T): (), function (): (T), function (): ())

record ChannelReader
record ChannelWriter
function reader_writer_channel(size: integer?):
    (ChannelReader, ChannelWriter)
function ChannelReader:read(): string?
function ChannelReader:read_until(delimiter: string,
                                  chop: boolean?): string?
function ChannelReader:close()
function ChannelWriter:write(data: string)
function ChannelWriter:close()
```

`ChannelReader`/`ChannelWriter` fields are local; their generated constructors
are **not public**. Use the factory.

Evidence: `titan/async.titan` and `doc/language/async-io.md`.

## Start and drive Tasks correctly

### Standalone Titan: `main` already runs as a Task

A standalone program that transitively imports an async module gets the private
bootstrap automatically. Write an ordinary exact `main`; do not wrap it and do
not call `async.loop()` inside it:

```titan
local async = import "async"
local timer = import "timer"

function main(_args: {string}): integer
  local worker = async.run<|string, value|>(function (): string
    timer.sleep(25)
    return "done"
  end)

  case async.join(worker)
  when succeeded(result) then
    if result == "done" then return 0 else return 2 end
  when failed() then
    return 1
  when cancelled() then
    return 3
  else
    raise "join returned a nonterminal status"
  end
end
```

The bootstrap schedules `main`, drives the one loop, and stays alive until
**every** Task has finished even if the main Task returns first. A failed Task
ends and logs only itself; healthy siblings continue. If the main Task fails,
the executable ultimately returns failure, but the Runtime still drains the
other Tasks and native cleanup.

`async.run` always returns before its function runs, even when called from a
Task. A new Task initially reports `ready` and starts on a callback-deferred
turn. One reusable Runtime timer drains its FIFO in bounded batches of entries
present at callback start; new entries wait for a later callback. Do not assume
a child has initialized shared state immediately after `run`, or rely on the
former per-wake timer-close ordering.

### Lua host: schedule, then drive once at the top level

```lua
local async = require "titan.async"
local timer = require "titan.timer"

local result
local task = async.run(function()
    timer.sleep(10)
    result = "done"
end)

assert(task:status():as_string() == "ready")
async.loop()
assert(task:status():as_string() == "succeeded")
assert(result == "done")
```

Only the Lua main thread calls `async.loop()`. Never call it from a Task,
operation callback, terminal listener, or private dispatcher. Libuv forbids
reentrant `uv_run`.

### Explicit manual sessions

A standalone or native test executable built with `--no-uv-bootstrap` calls
`main` directly. Only in that mode (or a Lua host) should the top-level owner
create a supervisor Task and then call `async.loop()`. Finish Task-owned
resources and close application resources inside that Runtime session. After a
successful loop/cleanup, a later `run`/`loop` pair creates a fresh Runtime.

A File is an OS descriptor, not a libuv handle: Runtime shutdown does not close
it. A Ticker is a handle and final `uv_walk` will close one left behind, but
explicit close is still the correct application policy because it releases
promptly and reports errors at the owner.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, and
`spec/stdlib/titan/uv/runtime_tests.titan`.

## Read Task state as a structured snapshot

`status()` is a snapshot. Live states are `ready`, `running`, and `waiting`;
terminal states are `succeeded`, `failed`, and `cancelled`. Repeated reads in
one transition return the same snapshot. A later transition gets a fresh
snapshot even when its tag repeats; retained snapshots never mutate. Internal
Runtime checks use scalar phase so unobserved nonterminal states allocate no
public snapshot.

Prefer a `case` when the payload matters:

```text
local terminal = async.join(task)
case terminal
when succeeded(result) then
  use_result(result)
when failed(failure) then
  report(failure.error, failure.traceback)
when cancelled(reason) then
  case reason
  when simple(message) then report_cancel(message)
  when complex(payload) then report_protocol_cancel(payload)
  end
else
  raise "join returned a live status"
end
```

The predicate methods are convenient when only one outcome matters:

```text
local succeeded, result? = task:status():has_succeeded()
if succeeded then
  -- In a bare string context Titan unwraps string? automatically.
  consume_string(result)
end
```

Do not add `result as string` merely because `result` is an option. Titan
options automatically unwrap in bare-value operations, field access, indexing,
and typed calls. Keep the option when absence itself is meaningful. Remember
that `A` may itself be `nil`; `has_succeeded()` can validly return `true, nil`.
A `case` is clearer for that shape.

`as_string()` returns exactly `"ready"`, `"running"`, `"waiting"`,
`"succeeded"`, `"failed"`, or `"cancelled"` and does not project a generic
payload.

If a value escapes a Task, terminal state is `failed(Error(value,
traceback))`. `async.OperationError` remains the exact `error` value inside the
wrapper. The Runtime reports the uncaught failure and traceback immediately;
later `join`, `race`, or `all` observation does not suppress that report.
Other Tasks continue.

An uncaught `OperationError` report includes `operation`, `name`, numeric
`code`, and `message`, followed by the existing traceback. Rendering remains
protected; it never changes the exact error value stored in the failed Task.

Evidence: `doc/language/async-io.md` and
`spec/stdlib/titan/async/tests/task_test.titan`.

## Cancellation is a request plus an ownership protocol

`Task:cancel(reason?)` has these exact semantics:

1. Omission or nil selects `async.CancellationReason.simple("cancelled")`.
2. The first reason wins. Later cancel calls do nothing.
3. Cancellation is sticky, but it publishes no intermediate status. A snapshot
   stays `ready`, `running`, or `waiting` until final `cancelled(reason)`.
4. The current cancellation action runs synchronously in the caller's current
   execution context before `cancel` returns. That context may be another Task
   or a terminal listener with no Task running. The action must not yield,
   raise, or depend on `async.running()`.
5. The target is resumed only through its legitimate callback or a
   callback-deferred ready-queue entry; cancellation never runs one Task
   inline inside another.
6. The nominal reason is injected at a cancellation-sensitive suspension
   boundary. Catching it, returning from the catch, or raising another value
   cannot change the authoritative final `cancelled` status or original reason.
7. Cancellation-sensitive new work is not submitted after a pending
   cancellation reaches its boundary. Ownership-retiring close and cleanup are
   cancellation-insensitive and still receive ordinary completion.

Example with a structured reason:

```text
record Shutdown
  code: integer
end

local task = async.run<|boolean, Shutdown|>(function (): boolean
  timer.sleep(60000)
  return true
end)

task:cancel(async.CancellationReason<|Shutdown|>.complex(Shutdown(42)))
local terminal = async.join(task)
case terminal
when cancelled(reason) then
  case reason
  when complex(detail) then
    handle_shutdown(detail.code)
  when simple(message) then
    handle_text_cancel(message)
  end
else
  raise "Task was expected to be cancelled"
end
```

`cancel` is not `join`: it requests cancellation and returns. Join before
releasing state that the target's callback or unwind still owns:

```text
if not task:status():has_finished() then
  task:cancel(async.CancellationReason.simple("owner is closing"))
end
local final_status = async.join(task)
```

An accepted one-shot libuv request and every borrowed string/buffer stay rooted
until its promised callback, even after cancellation. Do not implement
cancellation by clearing the last reference, using a finalizer, or calling
`uv_cancel` simply to make status look terminal sooner.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, and
`spec/stdlib/titan/uv/task_tests/cancellation_test.titan`.

### Timeout cleanup follows ownership, not a generic loser rule

Combinators never cancel unfinished operands. After a winner, clean up each
loser according to what it owns. A timer-only deadline does not own connection
state, so its close may safely finish after detachment. A read Task owns parser,
transport, or TLS-busy state, so a deadline winner must cancel **and join** the
read before tearing that shared state down:

```text
local reading = async.run<|string?, value|>(function (): string?
  return connection:read()
end)
local deadline = async.run<|nil, value|>(function (): nil
  timer.sleep(5000)
  return nil
end)

case async.any_two(reading, deadline)
when first(data) then
  -- Deadline owns only its timer. Request cancellation; no parser teardown
  -- waits on it.
  deadline:cancel(async.CancellationReason.simple("read completed"))
  consume(data)
when second() then
  -- Reading owns connection/parser activity. Retire it before teardown.
  reading:cancel(async.CancellationReason.simple("read timed out"))
  async.join(reading)
  teardown_read_state()
when none() then
  local read_status, deadline_status = async.join_two(reading, deadline)
  report_both(read_status, deadline_status)
end
```

Do not turn this asymmetry into a blanket “always join every loser” or “never
join deadlines” rule. Trace the resource ownership of the particular operation.
The production HTTP timeout follows this asymmetry and shields the reader
terminal drain on every exit, including cancellation of the parent. Ordinary
join in the sketch assumes the parent has no pending cancellation.

Evidence: `doc/language/async-io.md` and
`doc/implementation/libuv-runtime.md`.

## Use `suspend`/`resume` only for explicit Task coordination

`async.running()` returns the current all-value Task and raises outside a Task.
`async.suspend(token, cancel_action?)` likewise raises outside a Task. It
submits no native operation and registers no waiter by itself; the caller owns
the condition/waiter state. The Task stores that exact nominal token only for
this explicit suspension.

`Task:resume(token)` means only: “request a callback-deferred wake for the
current explicit suspension authorized by this exact token.” It first compares
record identity. A mismatch raises synchronously in the caller with this exact
message: `Task resume token mismatch (expected source: <source>)`. A nil
expected token or nil source is rendered as `unknown source`. The source does
not participate in equality.
The check is unconditional: before suspension, after wake delivery until
another explicit suspension, during an ordinary native wait, and after terminal
completion the expected token is nil, so every supplied token mismatches
instead of becoming a no-op.

With the correct token, `resume`:

- is synchronous and does not yield the caller;
- never enters the target inline;
- accepts one entry in the Runtime ready queue before publishing the wake;
- coalesces repeated requests before delivery; and
- guarantees deferred delivery, but not an exact number of libuv iterations.

At delivery, the private completion clears `suspended`, `resume_token`, and
`resume_pending` **before** `advance_task` re-enters user code. The resumed
continuation must never observe or inherit the completed suspension's token or
wake bit.

Keep tokens private to the coordination abstraction. Share one record among all
paths that own a single condition (for example one per channel), or create one
fresh record per combinator invocation. Do not use a token as a general native-
wait capability: one-shot callbacks settle their exact await capability,
while persistent sources publish through their subscription.

The optional suspend cancellation action is for idempotently detaching the
**exact** waiter. It runs synchronously only on cancellation, before the wake is
scheduled with the token captured by the suspension. Ordinary correct-token
`resume` does not run it. It must not yield or raise. Always pair the
registration with ordinary scope cleanup too.

A monotonic one-waiter latch uses this shape:

```titan
local async = import "async"

local record Gate
  local opened: boolean
  local waiter: async.Task?
  local resume_token: async.ResumeToken
end

local function gate(): Gate
  return Gate(false, nil, async.ResumeToken("Gate.wait"))
end

local function Gate:wait()
  if self.opened then return end
  if self.waiter then raise "Gate already has a waiting Task" end

  local current = async.running()
  self.waiter = current
  local detach = function ()
    if self.waiter == current then self.waiter = nil end
  end
  defer detach()

  async.suspend(self.resume_token, detach)
end

local function Gate:open()
  if self.opened then return end
  self.opened = true
  local waiter? = self.waiter
  if waiter then
    self.waiter = nil
    waiter:resume(self.resume_token)
  end
end
```

`open` commits the monotonic condition before the only authorized normal wake,
so a normal return from this single suspension already establishes `opened`.
Cancellation unwinds instead, and the defer removes the waiter. A resettable
level condition is different: recheck it after an authorized wake when other
token-authorized code can legitimately make it false again before delivery.
This is **not** an invitation to fence native one-shot operations: accepted
native operations settle their exact public await capability.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, `titan/async.titan`, and
`spec/stdlib/titan/uv/task_tests/continuations_test.titan`.

## Terminal listeners are synchronous observation, not Tasks

```text
function Task:add_terminal_listener(
    listener: function (TaskStatus<|A, B|>): ()): function (): ()
```

Rules:

- Each call on an unfinished Task creates a fresh registration in order and
  returns an idempotent remover for that exact registration.
- Registering the same closure twice creates two independent registrations.
  Removal never compares adjusted closure identity.
- Call the remover with `defer` immediately after registration.
- Registering on an already terminal Task does **not** call the listener; it
  returns an idempotent no-op remover. Inspect initial status first when waiting.
- Before terminal publication, the Runtime clears any explicit-suspension
  token and pending wake. A listener calling `resume` on that same Task gets the
  `unknown source` mismatch, including after callback-boundary failure.
- Terminal publication then stores the exact final status, detaches the
  registration Array as a stable snapshot, installs an empty live list, marks
  the snapshot registrations no longer live, and invokes the snapshot in
  registration order.
- Each listener call has its own empty `catch`: one listener's error cannot
  change status or skip later listeners.
- Delivery is on the main thread after the terminating coroutine is no longer
  current. `async.running()` raises inside a terminal listener. The listener
  must not yield. It may synchronously call `resume(token)` on a different Task
  explicitly suspended with that exact captured token; that only installs the
  target's deferred wake.

Use `async.join*`, `any_*`, `race_*`, or `all_*` rather than rebuilding their
listener protocol. When implementing a genuinely new bounded Task composition,
follow the canonical order:

1. reject the current Task as an operand;
2. scan named operand statuses left-to-right;
3. create one fresh private token for this composition invocation;
4. register a separate listener on each still-relevant named operand, capturing
   that token;
5. `defer` every returned remover;
6. call `async.suspend(token)` exactly once; and
7. let the deciding listener store captured result state and call the suspended
   Task's `resume(token)`.

No callback can interleave between steps 2 through 6. Do not add a post-register
poll, native joiner list, phase bridge, or Task Array. A Task Array would erase
the heterogeneous `(Ai, Bi)` positions.

Keep winner or rejection guards and completion counters when they arbitrate
multiple legitimate terminal listeners before deferred delivery. Do not add a
nullable waiting-Task guard to defend against an outside early wake; that caller
does not hold this invocation's private token. The existing `join*`
per-position `has_finished()` checks are redundant local idempotence: each
positional registration is invoked once. They are unrelated to this protocol.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, and
`spec/stdlib/titan/async/tests/task_test.titan`.

## Choose the right combinator

| Operation | Completion condition | Return/raise behavior | Losers |
| --- | --- | --- | --- |
| `any_two` ... `any_five` | first observed **success**, or all terminal without success | positional `AnyNResult` success; `none` if every operand failed/cancelled | never cancelled |
| `race_two` ... `race_five` | first observed terminal status of any kind | positional `RaceNResult` carrying exact terminal `TaskStatus` | never cancelled |
| `all_two` ... `all_five` | all succeed, or first observed failure/cancellation | exact success payloads as multiple results; raises positional `AllNError` containing the rejecting status | never cancelled |
| `join` | one Task terminal | returns its exact status; Task failure/cancellation is not raised by `join` | n/a |
| `join_two` ... `join_five` | every Task terminal | returns all exact statuses; Task outcomes are not raised | n/a |

Details that evaluations should preserve:

- All combinators require a running Task, even if operands are already terminal.
- Waiting on the current Task is rejected; it cannot terminalize while waiting
  for itself.
- Already-terminal ties choose the leftmost operand. Later events follow
  terminal-publication order. Duplicate Task operands are legal and retain
  positional identity; duplicate listener registrations run in registration
  order, so the leftmost position wins.
- `any` treats a successful nil payload as success, not `none`.
- `all` raises an `async.AllNError`, not the underlying Task error or
  cancellation reason directly.
- A failed Task has already logged its uncaught error. Joining it later does not
  retroactively “handle” or suppress the report.
- A combinator cancelled while suspended removes all operand listeners through
  their deferred removers.

Example `race` inspection:

```text
case async.race_two(first, second)
when first(status) then
  case status
  when succeeded(value) then consume_first(value)
  when failed(failure) then report(failure.error, failure.traceback)
  when cancelled(reason) then report_cancel(reason)
  else raise "race produced a live status"
  end
when second(status) then
  consume_second_status(status)
end
```

Example `all` rejection:

```text
do
  local left, right = async.all_two(first, second)
  consume_both(left, right)
catch
  if error is async.AllTwoError then
    local rejected = error as async.AllTwoError
    case rejected
    when first(status) then report_first(status)
    when second(status) then report_second(status)
    end
  else
    raise
  end
end
```

Evidence: `doc/language/async-io.md` and native coverage in
`spec/stdlib/titan/async/tests/any_race_test.titan` and
`spec/stdlib/titan/async/tests/all_join_test.titan`.

## Timers

The exact public timer API is:

```text
function sleep(milliseconds: integer)
function yield()

record Ticker
function ticker(milliseconds: integer): Ticker
function Ticker:tick(): boolean
function Ticker:close()
```

`Ticker` has a local native field; its constructor is **not public**. Use
`timer.ticker`. It incidentally satisfies the exact public `io.Closer`
Interface.

All timer operations require a running Task.

- `timer.sleep(ms)` waits at least until a one-shot timer fires. Negative values
  raise an `async.OperationError` for `timer.sleep`. Zero is valid and yields to
  a callback-deferred later turn.
- `timer.yield()` and `async.yield()` are the same public operation. They are
  Task scheduling points, not `coroutine.yield` and not Lua coroutine yields.
- `timer.ticker(ms)` requires `ms > 0` and creates a Runtime-bound recurring
  handle.
- `tick()` returns `true` for a firing. Only one Task may wait at a time.
- With no waiter, the Ticker remembers one pending fact. Multiple missed
  intervals coalesce; it is not a tick counter or queue.
- `close()` is idempotent, stops and asynchronously closes the native timer,
  wakes an existing waiter with `false`, and makes later `tick()` return
  `false`.
- Close is ownership-retiring and cancellation-insensitive: once accepted, it
  reaches close completion even if cancellation is pending.

Acquire and defer close in the same Task scope:

```text
local ticker = timer.ticker(100)
defer ticker:close()

local count = 0
while count < 4 do
  if not ticker:tick() then break end
  count = count + 1
end
```

Runtime shutdown will close a forgotten live Ticker through `uv_walk`, but that
is a final safety cleanup, not a reason to omit explicit close.

The public API promises callback-deferred waiting but no exact libuv phase or
number of loop iterations. Do not base application logic on timer phase order.
Ticker's public UV timer callback publishes to a CoalescingSubscription; its
exact reader reservation is queried for the duplicate-wait diagnostic. Sleep
instead owns one private one-shot timer and ResumeToken: firing/cancellation
coalesce through Task.resume, and a cleanup Completion waits for typed native
close before normal return or cancellation unwind. It does not construct a
Ticker/subscription.
`ResumeToken` remains the explicit `suspend`/`Task:resume(token)` capability;
native one-shot adapters settle their own await capabilities.

Evidence: `titan/timer.titan`,
`doc/language/standard-library-timer.md`, and
`spec/stdlib/titan/timer/tests.titan`.

## Bounded channels

`async.channel<|T|>(size?)` defaults to capacity 1; an explicit size must be at
least 1. It is a FIFO bounded circular buffer and can carry nil when `T` admits
nil. State `T` explicitly or supply an expected callback triple; a bare
unconstrained `channel()` closes to `value`.

```text
local send, receive, close = async.channel<|string|>(2)
defer close()

local producer = async.run<|nil, value|>(function (): nil
  send("first")
  send("second")
  return nil
end)

local first = receive()
local second = receive()
local producer_status = async.join(producer)
```

A full send or empty receive suspends. There is at most one blocked sender and
one blocked receiver; a second same-direction operation raises rather than
barging or creating a queue. Each channel owns one fresh private token shared
by its send, receive, close, and cancellation paths. Opposite-side progress
changes the buffer first, then calls the waiter's `resume(token)`; close commits
terminal state before doing the same. The occupied waiter slot prevents another
same-direction operation from stealing that progress before delivery. A
blocking operation therefore suspends once: a normal return has its buffer
postcondition or observes close, while a caller with another token cannot wake
it.

`close()` is synchronous and idempotent. It discards buffered values, wakes
both waiter slots, and makes every later or woken send/receive raise
`"channel is closed"` (unless authoritative Task cancellation wins the same
unwind). Cancellation uses the stored channel token to inject its reason and
unwinds; deferred cleanup removes the exact waiter so a new Task may occupy
that side.

`reader_writer_channel` wraps `channel<|string|>` in opaque Reader/Writer
facades. `read_until` is binary-safe across message boundaries; an empty
delimiter raises. Reader close discards its own saved suffix and returns nil for
new reads. Writer close preserves a suffix already transferred to the Reader,
but the next underlying channel receive observes close.

Evidence: `doc/language/async-io.md`, `titan/async.titan`, and
`spec/stdlib/titan/async/tests/channel_test.titan`.

## Public UV adapters and native binding ownership

Use ordinary `import "uv"` and `import "async"` for adapters. There is no
operation-specific Call union, dispatch method, Task pending-owner field, or
private callback-resume API to extend. Classify the native contract first:

| Native shape | Composition | Owner |
| --- | --- | --- |
| synchronous, no retained callback | direct public UV call | caller-owned input/result |
| one-shot request | `await` or `await_cancellable` | UV request plus adapter captures until completion |
| ownership retirement | `await_cleanup` | close/cleanup callback |
| worker-pool call | `uv.queue_work` or `async.run_foreign` | C-only carrier until after-work |
| persistent source | coalescing or buffered subscription | domain resource plus generic delivery state |

Public loop-thread callbacks are ordinary Titan callable values, including Lua
functions admitted by the normal callable boundary. Only UV's internal exact
foreign bridges know native storage and compiler callback layout. Never treat a
public callback as a known CClosure or expose the internal bridge ABI.

### Binding invariants

These rules apply when maintaining `titan/uv/`, not when writing an adapter:

- Initialize embedded native state only in its final concrete owner. Generic
  `handle_t`, `stream_t`, and `req_t` views preserve that owner's identity and
  lifetime; they do not copy native structs or rewire native `.data`.
- Native `.data` belongs to the binding. Public userdata lives in a separate
  traced `value` slot. Per-loop roots retain handles through close callbacks
  and accepted requests through completion. Root before acceptance and remove
  a rejected submission's root when its native contract promises no callback.
- A callback frame keeps the concrete owner alive until the actual native
  callback returns, even after clearing its pending registration and resuming
  user code. Extract/copy borrowed outputs, retire required native storage, and
  settle only after the promised native result is safe to consume.
- A request callback can reuse its request after the old registration is
  cleared. No late cancellation may target the successor request. Never add
  generations, token registries, event-kind dispatch, or duplicate owners to
  approximate this exact capability boundary.
- Loop callbacks run on the owning Lua main state. C worker/thread callbacks
  never enter Lua/Titan or recover a GC owner. They access only their typed
  native function/argument carrier; after-work on the loop thread owns delivery.
- Binding callbacks catch ordinary conversion/user-callback errors, remember
  the first caught error and traceback (preserving `false`; Lua 5.5 normalizes
  a raised `nil` to `"<no error object>"` before catch), stop driving, and return
  normally to libuv. `uv.run`/`uv.walk` rethrow afterward. Ownership remains
  valid for explicit cleanup. The selected boundary does not promise recovery
  from fatal VM stack exhaustion or out-of-memory failures.
- `handle:is_initialized()` is false before initialization and after the close
  callback retires it; it stays true during closing. `uv.is_closing(handle)`
  is valid only in that initialized interval. Guard repeated domain close as
  `not handle:is_initialized() or uv.is_closing(handle)`; do not duplicate
  closing state. `uv.walk` discovers native live handles at shutdown.

### Domain adapters

Use one callback per native protocol, ordinary await settlement for one-shot
work, and subscription publication for persistent events. Construct required
closures/views before accepting work. Preserve status codes, existing domain
operation names, Task requirements, cross-Runtime checks, fast paths, and
cancellation/error precedence. Synchronous resource constructors must not turn
into cancellation boundaries merely to query shutdown; use `is_closing()`.

Callbacks copy transient data, publish, and return. Filesystem watcher callbacks
queue raw notifications; the draining Task performs asynchronous `lstat` and
maps them. If classification retires a registration and new events reference
it, take the complete follow-on batch in callback order. Do not filter or
reorder other registrations' events. Keep exactly one raw event to one public
event and put recoverable mapping errors in the event payload.

Parent stdio classification belongs to `os`, using public UV operations plus
unrelated platform FFI. Preserve known TTY/pipe classifications, close-on-exec
duplicates, independent socket family/type evidence, immediately captured
errno, and the exact `stdio.parent.kind` diagnostics. Only denied metadata may
use the launcher's strict `TITAN_STDIO_PIPE_FDS` fallback; observed incompatible
metadata still rejects. See the OS manual and implementation chapter.

Native cancellation is optional and operation-specific. Ordinary await retains
accepted work through its callback; cancellable await requests cancellation
without pretending it has completed. Explicit handle close is separate from
wait cancellation. Libuv orders accepted writes; do not add another write queue.
Subscription buffers are justified by promised event semantics, not scheduling.

Evidence: `doc/implementation/libuv-extension-guide.md`,
`doc/implementation/libuv-runtime.md`, `titan/uv/`, `titan/async.titan`, and
the consumer implementations in `fs`, `net`, `os`, and `timer`.

## Raw Titan coroutines are a separate low-level API

The exact public `coroutine` surface is:

```text
record Coroutine
end

function create(func: function (value): (value), default_tag: value): Coroutine
function running(): Coroutine?
function Coroutine:resume(arg: value, tag: value): value
function Coroutine:error(err: value, tag: value): value
function Coroutine:status(): string
function yield(arg: value, tag: value): value
function is_yieldable(tag: value): boolean
```

`Coroutine` fields and constructor are **not public**; use `coroutine.create`.
Ordinary fixed-call adjustment makes the second argument to `create`, `resume`,
and `error` omittable by nil-fill. Nil means “no explicit tag”; resume/error then
use the stored default, and raise if neither is nonnil. `coroutine.yield` and
`is_yieldable` require an explicit nonnil tag and do not use a default.

`coroutine.running()` returns the currently executing Titan `Coroutine`, or
nil when none is executing. It returns the exact record produced by `create`,
so handle identity and ordinary methods are preserved. Nested resumes select
the innermost coroutine; yield, return, and uncaught errors restore the caller's
active coroutine or nil. Restoring a tagged skipped stack makes its innermost
coroutine current again.

Lua callers use `require "titan.coroutine"`; Lua's own `coroutine.running()`
observes Lua threads separately. `async.running()` returns the current Task
and raises outside a Task. Use Task APIs for scheduling and async I/O, and
`coroutine.running()` for low-level coroutine identity.

Tags use raw equality. A tagged yield finds the nearest active resumer with the
same tag; skipped inner coroutines become `stacked` until the suspended matching
handler resumes. Status strings are `suspended`, `running`, `normal`, `stacked`,
and `dead`.

```titan
local coroutine = import "coroutine"

function coroutine_example(): value
  local co = coroutine.create(function (arg: value): value
    local next = coroutine.yield(arg, "demo")
    return next
  end, "demo")

  local first = co:resume("ready")
  return co:resume("done")
end
```

This is not Lua's coroutine library and not `async.yield()`. Do not try to
obtain or yield Titan async's private `ASYNC_TAG`. Tagged nesting lets the Runtime's
private async yield cross nested Titan coroutines correctly, but application
code should still use Task APIs for scheduling and I/O.

Evidence: `doc/language/coroutines.md`, `titan/coroutine.titan`,
and `doc/implementation/coroutines.md`.

## Test async behavior in native Titan

Repository standard-library behavior belongs under `spec/stdlib/titan/` and
runs in the unified native executable outside LuaCov. Do not add a Lua wrapper
or root-level Busted boundary spec for Task/timer behavior.

The aggregate executable uses `--no-uv-bootstrap`, so each async case owns one
explicit Runtime session. The repository's `support.runtime` and
`support.async` are **test-private source helpers**, not installed public APIs:

```titan
local test = import "test"
local runtime_test = import "support.runtime"  -- TEST-PRIVATE
local task_support = import "support.async"    -- TEST-PRIVATE
local async = import "async"
local timer = import "timer"

function test_resume_is_deferred(_context: test.Context)
  runtime_test.run(function ()
    local trace = ""
    local resume_token = async.ResumeToken("resume test")
    local target = async.run<|nil, value|>(function (): nil
      trace = trace .. "suspend>"
      async.suspend(resume_token)
      trace = trace .. "target"
      return nil
    end)
    task_support.cleanup_task(target, "resume test cleanup")

    while target:status():as_string() == "ready" do timer.yield() end
    trace = trace .. "resume>"
    target:resume(resume_token)
    trace = trace .. "caller>"
    async.join(target)

    test.assert(trace == "suspend>resume>caller>target",
                "resume entered its target inline")
  end)
end
```

Register Runtime-bound cleanup in the supervisor Task (`defer`,
`runtime_test.cleanup`, or `task_support.cleanup_task`) so it runs before
`async.loop` returns. A later `Context:cleanup` is too late for a live Ticker,
stream, server, or Task because the Runtime session has already ended. Ordinary
non-Runtime test resources may still use `Context:cleanup`.

For an intentionally uncaught Task error, bracket expected raw diagnostics:

```text
context:log("BEGIN expected uncaught async Task diagnostics")
-- schedule and observe the failing Task
context:log("END expected uncaught async Task diagnostics")
```

Prefer public black-box behavior. Reuse existing callback/rooting proofs rather
than rewriting `titan/uv/*.titan`, adding test hooks, or building a delayed
source variant. A fresh-process public boundary belongs in a focused compiled
Titan child launched by the native parent, with an explicit result file removed
by `defer`.

Useful commands from the repository root:

```sh
make titan-stdlib-test TITAN_FILTER='async[.]tests[.]'
make titan-stdlib-test TITAN_FILTER='timer[.]tests[.]'
make titan-stdlib-test TITAN_FILTER='uv[.]task_tests[.]'
make stdlib-test
```

Evidence: `doc/language/standard-library-test.md`,
`spec/stdlib/titan/support/runtime.titan`,
`spec/stdlib/titan/support/async.titan`, and
`doc/implementation/libuv-extension-guide.md`.

## Async review checklist

Before accepting Task/application code, verify:

- It selects public high-level modules or explicit public `uv` callbacks;
  no adapter imports libuv FFI or uses `uv.titan` to reach private state.
- It assumes cooperative execution, not preemption, and explicitly yields a
  CPU-heavy loop.
- It does not call `async.loop` from a Task or callback.
- It remembers that `async.run` never starts inline and that standalone `main`
  is already bootstrapped.
- If it uses `run_foreign`, the function is C-only, every native argument owner
  survives completion, shared bytes are synchronized, and pool starvation is
  an accepted/documented tradeoff.
- It uses precise `Task<|A, B|>` types and supplies both explicit type arguments or
  neither.
- It handles the six status variants without inventing `cancelling`.
- It treats `cancel` as sticky first-reason request, not completion, and joins
  before releasing target-owned state when ownership requires it.
- It creates a private nominal `ResumeToken`, passes the same record to
  `async.suspend(token, ...)` and every authorized `Task:resume(token)`, and
  treats `source` as diagnostic only.
- It expects a wrong token—or any token at the wrong time—to raise in the
  caller as `Task resume token mismatch (expected source: <source>)`, with
  `unknown source` when no source is stored.
- It preserves the delivery ordering: clear `suspended`, `resume_token`, and
  `resume_pending` before `advance_task` re-enters user code.
- It uses `Task:resume(token)` only for the exact explicit
  `async.suspend(token, ...)` that stored the token, never as a native completion
  substitute.
- A suspend cancellation action only detaches exact waiter state, synchronously,
  idempotently, without yielding or raising; scope cleanup is also registered.
- Every terminal-listener remover is called in `defer`; initial statuses are
  checked first.
- It chooses `any`/`race`/`all`/`join` by outcome semantics and supplies an
  explicit loser policy. No combinator auto-cancels.
- A Ticker is closed explicitly and missed ticks are not counted.
- Runtime-bound test cleanup finishes inside `support.runtime`, not later in a
  test context cleanup.

Before accepting a UV binding change or public adapter, also verify:

- The native operation is classified as synchronous, one-shot, or persistent.
- A complete callback owner is rooted for exactly the native lifetime.
- Every borrowed argument/result interval and exactly-once cleanup is explicit.
- Rejection and accepted-callback paths follow the pinned native contract.
- The callback copies/releases before resuming, catches before returning to C,
  and never calls `uv_run`.
- A one-shot completion settles its exact await capability after native
  cleanup; persistent delivery uses the selected subscription.
- Inline registration completion is deferred until registration returns; a
  terminal callback failure uses its fatal capability and preserves the trace.
- Cancellation does not drop accepted work early or synchronously enter another
  Task.
- A worker callback reads only its raw function/argument carrier, never enters
  Titan/Lua, and leaves owner recovery and Task resumption to after-work on the
  loop thread.
- `uv_is_closing` and `uv_walk` remain authoritative; no duplicate resource
  graph, generation, or close flag appears.
- Behavioral tests use the public production facade unless a genuinely new
  native boundary demands a focused fixture.

## Evaluation cases for fresh agents

These cases are for evaluating whether an agent actually internalized this
skill. They are not additional public APIs.

### 1. Cooperative-interleaving review

**Prompt:** A proposed bounded queue checks `if waiter == nil`, then appends a
value, then installs a waiter. The author adds a mutex and Runtime generation
because “a libuv callback could run between the check and append.” Review it.

**Pass:** Reject the mutex/generation and explain that no libuv callback or
other Task can preempt running Titan code; interleaving occurs only after a
Task yield/return/error. Retain only state required across real suspension.
Recheck a level condition after a public wake only when token-authorized peers
can legitimately invalidate it again before delivery; a monotonic condition
committed before the wake needs no defensive loop.

**Fail:** Treat Tasks as threads, add locks/atomics, or propose another event
loop/ready queue.

### 2. `run` and bootstrap

**Prompt:** Write a standalone `main` that starts two timed Tasks and waits for
both.

**Pass:** Use `async.run`, `async.all_two` or `join_two` from ordinary `main`;
do not wrap `main` in another Task or call `async.loop`. State that `run`
returns before children start and the generated bootstrap drives the loop.

**Fail:** Call `async.loop` inside `main`, use Lua coroutines, or assume either
child initialized state inline.

### 3. Explicit resume ordering

**Prompt:** A Task appends `target` after `async.suspend(token)`; another running
Task appends `before`, calls `target:resume(token)`, then appends `after`. What
order is possible, and what does another token do?

**Pass:** `before>after>target`. Correct-token `resume` is synchronous only in
accepting the coalesced Runtime queue entry; it never enters target inline.
Repeated correct-token requests coalesce and exact libuv iteration count is not
promised. Another token raises in its caller as
`Task resume token mismatch (expected source: <source>)`; after wake delivery
and before another suspension—or after terminal completion—the expected source
is `unknown source`. The Runtime clears `suspended`, `resume_token`, and
`resume_pending` before `advance_task` enters `target`.

**Fail:** `before>target>after`, treat a wrong-time resume as a no-op, compare
token sources instead of identity, or claim a general native operation can be
forced complete with `Task:resume(token)`.

### 4. Suspend cancellation action

**Prompt:** Implement a one-waiter in-memory latch with cancellation.

**Pass:** Create one private token for the latch, store `async.running()`, and
install an idempotent exact-waiter detach. Call it both from `defer` and as the
second argument to `async.suspend(token, detach)`, make it nonyielding and
nonraising, and have the producer commit the monotonic latch before calling
`resume(token)`. Suspend once: a normal return has that postcondition, while
cancellation detaches and then wakes with the stored token to inject its reason.

**Fail:** Close shared state on waiter cancellation, run cleanup only after
resume, or make the cancellation action perform async work.

### 5. Native one-shot callback

**Prompt:** Adapt a public UV one-shot request whose callback returns a borrowed
buffer into a Task operation.

**Pass:** Ordinary compiled UV import plus generic await; distinguish native
rejection from acceptance; copy the result and clean native storage before
resolve/reject. Keep accepted ownership through cancellation. On consumed
callback failure, call fatal with the original error/trace and re-raise.

**Fail:** Call public `Task:resume(token)`, invent a token for native completion,
call `uv_run`, clear the owner on logical cancellation, rely on a finalizer, or
add an event-kind dispatcher.

### 6. Watcher callback classification

**Prompt:** A filesystem watcher callback must decide created/deleted/modified.
Should it call synchronous `stat` in the callback and keep a generation to
reject stale results? During asynchronous classification, a deletion retires
its registration after more callbacks have appended to the fresh batch. Which
notifications belong to this `poll`?

**Pass:** Copy one raw notification and return; classify with asynchronous
`lstat` when the Task drains it; map each notification one-to-one; root the
complete registration; separate stop from close; use `uv_is_closing`; no
Runtime generation, alias index, or batch rollback. If classification retires
a registration and the fresh callback batch contains that owner, drain the
complete fresh batch in order so no already-copied retired-owner event leaks
into the next poll; leave a live-owner-only batch buffered.

**Fail:** Block in the callback or add defensive state not promised by the
public watcher contract.

### 7. Cancellation status and ownership

**Prompt:** A Task is waiting on an accepted operation. Another Task calls
`cancel` twice with different reasons and immediately frees its buffer because
status should be cancelled.

**Pass:** First reason wins; status remains its current live variant until
terminal callback/unwind; accepted request and buffer remain rooted; cancel is
not join; ownership-retiring cleanup still completes; final status is
`cancelled(first_reason)` even if caught.

**Fail:** Publish `cancelling`, use the second reason, suppress the promised
callback, or free early.

### 8. Deadline composition

**Prompt:** Compose a connection read with a timer deadline.

**Pass:** Use `any_two` or `race_two` with exact Task types; handle positional
union; when read wins, cancel/detach the timer-only deadline; when deadline wins,
cancel and join the reader before parser/connection/TLS state teardown; do not
claim the combinator cancels losers.

**Fail:** Always abandon the reader, always wait for every timer regardless of
ownership, or add a scheduler timeout primitive.

### 9. Terminal listeners

**Prompt:** Build a two-Task composition from listeners.

**Pass:** Initial left-to-right status scan, one fresh private token for the
composition, distinct named listeners that capture it, immediate `defer` for
every remover, one `suspend(token)`, then the deciding listener stores result
and calls `resume(token)`. Explain terminal registration is not invoked
immediately, listeners run sequentially outside a user Task, errors are
isolated, and no callback can interleave before suspend.

**Fail:** Put heterogeneous Tasks in `{Task}`, poll statuses, add a post-register
race fence, depend on callback closure identity, or omit removers.

### 10. Pick `any`, `race`, `all`, or `join`

**Prompt:** (a) first success with `none` if no success; (b) first terminal
outcome including failure; (c) all success values but positional rejection;
(d) inspect every final status.

**Pass:** (a) `any_*`; (b) `race_*`; (c) `all_*`; (d) `join_*`. Mention arities
2-5, only unary `join`, left-to-right initial ties, and no automatic loser
cancellation.

**Fail:** Invent unary/variadic forms, say `join` raises the Task error, or say
`any` treats successful nil as no success.

### 11. Ticker lifecycle

**Prompt:** Review code that creates a Ticker, counts every elapsed interval
while busy, and relies on Runtime shutdown instead of close.

**Pass:** Add immediate `defer ticker:close()`, state that missed ticks coalesce
to one pending fact, only one waiter is allowed, close wakes it with false, and
explicit close is preferred even though `uv_walk` is final cleanup.

**Fail:** Promise accumulated tick counts, allow waiter queues, or use a GC
finalizer as prompt close.

### 12. Native async test placement

**Prompt:** Add a Task cancellation behavior test using a Lua Busted wrapper and
`Context:cleanup` for a live Ticker.

**Pass:** Put a native Titan `test_*` case under the owning
`spec/stdlib/titan/` module; run it in test-private `support.runtime`; close or
register Runtime cleanup inside that supervisor Task; use fine-grained
`titan.test` assertions/subtests; keep it outside LuaCov.

**Fail:** Add a Lua boundary spec for ordinary stdlib behavior or defer a live
Runtime handle until context cleanup after `async.loop` returned.

### 13. Coroutine distinction

**Prompt:** Yield one event-loop turn from a Task and explain whether Lua's
`coroutine.yield` is involved.

**Pass:** Use `async.yield()` or `timer.yield()`. Explain Titan's public
`coroutine.yield(value, tag)` is a separate stackful tagged control-transfer API,
Lua's coroutine library is different again, and async's tag is private.

**Fail:** Call Lua's coroutine API, invent a public `ASYNC_TAG`, or claim raw
coroutine creation schedules a Task.

### 14. Foreign worker boundary

**Prompt:** Offload a blocking C call by passing a capturing Titan closure and
record pointer to `async.run_foreign`, then free the record as soon as the Task
is cancelled.

**Pass:** Reject the Titan closure and GC record pointer. Use a compatible C
function pointer over native storage, retain its complete owner through the
after-work callback, synchronize all shared bytes, and explain that accepted
work is not stopped by Task cancellation. The worker calls only `f(arg)` and
never enters Titan/Lua; the shared pool can delay filesystem/DNS work.

**Fail:** Call Titan/Lua from the worker, treat cancellation as native
completion, release the argument early, or promise a dedicated background
thread.

## Source map

- Issue and maintainer corrections: GitHub issue `#82`, “Overhaul the Titan
  programmer skill and its reference docs.”
- Public Task/channel contract: `doc/language/async-io.md`.
- Public timer contract: `doc/language/standard-library-timer.md`.
- Public low-level coroutine contract: `doc/language/coroutines.md`.
- Public sources/signatures: `titan/async.titan`, `titan/timer.titan`, and
  `titan/coroutine.titan`.
- Runtime/Task and generic operation sources: `titan/async.titan`.
- Public callback binding: `titan/uv/` and `doc/language/standard-library-uv.md`.
- Private Runtime design: `doc/implementation/libuv-runtime.md`.
- Native extension recipes: `doc/implementation/libuv-extension-guide.md`.
- Coroutine mechanics: `doc/implementation/coroutines.md`.
- Watcher ownership example: `titan/fs.titan` and
  `doc/implementation/filesystem-library.md`.
- Native behavior evidence: `spec/stdlib/titan/async/`,
  `spec/stdlib/titan/timer/`, `spec/stdlib/titan/uv/task_tests/`,
  `spec/stdlib/titan/uv/runtime_tests.titan`, and
  `spec/stdlib/titan/coroutine/`.
