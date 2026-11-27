# Browser Wasm C Helpers, Host Imports & Synchronous C Callbacks

Read only for `--target browser` C helpers (`--c-source`), Wasm imports (`TITAN_WASM_IMPORT` / `create({ imports })`), sync C callbacks (`browser.pin` / `titan_browser_call_sync`), or bridge edits. For app JS/ES modules (Canvas 2D, Three.js, DOM), prefer `create({ bindings })` + `import "browser"` (`skill://titan-ffi`).

Generated `.mjs` images are self-contained (zero external `import`s). Keep C/JS Titan-first: wrap host capabilities only; keep state, policy, and validation in Titan.

## 1. Wasm-EH `longjmp` & Build Contract (`wasi-sdk` 34)

- **EH/SJLJ:** Browser Lua, runtime, generated C, providers, and `--c-source` use Wasm `exnref` (`-mexception-handling -mllvm -wasm-enable-sjlj -mllvm -wasm-use-legacy-eh=false`, `-lsetjmp`), plus Binaryen `wasm-opt --stack-check`. Mismatched objects fail target identity.
- **Defines/env:** `TITAN_TARGET_BROWSER=1`, `TITAN_COROUTINE_STACK_SIZE=262144` (256 KiB Task stack). Clear native `TITAN_PATH_0_6` and `TITAN_EXTRA_*`.
- **JSPI/faults:** JSPI is the sole coroutine backend (`catch`/`defer`/unwind survive suspensions; no JS SJLJ trampolines); `LUAI_MAXCCALLS=100`. Wasm EH catches language `longjmp` only; traps (`TITAN_BROWSER_TRAP`), `--stack-check` overflow (`RuntimeError: unreachable`), clobbered cookies (`TITAN_BROWSER_ABORT`), and JS exceptions poison the instance.

## 2. C Imports & `create({ imports })`

- **Headers:** Include `"titan/browser.h"`; annotate imports with `TITAN_WASM_IMPORT("name")` (`titan/ffi.h`: `__attribute__((import_module("env"), import_name("name")))` on `__wasm__`) or explicit `import_module`/`import_name`. Pass C files via `--c-source helper.c -I dir` (no `.c` file is needed merely to declare an import or `local foreign function`).
- **`create({ imports })`:** Plain object (any realm/null-prototype) or **sync** factory `(ctx) => importObject` called once pre-instantiation. Inner maps must be plain objects; arrays, `Map`s, class instances, and async promises throw `TypeError` (`"must be a plain object …"`).
- **Reserved:** Never override `wasi_snapshot_preview1.*`, `env.titan_browser_*`, `env.titan_mco_*`. Object form throws `TypeError` in `create()`; factory form rejects `initialize()`/`run()` with `TITAN_BROWSER_PROTOCOL` (`cause` = `TypeError`).
- **`ctx`:** `memory`, `table` (`__indirect_function_table`; call C fn ptrs via `ctx.table.get(fnPtr)`), `exports`, `HEAPU8`/`HEAPU32` (live getters—never cache across growth), `readCString(ptr)`, `readBytes(ptr, len)`, `writeBytes(ptr, bytes)`, `trace`, `abort(msg)`.
- **Suspension:** Imports may wrap async JS in `new WebAssembly.Suspending(asyncFn)`—**never** inside a sync C callback.

## 3. Synchronous C Callbacks (`browser.pin` + `titan_browser_call_sync`)

```text
-- browser: pin(fn: function(...: BrowserValue): BrowserValue): BrowserPin
-- BrowserPin:identity(): (integer, integer, integer) [slot 0 after close]; :close()
int titan_browser_call_sync(const titan_browser_identity *callable, uint32_t argc,
    const titan_browser_value *args, titan_browser_sync_result *result);
```

C invoked via `ctx.table.get(fnPtr)` runs synchronously below a JS frame (not a loader entry):

