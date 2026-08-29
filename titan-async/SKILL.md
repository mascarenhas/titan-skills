---
name: titan-async
description: Write, review, and test Titan asynchronous code with async Tasks, timers, channels, cancellation, terminal listeners, fixed-arity combinators, and the cooperative libuv continuation runtime. Use when working on Titan async.run/loop, suspend/resume, Task status or cancellation, join/any/race/all, timer.sleep/Ticker, low-level coroutine interaction, or private titan.uv callback and ownership code.
---

# Titan async

Use this skill for Titan Task code, Task-aware standard-library code, and reviews
of the private libuv continuation layer. Titan is not Go, JavaScript, Lua with
annotations, or a preemptive threaded runtime. Read the project-local
`titan-programmer` skill first for general Titan syntax, types, options,
`defer`, `catch`, tests, and build commands; this cartridge supplies the async
mental model and current API in one place.

## Start with the one scheduling invariant

Titan async is **cooperative, single-loop continuation execution**:

- `async.Task` is implemented with `titan.coroutine` and a private tagged yield.
- Only top-level `async.loop()` or the generated standalone bootstrap calls
  `uv_run`, on the Lua main thread.
- A Task runs synchronously until it yields an async operation, returns, or
  raises. While that Titan continuation is running, libuv cannot invoke another
  callback and another Task cannot preempt it.
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
`async.suspend(token)`. Do not add locks, atomics, scheduler generations, callback
fences, ready queues, `uv_check_t`, `uv_idle_t`, polling passes, or snapshot
rollback to defend against imagined preemption.

This does **not** remove ownership rules across a real yield. Native work and
borrowed values must remain alive through the callback libuv promised, and a
multi-shot source needs exactly the buffering/waiter state promised by its
public semantics.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, `titan/uv/task.titan`, and issue #82.

## Import the public layer, not `uv`

Application Titan code normally uses:

```titan
local async = import "async"
local timer = import "timer"
```

The parser expands these to `titan.async` and `titan.timer`. Lua hosts use
`require "titan.async"` and `require "titan.timer"`.

**Public application modules:** `async`, `timer`, `fs`, `net`, `io`, `os`, and
the higher-level `ssl` and `http` modules.

**Public but low-level:** `coroutine`. It is a control-transfer primitive for
scheduler authors, not a scheduler and not the normal way to wait for I/O.

**Not public:** `titan.uv`/`import "uv"`, `Runtime`, `Call`, `UV_TAG`,
`run_internal`, `running_task`, `await`, `resume_task_from_callback`,
`resume_condition_waiter_from_callback`, `handle_roots`, `close_handle`, and
all raw libuv request/handle owner records. They are source-private
collaboration machinery. Do not use them in application examples or expose
them from a public API.

Evidence: `doc/language/async-io.md` and
`doc/implementation/libuv-runtime.md`.

## Exact public `async` surface

The facade exports constructor-preserving aliases. Although the alias
statements do not repeat binders, their owners remain generic and their public
constructors/methods remain available through `async`:

```text
type Error = uv.Error
type OperationError = uv.OperationError
type CancellationReason = uv.CancellationReason
type TaskStatus = uv.TaskStatus
type Task = uv.Task
type ResumeToken = uv.ResumeToken
type SuspendCancelAction = () -> ()
```

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

union CancellationReason<B>
  simple: string
  complex: B
end

union TaskStatus<A, B>
  ready
  running
  waiting
  succeeded: A
  failed: Error
  cancelled: CancellationReason<B>
end
```

`Task<A, B>` means success payload `A` and complex-cancellation payload `B`.
A bare `Task`, `TaskStatus`, or `CancellationReason` is exactly the all-`value`
application. There is no public `cancelling` status.

The exact Task/status methods are:

```text
function Task:cancel(reason: CancellationReason<B>?)
function Task:status(): TaskStatus<A, B>
function Task:add_terminal_listener(
    listener: (TaskStatus<A, B>) -> ()): () -> ()
function Task:resume(token: ResumeToken)

