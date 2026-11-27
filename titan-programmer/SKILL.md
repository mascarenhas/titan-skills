---
name: titan-programmer
description: Load before writing, editing, compiling, or reviewing any .titan file, module, or Titan program. Covers types, T?/value, #arr holes, const/local records, unions, interfaces, generics, defer/catch, modules, and titanc; pair with titan-stdlib for string/math/iteration/io/path/fs/os/gc and peer skills for tests, async, net, FFI/JS, PEGs, JSON/proto/SQL, or packaging.
---

# Titan Programmer

Statically typed, AOT-compiled sister language to Lua (`titanc` → C → native/Wasm; `.titan` never runs under `lua`). Peers: `titan-stdlib`, `titan-application`, `titan-package`, `titan-tester`, `titan-async`, `titan-thread`, `titan-networking`, `titan-websocket`, `titan-ffi`, `titan-pegs`, `titan-json`, `titan-protobuf`, `titan-sqlite3`, `titan-reflect`, `titan-language-server`, `titan-completion`.

## Non-negotiable invariants

1. **Private state in `local` fields on exported `record`s:** Never invent Titan `RawX` + `{integer: X}` ID registries *(external C/OS/wire descriptors remain valid)*. Any `local` field makes synthesized `Record.new` `local`, so expose a public factory/custom `Record.new` using `{ ... }` in the defining module (`local` hides from ordinary `import`/Lua, not `.titan` source imports).
2. **Default `record` fields to `const` (`const f: T` / `local const f: T`):** Mutate only when needed (shallow; `const { T }` for read-only Arrays). `const` block locals ALWAYS need RHS and on inline C aggregates block member writes/mutable decay.
3. **Immediate `defer obj:close()` + sync `gc.finalizable` on external handles only:** Pair acquisition with LIFO `defer obj:close()` (`defer do ... end` for multi-statement); make `:close()` idempotent. Attach `gc.finalizable` **only** to external OS/C handles (never GC data) using a **sync, non-yielding, idempotent, non-capturing** param callback (**NEVER async `fs.File:close()` or `gc.*` in `__gc`**; errors warn; root active `uv` owners).
4. **Exact `#arr`, holes, `arr[#arr + 1] = val`, & `const? { T }`:** `#arr` is `0` empty, highest present index across interior `nil` holes, shrinks on trailing `nil`. Append via `arr[#arr + 1] = val`; read holes via `local x? = arr[i]`; never `{integer: T}` as Array. **`const? { T }` is a maybe-const Array view (`{ T }` or `const { T }`), NOT optional**—never compare to `nil` (optional is `{ T }?` / `(const? { T })?`).
5. **Options (`T?`), `boolean?`, `or nil`, & auto-unwrap:** Unannotated `local x = expr` drops `T?` (write `local x? = expr`). Compare `boolean?` with `== nil`/`~= nil`. Never write `cond and x or nil` when `x: T?` (`or` rejects `nil` RHS) or untyped `local x = nil`/`local x? = nil` (infer `nil`/`nil?`)—use `if` or `local x: T? = nil`. After `nil` check, use `x.field`/`x:method()`/`case` directly (no redundant `x as T`).
6. **No subtyping; `value` ≠ TS `any`:** Conversions (`integer -> float`, `T -> T?`, `R -> I`) act at typed sinks only (no container/function lifting). Ops (`+`, `<`, `..`, `#`, index) on `value` fail to compile. Implicit `value -> T` is **strict** (rejects `2.0` as `integer`, non-booleans as `boolean`); `value as/is T` & Lua convert dynamically (pair `if v is integer` with `v as integer`).
7. **Top-level `local function`, `raise` divergence, returns, `Record(...)`, & named calls:** **`local function name(...)` is module top-level ONLY** (syntax error inside bodies—use lambdas `local h = function (...): R ... end`; hoist recursion). Checker proves non-returning error paths from **`raise` statements** (`raise err` / `raise err.error, err.traceback`), **NOT** method calls like `err:raise()`. Omitted return = `: ()`; prefer `Record(...)`/`Record { ... }`; named calls target direct decls only (`f({ 1, 2 })` for positional brace).
8. **Short stdlib imports & exact initializer rules:** Use the 27 short names (`import "fs"`, `local strings = import "string"`; Lua: `require "titan.<name>"`). Mutable locals/module vars omit init ONLY for nil-admitting types (`nil`/`value`/`T?`/nullable C ptr); `const` block locals ALWAYS need RHS; uninit `const` module vars need nil-admitting type (`const x: string?`) and assign ONLY in trailing root `do ... end`. Module-var RHS cannot eval own vars/funcs/methods (default record/union ctors excepted)—put startup logic in root `do ... end`.

