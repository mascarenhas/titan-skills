---
name: titan-thread
description: Write, review, and test multi-threaded Titan code with titan.thread OS threads, bounded cross-thread MPMC channels, and structured thread groups. Use when spawning isolated OS threads with their own Lua/Titan state and async Runtime, sending/receiving values or nested channel endpoints across threads, composing Thread:task() with async combinators, or managing bounded concurrency and error propagation with thread.Group.
---

# Titan thread

Use this skill alongside [`titan-programmer`](../titan-programmer/SKILL.md),
[`titan-async`](../titan-async/SKILL.md), and
[`titan-tester`](../titan-tester/SKILL.md) when working with `titan.thread`
(`import "thread"` in Titan, `require "titan.thread"` in Lua).

## Core mental model

Each spawned Titan thread owns:
1. **A dedicated OS thread** (`uv_thread_t`, separate from libuv's fixed
   `uv_queue_work` pool).
2. **An isolated Lua 5.5 / Titan state** (`lua_State *`) with its own garbage
   collector and preloaded native module snapshot. No Lua or Titan GC objects
   are ever shared across threads.
3. **Its own `titan.async` Runtime and `uv_loop_t`**, allowing the child thread
   to spawn local `async.Task`s, timers, and non-blocking I/O.

Cross-thread communication uses **value transfer** (`titan.transfer` /
`titan.protobuf`) and **shareable channel endpoints (`Sender<|T|>` and
`Receiver<|T|>`)**:
- Scalars, strings, public records/unions, Titan closures (whose captures are
  transferable), and records implementing `to_transfer_payload` /
  `from_transfer_payload` cross thread boundaries safely.
- Passing a `Sender<|T|>` or `Receiver<|T|>` to a spawned thread or through
  another channel **retains a new endpoint reference at serialization time**
  and adopts it in the destination state without closing the caller's endpoint,
  enabling MPMC fan-out and fan-in naturally. `Sender` and `Receiver` transfer
  hooks are gated to `titan.thread` message transfer (`Sender:send`,
  `Sender:try_send`, `thread.spawn*`, and `Group:spawn*`); calling
  `protobuf.serialize`, `transfer.TransferValue.from_value`, or
  `to_transfer_payload` / `from_transfer_payload` directly raises
  `"thread endpoints can only be transferred through thread channels or spawn arguments"`.
- Public records and unions may embed `Sender<|T|>` or `Receiver<|T|>` fields
  (such as a reply channel inside a request record) and cross channels or
  `spawn_*` arguments automatically.

Choose the right primitive for the job:
- **`async.channel<|T|>`** — single-state, in-memory cooperative Task queue (no
  serialization, same `lua_State`).
- **`async.Receiver<|T|>`** — lossy, coalescing cross-state notification
  mailbox (latest value wins).
- **`thread.channel<|T|>`** — lossless, bounded FIFO cross-thread MPMC stream
  with backpressure, graceful close/drain, and transferable `Sender<|T|>` /
  `Receiver<|T|>` endpoints.

## Worked example

This function drives `async.loop()` itself. Call it from a Lua host outside a
Task, or compile a standalone caller with `--no-uv-bootstrap`.

```titan
local async = import "async"
local thread = import "thread"

record WorkRequest
  const value: integer
  const reply: thread.Sender<|integer|>
end

function compute_squares(): integer
  local result = 0
  async.run<|nil, value|>(function (): nil
    local req_tx, req_rx = thread.channel<|WorkRequest|>(4)
    local rep_tx, rep_rx = thread.channel<|integer|>(4)

    local pool = thread.group(2, true)
    for _ = 1, 2 do
      pool:spawn_one(function (rx: thread.Receiver<|WorkRequest|>)
        for _, job in rx:incoming() do
          job.reply:send(job.value * job.value)
        end
      end, req_rx)
    end
    for i = 1, 4 do
      req_tx:send(WorkRequest(i, rep_tx))
    end
    req_tx:close()

    local errs = pool:wait()
    if #errs > 0 then
      errs[1]:raise()
    end
    rep_tx:close()
    for _, square in rep_rx:incoming() do
      result = result + square
    end
    return nil
  end)
  async.loop()
  return result
end
```

