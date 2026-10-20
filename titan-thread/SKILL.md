---
name: titan-thread
description: Write, review, and test multi-threaded Titan code with titan.thread OS threads, bounded cross-thread MPMC channels, structured thread groups, and packet-scoped endpoint transfer (titan.transfer). Use when spawning isolated OS threads with their own Lua/Titan state and async Runtime, sending/receiving values or nested Sender/Receiver endpoints across thread channels or async.Receiver, composing Thread:task() with async combinators, or managing bounded concurrency and error propagation with thread.Group.
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
- Passing a `Sender<|T|>` or `Receiver<|T|>` (at the root, nested in public
  records/unions or their Array fields, inside opaque `to_transfer_payload`
  hooks, or captured in a Titan closure) **retains a new endpoint reference per
  occurrence** in the active packet's native resource table and serializes a
  4-byte little-endian packet-local slot index (`0xffffffff` is reserved
  invalid). Root, nested structural, and `TransferValue.from_value` /
  `:to_value()` policy conversions (including closure captures) dispatch through
  the registered `ResourceCodec` capability (`transfer.register_resource` /
  `protobuf.register_resource_codec`, keyed by canonical erased metatable
  identity) before reflective hook lookup. The direct userdata route in
  `from_value` requires a metatable with no metatable of its own; `:to_value`
  resolves the capability by initialized nominal name. Custom user hooks can
  still call `to_transfer_payload` / `from_transfer_payload`
  (`transfer.attach_resource` / `transfer.claim_resource`). Both reconstruction
  paths allocate the destination wrapper with `native = nil` and register its GC finalizer *before*
  claiming the slot and assigning the native pointer without further allocation
  or yielding.
- Each endpoint reference unit is owned by **exactly one** of: a live finalized
  wrapper, or an unconsumed in-flight native message entry. Adopting an entry
  into a pre-finalized wrapper moves that unit; discarding an unconsumed packet
  entry releases it natively; calling `close()` changes channel state only and
  never decrements endpoint counts. Message bytes, wake targets, loop liveness,
  and OS-thread retirement have separate lifetimes.
- Endpoint hooks require an active packet encode/decode scope
  (`transfer.encode_message` / `transfer.decode_message`, used by `Sender:send`,
  `Sender:try_send`, `thread.spawn*`, `Group:spawn*`, `Thread:cancel`, child
  outcomes, and `async.send` / `async.Receiver:wait`). `TransferValue` and
  protobuf helpers never manufacture a scope: endpoint hooks raise without a
  matching top encode or decode scope. Opaque-hook and capture collaboration
  within an existing packet may reuse its scope, but resulting index bytes do
  not become a reusable ownership policy. Independent `lua.Lua:run*` carriers
  have no packet attachment transport.
  Authority belongs only to the exact top scope, in the matching direction,
  for the current Lua-thread/coroutine execution. `ResourceScope` frames are
  acquired from and retired to a bounded state-local pool (independent of
  Task/coroutine identity so Task-per-message callers reuse retired frames),
   while `execution` and the enclosing `previous` frame stay in lexical locals
  and `resource_scopes[execution]` so idle pooled frames hold no authority or
  thread references and abandoned active frames are never pooled (their GC
  finalizer reclaims unfinished scratch units and decode packets natively).
  A state-wide installed-frame count lets lookups answer "no scope" without
  resolving the execution when it is zero; each entry point counts before
  registering its retiring `defer`, so the count can only over-estimate (an
  abandoned frame keeps it positive). Treat it purely as a fast negative: a
  positive count never authorizes anything, and the exact-top lookup still runs.
  Structural record/union and closure envelope codecs receive the packet's
  already-resolved `ResourceScope` (`serialize_inspected_*_to_buffer`,
  `deserialize_nominal_buffer_with_context`,
  `serialize_fields_to_buffer_with_context`, and
  `deserialize_fields_buffer_with_context`), and explicit nominal policies and
  opaque custom-hook roots allocate their single heap packet directly
  (`new_nominal_message`, with committed attachments stored in the aligned
  packet tail). Nested packet operations restore the enclosing scope on
  return/error; no older matching scope is searched. Another Task or child
  Coroutine inherits no permission. Custom `to_transfer_payload` and
  `from_transfer_payload` hooks remain synchronous and **must not yield**;
  execution isolation is not permission to broaden that hook contract.
