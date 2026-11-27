---
name: titan-ffi
description: Use for Titan C FFI/headers, callbacks, Lua interop (titan.lua), or browser JS (titan.browser, bindings.js). Covers foreign import/function, owned C storage, SDL/Cairo/Canvas/DOM/Three.js wrappers, require/lua.new, Wasm host imports, and runtime Lua C API; use titan-application for builds/deploy, titan-async for libuv/Tasks, skip plain C-backed stdlib use.
---

# Titan FFI, Lua Interop, and Browser JS Bindings

Use for C headers/types/callbacks (`foreign import`/`foreign function`), Lua interop (`require`, `import "lua"`), browser JS/Wasm bridges (`import "browser"`), or runtime Lua C API. Pair with `titan-programmer` (core syntax/records/const/defer), `titan-async` (libuv/`uv.native_*`/Tasks), `titan-application` (linking & browser builds), `titan-protobuf` (portable codecs), and `titan-tester` (tests).

## Non-negotiable invariants

1. **Thin Primitive-Only Foreign C & `bindings.js` Boundary:** BOTH native C shims/`foreign import` wrappers (SDL, Cairo, C libs) **and** browser `bindings.js` (`titan.browser` for Canvas 2D, Three.js, WebGL, DOM) MUST wrap **raw library primitives only**. Permitted plumbing: capability lookup, `BrowserValue` marshalling, `browser.pin`/unpin, handle/request teardown, listener attach/teardown, raw host event forwarding. Forbidden in C shims or `bindings.js`: rendering loops, scene/UI composition, layout/styling policy, state machines, event-handling policy—keep those in multi-module `.titan`.
2. **Unsafe Boundary & Narrow Owners:** `foreign import`, `foreign function`, raw pointers, and `titan.lua` are unsafe boundaries (Rust `unsafe`). Hold raw handles in `local` fields of exported `record`s (no `RawX` + ID registries), pair C handles with `defer` (non-yielding `gc.finalizable` only for sync release), and expose ordinary Titan types.
3. **No Closures as C Callbacks:** Titan closures cannot become C function pointers; write top-level restricted `[local] foreign function` (C-only, no `L`/`M`/GC/raises). On browser, invoke Titan synchronously from C via `browser.pin` + `titan_browser_call_sync`.
4. **Owned Bytes vs. Borrowed Pointers:** `owned *T`/`owned T[]` are GC-freed raw-byte userdata with **no C destructor**. Pointers borrowed from automatic locals, `owned`, or embedded fields never retain their owner. `value as foreign *T` is an unchecked lightuserdata/nil cast.
5. **Lua Edge Dynamics vs. Internal Strictness:** Lua→Titan edges run **dynamic conversion** (`2.0 -> integer`, truthiness `-> boolean`, strings reject numbers); internal `value -> T` and container reads run **strict guards** (`2.0` rejected). Custom `_ENV` in `lua.load` is not a sandbox.
6. **Conditional reference reads:**
   - **MUST read `skill://titan-ffi/references/runtime-lua-c-api.md`** before writing/auditing stdlib/runtime `lua_*`/`luaL_*`, runtime C shims, or authored browser-runtime JS (`titan-browser.mjs`, `titan-wasm-factory.mjs`).
   - **MUST read `skill://titan-ffi/references/browser-wasm-c-imports.md`** before compiling browser `--c-source` helpers, `TITAN_WASM_IMPORT`/`create({ imports })`, sync C callbacks (`browser.pin` + `titan_browser_call_sync`), or Wasm-EH `longjmp`.

## Start with the right tool

| Job | Mechanism |
| --- | --- |
| C headers / GC C storage | `foreign import "hdr.h"` (`ffi.*`); `owned *T`/`owned T[]`, embedded field, or fused `local const` tail |
| C callback (`qsort`, toolkit) | Top-level `[local] foreign function` (never a Titan closure) |
| Passed Lua fn / dynamic Lua | Typed `function (...)` param; `local lua = import "lua"` (`load`, `require`, `new()`) |
| Weak maps / libuv `uv.native_*` | `import "gc"` (`titan-stdlib`); `import "uv"` (`titan-async`; never `foreign import` libuv) |
| Browser JS/Canvas/Three.js/DOM | `local browser = import "browser"` (thin primitive `bindings.js` only) |
| Portable typed copies (JS/native) | `local protobuf = import "protobuf"` (`titan-protobuf`) |
| Browser C helpers / runtime `lua_*` | `references/browser-wasm-c-imports.md` / `references/runtime-lua-c-api.md` |

