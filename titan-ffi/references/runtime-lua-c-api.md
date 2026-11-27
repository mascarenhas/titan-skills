# Trusted Lua C API & Runtime Boundary

> **Not public FFI.** `foreign import "lua.h"` emits plain C calls with no stack-effect, GC rooting, relocation, or `longjmp` metadata. Restricted to audited, module-private stdlib/runtime code under `titan/` (`async`, `coroutine`, `gc`, `iteration`, `reflect`, `test`, `transfer`, `browser`, `http/parser`, `lua/*`, `peg/native`, `protobuf`, `string/*`, `thread/*`, `uv/*`). App code uses typed callables, `import "lua"`, `import "gc"`, and `pointer as string(n)`.

## Six guard-rails for stdlib/runtime C and authored browser JS

Every added `lua_*`/`luaL_*`, authored runtime C, or browser JS line (`titan-browser.mjs`, `titan-wasm-factory.mjs`, compiler JS, `create({ imports })`) must satisfy (`doc/implementation/standard-library-maintenance.md`):

1. **Layering — keep work in Titan; minimize C and JS.** Place each native piece strictly by how C or the host reaches it:

| Need | Required placement |
| --- | --- |
| C callback ptr (`uv_*`, `__gc`, `lua_CFunction`) | `local foreign function`, address taken |
| Named C helper / C-only critical interval (mutex, atomic handoff, non-raising move) | `local` or public `foreign function` (exported via `.titan.h` for C callers) |
| Exact unmangled C/Wasm symbol | Compiler-generated 1-line (weak if optional) forward to public `foreign function` |
| Entrypoint & image lifecycle (`main`, browser `initialize`/`entry`/`close`) | Compiler-generated launcher sharing one error/trace implementation |
| Browser runtime JS (`titan-browser.mjs`, `titan-wasm-factory.mjs`, `create({ imports })`) | **Only** host-only ops: JSPI suspend/resume, engine failure, JS/host storage & conversion, host scheduling/events (`setTimeout`, `MessageChannel`, `AbortSignal`, listeners, promises), embedder API, stack capture. 1-line forwards (`trusted`/`response`); state/policy/validation/timers stay in Titan |
| Struct access & marshalling | `foreign import` in Titan; headers hold layouts, prototypes, and 1-expr inline bridges (`lmacro_*` in `titan/ffi.h`) for macros/incomplete fields/`const` casts |
| Platform-conditional native code | `static inline` in `*_platform.h`/`*-native.h` taking formals and returning status/plain struct (errors stay in Titan); zero-arg facts are macros read via `ffi.*` (`TITAN_PATH_WINDOWS`) |

2. **Plain C stays plain C.** Keep C-only data in C locals/formals/status returns—never on the Lua stack. Never `lua_pcall` a C fn Lua never sees for protection; return status. A runtime `lua_CFunction` needing scratch across raising Lua calls anchors userdata on its own stack slot, never `luaL_ref`.
3. **Protected work in Titan.** Catch errors in Titan via `catch`/`defer` (`error`, `traceback`). Native callback trampoline: recover state/owner/closure/entry → push owner if handler may drop last ref → call entry → restore top. Browser JS imports catch at boundary and fill `titan_browser_response` so Titan raises; JS exceptions never unwind Wasm, and throws in trusted imports/sync callbacks poison the instance.
4. **Pinning & placement.** Store per-state roots in module vars (`loop.handles`, `pins_by_slot`) or owner fields (`gc.finalizable` state), never `luaL_ref`, registry, or uservalue tables (registry only for pre-module anchors). Cross-state maps live in host (JS token map), not C statics. Browser JS holds only host-lifetime values/promises/pending-reentry—never mirror Titan counts/queues; Titan passes facts (`WAIT_HELD`, `ready_head == nil`).
5. **Rooting.** Callers root Titan parameters until return; frame slots root locals (refreshed on decl/assign, reused after block exit). Declare owners needing wider lifetime in an outer block. Never `lua_pushtvalue` a param/local solely to root it. A `foreign function` invoking a native entry acts as caller and roots what it passes.
6. **Don't duplicate receiver checks.** Marshal dynamically typed peers once by runtime type into one tagged union (`BrowserValue`) so the receiver `case`s/rejects. Validate each fact once on its owning side (Titan: closed handle, inactive drive, pin gen; JS: brand, instance, sync release, op-ID exhaustion).