function TaskStatus:as_string(): string
function TaskStatus:has_finished(): boolean
function TaskStatus:has_succeeded(): (boolean, A?)
function TaskStatus:has_failed(): (boolean, Error?)
function TaskStatus:has_cancelled(): (boolean, CancellationReason<B>?)
```

The exact top-level scheduling API is:

```text
function run<A, B>(func: () -> A): Task<A, B>
function run_foreign(f: foreign (*void) -> (), arg: *void)
function loop()
function yield()
function running(): Task<value, value>
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
local task = async.run<string, value>(function (): string
  return "done"
end)
```

Do not write a partial `async.run<string>(...)`. `async.running()` deliberately
returns `Task<value, value>`, but it is a view of the same Task userdata and may
be compared with a precisely typed view. The Runtime stores success and complex
cancellation payloads through the all-`value` carrier; the exact `A`/`B` guard
occurs only when a typed view projects that payload. Identity comparison,
`status():as_string()`, and tag-only status inspection do not project it.
`async.version()` returns libuv's version string.

Evidence: `titan/async.titan`, `titan/uv/task.titan`, and
`doc/language/async-io.md`.

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
function any_two<A1, B1, A2, B2>(
    first: Task<A1, B1>, second: Task<A2, B2>):
    AnyTwoResult<A1, A2>
function any_three<A1, B1, A2, B2, A3, B3>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>):
    AnyThreeResult<A1, A2, A3>
function any_four<A1, B1, A2, B2, A3, B3, A4, B4>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>):
    AnyFourResult<A1, A2, A3, A4>
function any_five<A1, B1, A2, B2, A3, B3, A4, B4, A5, B5>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>,
    fifth: Task<A5, B5>):
    AnyFiveResult<A1, A2, A3, A4, A5>

function race_two<A1, B1, A2, B2>(
    first: Task<A1, B1>, second: Task<A2, B2>):
    RaceTwoResult<A1, B1, A2, B2>
function race_three<A1, B1, A2, B2, A3, B3>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>):
    RaceThreeResult<A1, B1, A2, B2, A3, B3>
function race_four<A1, B1, A2, B2, A3, B3, A4, B4>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>):
    RaceFourResult<A1, B1, A2, B2, A3, B3, A4, B4>
function race_five<A1, B1, A2, B2, A3, B3, A4, B4, A5, B5>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>,
    fifth: Task<A5, B5>):
    RaceFiveResult<A1, B1, A2, B2, A3, B3, A4, B4, A5, B5>

function all_two<A1, B1, A2, B2>(
    first: Task<A1, B1>, second: Task<A2, B2>): (A1, A2)
function all_three<A1, B1, A2, B2, A3, B3>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>): (A1, A2, A3)
function all_four<A1, B1, A2, B2, A3, B3, A4, B4>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>):
    (A1, A2, A3, A4)
function all_five<A1, B1, A2, B2, A3, B3, A4, B4, A5, B5>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>,
    fifth: Task<A5, B5>): (A1, A2, A3, A4, A5)

function join<A, B>(task: Task<A, B>): TaskStatus<A, B>
function join_two<A1, B1, A2, B2>(
    first: Task<A1, B1>, second: Task<A2, B2>):
    (TaskStatus<A1, B1>, TaskStatus<A2, B2>)
function join_three<A1, B1, A2, B2, A3, B3>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>):
    (TaskStatus<A1, B1>, TaskStatus<A2, B2>, TaskStatus<A3, B3>)
function join_four<A1, B1, A2, B2, A3, B3, A4, B4>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>):
    (TaskStatus<A1, B1>, TaskStatus<A2, B2>,
     TaskStatus<A3, B3>, TaskStatus<A4, B4>)
function join_five<A1, B1, A2, B2, A3, B3, A4, B4, A5, B5>(
    first: Task<A1, B1>, second: Task<A2, B2>,
    third: Task<A3, B3>, fourth: Task<A4, B4>,
    fifth: Task<A5, B5>):
    (TaskStatus<A1, B1>, TaskStatus<A2, B2>,
     TaskStatus<A3, B3>, TaskStatus<A4, B4>, TaskStatus<A5, B5>)
```

The exact result/error owners follow one positional pattern:

| Family | Owners | Variants |
| --- | --- | --- |
| `any_*` | `AnyTwoResult<A1,A2>` through `AnyFiveResult<A1,...,A5>` | `first: A1`, `second: A2`, then `third`, `fourth`, `fifth` as applicable, plus payload-free `none` |
| `race_*` | `RaceTwoResult<A1,B1,A2,B2>` through `RaceFiveResult<...>` | positional variants carrying the corresponding `TaskStatus<Ai,Bi>`; no `none` |
| `all_*` errors | `AllTwoError<A1,B1,A2,B2>` through `AllFiveError<...>` | positional variants carrying the corresponding `TaskStatus<Ai,Bi>`; no success variant |