## Lua → Titan Delta Table

Shares Lua's GC, truthiness (`nil`/`false` falsy; `0`/`""` truthy), and arithmetic; diverges here:

| Lua Habit | Titan Rule (`v0.6.2`) |
| --- | --- |
| Unified `table` | `{T}` Arrays (userdata proxy, exact `#arr`, positive keys) vs `{K: V}` Maps (Lua table). |
| `{ k = 1 }` | Record literal only; Map literals need brackets: `{ ["k"] = 1 }`. |
| `#t` anywhere | `#` works on `string`, Arrays, and exact `{integer: V}` Maps (`__len`/border) only. |
| Unified `number` | Distinct `integer`/`float`; `/` and `^` return `float`; numeric `for` never coerces `integer -> float`. |
| `tostring`/`n as string` | Numbers coerce to `string` **only** in `..` (`"" .. n`); `n as string` fails to compile. |
| `a == b` calls `__eq` | `value == value` is raw; only static Map operands enable `__eq`. `T? == T` never unwraps. |
| `local x` / `local x = nil` | Uninit mutable needs nil-admitting type; `const` local needs RHS; uninit `const` mod var needs nil-admitting type + root `do ... end`; `local x = nil` infers `nil` (write `local x: T? = nil`). |
| Nested `local function` | Module top-level ONLY (syntax error in bodies); use `local f = function (...): R ... end` (hoist recursion). |
| `pcall`/`goto`/`_G` | No `_G`/`try`/`goto`/`finally`; `catch` trails blocks; exe exports `main(args: {string}): integer`. |

## Types, Containers, Functions, and Control Flow

- **Scalars, aliases & `T?`:** `nil`/`boolean`/`integer`/`float`/`string`/`value`. `type Name = T` is transparent (no runtime identity/module field, forwards record/union namespaces + generics, rejects union variants/bare C types—`foreign type` in `titan-ffi`). No `T??`; `value? == value`; `{integer?} == {integer}`; Map keys reject `nil`/`T?`; `_` discards (repeatable).
- **`or`/`and` & sinks:** `x or fallback` yields `T` iff `x: T?` and `fallback: T` match (`x or 0.0`). Never write `cond and x or nil` when `x: T?` (`or` rejects `nil` RHS of `T?`)—use `if` or `local x: T? = nil` (never untyped `local x = nil`/`local x? = nil`, which infer `nil`/`nil?`). Traps: `false or 5` → `boolean` (`true`; `false or v` → `value`), `false and 1.0` → `nil`. Implicit conversions act in 8 sinks only (annotated `local`/module var, assign, `return`, call args, indices, ctors, generic-`for`)—never numeric `for`.
- **Arrays (`const`/`const?`) & Maps:** Reads `< 1`/`> #arr` → `nil`; writes `< 1` raise; `{}` → `{integer}`. `const { T }` never converts to `{T}`; `xs as const { T }` shallow-copies—or freezes O(1) for unaliased local builder / fresh-returning same-module helper. **`const? { T }`** is a zero-copy **maybe-const Array view** accepting `{ T }` or `const { T }`, **NOT `nil`** (never compare to `nil`; optional array is `{ T }?` or `(const? { T })?`; `v as const { T }` checks tag, never snapshots). Iterate dense/const via `for i = 1, #xs`, holed via `iteration.ipairs`, Maps via `iteration.pairs`.
- **Functions & calls:** Top-level decls are order-independent. **`local function name(...)` is valid ONLY at module top level** (in a body: `syntax error: Expected variable declaration after 'local'`; write `local h = function (...): R ... end`, hoist recursion). Optional params use `T?`, not `...: T`. Positional calls nil-fill/discard surplus; named calls eval L→R on direct decls, `Record { ... }`, union ctors (unnamed single part = `value`), direct methods, named C prototypes. Only last expr expands; `(f())` forces 1 result.
- **Variadics, flex & spreads:** Variadic params **require `: type`** (`...: value`, never bare `...`): `#...`, `...[i]` (raises OOB), `(...)` (`T?`), tail forward (max 200, no lambda capture, no `nil`/raw C ptr). Flex `(...: T)` projects `T?` in finite sinks, keeps count in 3 open sinks (variadic tail, flex `return`, final Array/`{integer: V}` slot). Spreads `...xs[a, b]`/`...[a, b]` are 1-based inclusive (max 100 prefix, never C `...`).
- **Closures & adjustment:** Lambdas infer omitted types only from expected function type (unannotated return without context = `: ()`), capture locals/`self`, share mutable cells, isolate loop locals. `obj:m` binds `obj` once (positional-only); `(function(...) ... end)(...)` inlines; callable adjustment adapts arities without lifting scalar/Option/Interface coercions.
- **Control flow & lexing:** Multi-assign freezes lvalues L→R, evals RHS L→R, stores L→R. `repeat ... until` sees body locals. Numeric `for`: exact bounds, readonly var, step `~= 0`. Generic `for`: `(iter, state, init, close)`, stops only on `nil`, runs `close(state)` on exit, takes bound methods (`for chunk in r:read do`). `return` must be last.
- **Precedence & keywords:** `as`/`is` sit below unary/`^`, above `* / // %`, never chain (`(x as value) is float`); add `;` after uncounted cast before next-line `(f)(x)` (`p as string(n)` counted C cast); write `(...) - 1`; `{function(): T}` = Array, `{(function()): T}` = Map. Keywords (`end`, `type`) work as member/field/variant/named-key names, not locals; `boolean`/`integer`/`float`/`string`/`value` are contextual.