## Public surface overview

See [`doc/language/standard-library-thread.md`](../../../doc/language/standard-library-thread.md)
for the complete signature table. The main entry points are:

- **Channels**: `thread.channel<|T|>(capacity?) -> (Sender<|T|>, Receiver<|T|>)`,
  `Sender:send`, `Sender:try_send`, `Sender:close`, `Sender:is_closed`,
  `Sender:clone`, `Receiver:receive`, `Receiver:receive_result`,
  `Receiver:try_receive`, `Receiver:incoming`, `Receiver:close`,
  `Receiver:is_closed`, `Receiver:clone`, and `ReceiveResult<|T|>`.
- **Standalone threads**: `thread.spawn` through `thread.spawn_five`,
  `Thread:status`, `Thread:join`, `Thread:cancel`, `Thread:task`,
  `ThreadStatus<|R|>`, and `Error` (`Error:raise()`).
- **Thread groups**: `thread.group(limit?, propagate_errors?) -> Group`,
  `Group:spawn` through `Group:spawn_three`, `Group:cancel`, and `Group:wait`.

## Spawning threads and observing outcomes

- `thread.spawn`..`thread.spawn_five` snapshot `entry` and all arguments
  synchronously on the caller thread before starting the OS thread. Any
  non-transferable capture or argument raises immediately in the caller.
- **`Thread:join(): ThreadStatus<|R|>`** suspends the calling `async.Task`
  until the thread finishes and returns `ThreadStatus<|R|>` (`succeeded(R)`,
  `failed(Error)`, or `cancelled(CancellationReason)`) **without raising**.
- **`Thread:task(): async.Task<|R, value|>`** returns a host-state `async.Task`
  proxy that resolves to `R` on success, rethrows the child's error with its
  traceback via `Error:raise()` on failure, or cancels if the thread cancelled.
  Use `Thread:task()` with `async.all_two`..`all_five`,
  `async.race_two`..`race_five`, `async.any_two`..`any_five`, or `async.join`.
- **`Thread:cancel(reason?)`** signals the child thread's loop to cancel its
  root Task cooperatively (`defer` and `await_cleanup` handlers run normally).
- Unobserved standalone threads that fail with an uncaught error report the
  error and traceback to `stderr` when the last `Thread` control reference
  drops. Joining, inspecting terminal status, calling `Thread:task()`, or
  spawning inside a `Group` marks the thread outcome as observed.

## Channels (`Sender<|T|>` and `Receiver<|T|>`)

- `thread.channel<|T|>(capacity)` creates a bounded FIFO channel with default
  `capacity = 1` (`capacity < 1` raises `"channel capacity must be positive"`).
- **`Sender:send(msg)`** serializes `msg` outside the channel lock; if buffer
  space is available it enqueues immediately without suspending, and if full it
  suspends the current `async.Task` until a receiver dequeues or closes.
- **`Sender:try_send(msg): boolean`** returns `true` when enqueued immediately,
  `false` when full, and raises `"channel is closed"` when closed.
- **`Sender:close()`** marks the shared channel closed for all clones while
  **preserving buffered messages** so receivers can drain remaining items
  before observing closure.
- **`Receiver:receive(): T`** returns the next message, suspending when empty,
  and raises `"channel is closed"` once closed and drained.
- **`Receiver:receive_result(): ReceiveResult<|T|>`** returns
  `ReceiveResult.message(val)` or `ReceiveResult.closed()` without raising on
  normal EOF.
- **`Receiver:try_receive(): (boolean, T?)`** returns `(true, val)` if a
  message is immediately available, or `(false, nil)` if empty or closed and
  drained.