1. **Rooting:** `browser.pin(fn)` adds a hold (raises `"browser state is closing"` on close; `close()` is idempotent; unreachable pins finalize). Root both `BrowserPin` and `owned *titan_browser_identity` in a long-lived owner **before** C sees the pointer; unregister **before** `pin:close()` and dropping the owner.
2. **Result/`free`:** Pass zeroed `titan_browser_sync_result` (`foreign titan_browser_sync_result.new()`). Statuses (`result.status` & return): `TITAN_BROWSER_OK` (`0`, `result.value`), `TITAN_BROWSER_TITAN_ERROR` (`1`, raise or stale `"browser callable is released"`, `message`/`trace`, instance usable), `TITAN_BROWSER_STATE` (`3`, closing/disposing/exited/poisoned/nesting, `message`), `TITAN_BROWSER_MEMORY` (`4`, empty). After **any** status, `free` `message`, `trace`, and `STRING`/`BYTES` `value.bytes` (`ffi.lmacro_unconst(...)` in Titan).
3. **Ownership:** `HANDLE` args are borrowed (`titan_browser_host_retain` gives callee its own unit; callee `:close()` never retires C's slot). `HANDLE` results live while open; `CALLABLE` results add **no pin** (valid only while a `BrowserPin`/JS wrapper holds them).
4. **No-switch/wake/reentry/poison:**
   - Per-depth callback thread (`titan_no_switch(L)` true): `coroutine.running()` is `nil`; coroutine switches/`async` waits raise; `async` acts outside a Task.
   - Open owner `BrowserPin` is a wake source (`relinquish(true)` uses `WAIT_HELD`, parking instead of `RELINQUISH_IDLE`).
   - Bindings in a callback reject `call`/`callTask`/`drain`/`run` (`TITAN_BROWSER_REENTRY`); outer JS queues them until return.
   - Any JS/Wasm exception unwinding out of `call_sync`—incl. `WebAssembly.Suspending` (V8 throws `SuspendError` first)—poisons (`TITAN_BROWSER_PROTOCOL`, `"a synchronous C callback ended by an exception"`).
   - Uses interrupted stack (256 KiB for a Task); deep recursion hits `--stack-check` and poisons.

### Headless runnable example (`host_cb.h`, `cb_demo.titan`, `host_imports.mjs`)

```c
/* host_cb.h */
#include "titan/browser.h"
typedef int (*host_cb)(void *userdata);
TITAN_WASM_IMPORT("host_dispatch")
int host_dispatch(void *userdata, host_cb cb);
```

```titan
-- file: cb_demo.titan
local browser = import "browser"
foreign import "host_cb.h"
foreign import "stdlib.h"
foreign import "titan/browser.h"
foreign import "titan/ffi.h"

local type Value = browser.BrowserValue

local record Slot
  const pin: browser.BrowserPin
  const id: owned *titan_browser_identity
end

local slots: {Slot} = {}
local hits = 0

local function on_tick(...: Value): Value
  hits = hits + 1
  return Value.is_integer(hits)
end

local foreign function dispatch_cb(ud: *void): int
  local res = foreign titan_browser_sync_result.new()
  local st = ffi.titan_browser_call_sync(ud as const *titan_browser_identity, 0, nil, res)
  local out: int = -1
  if st == ffi.TITAN_BROWSER_OK then
    if res.value.kind == ffi.TITAN_BROWSER_INTEGER then
      out = res.value.scalar.integer as int
    elseif res.value.kind == ffi.TITAN_BROWSER_STRING then
      ffi.free(ffi.lmacro_unconst(res.value.bytes))
    elseif res.value.kind == ffi.TITAN_BROWSER_BYTES then
      ffi.free(ffi.lmacro_unconst(res.value.bytes))
    end
  end
  ffi.free(ffi.lmacro_unconst(res.message))
  ffi.free(ffi.lmacro_unconst(res.trace))
  return out
end

function main(_args: {string}): integer
  local pin = browser.pin(on_tick)
  local id: owned *titan_browser_identity = foreign titan_browser_identity.new()
  local s, sl, g = pin:identity()
  id.state, id.slot, id.generation = s, sl, g
  local idx = #slots + 1
  slots[idx] = Slot(pin, id)     -- root BEFORE C sees pointer
  defer do
    ffi.host_dispatch(nil, nil)  -- unregister BEFORE closing pin
    slots[idx] = nil
    pin:close()
  end
  if ffi.host_dispatch(id, dispatch_cb) ~= 1 then raise "callback mismatch" end
  return 0
end
```

```javascript
// host_imports.mjs — "$PREFIX/lib/titan-browser/0.6/titan-browser-run" --root . --imports host_imports.mjs out/cb_demo.mjs
export default (ctx) => ({
  env: { host_dispatch(ud, fnPtr) { return fnPtr === 0 ? 0 : ctx.table.get(fnPtr)(ud); } },
});
```

## 4. Host Lifecycle, Fixed wasm32 ABI & Bridge Maintenance

- **State close/child states:** `titan.browser`'s `gc.finalizable` record runs after later finalizers (sync calls, output, `:close()` valid; new requests/listeners/reverse calls refused via `titan_state_closing`). Earlier finalizers see inert `:close()`/`release()` and raising calls. `lua.new()` loads `titan.browser` normally (`is_owner() == false`, no Task drive).
- **wasm32 ABI (`titan/browser.h`):** `_Static_assert` sizes: `titan_browser_value` 32 B, `delivery` 32 B, `completion` 48 B, `response` 56 B; `0` is never live (state/slot/gen/64-bit `operation_id`). Promised exports (`initialize`/`entry`/`invoke`/`close`) emit one completion; throwing imports fill `response`; trusted imports (`adopt`/`release`/`state_*`) never throw.
- **Sync `release_callable`/bracket:** `wrapper.release()` enters `titan_browser_release_callable` synchronously (no op ID/completion): protected, no-switch, stops GC (`GCSTPGC` via `lmacro_get_gcstp`/`lmacro_set_gcstp`) so root-slot polls cannot run finalizers mid-release; refused releases keep pins until state close. `titan_browser_callback_enter`/`leave` bracket stdlib trampolines on `frame->L` (not app API).
- **Bridge JS invariants:** Copy `Uint8Array` by content; re-read `HEAPU8`/`HEAPU32` after growth (copy aliased sources first); <= 1 sink in flight/stream; module-scope continuations with detachable mailbox cells; copy `create({ imports })` into null-prototype maps; after poison, skip C cleanup/response writes; drop context before awaiting disposal promises.
