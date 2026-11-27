---
name: titan-thread
description: Use for Titan OS worker threads (titan.thread), bounded MPMC channels, thread.Group, and titan.transfer. Covers CPU parallelism, Sender/Receiver drain, Thread:task(), TransferValue, closure snapshots, custom hooks, and native handoff; use titan-async for single-state Tasks, timers, async.channel, async.Receiver, or uv, and titan-ffi for lua.Lua.
---

# Titan OS threads and cross-state transfer

Covers `thread` (`import "thread"`, **native-only**; Lua `titan.thread`) and `transfer` (`import "transfer"`, native & browser; Lua `titan.transfer`; `async.TransferValue` alias).
Pair with `titan-programmer`, `titan-async` (`Task`/`async.channel`/`async.Receiver`/`uv`), `titan-ffi` (`lua.Lua`), `titan-tester`.

## Non-negotiable invariants

1. **Native-only OS isolation:** `thread` is absent on `--target browser` (`transfer` runs on browser for same-instance/sync `lua.Lua`). Each worker owns an OS thread (`uv_thread_t`, outside libuv's pool), Lua 5.5 state, GC, preloads, Titan path, and `async` Runtime. Never share GC objects or hold `uv.mutex_t` across yields (no `thread.Mutex`—use `thread.channel`).
2. **`TransferValue` & closure snapshots:** Cross-thread values serialize as `transfer` packets (`<= 127` chained records / 128 levels). **Rejected directly:** top-level `{T}`, `{K: V}`, Interfaces/bound Interface methods, Lua closures, upvalue C closures, `local` nominals, `owned` C storage, non-nil Lua `Udata*`, cycles—**wrap Arrays in public `record`/`union`**. Closures snapshot captures *before* hooks run; destination gets **independent fresh mutable cells** and its own module globals.
3. **MPMC close/drain & cycles:** `thread.channel<|T|>(cap?)` defaults `cap = 1`. **`Sender:close()`** closes all clones while **preserving buffered items**; **`Receiver:close()`** closes all clones, **discards unread items**, and wakes senders (`"channel is closed"`). Unread attachments pin endpoints outside GC (self-queued `Receiver`/cycles): keep a reachable `Receiver` and call `Receiver:close()` to break cycles.
4. **Packet attachments vs manual handoff:** Native discard (`discard_message`, `Receiver:close()`, full `try_send`, cancelled `send`, `async.Receiver` overwrite/close) frees **only** packet-table attachments (`Sender`/`Receiver`) in C—**never** runs `from_transfer_payload`. Manual handoffs detach on encode with no rollback: adopt once or dispose explicitly; drain before closing receivers.
5. **Exact-top scope & finalizer-first hooks:** Endpoint attach/claim needs an exact-top `encode_message`/`decode_message` scope (`thread`, `async.Receiver`); standalone `TransferValue`/`protobuf`/`lua.Lua:run*` open none and reject endpoints. Hooks must be **sync, non-yielding**; packet decoders allocate inert wrapper (`native = nil`) + `gc.finalizable` *before* claiming.
6. **OS retirement, `Group` vs `Thread`, `cancel`:** `Thread:status()` is a logical-finish snapshot—**not** OS retirement; dropping unjoined handles only detaches. Retire via `join()`, terminal `Thread:task()`, or `Group:wait()` before freeing shared state or leaving tests. Use `Group` for bounded pools/fail-fast cancel; `spawn*` for typed `R` or `Thread:task()`. `Thread:cancel` cancels only the worker's **root Task**—`defer`-cancel child Tasks inside it.

## Choosing the right concurrency primitive

| Primitive | Delivery & Scope | Use when |
| --- | --- | --- |
| `async.channel<|T|>` | Same state; zero-copy | Same-state Task queues (`titan-async`). |
| `thread.channel<|T|>` | Cross-thread; bounded MPMC FIFO | Pipelines, backpressure, fan-out/in, endpoints (native). |
| `async.Receiver` | Cross-state; **lossy coalescing** | Latest-value wake (`handle()` borrowed; stop senders before `close()`, `titan-async`). |
| `thread.Group` | Bounded OS pool (`limit`, `propagate_errors`) | Fan-out returning `{thread.Error}` (replies via channel). |
| `thread.spawn*` | Standalone `Thread<|R|>` + `task()` | Typed return `R` or `async.all_*`/`any_*`/`race_*`. |
| `lua.Lua` | Manual independent state (`titan-ffi`) | Dynamic Lua (`run*` lacks packet table—no `thread` endpoints). |

## Bounded MPMC channels (`Sender<|T|>` & `Receiver<|T|>`)

- **Endpoints & GC:** `thread.channel<|T|>(cap?) -> (Sender<|T|>, Receiver<|T|>)` (`<= 0` raises `"channel capacity must be positive"`). `clone()` increments active count; sending/spawning retains a ref leaving caller's handle valid. Last-`Sender` GC closes preserving buffer; last-`Receiver` GC closes discarding buffer in C (no Lua/Runtime).
- **Send:** `send(msg)` serializes outside lock, raises `"channel is closed"` if closed, enqueues if space exists, else suspends FIFO (wakes reserve no slot: Tasks retry). `try_send(msg): boolean` serializes first, raises if closed, returns `true` on enqueue, else discards packet -> `false`.
- **Receive:** `receive(): T` suspends if empty, raises `"channel is closed"` on closed+drained; `receive_result(): ReceiveResult<|T|>` -> `message(v)`/`closed()`; `try_receive(): (boolean, T?)` -> `(true, v)`/`(false, nil)`. `incoming()` yields `(true, msg)` then `(nil, nil)` on EOF—control flag keeps `nil`/`false` valid (`for _, msg?` keeps `nil`; `for _, msg` forces non-nil).
- **Fan-in & state close:** `tx:close()` closes **all** clones—close shared reply `Sender` after `pool:wait()`; drain `res_rx` concurrently in `async.run` when replies can exceed capacity. `Receiver:close()` overrides `Sender:close()`. State close withdraws parked waits safely (`defer` runs in non-yielding finalizer; drain Tasks first if cleanup awaits).

```titan
local async = import "async"
local io = import "io"
local thread = import "thread"

record Job
  const nums: {integer}
  const reply: thread.Sender<|integer|>
end

function main(args: {string}): integer
  local jobs_tx, jobs_rx = thread.channel<|Job|>(2)
  local res_tx, res_rx = thread.channel<|integer|>(2)
  local col = async.run(function (): integer
    local sum = 0
    for _, v in res_rx:incoming() do sum = sum + v end
    return sum
  end)

  local pool = thread.group(2, true)
  for _ = 1, 2 do
    pool:spawn_one(function (rx: thread.Receiver<|Job|>)
      for _, job in rx:incoming() do
        local sub = 0
        for i = 1, #job.nums do sub = sub + job.nums[i] end
        job.reply:send(sub)
      end
    end, jobs_rx)
  end

  for i = 1, 5 do jobs_tx:send(Job({ i, i * 10 }, res_tx)) end
  jobs_tx:close()
  local errs = pool:wait()
  res_tx:close()
  local total = 0
  case async.join(col)
  when succeeded(v) then total = v
  else raise "collector failed"
  end
  if #errs > 0 then errs[1]:raise() end
  if total ~= 165 then raise "bad total: " .. total end
  io.print("total = " .. total)
  return 0
end
```

## Standalone threads, `Thread:task()` & `thread.Group`

- **`thread.spawn`..`spawn_five`:** Snapshots `entry` + args sync before OS start. Worker loads `titan.thread`, runs `entry` as root Task in `async.loop()` (keeps `long double`/x87); sibling Tasks/handles keep loop alive after root returns. Uncaught error/bad return records `failed(Error(err, traceback))` (unencodable error -> string) and calls `async.request_exit(0)`.
- **`ThreadStatus<|R|>` & `Error`:** `running()`, `succeeded(v)`, `failed(err)`, `cancelled(reason)` + `:as_string()`, `:has_finished()`, `:has_succeeded()`, `:has_failed()`, `:has_cancelled()`. `Error`: `const error: value`, `const traceback: string`, `:raise()`.
- **`join()`, `cancel()`, observation:** `join()` needs a Task, awaits finish + OS join, caches `ThreadStatus<|R|>` without raising (join error -> `OperationError` `"thread.join"`, retryable). `cancel(reason?)` latches first host reason (`nil`/unencodable -> `simple("cancelled")`; child's sticky reason wins; pre-entry cancel -> `cancelled(reason)`). Unobserved failures log to `stderr` at GC (`status()` after finish/`join()`/`task()`/`Group` observe); finalized handles raise `"thread handle was finalized"`.
- **`Thread:task(): async.Task<|R, value|>`:** Memoized proxy resolving `R`, rethrowing `Error:raise()`, forwarding cancel (`simple("cancelled")` if uncancelled body failed). Prearmed native barrier publishes terminal status/listeners **only after** child cleanup + OS join; first cancel on unfinished proxy wins even during join.
- **Proxy join error & state close:** Join error escapes `async.loop()` as `OperationError` `"async.native_retirement.retire"` (retry next `async.loop()`); state close forwards cancel (`simple("async Runtime abandoned at Lua state close")`) without blocking join.
- **`thread.group(limit?, propagate_errors?)`:** `limit <= 0` raises `"group limit must be positive"` (`nil` = unbounded); `propagate_errors` (default `false`) cancels group (`simple("group thread failed")`) on first error and turns queued/later `spawn*` into no-ops.
- **`Group` spawn/wait/retry:** `spawn`..`spawn_three` queue FIFO at `limit` (cancelled waiters withdraw, passing granted slots). `cancel(reason?)` latches first reason; `wait(): {Error}` returns errors in completion order (proxy `stderr` visible). Pre-start error returns slot; post-start proxy/listener error keeps admitted `Thread` + slot for `wait()` retry.

## `TransferValue`, closures, custom hooks & handoff

- **Allowed & policy:** Scalars (exact kind/`-0.0`), NUL-safe strings, borrowed ptrs/C funcs (retain nothing), public all-public `record`/`union`, hooked public records, Titan closures, `thread` endpoints (in scope). `from_value(v)` keeps policy; `from_closure_payload(mod, entry, data)` defers checks to `:to_value()`.
- **`value`/erased fields:** Carry scalars/strings/public nominals/Arrays (`TitanValue`; callables/Maps/Interfaces raise `protobuf: unsupported dynamic value`); packet decode loads declaring modules on demand, standalone `:to_value()` only root's module.
- **Closures & custom hooks:** Top-level/local functions, lambdas, bound concrete methods, adapters transfer; captured `TransferValue` stays wrapped. Public records (incl. `local` fields) declare public `R:to_transfer_payload(): string` and `R.from_transfer_payload(payload: string): R` (incomplete/mismatched pairs raise instead of protobuf fallback; use `strings.pack`/`unpack` or `protobuf.serialize_fields`/`deserialize_fields`).
- **Manual-handoff inventory:** *`discard_transfer_payload(payload): integer`* (live Lua state, no Runtime/Task; consumes even on error): `uv.tcp_t`, `uv.pipe_t`, `net`/`ssl`/`websocket.Connection`, `http.Exchange`/`UpgradedStream`, `os.InputStream`/`OutputStream`. *Adopt + `:close()` (no discard):* `fs.File`, `os.InputOutputStream`, `sqlite3.Connection`. *Untransferable:* listeners, `fs.Watcher`, `os.Process`, split HTTP req/resp, SQLite statements/cursors.
- **5 handoff rules:** (1) Encode detaches source (unused stdio stays usable). (2) Adopt once; never copy/drop/double-adopt. (3) Recover/dispose failed sends (retain `TransferValue` for `async.Receiver`). (4) Post-detach composite error disposes built-in resource without rollback (`os.InputOutputStream` keeps first pipe on second error). (5) Sync/no Task; UV adapters need active non-closing Runtime on both hooks (`uv.tcp_t`/`pipe_t`: initialized loop on encode, active Runtime on decode).
- **Raw packets & scopes:** `decode_message(raw)` (Titan-only): non-captured `foreign *void` local + immediate `defer transfer.discard_message(raw)` (clears slot on return/error; never `ffi.free`; `copy_message` returns `nil` with attachments). `attach_resource` reserves before C-only `retain` -> 4B LE slot (`0..0xfffffffe`; `0xffffffff` invalid); `claim_resource` checks width/bounds/`expected_release`/unclaimed. Scope never inherits across Tasks/Coroutines; never hold `register_resource` decode `context` past return (pooled reuse undetected).

```titan
local async = import "async"
local io = import "io"
local strings = import "string"
local thread = import "thread"
local timer = import "timer"
local transfer = import "transfer"

record Token
  local const tag: string
  local const seq: integer
end

function Token.new(tag: string, seq: integer): Token return { tag = tag, seq = seq } end
function Token:label(): string return self.tag .. "#" .. self.seq end
function Token:to_transfer_payload(): string return strings.pack("<i8s4", self.seq, self.tag) end
function Token.from_transfer_payload(payload: string): Token
  local seq: integer, tag: string = strings.unpack("<i8s4", payload)
  return Token(tag, seq)
end

function main(args: {string}): integer
  local counter = 10
  local tok = Token("job", 1)
  local worker = thread.spawn_one(function (t: Token): string
    counter = counter + 5
    return t:label() .. ":" .. counter
  end, tok)
  counter = 99 -- origin mutation does not affect worker's snapshot

  local deadline = async.run(function (): nil timer.sleep(500); return nil end)
  local out = ""
  case async.any_two(worker:task(), deadline)
  when first(res) then deadline:cancel(); async.join(deadline); out = res
  when second() then worker:cancel(); worker:join(); raise "timeout"
  when none() then raise "worker failed"
  end

  local copy: Token = transfer.TransferValue.from_value(tok):to_value()
  if out ~= "job#1:15" or counter ~= 99 or copy:label() ~= "job#1" then raise "bad: " .. out end
  io.print(out)
  return 0
end
```

## Pre-delivery verification checklist

- [ ] `thread` native-only; browser `transfer` is same-instance/sync `lua.Lua` only.
- [ ] Wrap Arrays in public `record`/`union`; no top-level Arrays/Maps/Interfaces/`local` nominals/Lua closures/cycles.
- [ ] Close shared `Sender` after `pool:wait()`; drain fan-in concurrently; `Receiver:close()` breaks cycles; `msg?` in `incoming()` if `nil` valid.
- [ ] Retire `Thread`s (`join()`/terminal `task()`) & `Group:wait()` before freeing state/leaving tests; `defer`-cancel child Tasks; no `uv.mutex_t` across yields.
- [ ] Adopt/dispose handoffs once & drain before closing receivers; sync/finalizer-first hooks; `defer transfer.discard_message(raw)` on `decode_message(raw)`; pass `titanc --test`.