```titan
local io = import "io"

local function configure(label: string?, enabled: boolean?): string
  local active = true
  if enabled ~= nil then active = enabled end -- false ~= nil
  return (label or "default") .. ":" .. (active and "on" or "off")
end

local function freeze_slots(): const { string }
  local slots: {string} = {}
  slots[#slots + 1] = "a"; slots[#slots + 1] = "b"; slots[#slots + 1] = "c"
  slots[2] = nil; slots[3] = nil -- hole, then tail shrink #slots -> 1
  slots[#slots + 1] = "d"
  return slots as const { string } -- O(1) linear freeze
end

local function first_or(xs: const? { string }): string return xs[1] or "" end
local function tail_ints(xs: {integer}): (...: integer) return ...xs[2,] end

function main(args: {string}): integer
  local frozen, tag = freeze_slots(), configure { enabled = false }
  local a?, b? = tail_ints({10, 20})         -- finite: 20, nil
  local all = { 0, tail_ints({10, 20, 30}) } -- open: {0, 20, 30}
  local raw: value = 2.0
  local n = (raw is integer) and (raw as integer) or 0
  if #frozen ~= 2 or first_or(frozen) ~= "a" or tag ~= "default:off"
    or a ~= 20 or b ~= nil or #all ~= 3 or n ~= 2 then return 1 end
  io.print(tag .. " len=" .. #frozen .. " n=" .. n)
  return 0
end
```

## Records, Unions, Interfaces, and Generics

- **Records** *(nominal struct + methods; Lua userdata)*: `[local] record Name ... end`; fields `[local] [const] name: T`. Custom `[local] function Record.new(...)` replaces synthesized `new` (`Record(...)` inside `new` recurses) and locks `{ ... }` to defining module (even `.titan` importers must call `new`). Duplicate keys in `{ ... }`: eval all, last wins (named calls reject). Private methods: `local function R:helper(...)`. Shared field/method namespace; call via `:` (`r.m` fails); `R?` auto-unwraps; identity `==`.