Only `join` has a unary form. There is intentionally no unary `any`, `race`,
or `all`, and no variadic or Array-taking form.

Evidence: `titan/async.titan` and `doc/language/async-io.md`.

### Exact channel surface

Channels are public Task-to-Task coordination built entirely on `running` and
private token-bearing `suspend`/`resume`, not native Runtime queues:

```text
function channel<T>(size: integer?):
    ((T) -> (), () -> T, () -> ())

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
  local worker = async.run<string, value>(function (): string
    timer.sleep(25)
    return "done"
  end)

  case async.join(worker)
  when succeeded: result then
    if result == "done" then return 0 else return 2 end
  when failed then
    return 1
  when cancelled then
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
Task. A new Task initially reports `ready`; its zero-duration start timer closes
before the Task starts on a callback-deferred turn. Do not assume a child has
initialized shared state immediately after `run`.

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
terminal states are `succeeded`, `failed`, and `cancelled`.

Prefer a `case` when the payload matters:

```text
local terminal = async.join(task)
case terminal
when succeeded: result then
  use_result(result)
when failed: failure then
  report(failure.error, failure.traceback)
when cancelled: reason then
  case reason
  when simple: message then report_cancel(message)
  when complex: payload then report_protocol_cancel(payload)
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

If a value escapes a Task, terminal state is `failed(Error.new(value,
traceback))`. `async.OperationError` remains the exact `error` value inside the
wrapper. The Runtime reports the uncaught failure and traceback immediately;
later `join`, `race`, or `all` observation does not suppress that report.
Other Tasks continue.

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
   callback-deferred target-owned zero timer; cancellation never runs one Task
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

local task = async.run<boolean, Shutdown>(function (): boolean
  timer.sleep(60000)
  return true
end)

task:cancel(async.CancellationReason<Shutdown>.complex(Shutdown.new(42)))
local terminal = async.join(task)
case terminal
when cancelled: reason then
  case reason
  when complex: detail then
    handle_shutdown(detail.code)
  when simple: message then
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
local reading = async.run<string?, value>(function (): string?
  return connection:read()
end)
local deadline = async.run<nil, value>(function (): nil
  timer.sleep(5000)
  return nil
end)

case async.any_two(reading, deadline)
when first: data then
  -- Deadline owns only its timer. Request cancellation; no parser teardown
  -- waits on it.
  deadline:cancel(async.CancellationReason.simple("read completed"))
  consume(data)
when second then
  -- Reading owns connection/parser activity. Retire it before teardown.
  reading:cancel(async.CancellationReason.simple("read timed out"))
  async.join(reading)
  teardown_read_state()
when none then
  local read_status, deadline_status = async.join_two(reading, deadline)
  report_both(read_status, deadline_status)
end
```

Do not turn this asymmetry into a blanket “always join every loser” or “never
join deadlines” rule. Trace the resource ownership of the particular operation.
The production HTTP timeout follows this exact asymmetry.

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
- installs one target-owned zero timer;
- coalesces repeated requests before delivery; and
- guarantees deferred delivery, but not an exact number of libuv iterations.

At delivery, the private completion clears `suspended`, `resume_token`, and
`resume_pending` **before** `advance_task` re-enters user code. The resumed
continuation must never observe or inherit the completed suspension's token or
wake bit.

Keep tokens private to the coordination abstraction. Share one record among all
paths that own a single condition (for example one per channel), or create one
fresh record per combinator invocation. Do not use a token as a general native-
wait capability: operation and persistent-source callbacks keep their private,
tokenless continuation helpers.

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
  return Gate.new(false, nil, async.ResumeToken.new("Gate.wait"))
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
native operations resume through their source-private tokenless callback path.

Evidence: `doc/language/async-io.md`,
`doc/implementation/libuv-runtime.md`, `titan/async.titan`, and
`spec/stdlib/titan/uv/task_tests/continuations_test.titan`.

## Terminal listeners are synchronous observation, not Tasks

```text
function Task:add_terminal_listener(
    listener: (TaskStatus<A, B>) -> ()): () -> ()
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
when first: status then
  case status
  when succeeded: value then consume_first(value)
  when failed: failure then report(failure.error, failure.traceback)
  when cancelled: reason then report_cancel(reason)
  else raise "race produced a live status"
  end
