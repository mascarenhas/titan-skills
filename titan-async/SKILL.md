---
name: titan-async
description: Use for Titan cooperative Tasks, timers, channels, Receivers, cancel, join/race, coroutines, browser async/uv. Covers sleep/Ticker, all/any, ResumeToken, cross-state wakeup, await/subscriptions, callTask & libuv adapters; use titan-thread for OS threads/transfer, titan-networking for net/http, titan-stdlib for fs/os.
---

# Titan async, timers, coroutines & libuv

Covers `async`, `timer`, `coroutine`, and high-level `uv` boundaries. Pair with `titan-programmer` for syntax/types/`T?`/`defer`/`raise`.
Peers: `titan-thread`, `titan-networking`, `titan-websocket`, `titan-stdlib` (`fs`/`os`/`io`/`gc`), `titan-ffi`, `titan-tester`.

## Non-negotiable invariants

1. **Single-loop cooperative scheduling:** One `async.Task` runs uninterrupted until suspension (`timer.sleep`, I/O, channels, combinators, `async.yield()`), return, or raise—never preempted. Never add locks, polling loops, `uv.idle_t`/`check_t`, or recursive `async.loop()`/`uv.run()` (or from a Task/callback). Call `async.yield()` in long CPU loops or offload to `titan-thread`. Executables importing async stdlib auto-bootstrap `main` (`--no-uv-bootstrap` disables); Lua hosts call `async.run` + `async.loop()`.
2. **Explicit loser cancellation & teardown:** `race*`/`any*`/`all*` **never** cancel losing/sibling Tasks. Call `task:cancel(reason?)` (sticky first reason; delivered at suspension/`async.checkpoint()`) and await `async.join(task)` before freeing shared state—or in a cancellation-prone `defer`, use removable `add_terminal_listener` + `async.await_cleanup<|T, E|>` (`async.join` is cancellation-sensitive). Never hold blocking `uv` locks or call `uv.sleep` in Tasks.
3. **`async.channel` vs `async.Receiver` vs `thread.channel`:** Same-state FIFO → `async.channel<|T|>(cap?)` (1 waiter/direction; `close()` drops buffered items—use `T?` sentinel to drain). Cross-state **lossy coalescing** latest-value wake → `async.Receiver` (`rx:handle()` `foreign *void`; stop senders before `rx:close()`). Lossless cross-thread FIFO → `thread.channel<|T|>` (`titan-thread`).
4. **Event-driven waiting via `ResumeToken` (never poll):** Check condition first, allocate fresh `async.ResumeToken("source")` per wait (nominal identity), publish waiter *before* final check, `defer` removers, and call `async.suspend(token, cancel_action?)` once. Clear registration before `waiter:resume(token)` (or loop on condition for wake latching).
5. **Browser async rules:** Turn-based on **owner** Lua state only; `<= 64` ready Tasks/turn before macrotask yield (`async.yield()`/`timer.sleep(0)` skip 4 ms clamping). Absent on browser: `uv`, `current_loop`, `await_*_with`, `await_cancellable*`, `run_foreign`, `ExternalWait` ops, `Receiver`/`send`, `version`. Never call JSPI-suspending raw imports in Tasks; sync C callbacks (`titan_browser_call_sync`) run outside Tasks and forbid coroutine switches; `callTask` joins/starts drives; `request_exit`/`dispose` cancel Tasks (`"program exit"`/`"instance disposed"`).
6. **Short imports & union `case`:** Import `"async"`, `"timer"`, `"coroutine"`, `"uv"` (`require "titan.<name>"` in Lua). Inspect `TaskStatus`, `Result`, `CancellableResult`, `Any*Result`, `Race*Result`, and `uv` enum unions with `case` (or `TaskStatus:has_*`)—never `==` (`success(nil)` may be shared).
7. **Raw `uv` & native adapters (reference gate):** App code uses `timer`/`fs`/`net`/`ssl`/`http`/`websocket`/`os`—never raw `uv`. **MUST read `skill://titan-async/references/uv-and-native-adapters.md`** for raw `titan.uv`, `async.await*`/`Completion`/`fatal`/`Subscription`/`ExternalWait`/`run_foreign`, or native `uv` transfers—and look up signatures in `doc/language/uv/functions/<family>.md`.