## C FFI: headers, types, calls, casts, and storage

- **Headers & linking:** `foreign import "<hdr>"` emits direct C calls (no `libffi`), preprocessing in order (`.titan` source-import `.ffi.h`s → folder main → contributors by filename). Absolute/source-relative headers emit `"..."`; `"titan/ffi.h"` resolves from SDK (`lua_State`, `TValue`, `Udata`); others emit `<...>`. Link native libs via `titanc -I -D -L -l --c-source` (`titan-application`); never link bundled `libuv`/`lpeglabel`.
- **Namespaces & types:** `ffi` is compile-time-only (`ffi.<fn|var|enum|macro>`; `ffi.x = 1` fails—write via pointer/index/field or setter). Prefix C types with `foreign` at Titan sinks; omit inside foreign constructors (`foreign *(*int)`, `owned (*int)[]`). C99 primitives (`void`, `bool` [`_Bool`, not `boolean`], int/float ranks) need no header. File-scope `struct`/`union` tags work directly (`foreign tm`; `typedef` wins); keywords work in C names (`ffi.type`, `obj.repeat`).
- **Layout, typedefs & exports:** `foreign T.sizeof`/`alignof` yield checked `integer` (`size_t` in foreign bodies). `foreign type Name = foreigntype` (no `local`) emits a local `typedef` in `.ffi.h`, inherited only by `.titan` source imports (no `owned` RHS). Exportable C types: complete non-GC non-FAM aggregates, portable primitives/pointers/callbacks, eligible `owned`, named header typedefs/tags (enums/anonymous structs stay private). Header-dependent exports force importers to `foreign import` compatible headers; prefer header-free Titan records with `local` C fields.
- **Calls, variadics & out-params:** `ffi.fn(...)` uses strict C arity (named calls need nonvariadic prototypes with unique param names). **Cast numeric args to C variadics (`printf`/`snprintf`) to exact format types** (`n as foreign long long`, since `integer` is `lua_Integer`); Titan `...`/spreads cannot feed C `...`. `ffi.fn` is not a closure. Mutable local `T` → `foreign *T` (`*T` → `foreign *(*T)`) passes its address; by-value expr → `foreign const *T` takes a call-scoped address. Address-exposed mutable locals keep a stable home across `raise`/`catch`.
- **Strings, casts & options:** Titan `string` → `foreign const *char`/`*void` is zero-copy for the call only (never store/mutate/free). C → Titan uses written casts: `ptr as string` (NULL-checked to `\0`); `ptr as string(n)` (exact `n`-byte binary copy; `n == 0` returns `""` even on `NULL`; `ptr is string(n)` checks without reading; add `;` before next-line `(...)`); `owned char[] as string` copies exact length. Typed sinks insert checked C↔Titan numeric conversions, `nil -> NULL`, pointer truthiness, and array decay. Options never chain: unwrap `(owned *int)?` to `owned *int` before `foreign *int`. `value -> foreign *T`/fn-ptr, `*void -> *char`, and fn-ptr ↔ `*void` need written `as`.
- **C-mode ops & macros:** Any C operand on `- ~ + - * / % & | ~ << >> < <= > >= == ~=` uses C99 arithmetic (truncating `/`, C promotions, signed overflow/shift UB: `c_int + 1` is C `int`). Cast to `integer` *before* the op for Titan semantics. `// ^ and or not .. #` stay Titan-only. Object-like macros (`ENOENT`, `INFINITY`, `SIG_IGN`, `errno`, dotted projections like `st_mtime`) import via `ffi.*`; wrap function-like macros in `static inline`.
- **0-based indexing, `owned`, FAM & embedding:** Raw pointers/`foreign T[]` are NULL-checked only (no bounds/`#`); fixed arrays, `owned T[]`, and FAM structs with live provenance are bounds-checked with `#`. Direct locals: `foreign T.new()`/`.new_array(N)` (const `N`) = stack-automatic (never escape pointer); `owned *T`/`owned T[]` = GC userdata (outer `const` rejected; no destructor). FAM uses `foreign F.new(count)` only. Mutable pointer locals default to `NULL`; others/`const` need initializers. Fixed non-GC C structs/arrays in records/unions copy on construction and yield borrowed interior pointers (keep owner alive). Fresh `foreign T.new_array(n)`/`F.new(n)` directly inside a generated constructor for a `const` `foreign T[]`/`*F` field fuses into **one userdata allocation** (init self-referential handles *after* construction). Ordinary functions get readonly `L: foreign *lua_State` (current-call-only; never save/return/re-enter active ancestor threads) and `M` (`M as foreign *Udata` with `"titan/ffi.h"`).