```titan
local gc = import "gc"
local io = import "io"
foreign import "stdlib.h"

record BufferStore
  const label: string
  local raw: foreign *void
  local const slots: {string}
end

local function finalize_store(candidate: value)
  local store: BufferStore = candidate
  store:close() -- sync, non-yielding, non-capturing, idempotent
end

function BufferStore.new(label: string, bytes: integer): BufferStore
  local raw = ffi.malloc(bytes as foreign size_t)
  if raw == nil then raise "out of memory" end
  local store: BufferStore = { label = label, raw = raw, slots = {} }
  gc.finalizable<|value|>(store, finalize_store)
  return store
end

local function BufferStore:live(): integer
  local n = 0
  for i = 1, #self.slots do
    local msg? = self.slots[i]
    if msg ~= nil then n = n + 1 end
  end
  return n
end

function BufferStore:add(msg: string): integer
  local idx = #self.slots + 1; self.slots[idx] = msg; return idx
end

function BufferStore:remove(idx: integer) self.slots[idx] = nil end

function BufferStore:close()
  if self.raw ~= nil then ffi.free(self.raw); self.raw = nil end
end

function main(args: {string}): integer
  local store = BufferStore("inbox", 64)
  defer store:close()
  local a, b = store:add("first"), store:add("second")
  store:remove(a)
  if store.label ~= "inbox" or store:live() ~= 1 or b ~= 2 then return 1 end
  store:remove(b); if store:live() ~= 0 then return 1 end
  store:close(); io.print("store ok"); return 0
end
```

- **Unions & `case`** *(closed nominal sum; Lua userdata)*: `empty()`, `single(T)` (= `single(value: T)`), `named(a: A, b: B)` (no `...: T`). Variants (`U.v`) are ctors, not types; wrap positional record payloads (`U.step({ x = 1.0 })`). In `case u`, arms **require `when Variant(...)` with parens even for 0-arg unit variants** (`when closed()`, `when quit()`) or `when Variant { ... }` named binders (bare `when closed` is a syntax error); `when v(a)` omits trailing parts; `when v { alias = part, x }` puts **alias LEFT, part RIGHT** (`finish = end`).
  - Arms are full blocks (`defer`, arm `catch` seeing binders, `break` targets enclosing loop); no fallthrough. `U?` auto-unwraps (`nil` raises, never enters `else`). Non-fallthrough needs all closed variants or terminating `else` (imported unions with `local` variants need `else`). Identity `==`; method-only Interfaces only.