- **`Receiver:incoming()`** returns a generic-`for` iterator triple
  (`for _, msg? in rx:incoming() do ... end`) that yields `(true, message)`
  until the channel is closed and drained, then `(nil, nil)`. The first result
  is a continuation marker, so nil and false messages remain data. Use `msg?`
  when nil is allowed; an ordinary binding intentionally forces non-nil.
- **`Receiver:close()`** closes the channel from the consumer side, discards
  any unread buffered messages, and wakes blocked senders with
  `"channel is closed"`.

## Structured thread groups (`thread.Group`)

- `thread.group(limit, propagate_errors)` creates a group with optional
  concurrency cap `limit` (`limit < 1` raises `"group limit must be positive"`)
  and optional `propagate_errors` (defaults to `false`).
- When `limit` is reached, `Group:spawn*` suspends the calling `async.Task` in
  a FIFO admission queue until a running thread finishes or the group aborts.
- When `propagate_errors` is `true`, the first uncaught thread error cancels
  all currently running group threads and causes queued/subsequent
  `Group:spawn*` calls to become no-ops.
- **`Group:wait(): {Error}`** suspends until all active threads and queued
  admissions finish, returning all uncaught `Error` records in completion
  order.

## Pitfalls

- **Top-level `Array` and `Map` values are not directly transferable**: wrap an
  `Array` in a public `record` or `union` before sending it over a channel,
  capturing it in a thread closure, or returning it from `thread.spawn`.
- **`Sender:close()` vs dropping a clone**: calling `tx:close()` closes the
  shared channel immediately for all `Sender` clones. When fanning out work
  across multiple producer threads, either let `Group:wait()` finish before
  calling `tx:close()` on the coordinator, or drop the parent's `Sender`
  reference so the channel auto-closes only when the last producer's `Sender`
  is collected.
- **Endpoints only transfer through `titan.thread` operations**: do not pass a
  `Sender` or `Receiver` (or a record containing one) to `protobuf.serialize`
  or `transfer.TransferValue.from_value` directly; endpoint transfer hooks are
  only active during `Sender:send`, `Sender:try_send`, `thread.spawn*`, and
  `Group:spawn*`.
- **Native resource moves need explicit ownership**: sending an Exchange,
  WebSocket or other native owner directly through a generic thread channel is
  not a deterministic cleanup alternative to a raw payload. Channel discard
  cleans endpoint references; it does not run arbitrary native-resource disposal
  after failed enqueue or receiver teardown. Use an explicit manually owned
  payload protocol. Recover or discard rejected delivery; stop producers and
  drain/dispose queued payloads before `Receiver:close()` discards their bytes.
  Follow the [networking handoff contract](../titan-networking/SKILL.md#native-connection-and-http-handoff)
  and [WebSocket disposal guidance](../titan-websocket/SKILL.md#transferring-native-sessions).
- **`Thread:cancel` targets the child's root `Task`**: if a worker thread
  spawns background child tasks via `async.run`, use a `defer` in the worker's
  root `Task` to cancel and join those child tasks when the root `Task` unwinds.

## Testing

- Wrap asynchronous `thread` tests in `runtime_test.run(function () ... end)`
  (`import "support.runtime.titan"`; see
  [`titan-tester`](../titan-tester/SKILL.md)). Always join spawned `Thread`s
  (`th:join()` or `async.join(th:task())`) and wait on `Group`s (`g:wait()`)
  before a test returns so detached worker threads do not outlive the test case.
- When spawning helper `async.Task`s in a test (such as producer/consumer tasks
  driving a `thread.channel`), register them immediately with
  `task_support.cleanup_task(task, "...")` from `support.async.titan` so
  assertion failures cancel and clean up suspended tasks cleanly.
- Because `async.run` defers initial execution, use `async.yield()` in a loop
  until `task:status():as_string() == "waiting"` before asserting that a task is
  parked on a channel or group slot.

## References

- Language manual:
  [`doc/language/standard-library-thread.md`](../../../doc/language/standard-library-thread.md)
- Implementation manual:
  [`doc/implementation/thread-library.md`](../../../doc/implementation/thread-library.md)
