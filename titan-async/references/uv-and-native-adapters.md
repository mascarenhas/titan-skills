# Titan libuv & native async adapters

On-demand reference for `titan-async`. Read this when writing custom `async` adapters (`await*`, `Completion`, `Subscription`, `ExternalWait`, `run_foreign`, `add_close_listener`) or using public `titan.uv` directly. Application code should prefer `timer`, `fs`, `net`, `ssl`, `http`, `websocket`, and `os`.

## On-demand `uv` reference lookup (`doc/language/uv/`)

- **Pinned native library:** `titan.uv` (`import "uv"` in Titan, `require "titan.uv"` in Lua; native-only) bundles pinned, patched libuv **1.53.0** (`vendor/libuv/libuv-1.53.0-spawn-close.patch`). `uv.has_api(name)` (omit `uv_` prefix) tests exported canonical wrappers only (false for supplemental/omitted helpers; does not probe kernel support). `uv.version()`/`version_string()` never identify Titan's patch.
- **Never guess libuv signatures:** Look up exact contracts in `doc/language/uv/functions/<family>.md` (`loop`, `handle`, `request`, `timer`, `prepare`, `check`, `idle`, `async`, `signal`, `poll`, `stream`, `tcp`, `pipe`, `tty`, `udp`, `dns`, `fs`, `fs_event`, `fs_poll`, `process`, `threadpool`, `threading`, `dll`, `errors`, `metrics`, `version`, `undocumented`), `uv/{types,callbacks,supplemental,CONTRACT-NOTES,PROCESS-POLICY,coverage}.md`, and `uv/examples/*.titan`.
- **9 omitted wrappers & 5 auto-freed snapshots:** Omitted: `default_loop` (`uv.loop_t()`+`loop_init`), `library_shutdown`, `loop_new`, `loop_delete` (`loop_close`), `print_{active,all}_handles` (`walk`+`is_active`), `replace_allocator`, `setup_args` (`setup_process_args()`), `write_nwritten`. Auto-freed: CPU info, interface addrs, environ, passwd, group (`getaddrinfo` needs `uv.freeaddrinfo`).

## One-shot async adapters (`await*`, `Completion`, `fatal`)

Prefer named `_with` registrars (`await_with`, `await_cancellable_with`, `await_cleanup_with` — native-only; avoids the 3-closure/wait `await*` facade on hot paths). Registrars run **outside** Task context (`async.running()` raises; borrow the loop with `async.current_loop()`, check shutdown with `async.is_closing()`).

| Wait family | Pending cancel before start | After native acceptance | Terminal delivery with cancel pending |
| --- | --- | --- | --- |
| `await_with` / `await` | Skip registrar; raise reason | Retain request; no `uv.cancel` | Wait for callback, then raise reason |
| `await_cancellable_with` / `await_cancellable` | Skip; return `cancelled(reason)` | Must return `uv.req_t` (unless inline-settled); `cancel` calls `uv.cancel` | Wait for callback, then return `cancelled(reason)` |
| `await_cleanup_with` / `await_cleanup` | Still runs (cancel/shutdown) | Retain request; no `uv.cancel` | Return ordinary `Result<|T, E|>` |

- **Snapshot `number` & context before settling:** `Completion<|C, T, E|>` is reused per Task. Capture `number` at registration for `context`/`resolve`/`reject`/`fatal` (stale numbers/duplicates raise). Copy context needed after settlement into callback locals first—settlement clears the completion slot immediately.
- **Ownership across cancellation:** Commit acquired OS handles (e.g., fd from `fs_open`) onto an unpublished lexical/domain owner and copy borrowed bytes **before** `uv.fs_req_cleanup` and settlement; clean up in `catch` if cancellation replaces the await result. In close adapters, clear the owner's descriptor before `await_cleanup`, restore it only on pre-acceptance rejection, and keep it terminal once accepted.
- **Unexpected callback exceptions (`fatal`):** Use `reject(E)` for expected errors. On unexpected exceptions in a terminal callback, run mandatory request cleanup, call `done:fatal(number, error, traceback)` (or `fatal(error, traceback)`), and bare `raise` so the outer `uv` boundary records failure. Call `fatal` only outside a running Task after native completion is consumed.