## Concurrency primitive & idiom delta

| Need | Primitive | Key Titan delta |
| --- | --- | --- |
| Concurrent I/O, timers, shared state | `async.run` + `timer` | Cooperative `Task<|A, B|>`; explicit typeargs supply both `A, B`. |
| Same-state FIFO / byte stream | `async.channel` / `reader_writer_channel` | Zero copy; 1 waiter/dir; `close()` drops buffered items (`T?` sentinel). |
| Latest-value cross-state wake | `async.Receiver` *(native)* | Lossy single slot; `rx:handle()` crosses states; never retry committed `send`. |
| Multi-core CPU / lossless FIFO | `thread.spawn*` / `thread.channel` | Isolated OS threads/states; **load `titan-thread`**. |
| Sync generator / custom scheduler | `coroutine.create` | Stackful, explicit non-nil yield tags; independent of Lua's `coroutine`. |
| Custom libuv / C wait adapter | `uv` + `async.await_with` | **Read `references/uv-and-native-adapters.md`**; `uv.sleep` blocks OS thread! |

## `async` Tasks, combinators, cancellation & `ResumeToken`

- **Scheduling (`Task<|A, B|>`):** `async.run(fn)` queues on FIFO (`<= 64`/turn) without inline call (`B` defaults `value`; explicit typeargs supply both `async.run<|A, B|>`). `async.running()` → `Task<|value, value|>` (Task-only); `async.yield()` requeues; `async.checkpoint()` checks cancel/shutdown without yielding. `async.request_exit(code)` (Task-only) latches first code, cancels Tasks (`"program exit"`), runs cleanup, returns `code` (Lua returns from `async.loop()`).
- **Cleanup Tasks & `await_cleanup`:** `async.run_with_cleanup(body, cleanup, final_wait?)` installs `defer cleanup(reason)` (`CancellationReason<|B|>?`, `nil` if uncancelled; native `final_wait` binds `prepare_native_retirement`, browser `nil`).
- **`await_cleanup` signatures:** Cancellation-immune cleanup await *(Native & Browser)*: `async.await_cleanup<|T, E|>(op: function (function (T): (), function (E): (), function (value, string): ()): ()): Result<|T, E|>`—pass explicit `<|T, E|>` (or annotate all 3 `resolve`/`reject`/`fatal` params) so `T`/`E` don't default to `value`. Native zero-closure form: `async.await_cleanup_with<|C, T, E|>(context: C, start: function (Completion<|C, T, E|>, integer): (uv.req_t?)): Result<|T, E|>` *(see reference)*.
- **Status & `async.Error`:** `Task:status()` → immutable `TaskStatus<|A, B|>` (`ready()`, `running()`, `waiting()`, `succeeded(v)`, `failed(Error)`, `cancelled(CancellationReason<|B|>)`) with `:as_string()` and `:has_finished/succeeded/failed/cancelled()`. `async.Error` has fields **`error: value`** and **`traceback: string`**; sticky cancel overrides return/catch/failure. On non-`nil`-returning error paths, prefer **`raise err.error, err.traceback`** over `err:raise()` (`err:raise()` is a method call, NOT statically recognized as diverging).
- **Fixed-arity combinators** *(interleaved `(A1, B1, A2, B2, ...)` typeargs; scan L→R then publication order; passing `async.running()` raises; never cancel siblings)*:
  - `join(t)` → 1 `TaskStatus<|A, B|>`; `join_two..five` → **N-tuple** `(TaskStatus<|A1, B1|>, ..., TaskStatus<|AN, BN|>)` (2..5 returns). Waits for all; **never** raises child errors/cancels.
  - `all_two..five` → **N-tuple** `(A1, ..., AN)` (2..5 returns) when all succeed; on first fail/cancel **raises** `AllTwoError`..`AllFiveError` (`first(TaskStatus)`..`fifth(TaskStatus)`).
  - `race_two..five` → **1 union** `RaceTwoResult`..`RaceFiveResult` (`first(TaskStatus)`..`fifth(TaskStatus)`) for first finished Task (any status); **never** raises child errors.
  - `any_two..five` → **1 union** `AnyTwoResult`..`AnyFiveResult` (`first(A1)`..`fifth(AN)` | `none()`) for first succeeded Task; when **all** fail/cancel, returns **`none()`** (**never** raises—inspect via `:status()`/`join*` and re-raise with `raise err.error, err.traceback`).