- Claim validation checks exact 4-byte index width, active packet bounds,
  expected release callback (`Sender` cannot claim a `Receiver` slot or vice
  versa), and unclaimed state before touching any native pointer; a claimed
  entry clears its resource pointer to `nil` as the consumed sentinel while
  retaining its release callback so claiming an already-consumed slot with the
  wrong resource kind still raises `"transfer: resource attachment kind mismatch"`
  before `"transfer: resource attachment was already claimed"`. Index bytes are
  not global anti-replay tokens: the same number can identify a different valid
  entry in another packet. They cannot select an arbitrary native pointer or
  adopt one current entry twice.

Choose the right primitive for the job:
- **`async.channel<|T|>`** — single-state, in-memory cooperative Task queue (no
  serialization, same `lua_State`).
- **`async.Receiver`** — lossy, coalescing cross-state latest-value slot that
  encodes transferable values (including `Sender<|T|>` / `Receiver<|T|>`
  attachments) or explicit `async.TransferValue` policies into native packets,
  decodes eagerly in `wait()`, and disposes overwritten/unread packets natively.
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
  until the thread reaches logical finish and its OS thread is actually joined,
  then returns `ThreadStatus<|R|>` (`succeeded(R)`, `failed(Error)`, or
  `cancelled(CancellationReason)`) without raising the thread's own outcome. A
  native join failure instead raises `async.OperationError` with operation
  `thread.join` and keeps the token for a later retry.
- **`Thread:task(): async.Task<|R, value|>`** returns a memoized host-state
  proxy resolving to `R`, rethrowing the child's saved error/traceback via
  `Error:raise()`, or reflecting child cancellation. Compose it with
  `async.all_two`..`all_five`, `async.race_two`..`race_five`,
  `async.any_two`..`async.any_five`, or `async.join`. Requesting cancellation of
  an observer before its proxy is terminal is not proof that the OS thread has
  finished; retain shared native owners through actual child completion.
- **Proxy retirement is native and prearmed**: `Thread:task()` memoizes one
  `async.run_with_cleanup` proxy whose third argument is
  `async.prepare_native_retirement(...)` over the worker control block, so the
  barrier is armed before the proxy is exposed and does not depend on a cleanup
  callback being reached. The body awaits logical finish only and never calls
  `Thread:join()`; only the prearmed barrier attempts the proxy's OS join.
  Cleanup forwards the first reason with `Thread:cancel(reason)` while
  `finished` is false; when the proxy body failed without a cancellation the
  cleanup reason is nil, so `Thread:cancel(nil)` supplies the default
  `simple("cancelled")`. It then waits the shield barrier (`wait_cleanup`) and
  closes the view in LIFO defer order. Terminal status and listeners publish only
  after the child's own cleanup plus a successful OS join, covering cancellation
  while still `ready`, cancellation during child unwind, and failure before
  root/cleanup entry. The host's first reason/error and an accepted child reason
  are never replaced by a later cancellation, but a first explicit proxy
  cancellation that arrives while the proxy is still unfinished — including
  while native retirement is pending — takes precedence over a pending body
  success or error, exactly as for any unfinished Task; terminal status still
  follows the OS join.
  If ordinary forwarding was missed or failed, native reasonless cancellation is
  permitted only with no admitted child cancellation (`cancel_requested == 0`
  and no recorded outcome): at the exact bound cleanup wait after the forwarding
  attempt, or while terminal publication is pending because ordinary cleanup
  failed. Never run it on an unfinished normal body or merely because prearming
  linked a waiter. A failed native join retains the barrier, token, nonterminal
  Task and Runtime; the generic driver reports
  `async.native_retirement.retire` and permits an explicit later `async.loop()`
  retry without re-registration or epoch reset. Never spin, detach, or publish
  false completion.
- **Join and wait wiring**: `Thread:status()` is a nonblocking logical-finish
  snapshot that never joins; logical finish can be published before the worker's
  foreign callback returns, so a terminal status may precede the OS/TLS tail.
  `Thread:join()` awaits that finish through the shared external wait and then
  performs the actual native join, so cached, immediate and suspended returns all
  satisfy it; a join failure raises `async.OperationError` (`thread.join`) and
  keeps the token for a retry, while a successful join consumes the token and
  latches joined state. The join takes no mutex across the native call and does
  not yield. Channel send/receive use `async.wait_external_native` with C-ABI
  registrars and the traced endpoint owner; join uses `async.wait_external`.
  Both use the Runtime's one `uv.external_wake_t`; waiters retain a
  `wake_target` per registration, inline readiness never links or retains one,
  and `try_send`/`try_receive` prepare no wait. Channel calls borrow an automatic
  C context and embedded waiter in the suspended stackful frame, which stays
  valid until synchronous cancellation/unwind unlink completes. Registrars
  commit packet ownership in C before delivery can raise; immediate channel
  paths allocate no registrar closures/capture boxes, and slow paths add no
  context userdata. Titan code touches the cell only through a pointer local,
  never as a by-value aggregate whose try-spill reload would roll back a
  registrar's packet commit. Do not let that raw borrow escape the call or
  mistake the traced endpoint for state-close protection.
  Requesting proxy cancellation while the proxy is not yet terminal, or dropping
  an unjoined handle (which best-effort detaches its token at native
  destruction), is not proof that the child retired; a terminal proxy status does
  follow the actual OS join.