```titan
local async = import "async"
local uv = import "uv"

record StatArgs
  const path: string
  const req: uv.fs_t
end

local function start_stat(
    done: async.Completion<|StatArgs, integer, integer|>,
    number: integer): uv.req_t?
  local args = done:context(number)
  local cb = function (completed: uv.fs_t)
    local res = uv.fs_get_result(completed)
    local size = 0
    if res >= 0 then size = uv.fs_get_statbuf(completed).st_size end
    uv.fs_req_cleanup(completed)
    if res < 0 then done:reject(number, res) else done:resolve(number, size) end
  catch
    uv.fs_req_cleanup(completed)
    done:fatal(number, error, traceback)
    raise
  end
  local st = uv.fs_stat(async.current_loop(), args.req, args.path, cb)
  if st < 0 then uv.fs_req_cleanup(args.req); done:reject(number, st); return nil end
  return args.req:as_req_t()
end

function stat_size(path: string): integer
  local req = uv.fs_t()
  case async.await_cancellable_with<|StatArgs, integer, integer|>(StatArgs(path, req), start_stat)
  when success(size) then return size
  when error(code) then raise async.OperationError(code, uv.err_name(code), uv.strerror(code), "fs.stat")
  when cancelled(_) then raise "cancelled"
  end
end

function main(args: {string}): integer
  if stat_size(".") < 0 then raise "bad stat" end
  return 0
end
```

## Persistent subscriptions, `run_foreign`, `ExternalWait` & teardown

- **Subscriptions (`CoalescingSubscription<|T, E|>` vs `BufferedSubscription<|T, E|>`):** Both take **2 type args** (item `T`, error `E`); `SubscriptionActions<|T|>` takes **1** (`T`). Construction runs `producer(publish, fail, finish)` sync and expects `SubscriptionActions<|T|>(stop, close)`. `CoalescingSubscription<|T, E|>` overwrites unread values without disposal—use `BufferedSubscription<|T, E|>` for resource-bearing events, disposing unread items on `publish() == false`/raise and in `actions.close(drain)`.
- **Subscription reading & controls:** `next()` drains queued items before `error`/`ended`; `closed()` takes immediate priority. Iterate `next_batch()` via `1..batch.count` (`nil`/`false` are data). Single waiter across `next`/`next_batch`; `stop()` is sync/idempotent; `close()` requires a Task on first call and repeats are no-ops (never join an in-progress close). Sync controls: `drain_pending()`, `snapshot_pending()`, `drain_if(pred)`, `wake_batch()`.
- **`async.run_foreign(f, arg, abandoned?)` *(native, statically compiled)*:** Runs C-only `f(arg)` on libuv's worker pool (never touches Lua/Titan; Windows workers start with 53-bit x87 precision). Cancellation never stops `f(arg)`. **State-close trap:** during `lua_close`, a parked Task unwinds *before* `f(arg)` returns—never free raw `arg` in `defer`. Use `owned` storage or C-only `abandoned(arg)` (runs on closing thread *only* on state-close unwind after `f` returns; on normal/catch paths free via flag).
- **`ExternalWait` & `external_wake_t` *(native)*:** Multiplex cross-thread waits onto the Runtime's shared `uv.external_wake_t` (reserve without loop liveness; activate on wait; producers call `uv.native_external_wake_{retain,notify,release}`). Cancel calls `unregister_fn()` synchronously—relay exclusive wakeups to another waiter. `native_external_wake_unregister(target)` is destination-loop-thread-only (clear your map/borrow first); `external_wake_t:close()` returns `EBUSY` while any registration remains.
- **`prepare_native_retirement`:** Binds to `run_with_cleanup`'s 3rd arg, holding terminal status/listeners until `retire(ctx)` returns `0`; negative status escapes `async.loop()` as `OperationError("async.native_retirement.retire")` keeping barrier/Runtime intact so the next `async.loop()` retries once before blocking.
- **`add_close_listener` & Lua-state close:** `async.add_close_listener(fn)` runs once outside Tasks *after* `uv.loop_close` (never yield/start work; remove on owner close). Closing a Lua state with an active Runtime unwinds Tasks in a finalizer and calls `uv.loop_abandon` (no user callbacks/close listeners; `async.run` raises `"cannot start a Task during Lua state close"`).

## Public `titan.uv` lifecycle, views & critical hazards