- **Listeners & `ResumeToken`:** `task:add_terminal_listener(fn)` runs `fn(status)` once at terminal publication and returns an idempotent remover (`defer` it; already-terminal returns no-op remover; listener errors ignored). `async.suspend(token, cancel_action?)` parks until `task:resume(token)` (mismatch raises `Task resume token mismatch`). `resume(token)` while running/registering latches `token` for an immediate `suspend(token)`; `cancel_action` runs sync once on cancel (never yield/raise; detach in `defer`).

```titan
-- Portable: compiles and runs on both native and --target browser
local async = import "async"
local timer = import "timer"

record Gate
  local opened: boolean
  local waiter: async.Task?
  local token: async.ResumeToken?
end

function Gate.new(): Gate return { opened = false, waiter = nil, token = nil } end

function Gate:wait()
  if self.waiter ~= nil then raise "Gate busy" end
  local cur, tok = async.running(), async.ResumeToken("Gate.wait")
  self.waiter = cur; self.token = tok
  local detach = function ()
    if self.waiter == cur then self.waiter = nil; self.token = nil end
  end
  defer detach()
  if self.opened then return end
  async.suspend(tok, detach)
end

function Gate:open()
  self.opened = true
  local w?, t? = self.waiter, self.token
  if w ~= nil and t ~= nil then
    self.waiter = nil; self.token = nil
    w:resume(t)
  end
end

local function join_cleanup(task: async.Task<|string, value|>): async.TaskStatus<|string, value|>
  local st = task:status()
  if st:has_finished() then return st end
  local res = async.await_cleanup<|async.TaskStatus<|string, value|>, string|>(
    function (resolve, _reject, _fatal)
      local remove = task:add_terminal_listener(function (done) resolve(done) end)
      local cur = task:status()
      if cur:has_finished() then remove(); resolve(cur) end
    end)
  case res
  when success(done) then return done
  when error(msg) then raise msg
  end
end

function main(args: {string}): integer
  local gate, cleaned = Gate(), false
  local worker = async.run(function (): string
    defer cleaned = true
    gate:wait()
    return "ok"
  end)
  local deadline = async.run(function (): nil timer.sleep(15); return nil end)
  case async.any_two(worker, deadline)
  when first(_) then
    deadline:cancel(async.CancellationReason.simple("done")); async.join(deadline)
  when second() then
    worker:cancel(async.CancellationReason.simple("timeout"))
    local cancelled, _ = join_cleanup(worker):has_cancelled()
    if not cancelled or not cleaned then raise "expected cancelled cleanup" end
  when none() then
    local w_st, _ = async.join_two(worker, deadline)
    local failed, err? = w_st:has_failed()
    if failed and err ~= nil then raise err.error, err.traceback end
    raise "both failed"
  end
  local tk = timer.ticker(5)
  defer tk:close()
  timer.sleep(0)
  if not tk:tick() then raise "expected tick" end
  return 0
end
```

## `timer`, `async.channel`, streams & cross-state `Receiver`