## Current-state stack transaction & GC invariants

Every current-state helper pushing onto the Lua stack uses one transaction (`doc/implementation/ffi-lua-api-followup.md`):

1. Snapshot `local top = ffi.lua_gettop(L)` before the first push and immediately `defer ffi.lua_settop(L, top)` (never ad-hoc pops).
2. Reserve full max temporary slots with `lua_checkstack` (`luaL_checkstack` in foreign bodies) before pushing; keep a path-by-path ledger covering optional lookups and zero-result paths.
3. Copy surviving collectables before restore via **two-step `foreign TValue` → `value` → `as T`**: `ffi.lua_totvalue(L, idx)` returns **`foreign TValue`** (not concrete Titan types like `string`/`function`; direct `local s: string = ffi.lua_totvalue(L, -1)` is a type error). Land in `local v: value = ffi.lua_totvalue(L, -1)` first, then narrow (`return v as T` / `local s = v as string`) before `lua_settop(L, top)`. Pushed slots root only while below `L->top.p`.
4. Retain **no** raw `StkId`, `TValue *`, or borrowed string/userdata pointer across allocation, Lua calls, metamethods, callbacks, `longjmp`, or stack growth—hold traced owner + offset and re-derive.

```titan
foreign import "lua.h"
foreign import "titan/ffi.h"

local function global_string(name: string): string
  local top: foreign int = ffi.lua_gettop(L)
  defer ffi.lua_settop(L, top)
  if ffi.lua_checkstack(L, 1) == 0 then
    raise "cannot reserve Lua stack for global lookup"
  end
  ffi.lua_getglobal(L, name)
  local v: value = ffi.lua_totvalue(L, -1)
  return v as string
end
```

```text
-- Chunk compilation + optional _ENV setup (explicit pop asymmetry):
local top: foreign int = ffi.lua_gettop(L); defer ffi.lua_settop(L, top)
if ffi.lua_checkstack(L, 2) == 0 then raise "stack reserve failed" end
if ffi.luaL_loadbufferx(L, chunk, #chunk as foreign size_t, name, nil) ~= ffi.LUA_OK then
  local err: value = ffi.lua_totvalue(L, -1); raise err
end
if env ~= nil then
  ffi.lua_pushtvalue(L, env)
  if not ffi.lua_setupvalue(L, -2, 1) then ffi.lua_settop(L, -2) end -- non-pop on NULL
end
local v: value = ffi.lua_totvalue(L, -1) -- foreign TValue; direct `local s: string = ...` fails
return v as T -- narrow from `value` before `defer` runs `lua_settop(L, top)`
```

- **State & calls:** Builtin `L` is current-call-only (never save/return/substitute); independent `lua.Lua` states never take host GC objects/callbacks (`doc/implementation/lua-library.md`). Typed Lua callables run via `codevaluecall` (`luaD_callnoyield`), never manual `pcall`. Only **3** `lua_pcallk` sites exist (`titan/lua/worker.titan` `lua_state_open`/`lua_state_run`, `titan/thread/spawn.titan` `thread_worker_main`, `nil` cont). Never `longjmp` across foreign/worker entry into host state; user fns/metamethods are non-yieldable.
- **Byte copies, barriers & C types:** Prefer `pointer as string(n)` / `as string` for current-state copies; reserve `lua_pushlstring` for Lua stack args/keys/results or independent states. Under Lua 5.5 generational+incremental GC, anchor fresh objects before alloc/poll and use public Lua API setters (write barriers), never raw `TValue` stores. C types in Titan annotations always take `foreign` (`foreign int`, `foreign size_t`, `foreign TValue`—never bare `int` or `mod.int`).

## Audited operation ledger

Document stack, alloc, error, callback, and borrowed-pointer obligations here and at the call site for any new raw op.