when second: status then
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
    when first: status then report_first(status)
    when second: status then report_second(status)
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
Privately, `ticker_callback` publishes its fired state and uses tokenless
`resume_task_from_callback` for an installed waiter. `ResumeToken` remains
exclusive to explicit `suspend`/`Task:resume(token)` coordination.

Evidence: `titan/timer.titan`,
`doc/language/standard-library-timer.md`, and
`spec/stdlib/titan/timer/tests.titan`.

## Bounded channels

`async.channel<T>(size?)` defaults to capacity 1; an explicit size must be at
least 1. It is a FIFO bounded circular buffer and can carry nil when `T` admits
nil. State `T` explicitly or supply an expected callback triple; a bare
unconstrained `channel()` closes to `value`.

```text
local send, receive, close = async.channel<string>(2)
defer close()

local producer = async.run<nil, value>(function (): nil
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

`reader_writer_channel` wraps `channel<string>` in opaque Reader/Writer
facades. `read_until` is binary-safe across message boundaries; an empty
delimiter raises. Reader close discards its own saved suffix and returns nil for
new reads. Writer close preserves a suffix already transferred to the Reader,
but the next underlying channel receive observes close.

Evidence: `doc/language/async-io.md`, `titan/async.titan`, and
`spec/stdlib/titan/async/tests/channel_test.titan`.

## [PRIVATE IMPLEMENTATION] Native callback and ownership rules

The rest of this section applies only when maintaining standard-library source
that directly collaborates with `titan.uv`. None of the named helpers or
records is public application API.

### Classify before adding state

| Native shape | Private continuation shape | Owner |
| --- | --- | --- |
| synchronous call, no retained callback | no `Call` variant | automatic/local state unless the contract retains a pointer |
| one-shot request that suspends a Task | one submission `Call` variant | one request owner, normally rooted by the Task's private `pending` field |
| one-shot callback on a new handle | usually one submission variant plus close | one rooted handle owner transferred through `uv_close` |
| explicit worker-pool call | one `run_foreign` variant | one request owner retaining raw carrier and completion callback until after-work |
| persistent multi-shot source | wait/consume and close variants | one rooted handle owner with natural buffered/terminal state and at most one waiter |

Do not rebuild a control hierarchy, operation registry, event-kind dispatcher,
scheduler queue, Task generation, or generic native waiter around a direct
libuv contract.

The source-private path is:

```text
public async/fs/net/os/timer/io method
  -> private titan.uv convenience function
  -> await(Call.variant(payload)) only when the Task must suspend
  -> payload:dispatch(Task)
  -> direct uv_* submission
  -> exact source-defined foreign callback
  -> exact ordinary Titan callback handler
  -> publish/buffer result or resume the exact continuation