- **`timer` (Task-only; Native & Browser):** `timer.sleep(ms)` waits `>= ms` ms (`< 0` raises `OperationError` `name == "EINVAL"`, `operation == "timer.sleep"`; cancel checked first); `sleep(0)` yields a turn; `timer.yield()` == `async.yield()`.
- **`timer.ticker(ms)`:** `ms > 0`, `io.Closer`; `defer ticker:close()`. `tick(): boolean` → `true` (or `false` when closed), rejects concurrent waiters, coalesces missed ticks. Cancel detaches waiter only; `close()` is idempotent/cancellation-insensitive (safe in `defer`), wakes waiters with `false`; Runtime drain auto-closes.
- **`async.channel<|T|>(size?)` & streams:** Returns `(send, receive, close)` (`size` default `1`, `<= 0` raises; omitted `T` → `value`; `nil` valid if `T` admits `nil`). Non-blocking ops work outside Tasks; max 1 waiter/direction (competing raises). `close()` drops buffered items, wakes waiters (`"channel is closed"`). `reader_writer_channel(size?)` → `(ChannelReader, ChannelWriter)` (`io.ReaderCloser`/`WriterCloser`, binary-safe `read_until(delim, chop?)`; Reader `close()` drops suffix→`nil`, Writer `close()` keeps suffix until next receive raises).
- **`async.Receiver` *(native)*:** `rx = async.receiver()` may bootstrap Runtime outside Task without driving `async.loop()`. Keep `rx` rooted; pass `rx:handle()` (`foreign *void`). `async.send(handle, v)` encodes via `transfer.encode_message`, atomically swaps slot, discards overwritten packets natively (`transfer.discard_message`—releases `thread` endpoints, never `from_transfer_payload`), calls `uv_async_send` (never retry `OperationError("async.send")`: ownership committed—wrap in `TransferValue.from_value` if pre-exchange failure must stay recoverable).
- **`Receiver:wait()` & `close()`:** `rx:wait(): value` reserves single reader *before* slot check (2nd raises `"receiver already has a waiting reader"`), decodes eagerly (`nil`/`false` are data; `is_pointer`/`is_lua_state` → lightuserdata; decode error consumes packet & raises). Cancel withdraws reservation only; `rx:close()` idempotent, needs no Task, discards unread packets, wakes waiters (`"receiver is closed"`).

```titan
-- Native: channels, string streams, and coalescing cross-state Receiver
local async = import "async"

function main(args: {string}): integer
  local send, recv, close_ch = async.channel<|integer?|>(2)
  defer close_ch()
  local prod = async.run(function (): nil send(10); send(20); send(nil); return nil end)
  local total = 0
  while true do
    local item? = recv()
    if item == nil then break end
    total = total + item
  end
  async.join(prod)
  if total ~= 30 then raise "channel sum" end

  local r, w = async.reader_writer_channel(2)
  defer r:close(); defer w:close()
  local wt = async.run(function (): nil w:write("hi\n"); return nil end)
  local line? = r:read_until("\n", true)
  async.join(wt)
  if line ~= "hi" then raise "stream" end

  local rx = async.receiver()
  defer rx:close()
  async.send(rx:handle(), "old"); async.send(rx:handle(), "latest")
  local got: string = rx:wait()
  if got ~= "latest" then raise "receiver coalesce" end
  return 0
end
```

## Low-level stackful `coroutine`

- **Independent of Lua coroutines:** Native & Browser (`import "coroutine"`, Lua `require "titan.coroutine"`). Sync transfer without event loop (`coroutine.yield` never calls `lua_yield`). Stacks: native 2 MiB (vmem), browser 256 KiB (`calloc`/`free` + JSPI).
- **Tags & statuses:** `create(func, default_tag?)`, `running(): Coroutine?`, `co:resume(arg, tag?)`, `co:error(err, tag?)`, `coroutine.yield(arg, tag)`, `is_yieldable(tag)`. Non-nil tags (raw equality); `yield` always needs explicit non-nil `tag`. Statuses: `"suspended"`, `"running"`, `"normal"`, `"stacked"` (resume outer handler to restore), `"dead"`. Resuming non-`"suspended"` raises.
- **Non-raising `transfer`:** `co:transfer(payload, tag?, inject_error): (boolean, value, string?)` → `(false, val, nil)` on yield/return (check `status()`; omit/`_?` 3rd slot) or `(true, err, trace)` on uncaught error. Branch on 1st boolean (`nil`/`false` valid); misuse raises.
- **Abandoned unwind & browser sync:** Unreachable `"suspended"`/`"stacked"` coroutines unwind in finalizer (`defer`/generic-`for` innermost-first, uncatchable, skipping C frames; no yield/await/`gc`; errors warn; never rely on for net shutdown). In browser `titan_browser_call_sync`, `resume`/`error`/`transfer`/`yield` raise `"coroutine.<op> is unavailable in a synchronous callback"`, `running()`→`nil`, `is_yieldable()`→`false`, `create` works, unwind defers.