| Operation | Stack effect & obligations |
| --- | --- |
| `lua_gettop`, `lua_settop(L, saved)` | Snapshot and authoritative entry-height restore. |
| `lua_checkstack`, `luaL_checkstack` | Net 0; reserve max temp slots before pushing (may relocate stack). `checkstack` returns 0 (caller raises); `L_checkstack` raises. |
| `ffi.lua_pushtvalue`, `ffi.lua_totvalue` | `pushtvalue` pushes 1 traced `value` (`titan/ffi.h`); `totvalue` is net 0, returns **`foreign TValue`** (not concrete Titan types): land in `local v: value = ffi.lua_totvalue(L, idx)`, then narrow via `v as T` before `lua_settop(L, saved)`. |
| `lua_pushnil`/`boolean`/`integer`/`number`/`lightuserdata`, `ffi.lua_pushconstlightuserdata` | Push 1 scalar or borrowed address. Cross-state args use lightuserdata, never foreign-state GC refs. |
| `lua_pushstring`, `lua_pushlstring`, `lua_concat` | Push 1 copied/concatenated string (`lstring` honors explicit length). May allocate/raise. |
| `lua_pushvalue`, `lua_copy`, `lua_absindex`, `lua_pushthread` | `pushvalue`/`pushthread` push 1; `copy`/`absindex` net 0. |
| `lua_pushcclosure` | Push 1 C fn: **only** restricted source `foreign function` with 0 upvalues, never an adapted Titan closure. |
| `lua_getglobal`, `lua_getfield`, `lua_setfield` | `get*` push 1, `setfield` pops 1; may run `__index`/`__newindex`, allocate, or raise. |
| `lua_rawget`/`i`/`p`, `lua_rawset`, `lua_rawequal` | No metamethods; `rawget` replaces key, `rawgeti`/`p` push 1, `rawset` pops 2 (barrier), `rawequal` net 0. |
| `lua_next` | Pops key; pushes `(k, v)` or nothing on exhaustion; raises on invalid key. Copy results before restore. |
| `lua_getmetatable`, `lua_setmetatable` | `get` pushes 1 if present (no `__metatable`); `set` pops 1 (`__gc` marks finalizable). |
| `luaL_testudata` | Net 0; `NULL` if slot is not userdata with named registry metatable. |
| `lua_getupvalue`, `lua_setupvalue` | `get` pushes 1 if present else 0. `set` pops + barrier if present, else returns `NULL` and **pops nothing**. |
| `lua_type`/`typename`/`isinteger`/`toboolean`/`tointegerx`/`tonumberx`/`tothread`/`touserdata`/`tocfunction`/`topointer`, `ffi.lua_togco` | Net 0; check kind first. Pointers are borrowed, never roots (`topointer` is identity-only). |
| `lua_tolstring`, `luaL_tolstring` | `tolstring`: net 0 on string (borrowed while rooted; number conversion allocates). `luaL_tolstring`: pushes 1 string via **2 transient slots** above value (reserve **3** if pushing value); may run `__tostring`/alloc/raise. |
| `luaL_loadbufferx`, `luaL_loadstring` | Push 1 compiled chunk or 1 error (`loadbufferx` uses explicit length). May allocate/raise. |
| `lua_pcallk`, `lua_callk`, `lua_error`, `luaL_error` | `pcallk`: only the 3 audited independent-state/thread sites. `callk`: only inside protected callback or `transfer_load_module` preload (nil continuation = non-yieldable). Never `longjmp` across worker/host boundary. |
| `luaL_newstate`, `lua_close`, `luaL_openselectedlibs`, `ffi.titan_newthread` | State create/destroy, protected library open, or coroutine thread with reserved stack. |
| `lua_getinfo`, `lua_gc` | `getinfo(">")` pops fn (`titan.reflect` only). `lua_gc` net 0; `-1` is error; never call in a finalizer. |
| `titan_module_preload_symbols`, `titan_module_preload` | Net 0 on success; each reserves **4** slots internally, may allocate/raise, never invokes loaders. |