```

Use the existing direct owner/helper. Do not add a facade alias or forwarding
C wrapper around a public `uv_*` function.

Evidence: `doc/implementation/libuv-extension-guide.md`.

### One-shot ownership

- Allocate the smallest record containing stable owned request storage and one
  exact callback closure. Let that closure capture the Task and values libuv
  still borrows; do not duplicate captures in “rooted” aliases.
- Set request data and the Task's private `pending` owner before libuv can accept
  the request.
- A documented negative submission result means no callback will arrive: clear
  the request root, run request-specific cleanup, and return an immediate error.
  Do not recursively resume the Task and do not call `uv_run`.
- An accepted submission returns from dispatch immediately. Its callback is now
  authoritative.
- In the callback, copy borrowed result memory, extract scalars, call required
  request cleanup exactly once, release libuv-owned results, and dispose of an
  abandoned produced resource **before** resuming user code.
- Then ordinary operation callbacks use source-private
  `resume_task_from_callback(task, failed, payload)`. This is not
  `Task:resume(token)`; the latter is only for the explicit `suspend` that
  stored that exact token. Native callback continuation remains token-free.
- Catch callback conversion/continuation errors at the boundary so only that
  Task retires and the foreign callback returns normally to libuv.
- Cancellation never releases accepted request storage early and does not add
  a fictitious `uv_cancel` path.

Evidence: `doc/implementation/libuv-extension-guide.md` and
`titan/uv/file.titan`/`titan/uv/tcp.titan`.

### Foreign worker ownership

`Call.run_foreign` carries `WorkCall`, whose `owned WorkPointer[]` carrier has
three slots: after-work owner, erased `WorkFunction`, and argument. Dispatch
allocates an owned `uv_work_t`; `WorkOwner` retains that request, the carrier,
and its ordinary loop-thread completion closure, and `Task.pending` roots the
complete owner before `uv_queue_work` can accept it.

The source `uv_work_cb` is intentionally unlike ordinary callbacks. It runs on
a worker thread, reads only the function and argument carrier slots, and calls
`f(arg)`. It must never recover the after-work owner or enter any Titan/Lua
helper. The source `uv_after_work_cb` runs on the loop thread, recovers the
owner, and invokes the protected `complete_work` path. Only submission status
zero is accepted; a nonzero status is the no-callback case and clears the
pending root synchronously. An
accepted submission is never cancelled with `uv_cancel`; the after-work
callback owns terminal release even if Task cancellation is pending.

Evidence: `titan/uv/work.titan`, `doc/implementation/libuv-runtime.md`, and
`doc/implementation/libuv-extension-guide.md`.

### Persistent handle ownership

- The owner is the complete callback owner: stable native handle, exact callback
  closures, Runtime/root slot, at most one waiter, and only the buffered or
  terminal state promised by the API. `Runtime.handle_roots` roots this complete
  record, not merely raw native storage.
- Root before successful `uv_*_init` can link the handle into the loop. On
  verified init rejection, unroot; after successful init, even a later start
  rejection must asynchronously close.
- A callback copies/publishes its natural result and clears/takes its waiter
  before delivery. An ordinary completed native operation uses the private
  callback-resume path. A source-private condition callback first publishes the
  condition and may use `resume_condition_waiter_from_callback`; if a correct-
  token public explicit-resume timer is already pending, that timer remains the
  sole continuation. The callback helper itself remains tokenless.
- With no waiter, store only the public-semantics state: one fired bit/latest
  value when coalescing is promised, a dense buffer when every value is
  promised, or sticky EOF/error for a terminal stream.
- Cancelling a wait detaches only that waiter and wakes that Task on its own
  deferred path; it does not close a shared handle.
- Explicit close stops where required, clears discarded buffered state, settles
  a waiter on a callback turn, and transfers lifetime to the shared close path.
  Do not add a close-waiter queue.
- `uv_is_closing` is authoritative. Never mirror it with another close flag or
  call `uv_close` twice. `uv_walk`, not `handle_roots`, discovers final live
  handles. The root Array is never traversed as a resource registry.

Evidence: `doc/implementation/libuv-extension-guide.md`,
`doc/implementation/libuv-runtime.md`, and `titan/uv/runtime.titan`.

### Callback production must stay small

A raw loop-thread native callback copies or converts data that is valid only
during the callback, publishes one natural event/result, wakes its exact
continuation, and returns. It must not do synchronous filesystem work or other
potentially blocking classification. The `run_foreign` worker callback is the
separate C-only exception described above; it cannot publish or resume at all.

The current filesystem watcher is the model:

1. `fs_watcher_event_cb` recovers the complete `WatchRegistration` owner.
2. Its Titan handler copies nullable filename bytes and appends exactly one raw
   `WatcherNotification`.
3. It wakes the poller through the tokenless condition-callback helper and
   returns. Each blocking poll's fresh private `"fs.watcher"` token belongs
   only to that one explicit suspension and its facade-owned wake path. The
   callback-buffered notification or last-registration removal establishes the
   postcondition before delivery, so the poll does not defensively resuspend.
4. When the Task drains notifications, it asynchronously calls `lstat`, maps
   each raw notification to exactly one public event, and closes a retired
   registration as needed.
5. Because classification can yield, callbacks append to a fresh Array. If a
   mapped event retires a registration and the fresh Array contains that
   retired owner, the drain takes the complete fresh batch in callback order
   and repeats. A live-owner-only fresh batch remains buffered for the next
   `poll`.

There is no alias index, Runtime generation, raw-batch rollback, or duplicate
close state. Stop removes registration ownership; close then retires the native
handle. Taking a complete follow-on batch preserves cross-registration order;
it does not filter, merge, discard, or duplicate notifications. An
`OperationError` in one mapping becomes one error event rather than rolling
back the batch.

The same split applies to `fs.realpath`: each call creates a fresh private
`"fs.realpath"` token and suspends exactly once. The suspension's cancellation
closure retains that token, while the accepted request's sole callback
publishes completion through the tokenless callback helper.

Evidence: `titan/fs.titan` and `doc/implementation/filesystem-library.md`.

### Do not invent defensive epicycles

Reject these unless a documented public/native contract requires them:

- reentrant `async.loop`/`uv_run`;
- a scheduler ready queue, Runtime join protocol, Task polling loop, phase
  bridge, or generic public Waiter;
- generation counters or operation IDs meant only to defend against a callback
  resuming the wrong continuation;
- a parallel handle registry or traversal of `handle_roots`;
- a second active-Task counter beside `task_roots`;
- close flags that duplicate `uv_is_closing`;
- Task-side queues duplicating libuv's accepted write order;
- a common control wrapper around operation-specific owners;
- a callback event-kind parameter when an exact callback protocol suffices;
- a finalizer racing an outstanding native request;
- synchronous filesystem classification inside a libuv callback;
- source-transformer/fault hooks that rebuild a production provider merely to
  repeat an already-owned generic lifetime proof.

When the public contract really does promise every distinct event, buffer those
events directly. When it promises coalescing, use one bit/latest value. When a
new native API has an unusual partial-init or borrowing rule, verify that exact
pinned libuv contract instead of generalizing another operation's workaround.

## Raw Titan coroutines are a separate low-level API

The exact public `coroutine` surface is:

```text
record Coro
end