## Source-defined foreign functions and C callbacks

Top-level `[local] foreign function name(p1: C1, ...): CR ... end` (omit `: CR` for `void`) emits a plain C-ABI function (no `lua_State *`, GC frame, or error handler). Exported entries need exportable C types, emit compiler-owned `<module>.titan.h` beside `<module>.ffi.h` (never hand-edit), and are callable from Titan modules and C (invisible to Lua `require`); `local foreign function` stays module-private (+ `.titan` source imports). Callback pointer type: `foreign function (P...): R` (already a pointer; canonical address).

- **C-only subset:** Omit `foreign` in signature/body (`l: const *void`, `local x: int = 0`, `p as *int`), keeping it only on `foreign T.new()`/`.new_array(N)`/`.sizeof`/`.alignof`. Allowed: C params/locals, `ffi.*`/foreign calls, C ops/casts/fields/indexing, `do`/`if`/`while`/`repeat`/numeric `for`/`break`/`return`, zeroed block-automatic `.new()`/`.new_array(N)`/`.new(N)` (const `N`). Rejected: Titan globals/fns/records/methods, `L`/`M`, `raise`/`catch`/`defer`/`case`/`for..in`, lambdas, `owned`, dynamic `.new_array(n)`, `# .. // ^ and or not ? is as string(n)`. Raw ops skip NULL/bounds/overflow checks; Titan guarantees left-to-right single evaluation.

```titan
local io = import "io"
foreign import "stdio.h"
foreign import "stdlib.h"

local foreign function cmp_desc(l: const *void, r: const *void): int
  local a, b = (l as const *int)[0], (r as const *int)[0]
  if a > b then return -1 elseif a < b then return 1 end
  return 0
end

record IntBuf
  const len: integer
  local const data: foreign int[]
end

function IntBuf.from(xs: {integer}): IntBuf
  local b = IntBuf(#xs, foreign int.new_array(#xs)) -- fused single userdata
  for i = 1, #xs do b.data[i - 1] = xs[i] end
  return b
end

function IntBuf:max_text(): string
  ffi.qsort(self.data, self.len, foreign int.sizeof, cmp_desc)
  local out: owned char[] = foreign char.new_array(32)
  local n: integer = ffi.snprintf(out, 32, "max=%lld", self.data[0] as foreign long long)
  if n < 0 then raise "snprintf failed" end
  local p: foreign *char = out
  return p as string(n)
end

function main(_args: {string}): integer
  io.print(IntBuf.from({3, 1, 5, 2}):max_text()) -- max=5
  return 0
end
```

## Browser JavaScript bindings (`titan.browser`)