- **Loop & handle ownership:** Construct `uv.loop_t()` + `uv.loop_init(loop)` (`--no-uv-bootstrap` if importing `async`). Every successful `*_init` (even nil callback, rejected start, or failed `spawn`) requires `uv.close(owner:as_handle_t(), cb?)`; `stop`/`unref` ≠ close. Nil `cb` still closes; `uv.close` raises on fresh/retired/closing; never query `is_closing`/`is_active`/`has_ref` inside a close callback unless reinitialized first.
- **Loop drain & timers:** Order: close all handles → `uv.run(loop, nil)` → `uv.loop_close(loop)` (`loop_alive` false can still `EBUSY` on stopped/unreffed handles; `uv.run` returns liveness int; avoid `check(uv.loop_close)` in `defer` where `EBUSY` masks primary errors). `uv.now` is cached (`uv.update_time` after slow work); `timer_again` on never-started timer → `EINVAL`; second `start` on active `idle`/`prepare`/`check`/`fs_poll` is a no-op (stop first).
- **Views, unions, constants & tuples:** No subtyping—use `:as_handle_t()`, `:as_stream_t()`, `:as_req_t()`. `handle_type`/`req_type`/`tty_mode_t` are unions—use `case`, never `==`. Platform constants (`AF_UNIX`, `SIG*`, `S_I*`) are `integer?`—check `== nil` first. Tuples `(status, val?, len)`: bind `val?`, check `status` first; capacity queries (`cwd`, `exepath`, `os_getenv`, `fs_event_getpath`) never auto-retry on `ENOBUFS`.
- **Optional `uv` callbacks require explicit param annotations:** Optional callback parameters typed `(function (...): ())?` (`uv.close`, `uv.write`, `uv.write_string`, `uv.write2`, etc.) **cannot infer unannotated lambda parameter types**—always annotate them explicitly (e.g., `function (_: uv.handle_t)` or `function (_: uv.write_t, status: integer)`).
- **Request data, FS & DNS:** Six requests have concrete `{get,set}_data` (`write`, `connect`, `fs`, `getaddrinfo`, `shutdown`, `work`); `getnameinfo_t`/`random_t`/`udp_send_t` use `uv.req_{get,set}_data(x:as_req_t(), ...)`. `nil` callback = **sync** mode on FS/DNS/random. Only `fs_t` needs `uv.fs_req_cleanup` (even on rejection; copy `fs_get_*` *before* cleanup). `fs_opendir` needs `fs_closedir`; `fs_open`/`fs_mkstemp` fds outlive cleanup; `getaddrinfo` needs `uv.freeaddrinfo(res)`. Only `fs`/`getaddrinfo`/`getnameinfo`/`random`/`work` support `uv.cancel` (writes→`EINVAL`; `0`/`EBUSY` still deliver one callback).
- **Streams, pipes & process:** Keep write buffers immutable until callback (`write_string` retains string); `try_write` short positive return is partial. Exact signatures: `uv.accept(server: uv.stream_t, client: uv.handle_t): integer` (2nd arg is `client:as_handle_t()`, **NOT** `uv.stream_t`); `pipe_connect` is void—use `uv.pipe_connect2(req: uv.connect_t, handle: uv.pipe_t, name: string, namelen: integer, flags: integer, callback: uv.connect_cb): integer` (`flags` comes **before** `callback`). `CREATE_PIPE` needs a fresh untouched `pipe_init` on the spawn loop (any native I/O/handoff consumes eligibility, even on failure); `process_t` close never kills/reaps a child (`is_initialized()`/`is_active()`).
- **UDP & TTY:** `udp_send`/`udp_try_send` reject empty vectors (use one 0-len `buf_t`); `udp_recv_start` `nread==0`+`addr~=nil` is an empty datagram (`addr==nil` is no-data); `UDP_RECVMMSG` allocs must be positive multiples of 64 KiB. Windows TTY `read_start`/`tty_set_mode` may fire inline (`uv.run`/`loop_close` reentry forbidden; `uv.close` ok); Windows CRT fds, `HANDLE`s, and `SOCKET`s are distinct.
- **Sync/threads:** Checked owners (`mutex_t`..`key_t`) go Fresh→Live→Retired (no GC destroy; `:borrow()` unrooted; `mutex_t.create_native()` pairs only with `native_mutex_destroy`—never `:borrow()`; `once_t()` has no init/destroy; `key_t` is OS-thread-local; `barrier_wait` returns `>0` serial/`0` others; `cond_*wait` has spurious wakes & relative ns; `thread_detach` needs nil `argument_owner`).
- **DLL, WTF-8 & native handoff:** `dlopen` returns `0`/`-1` (not `E*`); `dlclose` even after failed open; `dlsym` pointers die at `dlclose`. UTF-16/WTF-8 NUL asymmetry: `utf16_length_as_wtf8` excludes NUL; `wtf8_length_as_utf16` and `wtf8_to_utf16` include it. Native handoff (`tcp_t`/`pipe_t` `{to,from,discard}_transfer_payload`, `stream_transfer_status`, `{bind,unbind}_transfer_loop`): idle connected RW TCP or non-IPC pipe with nil userdata; manual-handoff rules (`titan-thread`).

```titan
local uv = import "uv"

function main(args: {string}): integer
  local loop = uv.loop_t()
  if uv.loop_init(loop) < 0 then return 1 end
  local timer = uv.timer_t()
  if uv.timer_init(loop, timer) < 0 then uv.loop_close(loop); return 1 end
  local fired = 0
  local st = uv.timer_start(timer, function (owner: uv.timer_t)
    fired = fired + 1
    uv.close(owner:as_handle_t(), nil)
  end, 1, 0)
  if st < 0 then
    if timer:as_handle_t():is_initialized() then uv.close(timer:as_handle_t(), nil) end
    uv.run(loop, nil); uv.loop_close(loop); return 1
  end
  uv.run(loop, nil)
  if uv.loop_close(loop) < 0 or fired ~= 1 then return 1 end
  return 0
end
```