- **`Thread:cancel(reason?)`** signals the child thread's loop to cancel its
  root Task cooperatively (`defer` and `await_cleanup` handlers run normally).
  Omission or `nil` selects `CancellationReason.simple("cancelled")`; the first
  host request wins, later requests and already-finished threads are no-ops.
  The actual `simple(text)` / `complex(value)` payload travels in an owned
  packet with native kind metadata, so empty text, nil, `false` and endpoint
  attachments survive. An unencodable cancellation reason is retried as rendered
  text under DEFAULT metadata, but the DEFAULT decoder ignores that payload: the
  host request reaches the child as `simple("cancelled")`, and an unencodable
  child outcome is likewise recorded under DEFAULT so the host proxy and
  `Thread:status()` report `simple("cancelled")` instead of the child's real
  payload. Rendered text is promised to neither side. The host proxy retains its
  exact first reason. The child root's own first sticky reason is authoritative
  for its outcome, even if a host packet arrives during self-cancel unwind; the
  host Task's original reason/error stays preserved separately. A child cancelled
  before its first statement is reported from its real outcome
  (`cancelled(reason)`), not as a generic failure.
- Unobserved standalone threads that fail with an uncaught error report the
  error and traceback to `stderr` when the last `Thread` control reference
  drops. Joining, inspecting terminal status, calling `Thread:task()`, or
  spawning inside a `Group` marks the thread outcome as observed. Dropping an
  unjoined handle best-effort detaches its still-owned OS-thread token; that is
  reclamation, never retirement evidence.

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
- **`Receiver:close()`** closes the channel from the consumer side (`closed = 2`),
  wakes blocked senders with `"channel is closed"`, and drains/discards unread
  buffered messages outside the channel mutex. Last-`Receiver` finalization
  uses the same C-ABI drain while keeping the last receiver reference pinned
  until draining completes, so recursive channel releases cannot free the
  channel mid-drain. Unread packet disposal (`transfer.discard_message`)
  releases unclaimed endpoint attachments directly via C-ABI `foreign function`
  callbacks (`channel_release_sender_native`, `channel_release_receiver_native`)
  without entering Lua, running `from_transfer_payload` decoders, loading
  modules, or requiring a Runtime (safe even during or after `lua_close`).

## Structured thread groups (`thread.Group`)

- `thread.group(limit, propagate_errors)` creates a group with optional
  concurrency cap `limit` (`limit < 1` raises `"group limit must be positive"`)
  and optional `propagate_errors` (defaults to `false`).
- A group member is exactly **one memoized public `Thread:task()` proxy plus one
  terminal listener**; there is no extra observer Task. The active set is a Map
  `Thread -> boolean`: `false` = admitted but listener setup did not return,
  `true` = listener installed, absent = retired. Terminal accounting removes the
  membership entry first and defers slot release before any fallible projection;
  an already-terminal Task is accounted inline, and the group never respawns an
  admitted child. When `limit` is reached, `Group:spawn*` suspends the calling
  `async.Task` in a FIFO admission queue until a running thread finishes or the
  group aborts. Only the monitor's terminal status (successful native OS join)
  retires membership and releases the slot.
- When `propagate_errors` is `true`, the first uncaught thread error cancels all
  currently running group threads and causes queued/subsequent `Group:spawn*`
  calls to become no-ops. Omitted `Group:cancel` reason is
  `CancellationReason.simple("cancelled")`; the first group reason wins.
- **`Group:wait(): {Error}`** makes one observation pass, then suspends until
  all active threads and queued admissions finish, returning uncaught `Error`
  records in completion order. If the child did not fail but its host monitor
  failed, the monitor's error/traceback is collected instead (no duplicate).
  The standard proxy's normal uncaught-Task child-failure diagnostic stays
  visible on `stderr`; do not suppress it.