- **Interfaces** *(public, nonempty, type-only structural view)*: Fields (`name: T`) are `const`, need visible `const` record fields, **shallow-snapshot** on conversion. Methods match via callable adjustment (named calls use Interface param names). Each `R -> I` builds a **fresh** wrapper (bind `local key: I = item` before `{I: V}` indexing). No lifting (`{R}` ≠ `{I}`). Downcast via `i is R`/`i as R` (no `i as J`/`r_opt as I`). At `value`/Lua boundaries, bare `R` converts to `I` **only if an initialized module compiled a static `R -> I` conversion** (`r is I` doesn't witness it).
- **Generics (`<|T|>`):** On `record`/`union`/`interface`/named callables (not aliases/lambdas/`foreign function`; generic `main` not entry). Method defs omit owner params (`function Pair:map<|V|>`). `T: I` exposes only `I` members (rigid params can't cast to `Tag<|integer|>`). Invariant; bare generic = all-`value` (unconstrained only). Inference: explicit `<|...|>` → receiver → expected results → args (unresolved → `value`/`I`). Owner args attach to owner (`Box<|integer|>(1)`); callable args follow `.new<|U|>`. Excludes raw `foreign *T`/C aggregates. Erased: `raw as Box<|integer|>` checks outer identity only.

```titan
interface Named
  name: string
  function describe(): string
end

record Tag<|T|>
  const name: string
  const payload: T
end

function Tag:describe(): string return self.name end

union Event
  quit()
  write(string)
  span(from: string, end: integer)
end

local function format_event(ev: Event?): string
  if not ev then return "none" end
  case ev
  when write(text) then return "write:" .. text
  when span { finish = end, from } then return from .. ":" .. finish
  when quit() then return "quit"
  end
end

local function label_of<|N: Named|>(item: N): string
  return item.name .. ":" .. item:describe()
end

function main(args: {string}): integer
  local t = Tag<|integer|>("code", 7)
  local view: Named = t
  local out = view is Tag<|integer|> and (view as Tag<|integer|>).payload or 0
  if label_of(t) ~= "code:code" or out ~= 7
    or format_event(Event.span { end = 9, from = "a" }) ~= "a:9" then return 1 end
  return 0
end
```

## Errors, `defer`, Modules, and Basic `titanc`

- **`raise`, `catch`, `defer`:** `T?` for absence; `raise` for errors (`raise nil` → `"<no error object>"`). **Return-path divergence:** checker recognizes **`raise` statements** (`raise err` or `raise err.error, err.traceback`) as non-returning—**NOT** method calls like `err:raise()` (always use `raise ...` on non-`nil`-returning error paths). `catch` trails any block (no `try`/`finally`) as a **sibling scope** (body locals invisible except `case` binders) with readonly `error: value` and `traceback: string`.
  - Inside `catch`, bare `raise` preserves traceback, `raise err` resets it, `raise err, trace` attaches saved trace. `defer <stat>`/`defer do ... end` runs LIFO on exit (returns save first; no `return`/escaping `break`; `defer` error overrides; abandoned coroutine `defer` runs in non-yielding finalizer without `catch`).

```titan
local function parse_pos(n: integer, log: {string}): integer
  defer log[#log + 1] = "cleanup"
  if n <= 0 then raise "non-positive" end
  return n
catch
  log[#log + 1] = "caught"; raise -- preserves original traceback
end

function main(args: {string}): integer
  local log: {string}, trace: string = {}, ""
  do parse_pos(-1, log) catch trace = traceback end
  if #log ~= 2 or log[1] ~= "cleanup" or log[2] ~= "caught" or #trace == 0 then return 1 end
  return 0
end
```

- **Modules & variants:** Flat `pkg/mod.titan` vs folder `pkg/mod/mod.titan` + sibling `*.titan` contributors share namespace/`local`/artifact (order: main → byte-sorted contributors → main's trailing `do ... end`; contributors unimportable). Variants `name.<linux|darwin|windows|native|browser>.titan`: most-specific wins (main variant replaces default main + `do ... end`). Built-ins: `ffi`, `M` (`M.member`/`M.Type`/`M.end`), `L` (not in `foreign function`). LDoc `---` attaches to next decl.
- **Initializers:** Mutable block locals & mutable module vars omit initializers ONLY on explicit nil-admitting types (`nil`, `value`, `T?`, nullable C ptr; multi-var uninit decls need per-var types); `const` **block locals** ALWAYS need RHS. Uninit `const` **module vars** need explicit nil-admitting type (`const x: string?`) and assign ONLY directly inside trailing root `do ... end` (nested blocks keep authority; called funcs/lambdas do not).
- **Init frontier:** Module-var decl RHS sees only earlier imports/vars and **cannot evaluate references/calls to own vars, funcs, or methods** (synthesized default record/union constructors are the sole exception; lambdas/bound methods created without running are ok)—put startup logic reading own vars or calling own funcs in trailing root `do ... end`.
- **`.titan` imports & `titanc`:** `import "pkg.mod.titan"` requires source, grants direct-only `local` access, inherits C headers transitively, fails against SDK fallback in libs; cycles fail. Invoke `titanc` with dotted names: `titanc -q --tree . -o out --exe app app.main` (lib: omit `--exe`; `-c`: compile-only; `-T browser -o out`). `main` auto-bootstraps `async` (`--no-uv-bootstrap` opts out). Layouts/locks/`--static`/browser/rocks → `titan-application`/`titan-package`.

## Pre-delivery verification checklist

- [ ] Exported `record`s: `local` fields + public factory/custom `new` (no `RawX`+ID registry); unmutated fields `const`/`local const`.
- [ ] External handles: idempotent `:close()` + immediate `defer obj:close()`; `gc.finalizable` only on external handles (sync, non-yielding, non-capturing; never `fs.File:close()`/`gc.*`).
- [ ] Arrays/Options: `arr[#arr + 1] = val`; `local x? = arr[i]`/`iteration.ipairs`; `const? { T }` is maybe-const view (never `== nil`); `boolean?` uses `== nil`/`~= nil`; no `cond and x or nil` on `T?`, no untyped `local x = nil`, no redundant `x as T`/`n as string`.
- [ ] Syntax/Init: top-level `local function` only; `raise ...` (not `err:raise()`) on non-returning paths; `...: T` variadics; `when Variant()` with parens; short stdlib imports; module startup in root `do ... end`; compile via `titanc` with dotted names & `-o <dir>`.