```titan
-- Portable: compiles and runs on both native and --target browser
local coroutine = import "coroutine"

local function inner_fn(_: value): value
  local back: string = coroutine.yield("from-inner", "outer")
  return "inner:" .. back
end

local function guarded(_: value): value
  coroutine.yield("step", "t"); raise "boom"
end

function main(args: {string}): integer
  local inner = coroutine.create(inner_fn, "inner")
  local outer = coroutine.create(function (_: value): value
    local r: string = inner:resume(nil)
    return "outer:" .. r
  end, "outer")
  local first: string = outer:resume(nil)
  if first ~= "from-inner" or outer:status() ~= "suspended" or inner:status() ~= "stacked" then
    raise "nested status"
  end
  if (outer:resume("ok") as string) ~= "outer:inner:ok" then raise "nested resume" end

  local g = coroutine.create(guarded, "t")
  local f1, v1, _? = g:transfer(nil, nil, false)
  local f2, err, trace? = g:transfer(nil, nil, false)
  if f1 or (v1 as string) ~= "step" or not f2 or (err as string) ~= "boom"
     or trace == nil or g:status() ~= "dead" then raise "transfer" end
  return 0
end
```

## Browser async runtime & native adapter handoff

- **Driver & timers:** Owner state drives `<= 64` Tasks/turn, flushes stdio, yields one macrotask (`MessageChannel`/Node `setImmediate`). `timer.sleep` `> 2,147,483,647` ms chains automatically. Idle Tasks with no host request/listener/`BrowserPin` fail with `"async Runtime became idle while Tasks were waiting"`.
- **Host calls & sync:** During a drive, JS `call()`/`callTask()` queue for next turn; `run()`/`drain()` & in-binding reentry reject `TITAN_BROWSER_REENTRY` (`notify()`). `callTask(fn, args, { signal })` maps `AbortSignal` → `TITAN_BROWSER_CANCELLED`. Sync C callbacks run outside Tasks (`running()`/`await`/`suspend`/`yield` raise; `resume`/`cancel`/`run` schedule next turn).
- **Exit, disposal & native adapters:** `request_exit`/`os.exit` marks exited (`TITAN_BROWSER_EXITED`); `dispose()` cancels Tasks (`"instance disposed"`), settles in-flight host requests for `defer`, rejects new ones (`"browser state is closing"`), then closes Lua. For `await_with`/`Completion`/`fatal`, `Subscription`, `ExternalWait`/`prepare_native_retirement`, `run_foreign`, `add_close_listener`, `uv.loop_abandon`, & `titan.uv` hazards, read `skill://titan-async/references/uv-and-native-adapters.md`.

## Pre-delivery verification checklist

1. **Cooperative discipline:** No recursive `async.loop()`/`uv.run()`, no `uv.sleep`/blocking `uv` locks in Tasks, `async.yield()` in long CPU loops.
2. **Loser cleanup & errors:** `race*`/`any*` cancel losers and await `async.join` (or terminal listener + `await_cleanup<|T, E|>` in `defer`); propagate `async.Error` via `raise err.error, err.traceback` on non-`nil` paths.
3. **Teardown pairing:** Every `timer.ticker`, `async.channel`, `ChannelReader`/`Writer`, and `async.Receiver` has `defer :close()`; stop `Receiver` senders before `close()`; drain `async.channel` via sentinel.
4. **Event-driven waits & targets:** Fresh `ResumeToken` per wait, waiter published before check, removers in `defer`, wake latching handled; browser avoids native-only `async`/`uv`/JSPI-in-Task/sync-callback switches; raw `uv`/`await*`/`Subscription`/`run_foreign`/`ExternalWait` follow `skill://titan-async/references/uv-and-native-adapters.md` & `doc/language/uv/functions/<family>.md`.