**Thin primitive-only `bindings.js` (Invariant #1):** Wrap raw Canvas 2D, Three.js, WebGL, and DOM primitives + bridge plumbing (capability lookup, `BrowserValue` marshalling, `browser.pin`/teardown, raw event forwarding) only; keep rendering, scene/UI composition, styling, state machines, and event policy in multi-module `.titan`.

`local browser = import "browser"` is `--target browser` only. Never cast closures to addresses, touch `lua_State *`, use `externref`, or add sync JS→Titan calls. Builds/deploy: `titan-application`; Tasks/`callTask`: `titan-async`; C helpers/`TITAN_WASM_IMPORT`/`create({ imports })`/sync C callbacks: **MUST read** `skill://titan-ffi/references/browser-wasm-c-imports.md`.

- **Lookup & `BrowserError`:** `browser.binding(name)` looks up literal keys in `create({ bindings })` (no globals/`eval`; bind `this` in JS; keeps `false`/`0`/`null`/`undefined`). `titan:*` keys are SDK-reserved (`TypeError`)—use `timer`/`os`/`http`/`websocket`. Throwing bindings raise `browser.BrowserError` (`const message: string`, `const thrown: BrowserHandle`); catch `error is browser.BrowserError` and call `err:close()`. Handle-creation failure raises a string; traps/aborts/protocol errors poison the instance.
- **`target:call(...: BrowserValue): BrowserValue` marshalling (strict runtime type):**

| JS (in) | `BrowserValue` | JS (out) | Trap |
| --- | --- | --- | --- |
| `null`/`undefined` | `is_nil()` | `null` | `undefined` → `null` |
| `boolean` | `is_boolean(boolean)` | `boolean` | — |
| Signed i64 `BigInt` (`5n`) | `is_integer(integer)` | `BigInt` | `Number` `5` → `is_float(5.0)`; overflow → `TypeError` |
| `Number` | `is_float(float)` | `Number` | Keeps `NaN`, `-0` |
| UTF-16 `string` | `is_string(string)` (UTF-8) | `string` | Lone surrogates → `TypeError`; bad UTF-8 raises |
| `Uint8Array` | `is_bytes(string)` (copied) | `Uint8Array` | Arbitrary bytes (incl. NULs) |
| Titan callable wrapper | `is_callable(fn)` | Same wrapper (`===`) | Recovers original closure & captures |
| Object/Array/fn/Promise | `is_handle(BrowserHandle)` | Underlying JS value | Holding `Promise` never observes rejections |

- **Handles, callables, requests & copies:** `BrowserHandle`/`BrowserRequest` have idempotent `:close()` (state-owned; handles finalize, state close retires rest). Use `defer h:close()` locally; `main`'s `defer`s run before `drain()`/events, so store callback handles on a long-lived owner closed at teardown/`dispose()`. Export `function(...: BrowserValue): BrowserValue` via `is_callable(fn)` (bound `self:m`/lambda, never `self.m`). JS→Titan calls (`instance.call`/`fn.call`) return Promises (raises reject `TITAN_BROWSER_TITAN`); `call`/`callTask`/`drain` inside a binding rejects `TITAN_BROWSER_REENTRY` (use `notify()` + `drain()`). Callables stay pinned via JS wrapper (`wrapper.release()`—sync, idempotent, safe in bindings), active `start`/`listen`, or `BrowserPin`. Break JS↔Lua cycles via `release()`, `:close()`, and `await instance.dispose()` in `finally`. `start(ok, fail, ...)` expects `{ kind: "detachable"|"retained", promise, cancel? }` (`ok(val)`, `fail(msg, thrown)`); `listen(ok, fail, ...)` expects `{ kind: "listener", subscribe(emit): unregister }` (FIFO; cancel/close drops remaining events). `browser.failure_text(msg, thrown)` closes `thrown` and returns `msg`; uncaught `ok`/`fail` errors hit `onNotificationError`; `start`/`listen` during `dispose()` raise `BrowserError("browser state is closing")`. Copied nominals/Arrays: `protobuf.portable` (`describe()` as `is_string`, `encode()` as `is_bytes`, `titan-protobuf.mjs`—`titan-protobuf`). `lua.new()` loads `titan.browser` (`is_owner() == false`, no Tasks).

```titan
-- file: counter_bridge.titan
local browser = import "browser"
local type Val = browser.BrowserValue

record Counter
  local count: integer
  local const set_text: browser.BrowserHandle
  local listener: browser.BrowserRequest?
end

local function Counter:on_click(...: Val): Val
  case ...[1]
  when is_integer(d) then self.count = self.count + d; self:render(); return Val.is_integer(self.count)
  end
  raise "expected BigInt"
end

function Counter.mount(): Counter
  local self = Counter { count = 0, set_text = browser.binding("set_text"), listener = nil }
  local ok = false; defer if not ok then self:close() end
  local on_click = browser.binding("on_click"); defer on_click:close()
  self.listener = on_click:listen(self:on_click, function(...: Val): Val
    browser.failure_text(...[1], ...[2]); return Val.is_nil()
  end)
  self:render(); ok = true; return self
end

function Counter:render(): boolean
  self.set_text:call(Val.is_string("Count: " .. self.count)); return true
catch
  if error is browser.BrowserError then local e: browser.BrowserError = error; e:close(); return false end
  raise
end

function Counter:close()
  local r? = self.listener
  if r then self.listener = nil; r:close() end
  self.set_text:close()
end
```

```javascript
// Thin bindings.js: raw DOM/event primitives only (BigInt 1n -> Titan integer).
export const makeBindings = (el, btn) => ({
  set_text(s) { el.textContent = s; },
  on_click: () => ({ kind: "listener", subscribe(emit) {
    const fn = () => emit(1n); btn.addEventListener("click", fn);
    return () => btn.removeEventListener("click", fn);
  }}),
});
```

## Lua interoperability and `titan.lua`

- **Lua→Titan:** `require "titan"` installs the searcher once (preinstalled in Titan exes, `lua.new()`, `thread` workers); load stdlib as `titan.*` (`require "titan.os"`). Modules are protected userdata (read-only fns, `Mod.Rec(...)` via `__call` if `new` is public, dynamic writes on mutable vars; `const`/unknown/`local` raise). Lua calls are positional-only (`mod.f { a = 1 }` passes a table); void fns return 0 values; errors cross to `pcall`/`xpcall` with `require("titan").backtrace()`. No recursive scans. Maps = aliased tables; Arrays = userdata proxies preserving `{T}`/`const { T }` and holes (plain tables rejected; `table.*` works; `rawget`/`rawset`/`rawlen` fail); records expose public fields/methods (`local` raises); unions are opaque (`case` only in Titan); Interfaces are read-only wrappers (accept wrappers or records/unions with a compiled witness).
- **Dynamic loading (`import "lua"`):** Pass Lua functions to typed `function (...)` params when possible. `lua.load(chunk, name?, env?)`/`load_from_reader(reader, name?, env?)` compile binary-safe chunks into `function(...: value): (...: value)`, raising on error (`env` sets `_ENV`, **not** a sandbox; `load_from_reader` never closes `reader`). `lua.dofile` is **native-only** (async Task). `lua.require(modname): value` shares `package.loaded`, searches preload → async `fs` `package.path` (no-fs miss on browser) → `package.searchers[3..]` (non-yieldable), rejecting recursive/concurrent same-module loads.
- **Independent states (`lua.new()`):** Isolated globals/GC snapshotting zero-upvalue native C preload loaders (incl. initialized Titan modules). Pair with `defer state:close()` (idempotent; `detach()` transfers idle `foreign *lua_State`). Values cross via `transfer.TransferValue` (copied strings/protobuf nominals/custom hooks/snapshotted closures; borrowed `is_pointer`/`is_lua_state`/`is_function` need caller liveness; **no packet-attached `thread.Sender`/`Receiver`**—use `titan-thread`/`async.Receiver`). Native adds `run_async`/`run_async_from_loader` on libuv's worker pool (1 active call/handle; cancellation waits for worker; two-phase `async.Receiver` bootstrap must drain all `async.send` calls before remote close). Browser omits `dofile`/`run_async*`; `lua.new()` runs sync on owner thread (no browser Tasks; `os.clock` raises, `os.exit` delegates to linked `titan.os` only in an owner-state Task).

```titan
local io = import "io"
local lua = import "lua"
local transfer = import "transfer"

function main(_args: {string}): integer
  local fn = lua.load("local n = ...; return n * k", "=s", { ["k"] = 7 })
  local n: integer = fn(6)
  local st = lua.new(); defer st:close()
  local res = st:run("return string.upper(...)", "=u", transfer.TransferValue.is_string("ok:" .. n))
  case res when is_string(s) then io.print(s) else raise "bad result" end
  return 0
end
```

## Pre-delivery verification checklist

- [ ] Native C shims and `bindings.js` wrap raw primitives only; rendering, scene/UI, styling, and event policy live in `.titan`.
- [ ] Raw C handles live in `local` record fields (no `RawX`/ID registries) with `defer` cleanup (`gc.finalizable` only for sync release).
- [ ] C variadics cast `integer` args explicitly; C-mode ops cast to `integer` first; C callbacks use `[local] foreign function`.
- [ ] Browser ints cross as `BigInt` (`5n`), `BrowserError` calls `err:close()`, local handles/requests use `defer :close()`, cycles break via `release()`/`:close()`/`dispose()`.
- [ ] Runtime `lua_*` follows `references/runtime-lua-c-api.md`; browser Wasm imports follow `references/browser-wasm-c-imports.md`; native and `--target browser` examples compile cleanly.