function create(func: (value) -> value, default_tag: value): Coro
function Coro:resume(arg: value, tag: value): value
function Coro:error(err: value, tag: value): value
function Coro:status(): string
function yield(arg: value, tag: value): value
function is_yieldable(tag: value): boolean
```

`Coro` fields and constructor are **not public**; use `coroutine.create`.
Ordinary fixed-call adjustment makes the second argument to `create`, `resume`,
and `error` omittable by nil-fill. Nil means “no explicit tag”; resume/error then
use the stored default, and raise if neither is nonnil. `coroutine.yield` and
`is_yieldable` require an explicit nonnil tag and do not use a default.

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
obtain or yield Titan async's private `UV_TAG`. Tagged nesting lets the Runtime's
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
    local resume_token = async.ResumeToken.new("resume test")
    local target = async.run<nil, value>(function (): nil
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

- It imports public `async`/`timer`/high-level modules, not `uv`.
- It assumes cooperative execution, not preemption, and explicitly yields a
  CPU-heavy loop.
- It does not call `async.loop` from a Task or callback.
- It remembers that `async.run` never starts inline and that standalone `main`
  is already bootstrapped.
- If it uses `run_foreign`, the function is C-only, every native argument owner
  survives completion, shared bytes are synchronized, and pool starvation is
  an accepted/documented tradeoff.
- It uses precise `Task<A,B>` types and supplies both explicit type arguments or
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

Before accepting private libuv code, also verify:

- The native operation is classified as synchronous, one-shot, or persistent.
- A complete callback owner is rooted for exactly the native lifetime.
- Every borrowed argument/result interval and exactly-once cleanup is explicit.
- Rejection and accepted-callback paths follow the pinned native contract.
- The callback copies/releases before resuming, catches before returning to C,
  and never calls `uv_run`.
- An ordinary completion uses the private callback continuation helper;
  it remains tokenless, while `Task:resume(token)` is reserved for the matching
  explicit suspension.
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
scheduling the coalesced target-owned zero timer; it never enters target inline.
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

**Prompt:** Add a source-private libuv request whose callback returns a borrowed
buffer.

**Pass:** One exact request owner; root before accepted submission; distinguish
negative/no-callback from accepted/callback; copy the borrowed result and clean
native storage exactly once before private `resume_task_from_callback`; retain
accepted ownership through cancellation; return normally to libuv.

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

**Fail:** Call Lua's coroutine API, invent a public `UV_TAG`, or claim raw
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
- Private Runtime/Task sources: `titan/uv/runtime.titan`,
  `titan/uv/task.titan`, `titan/uv/work.titan`, and the other
  `titan/uv/*.titan` contributors.
- Private Runtime design: `doc/implementation/libuv-runtime.md`.
- Native extension recipes: `doc/implementation/libuv-extension-guide.md`.
- Coroutine mechanics: `doc/implementation/coroutines.md`.
- Watcher ownership example: `titan/fs.titan` and
  `doc/implementation/filesystem-library.md`.
- Native behavior evidence: `spec/stdlib/titan/async/`,
  `spec/stdlib/titan/timer/`, `spec/stdlib/titan/uv/task_tests/`,
  `spec/stdlib/titan/uv/runtime_tests.titan`, and
  `spec/stdlib/titan/coroutine/`.