- **Admission failure timing differs.** A pre-start preparation or native-create
  failure raises from `Group:spawn*` with **no worker started** and returns the
  reserved slot. A proxy/listener setup failure after the worker exists retains
  the **same admitted child and slot** for the explicit `Group:wait()` retry;
  the group never respawns it.
- **Retry boundaries differ.** A live member's negative OS join escapes
  `async.loop()` as the driver `OperationError` and keeps Task/control/token/
  Runtime plus its occupied slot; an explicit later `async.loop()` retries it.
  A child already finished before proxy construction can fail synchronous
  retirement with ready `0`: `Group:spawn*` propagates that constructor error
  while the Thread and slot stay admitted, and an explicit later `Group:wait()`
  retries setup once (no spin, no proxy replacement).
  On Runtime shutdown each memoized member proxy is cancelled as an ordinary
  Task; that cancellation is forwarded to the worker, and membership/slot
  accounting still waits the actual OS join.
- If terminal-listener registration installs its callback but fails allocating
  the remover, the member and memoized Task stay owned; the next explicit
  `Group:wait()` finishes inline for an already-terminal Task (terminal Tasks do
  not invoke new listeners) or installs another listener. Retirement is
  membership-guarded, so partially admitted listeners cannot release twice.

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
- **Native endpoint cycles need explicit receiver close**: unread packet
  attachments retain endpoints outside Lua GC. A channel holding its own
  `Receiver`, or channels holding one another's receivers, can prevent
  last-receiver finalization from draining them. Keep a receiver reachable and
  call `Receiver:close()` to break the cycle before dropping the last
  application handle; `Sender:close()` preserves unread packets.
- **Endpoints require a matching exact-top packet scope**: standalone protobuf
  and `TransferValue` calls create none and reject resource hooks without one.
  Within packet-owned opaque hooks/capture conversion they can reuse the
  existing scope; the resulting index bytes own nothing and are not reusable
  standalone policies. Standalone `TransferValue` policies and `lua.Lua:run*` do
  not transport packet attachments; pass endpoints through thread channels/spawn
  or `async.send` / `async.Receiver`.
- **Native resource moves need explicit ownership**: automatic packet discard
  (`transfer.discard_message`) only releases registered packet resource-table
  entries (initially `thread.Sender` and `thread.Receiver`). Sending an
  `http.Exchange`, `http.UpgradedStream`, `websocket.Connection`,
  `net.Connection`, `ssl.Connection`, or a transferable `uv.tcp_t`/`uv.pipe_t`
  through a thread channel or `async.Receiver` uses manual payload bytes, not a
  packet disposer. Native discard never runs decoders. Recover using the owning
  type's documented adoption/close procedure, or its `discard_transfer_payload`
  helper where one exists. Files, io/os streams and SQLite Connection have no
  such helper. Stop producers and recover/drain handoffs before closing either
  `thread.Receiver` or `async.Receiver`. Follow the
  [networking handoff contract](../titan-networking/SKILL.md#native-connection-and-http-handoff)
  and [WebSocket disposal guidance](../titan-websocket/SKILL.md#transferring-native-sessions).
- **`Thread:cancel` targets the child's root `Task`**: if a worker thread
  spawns background child tasks via `async.run`, use a `defer` in the worker's
  root `Task` to cancel and join those child tasks when the root `Task` unwinds.
- **Do not block event-loop Tasks on OS synchronization primitives**:
  `uv.mutex_t` and `uv.native_mutex_lock` block the OS thread, not just the
  current `async.Task`. Never hold a blocking lock across an `async` suspension
  or wait for a sibling Task on the same loop thread to unlock it; use
  `thread.channel` for cooperative cross-thread coordination (there is no
  `thread.Mutex`).

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
- For a `Thread:task()` proxy, a cancellation request is not a retirement
  oracle: wait for the terminal proxy status (which follows the actual OS join)
  or `join()` before releasing shared native owners. Cover the nil cleanup reason from a failed proxy body,
  which becomes the default `simple("cancelled")` request, the DEFAULT outcome
  that surfaces to the host as `simple("cancelled")`, and a first proxy
  cancellation that arrives while native retirement is pending.

## References

- Language manual:
  [`doc/language/standard-library-thread.md`](../../../doc/language/standard-library-thread.md)
- Implementation manual:
  [`doc/implementation/thread-library.md`](../../../doc/implementation/thread-library.md)
- Transfer and packet ownership manuals:
  [`doc/language/standard-library-transfer.md`](../../../doc/language/standard-library-transfer.md)
  and [`doc/implementation/transfer-library.md`](../../../doc/implementation/transfer-library.md)
