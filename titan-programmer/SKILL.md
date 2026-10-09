---
name: titan-programmer
description: Mandatory base skill before writing, editing, or reviewing any .titan source, including tests and specialized library code; load it alongside every applicable Titan peer skill. Write, review, compile, and debug ordinary Titan modules and programs. Covers the Titan language, automatic conversions, expression-list and spread adjustment, core data modeling, errors and cleanup, modules, titanc, and the core string/math/iteration/io/fs/os libraries. Load a narrower Titan skill as well for tests, async internals, networking, FFI/Lua escape hatches, or PEG parsers.
---

# Titan programmer: the Titan basics cartridge

Titan is a **statically typed, ahead-of-time-compiled sister language to Lua**.
It is not Lua with optional annotations, TypeScript-for-Lua, or a language that
`.titan` files can execute with `lua`. `titanc` parses and typechecks Titan,
generates C, invokes the native toolchain, and emits a native module provider or
standalone executable. Titan deliberately resembles Lua, shares Lua values and
Lua's garbage collector, and preserves Lua arithmetic and truthiness, but it has
its own static types, module system, nominal data, container protocols, call
adjustment, and checked Lua boundary.

Use this cartridge before writing or reviewing any `.titan` source. Do not
reconstruct Titan from memories of Lua, Go, TypeScript, or C.

## Route specialized work before coding

This is the primary cartridge. Add the relevant specialist cartridge when the
work crosses one of these boundaries:

- **[`titan-application`](../titan-application/SKILL.md)** — starting an application
  repository, source/test build layout, initial ignore rules, and executable
  delivery checks.
- **`titan-tester`** — native `titan.test` modules, `titanc --test`, subtests,
  cleanup, filtering, and repository test-layer ownership.
- **`titan-async`** — Tasks, cancellation, Runtime ownership, timers, libuv
  callbacks, callback-to-Task resumption, and async standard-library internals.
- **`titan-networking`** — `net`, `ssl`, `url`, and `http` APIs and
  protocols.
- **[`titan-websocket`](../titan-websocket/SKILL.md)** — WebSocket clients, HTTP upgrades,
  message framing, origin/subprotocol policy, Ping/Close, and session cleanup.
- **`titan-ffi`** — C `foreign import`, C operators and ownership, foreign
  callbacks, the Lua C API, and the `titan.lua` dynamic escape hatch.
- **`titan-pegs`** — `titan.peg`, relabel grammars, combinators, and parser error
  design.
- **`titan-reflect`** — `titan.reflect`, runtime value inspection, nominal type queries,
  descriptors, and dynamic record/interface field access with GC safety.
- **`titan-json`** — JSON encoding/decoding, explicit schema selection, null
  preservation, record/union mapping, diagnostics, and JSON-library maintenance.

The core `fs`, `io`, and `os` APIs below have synchronous-looking Titan calls
that may suspend. Application-level use is covered here; load **`titan-async`**
for lifecycle or implementation changes. `titan.lua` can be as powerful an
escape hatch as the C FFI. Use it just as sparingly and keep it behind a narrow,
typed, audited boundary.

`async.run_foreign` is the deliberate cross-cutting exception: it exposes a
portable raw C function-pointer/pointer signature so a Task can wait for a
blocking external C call in libuv's worker pool. Load both **`titan-async`** and
**`titan-ffi`** before using or changing it; the worker may not enter Titan or
Lua, and cancellation does not end accepted native ownership.

Across this skill tree, a `titan` fence is a complete module or an explicitly
named file in a paired composition. Signature inventories, placeholders,
continuations, and intentionally invalid examples use `text`; do not paste a
`text` fragment at module scope without supplying its stated context.

## The working mental model

1. **Static by default, dynamic by choice.** Every expression has a static
   type. `value` explicitly marks a Lua-shaped dynamic slot; it does not turn
   off checking around it.
2. **No general subtyping.** Titan has exact identity, named direct
   conversions, gradual views, directional callable adjustment, and nominal
   Interface wrappers. These are separate operations, not one transitive
   “assignable” relation.
3. **Fail at the first false assumption.** A possibly absent `T?` can flow into
   a required `T`; Titan inserts a runtime nil check. A typed Array or Map read
   checks the requested element representation before native Titan uses it.
4. **Nominal values are not tables.** Records, unions, Interfaces, and Arrays
   cross Lua as userdata. Maps cross as ordinary Lua tables.
5. **Direct code is idiomatic code.** Let the compiler apply the documented
   conversion at a typed sink. Put behavior on its real record owner. Use the
   existing owner/helper and direct state transition instead of adding facade
   aliases, forwarding wrappers, duplicate flags, generations, or partial
   hardening for unsupported interleavings.
6. **Ownership is lexical where possible.** Acquire a resource, immediately
   `defer` its close, and let the current existing block own the cleanup. Do
   not add a `do ... end` merely because you want `defer` or `catch`.

## Surface syntax and source shape

Comments and literals follow Lua closely: `--` comments, long bracket strings,
short quoted strings, decimal/hexadecimal integers and floats, `nil`, `true`,
and `false`. Identifiers are ASCII `[A-Za-z_][A-Za-z0-9_]*`. Only `nil` and
`false` are falsy; `0`, `0.0`, and `""` are truthy.

A flat module is a sequence of top-level declarations, optionally followed by
one final root initializer:

```titan
local fs = import "fs"
local string = import "string"
local math = import "math"

local default_marks = 3

record Greeting
  name: string
  marks: integer
end

local function Greeting:render(): string
  return "Hello, " .. self.name ..
         string.rep("!", self.marks)
end

function write_greeting(path: string, name: string)
  local greeting = Greeting.new(name, default_marks)
  fs.write_file(path, greeting:render())
end

do
  -- The sole optional computed module initializer. It runs once per Lua state.
end
```

Top-level forms are imports, module variables, functions, type aliases,
records, unions, Interfaces, methods/nominal functions, and (in FFI code)
foreign declarations. A top-level `name = expression` is a **module-variable
declaration**, not assignment. Top-level declarations are exported unless the
form admits and uses `local`.

Const locals always need an initializer expression list. An ordinary mutable
local may omit its RHS only when every name has an explicit type that actually
admits missing nil (`nil`, `value`, an Option, or an existing nullable pointer
domain); the compiler supplies a typed nil for each slot:

```titan
local function declarations()
  local count: integer = 0
  local label = "ready"             -- inferred string
  local missing: string?             -- initialized to nil
  const ready = label
  local const limit: integer = 10
end
```

`local count: integer` is rejected, as is every const declaration without an
RHS. `const name = value` and `local const name = value` have the same
block-local semantics; neither binding can be assigned later, including from a
capturing closure.

Assignment to an undeclared name is an error; Titan has no ambient Lua globals.
A local enters scope only after its whole declaration, so `local x = x + 1`
reads an outer `x`. `return` must be the final statement of its current block.
Only a call may be used as an expression statement.

Type words `boolean`, `integer`, `float`, `string`, and `value` are contextual
identifiers. Top-level declarations and members accept `AnyName`, including
reserved words; locals/parameters use nonreserved `Name`. Ordinary functions,
methods, lambdas, and the module initializer bind readonly `L` (current Lua
state) and `M` (current module). `M.member` and body-local types `M.Type` select
module declarations despite local/generic shadows, including keyword-named
members; `M as foreign *Udata` exposes the borrowed module pointer. Foreign
functions receive neither builtin. The readonly builtin `ffi` may be shadowed
by ordinary declarations.

## The type vocabulary

| Purpose | Titan spelling |
| --- | --- |
| absence | `nil` |
| scalar values | `boolean`, `integer`, `float`, `string` |
| dynamic Lua-shaped slot | `value` |
| optional value | `T?` |
| mutable / const / maybe-const Array | `{T}` / `const { T }` / `const? { T }` |
| Map | `{K: V}` |
| function | `function (A, B): (R)`, `function (): ()`, `function (A): (R1, R2)` |
| variadic input | `function (...: T): (R)` or fixed prefix plus `...: T` |
| flexible results | `function (): (...: T)` or `function (): (R, ...: T)` |
| transparent alias | `type Name = T` |
| nominal data | `record R ... end`, `union U ... end` |
| nominal behavioral view | `interface I ... end` |
| generics | `Box<\|T\|>`, `function id<\|T\|>(x: T): T` |

`integer` and `float` are distinct static types. Strings are immutable byte
strings, not implicit Unicode text. Type equality is structural for basic,
Option, Array, Map, and function types; records, unions, and Interfaces are
nominal by fully qualified declaration identity. A type alias is transparent:
`type UserId = integer` introduces no runtime value or new identity.

A generic owner or named callable may declare parameters:

```titan
record Pair<|T, U|>
  first: T
  second: U
end

function id<|T|>(item: T): T
  return item
end

function use_generics(): integer
  local pair = Pair.new(1, "one")          -- Pair<|integer, string|>
  return id<|integer|>(pair.first)
end
```

Calls normally infer a complete argument list locally. Explicit lists are
all-or-none. Owner arguments attach to the owner (`Pair<|integer,
string|>.new(...)`), not to `new`. Generics are invariant and erased; a generic
body is checked once. A bare generic owner in an ordinary type position means
the all-`value` application, not a wildcard.

### Foreign types and owned storage are a specialist boundary

Titan types and raw foreign types have separate syntax and name resolution.
Use `foreign int`, `foreign float`, `foreign *Item`, and
`foreign function(*void): void` in ordinary annotations/casts. Within a foreign
signature/type, names are unqualified: no `ffi.` or module prefix. Primitive
C words remain identifiers elsewhere, so Titan names do not reserve them.
Nested pointer/array/callback constructors are grouped, as `foreign *(*int)`.

`foreign type Name = foreigntype` creates an always-local raw C typedef, with no
`local` modifier. It is emitted in the generated `.ffi.h`; explicit source
imports inherit its unqualified name through transitive C headers. Ordinary
imports do not. Names obey real C collision rules, including the native SDK.
Ordinary `type` aliases may contain raw C components inside Titan structures,
but cannot alias a direct raw C type just by adding parentheses.

`owned foreigntype` is a Titan constructor. Its operand must resolve to a C
pointer or array, including through an alias: `owned *Item`, `owned Item[]`,
and `type Owner = owned *Item` are valid. Ownership does not belong in foreign
alias RHS types, foreign signatures, or local declarations in foreign bodies.
An outer `const` on the resolved operand is rejected: Titan cannot allocate
and initialize const owned storage together.

Allocation/layout expressions spell `foreign T.new()`, `.new_array(count)`,
`.sizeof`, and `.alignof`; type operations never come from term lookup. Positive
literal or eligible integer macro counts can infer fixed automatic C arrays at
a direct local sink. An explicit owned type requests GC-owned storage. Written
sized C array annotations are removed; there is no size threshold.

A public compiled interface may recursively contain portable C primitives,
pointers, structural callback pointers, and eligible owners. Header typedefs,
aggregates, arrays, enums, and graphs containing them remain source-local.
Load **`titan-ffi`** for exact export, coercion, lifetime, callback, and allocation
rules.

## Automatic conversions: use the typed context

Most `as` casts written by an agent are unnecessary. Titan's checker records an
adjustment at ordinary typed sinks: annotated declarations, assignments,
arguments, returns, constructor entries, module variables, typed indices, and
generic-`for` tuple/binding slots. One sink can apply one accepted outer
operation:

- exact identity;
- a named direct conversion;
- a strict gradual projection or same-kind Array/Map view; or
- a directional callable adjustment.

Important direct conversions include:

| Source → target | Behavior |
| --- | --- |
| `integer → float` | total numeric conversion |
| `float → integer` | checked; requires an exact in-range integer value |
| `T → T?`, `nil → T?` | total Option introduction |
| `T? → T` | checked nil force |
| compatible numeric Options | preserve nil; convert a present payload |
| ordinary Titan value → `value` | total gradual injection (boxable C scalars have their own checks) |
| `value → T` in an implicit typed sink | **strict** runtime projection; the value must already have `T`'s required tag/identity, except that an Interface target may use a compiler-witnessed metatable entry (a Function target deliberately defers callability until invocation) |
| satisfying record/union `R → I` | construct a fresh nominal Interface wrapper |
| many statically known Titan values → `boolean` | Lua truthiness |

A scalar conversion does **not** lift through an Array, Map, Function, generic
owner, record field layout, or union payload:

```text
integer -> float                  accepted
integer -> integer?               accepted
{integer} -> {float}              rejected
function(): integer  ->  function(): float     rejected
function(): integer  ->  function(): integer?  rejected
```

`{T}` and `const { T }` are distinct invariant types. `const? { T }` is a
maybe-const view type: `{T}`, `const { T }`, and `const? { T }` can all be
implicitly assigned to `const? { T }` (and `({T})?` / `(const {T})?` to
`(const? {T})?`). `const? { T }` cannot be implicitly assigned back to `{T}`
or `const { T }`, but can be explicitly downcast with `as {T}` or `as const {T}`
(which perform runtime metatable checks). A direct `as const { T }` from a
mutable `{T}` performs an explicit shallow snapshot (or in-place freeze when
linear).

Put the scalar expression in the scalar target instead:

```titan
local floats: {float} = {1, 2, 3}  -- each constructor slot converts integer
```

A number converts to a string only as an operand of `..`. Use `"" .. number`
when that formatting is intended; `local text: string = number` and
`number as string` are rejected.

### Options auto-unwrap at use sites

`T?` is exactly a `T` or nil; there is no wrapper object and no flow-sensitive
proof system. Titan automatically inserts a checked force whenever a bare `T`
is required. This includes:

- annotated declarations, assignments, arguments, and returns;
- arithmetic, bitwise, relational, concatenation, unary minus/bit-not, and
  length operands;
- Array/Map indexing and the indexed container expression itself;
- record field access;
- calls through an optional function and method calls on an optional nominal
  receiver;
- a union `case` scrutinee;
- numeric-`for` bounds (which otherwise require exact numeric types); and
- unannotated local inference, which deliberately drops the Option and fails
  fast if it is absent.

Therefore, after ordinary presence handling, use the value directly:

```titan
local fs = import "fs"

function describe_path(path: string): string
  local info? = fs.stat(path)
  if not info then return "missing" end
  return info.kind .. ": " .. info.size
end
```

Do **not** write `info as fs.Stat` merely because `info` is `fs.Stat?`.
`info.kind` is a field-access force and will raise only if the value is nil.
The preceding check makes that force safe, although it does not change the
static type.

An indexed read has an Option type. An ordinary inferred local forces it; a
`?` on the name preserves it:

```titan
function required_or_default(values: {string}, index: integer): string
  local required = values[index]       -- string; raises here if absent
  local optional? = values[index]      -- string?; absence is retained
  return optional or required
end
```

Use `x == nil` / `x ~= nil` when a present base value can itself be falsy. A
`boolean?` has three states (`true`, `false`, nil), while a plain condition
merges false and nil. `x or default` is the normal defaulted unwrap when the
right operand has exactly the base type. Conditions and `==`/`~=` do not force
Options; they observe nil/truthiness directly.

### `value` is checked dynamism, not TypeScript `any`

`value` can carry any Lua-representable value, including nil, heterogeneous
objects, Lua callables, and ordinary Titan boxed values. Use it at a real
dynamic boundary and recover a precise type close to that boundary.

A raw `value` may be stored, returned, passed, tested for truthiness, used as an
index through a typed key projection, and called **contextually** when the
argument/result context supplies a temporary function contract. Two `value`
operands use raw `==`/`~=`, even when both contain tables with `__eq`; only a
comparison whose static pair includes a Map enables the scoped table equality
described below. The checker rejects arithmetic, relational comparison,
concatenation, `#`, and indexing *into* `value` until a precise type is
requested. This is unlike TypeScript's `any`, which largely suppresses static
checking and permits operations to propagate more `any`. Titan keeps the
operation illegal or inserts an explicit runtime guard; it never silently
turns the surrounding expression into `value`.

The closest limited analogy is Go's `interface{}`/`any`: both can hold
heterogeneous boxed values and normally need recovery before type-specific
operations. Do not take the analogy further:

- Titan `value` is a Lua `TValue`-shaped dynamic slot and includes nil.
- A typed Titan sink may perform an **implicit strict projection**; Go does not
  implicitly type-assert an `interface{}` assignment to a concrete type.
- Written Titan `as` is sometimes a conversion, not just a tag assertion:
  integral floats may become integers and values may undergo truthiness or
  recursive Option conversion.
- Titan permits Lua truthiness/raw equality and contextual calls on `value`.
- Titan's `interface` declaration is a different feature: a nominal behavioral
  wrapper constructed from a statically known satisfying record or union, or
  dynamically through a pair already witnessed by compiled conversion code.
  It is not Titan's spelling of `value` and is not Go's structural runtime
  interface model.

### Strict implicit projection versus written dynamic conversion

This distinction is central:

```titan
function strict_integer(candidate: value): integer
  return candidate
end

function converted_integer(candidate: value): integer
  return candidate as integer
end
```

`strict_integer` accepts a value already carrying the Lua integer tag and
rejects a float `2.0`. The written `as integer` requests the broader dynamic
conversion and accepts an exactly integral, in-range float. At genuine Lua
argument/field/Array-write boundaries, Titan uses that broader target-directed
dynamic conversion too.

Use `as` when you intentionally need that broader dynamic conversion, an
explicit Interface/concrete downcast, or an FFI-only operation. Do not use it
as ceremony after an Option presence check or where a normal typed sink already
requests the intended direct conversion.

`exp is T` applies the non-raising predicate for the corresponding written
`exp as T` operation. It evaluates once, returns boolean, and **does not
narrow** the expression's static type. It shares `as`'s broad dynamic rules:
`value is integer` is true for an integral float, so a subsequent **strict**
implicit integer projection could still reject that float. In that numeric case, perform the matching
`as integer` conversion. For exact nominal targets such as `os.Date`, both
strict and written dynamic checks require the same exact identity, so an
annotated local can recover it without an explicit cast.

Interface targets are the nominal exception. Both strict projection and
written/Lua dynamic conversion accept an existing exact wrapper or bare full
userdata whose metatable advertises a compiler-witnessed wrapper for that
Interface. They never search methods at run time. `value is I` tests only
exact identity or non-nil witness presence; `value as I` calls a present
witness and constructs a fresh wrapper.

## Operators and control flow

Titan keeps Lua precedence and Lua-faithful results. Key rules:

- `+ - * // %` return `integer` for two integer operands and otherwise
  `float`; `/` and `^` always return `float`.
- Bitwise operators return `integer`; a float operand is checked for an exact
  integer representation.
- Integer overflow, floor division, modulo, and shifts reproduce Lua, not raw C.
- Mixed integer/float comparisons compare mathematical values without first
  rounding the integer through a float.
- `..` accepts strings and numbers and returns string. `#string` counts bytes;
  `#array` uses the deterministic highest present positive index; an exact
  integer-key Map uses `__len` when present and otherwise a Lua table border,
  and accepts only an exact Lua integer from the metamethod.
- Map/Map and Map/`value` equality in either orientation start with
  identity/raw equality. Distinct run-time tables select the left `__eq`, then
  the right when the left has none, and use Lua truthiness. A non-table dynamic
  `value` cannot dispatch; `value`/`value` equality remains deliberately raw.
- `and`/`or` short-circuit and return values under Titan's Option-aware rules;
  `not` returns boolean.
- Every condition accepts every type and uses Lua truthiness. A condition does
  not narrow its operand.

Blocks include function/lambda bodies, each `if`/`elseif`/`else` arm, each
`case` arm/else, loop bodies, and explicit `do ... end`. Each is its own lexical
scope.

Numeric loops require exact bound types; no integer-to-float conversion is
inserted there:

```titan
function half_step_total(): float
  local total = 0.0
  for x: float = 1.0, 10.0, 0.5 do
    total = total + x
  end
  return total
end
```

The control variable is read-only. Generic iteration is covered with
containers below.

## Functions, calls, closures, and result lists

Every named-function parameter is annotated. Omitting a return annotation means
**zero results**, not one nil:

```titan
function log(message: string)          -- function(string): ()
end

function one_nil(): nil                -- function(): nil
  return nil
end

function divmod(a: integer, b: integer): (integer, integer)
  return a // b, a % b
end
```

A fixed positional call is adjusted to the declaration:

- missing parameters are filled with nil, then typechecked;
- surplus argument expressions still run left-to-right, but a non-variadic
  callee discards their values; and
- `...: T` is only for a callee that semantically consumes every trailing `T`.

This makes an optional fixed parameter a normal `T?` parameter, not a special
default syntax. `string.rep("x", 3)` works because its third parameter is
`string?` and receives nil. Do not add a variadic tail merely to ignore extras.

Named calls use bare braces and are available only while the callee is a direct
declaration with parameter names:

```titan
function clamp(number: integer, lower: integer, upper: integer): integer
  if number < lower then return lower end
  if number > upper then return upper end
  return number
end

function bounded_example(): integer
  return clamp { upper = 10, number = 17, lower = 0 }
end
```

Use named calls when positional arguments are ambiguous, including record
constructors with many parameters, repeated same-typed values, adjacent boolean
flags, or runs of `0`, `nil`, and empty containers. Read the declaration and use
its actual parameter names; an overridden `new` may have parameters unrelated
to the record's fields. Keep short, self-explanatory calls positional, such as
`Point(x, y)` or `Error(message)`. When converting a call, preserve the written
evaluation order and expression-list adjustment: a final call or spread that
supplies several parameters cannot simply become one named entry.

Explicit named expressions evaluate in written order, then map to formal
positions. Omitted names receive nil and must accept it. Function values,
lambdas, bound methods, and variadic functions are positional-only. Direct
union variant constructors publish their payload part names and accept named calls. Bare braces always mean named-call syntax;
to pass a constructor as one positional argument, keep parentheses:
`consume({x = 1})`.

Only the last call in an expression list expands. Parentheses around a call
force one result:

```text
function consume_divmod(): integer
  local quotient, remainder = divmod(17, 5)
  local only_quotient = (divmod(17, 5))
  return quotient + remainder + only_quotient
end
```

A flexible result `(...: T)` has runtime-selected length. A finite consumer
sees each requested flexible position as `T?`; an open sink preserves every
actual value. Open sinks are a variadic call tail, a flexible `return` tail,
and the final position of a positional Array/integer-Map constructor. Use an
explicit Array instead when the collection is conceptually unbounded.

### Spread expressions

A spread expression expands an Array, an integer-keyed Map, or a selected part
of the current function's input-vararg run into the surrounding positional
expression list. Only the final item can expand. The collection and ranged
input-vararg forms are:

```text
...subject
...subject[, last]
...subject[first,]
...subject[first, last]

...                    whole current input-vararg run
...[, last]
...[first,]
...[first, last]
```

A collection subject may be an Array `{T}` (including `const { T }` and
`const? { T }`) or an exact integer-keyed Map `{integer: T}`. The corresponding
Option types are accepted and undergo the ordinary checked `S? -> S` force
once. Other Map key types, `value`, and C arrays are not spread subjects unless
a written conversion first produces one of those accepted Titan types.

Ranges are one-based, closed, and inclusive. A missing lower bound means 1; a
missing upper bound means the subject's length. The subject and explicit bounds
are evaluated once, left-to-right, even when the consumer ultimately requests
no elements. Array holes and Map `__len`/`__index` behavior remain the ordinary
container behavior.

```titan
function relay(sink: function (...: integer): (), values: {integer}?)
  sink(0, ...values[2,])
end

function middle(values: {string}): {string}
  return {...values[2, #values - 1]}
end

function forward_middle(...: string): (...: string)
  return ...[2,]
end
```

A finite consumer requests only its remaining fixed positions and observes
each projected element as `T?`; normal assignment adjustment then preserves
nil at an optional destination or forces presence at a required `T` destination.
An open consumer preserves the selected run-time length and observes elements
as `T`. Open consumers are a variadic call tail, a flexible `return` tail, and
the final positional field of an Array or exact integer-keyed Map constructor.
Declarations, assignments, fixed calls/returns, and generic-`for` tuples are
finite when their remaining shape is fixed.

Do not write another positional item after a spread: `sink(...values, 0)` is
rejected. Bare `...` is the whole input-vararg tail, `...[index]` is the scalar
raising index operation, and only comma-bearing input-vararg brackets select a
spread range. Parenthesized `(...)` is the single adjusted vararg value. Thus
`... -1` is a collection spread whose subject is unary `-1` (and is rejected by
type), while `(...) - 1` is scalar subtraction.

Titan input-vararg spreading and C variadic arguments are different mechanisms.
A direct nonvariadic C function, C function pointer, or C allocation pseudo-call
may consume a spread only through its declared finite positions; a Titan spread
does not supply a C function's `...` operands. Load **`titan-ffi`** before using
spreads at a foreign-call boundary.

Existing tail, container, and generic-result capacity limits still apply. When
a spread's length is known only at run time, the generated code checks the
applicable remaining capacity before reading its selected elements or partially
updating a destination.

Functions are first-class. A lambda takes parameter/result types from its
expected function type; absent usable context, annotate its parameters and
result. Without a return annotation or expected result shape it returns zero
values, even if its body writes `return expression`:

```titan
function apply(transform: function (integer): (integer), item: integer): integer
  return transform(item)
end

function use_lambda(): integer
  return apply(function (item) return item + 1 end, 41)
end
```

Lambdas capture lexical locals; mutations are shared by all closures capturing
the same local. `object:method` without call arguments is a bound function
value whose receiver is evaluated once. A lambda cannot name itself through
the local being initialized; use a named top-level helper for recursion.

## Arrays, Maps, and ordinary iteration

An Array `{T}` uses positive integer positions and may have holes. A Map
`{K: V}` is a key/value dictionary. They are distinct:

| Property | Array `{T}` | Map `{K: V}` |
| --- | --- | --- |
| read | `T?` | `V?` |
| nil write | deletes position | deletes key |
| length | highest present positive index, deterministic | only exact integer-key Maps; `__len` or Lua border |
| Lua form | canonical Titan userdata proxy | ordinary Lua table |
| construction | positional entries | `[key] = value`; positional only with exact integer-key context |

`const { T }` is a read-only Array container. It supports indexing, `#`,
iteration, and the same strict element reads, but Titan rejects indexed writes.
A positional constructor in a const target constructs the const tag directly:

```titan
function primes(): const { integer }
  return {2, 3, 5, 7}
end
```

Mutable and const Arrays have distinct canonical Lua proxy tags. Lua may read
and take `#` of either; the const proxy has no writer, so assignment and
mutating `table.*` operations fail.

`const? { T }` is a maybe-const Array view type. It allows a function or data
structure to accept both mutable `{T}` and const `const { T }` Arrays with
zero overhead and zero conversions:

```titan
function sum(items: const? { integer }): integer
  local total = 0
  for i = 1, #items do
    total = total + (items[i] or 0)
  end
  return total
end
```

- `const? { T }` supports `#` and indexed reads, but rejects indexed writes
  (`items[i] = v` is a compile error).
- `{T}`, `const { T }`, and `const? { T }` can all be assigned to
  `const? { T }` (provided element types are consistent).
- Option versions propagate consistently: `({T})?` and `(const {T})?` can both
  be assigned to `(const? {T})?`.
- `const? { T }` cannot be implicitly assigned to `{T}` or `const { T }`.
- `items as { T }` and `items as const { T }` explicitly downcast a `const?`
  Array at runtime, verifying the proxy metatable and raising if the qualifier
  mismatches.
- `items is { T }` and `items is const { T }` perform non-allocating qualifier
  tests.
- Dynamic `value -> const? { T }` unboxing checks both mutable and const
  metatables in $O(1)$.

Cross-qualifier conversion from mutable `{T}` to `const { T }` uses an explicit
shallow snapshot:

```titan
function finish(items: {string}): const { string }
  return items as const { string }
end
```

Semantically this copies the Array container, preserving length, holes, and
element identities. The compiler optimizes this by freezing the original proxy
in place (`titan_array_freeze`) without copying or allocating when conservative
linear-use analysis proves the mutable allocation is unique and unaliased:

1. **Local builder pattern:** A fresh mutable builder local `{}` whose
   references are non-escaping reads/writes (loops, `#`, indexing), with no
   closure captures, frozen in place at its terminal same-block cast or return.
2. **Linear function returns:** When all return paths of a function return a
   freshly constructed array or an unaliased local builder array, the function's
   return type is marked linear. Callers directly assigning or casting the call
   result to a `const` target (e.g. `local res: const { B } = map(xs, f)`)
   freeze the returned array in place without memory allocation.

Passing, storing in an outer aggregate/container, aliasing, rebinding, or
capturing the Array, or using the source afterward retains the copy. Code cannot
observe which path was selected.

Container value types are de-optionized: `{integer?}` means `{integer}`, and
`{string: integer?}` means `{string: integer}`. Nil means absence, not a stored
optional payload. Map keys cannot be nil or Option types.

Constructor shape matters:

```titan
local numbers: {integer} = {10, 20, 30}
local scores: {string: integer} = {
  ["Ada"] = 10,
  ["Grace"] = 20,
}
local empty_map: {string: integer} = {}
```

`{name = value}` is record-constructor syntax, never a string-keyed Map entry.
Array reads below 1 return nil; Array writes below 1 raise. `#array` is the
highest present positive index, not the element count:

```titan
function length_with_hole(): integer
  local values: {value} = {10, 20, 30}
  values[2] = nil
  return #values -- still 3 because position 3 is present
end
```

Maps are their backing ordinary Lua tables and retain any metatable attached at
the Lua boundary. Typed operations use this exact table protocol:

| Titan operation | Lua-compatible rule |
| --- | --- |
| `map[key]` | Return a raw hit; only a miss follows ordinary `__index` chains. Apply the same strict `V?` tag guard to either result. |
| `map[key] = item` | Update or delete a raw-present key directly. Only a raw-absent key follows `__newindex`, including an absent-key nil assignment. |
| `#map` | Accept only an exact `integer` key type. Invoke `__len` when present and require its result to carry the exact Lua integer tag; otherwise use a valid Lua border. |
| Map equality | Resolve identity/raw equality first. For distinct run-time tables, use the left `__eq`, then the right fallback, with Lua truthiness. Map/`value` works in either orientation only when the dynamic value is a table. |

Two `value` operands intentionally remain raw equality even when both happen to
contain those same tables. Metamethod-aware comparison is scoped by a statically
known Map operand, not inferred from dynamic contents.

Typed reads are strict, including values returned by `__index`. If Lua or a
`{value}` view puts a float `2.0` into a slot later observed as `integer`, the
read raises instead of narrowing it. A Map metamethod likewise does not create
a dynamic conversion boundary. A final nil remains the ordinary absent `V?`.
Array passage through Lua/value preserves its one proxy and construction-time
Lua-writer policy. A plain Lua table can satisfy a Map boundary but never an
Array boundary.

### Generic `for`

A generic iterator expression supplies up to four values in this exact order:

```text
(iterator, state, initial control, close)
```

The iterator is required; the rest may be nil. Iteration stops only when the
first iterator result is nil—false is a real item. A present close function is
run after exhaustion, `break`, `return`, or an error from iteration/body. If it
accepts one argument, Titan passes the state.

Use the generic iteration module for collections:

```titan
local iteration = import "iteration"

function total(scores: {string: integer}): integer
  local result = 0
  for _, score in iteration.pairs(scores) do
    result = result + score
  end
  return result
end
```

`iteration.next<|K, V|>` and `iteration.pairs<|K, V|>` preserve Map key/value types.
`iteration.ipairs<|T|>` visits every integer position from 1 through `#array`,
including holes; its **index** is the nonnil first result, while its item is
`T?`:

```titan
local iteration = import "iteration"

function count_positions(items: {string}): integer
  local positions = 0
  for _, item? in iteration.ipairs(items) do
    positions = positions + 1
  end
  return positions
end
```

Unlike Lua's `ipairs`, a nil item does not stop this iterator. `_` is an
ordinary variable, used by convention for an intentionally ignored value.

For a nil-terminated Reader method, the method itself is often the clearest
iterator:

```titan
local io = import "io"

function copy_reader(reader: io.Reader, writer: io.Writer)
  for chunk in reader:read do
    writer:write(chunk)
  end
end
```

### Prefer dense one-to-one construction

When semantics say each dense input position maps to exactly one output
position, allocate the result and assign the same index. Do not pass a mutable
output Array into a “mapper”, invent an append protocol, or split one obvious
state transition across wrappers:

```titan
local string = import "string"

local function uppercase_all(input: {string}): {string}
  local output: {string} = {}
  for index = 1, #input do
    output[index] = string.upper(input[index])
  end
  return output
end
```

This spelling assumes density is part of the operation's contract; an absent
input position fails at its use. If holes are meaningful, use
`iteration.ipairs` and handle the optional item explicitly.

## Records and private behavior

Records and unions keep one nominal identity while storing native fields
separately from traced values. Private fixed non-GC foreign aggregates/arrays
can be embedded by copy; reading them borrows a pointer into the owner. Keep
that owner live and distinguish shallow binding constness from explicit C
pointee qualifiers. Direct fresh const-array/FAM constructor arguments can use
storage in that same owner. Use the FFI cartridge for these cases and
`doc/language/nominal-storage.md` for examples; do not infer field storage from
Lua uservalue indices. Wide native C fields may fail only when an actual
Lua/`value`/reflection observation needs checked boxing.


A record is nominal, reference-like fixed data. Fields are declared inside the
record; methods are top-level colon declarations:

```titan
record Point
  x: float
  y: float
end

function Point:move(dx: float, dy: float)
  self.x = self.x + dx
  self.y = self.y + dy
end

function Point.origin(): Point
  return Point(0.0, 0.0)
end
```

Prefer calling the record: `Point(...)` and `Point{...}` select `Point.new`
with its ordinary visibility, argument adjustment, and complete result list.
`Label "text"` also selects `Label.new "text"`. Imported record names and
aliases behave the same way. Keep `.new` to take the function as a value or
supply its own explicit generic arguments. A bare record namespace is still
not a first-class Titan value. Choose `Record { parameter = value, ... }`
for ambiguous constructor arguments using the named-call guidance above.

By default `new` is synthesized with fields in declaration order. It is private
for a local record or a record with private fields. A context-typed constructor
expression allocates the raw record:

```text
local a = Point(1.0, 2.0)
local b = Point { y = 2.0, x = 1.0 }
local c: Point = { x = 1.0, y = 2.0 }
```

Override construction with an ordinary `[local] function Record.new(...)`:

```titan
record Counter
  local amount: integer
end

function Counter.new(initial: integer?): Counter
  local amount = initial or 0
  if amount < 0 then raise "negative initial count" end
  return { amount = amount }
end
```

The override replaces the generated function completely. Build raw storage
with `{ ... }` inside the defining module; calling `Counter(...)` or
`Counter.new(...)` inside the override recurses. Once `new` is overridden,
context-typed record literals are forbidden outside that module, even through
an explicit `.titan` import and even if all fields and `new` are public.
Importers must call the visible constructor. A public override may initialize
private fields; a local override stays private even for an all-public record.

An override may have arbitrary parameters and results, including no results,
multiple results, or variadic/flexible tails. `Record(...)` has exactly that
call contract; returning the record itself is not required. Overrides are
ordinary computed calls and cannot be constant module-variable initializers.
`Box<|integer|>(x)` binds owner arguments; if `new` has its own generic binders,
use `.new<|U|>` when explicit member arguments are needed, retaining the existing
both-explicit-or-both-inferred rule.

Lua receives a namespace table with `__call` only when `new` is public; its
call forwards to the `new` member without a namespace receiver and preserves
all results. Lua brace calls still pass one table and are not named calls.

A field may be declared `const` after an optional `local`:

```titan
record Request
  const method: string
  local const token: string?
  metadata: {string: value}
end
```

Construction initializes const fields, but later Titan and Lua writes reject
replacement. Constness is shallow: a const Map/record/ordinary mutable Array
field still refers to the same mutable object. Field visibility remains
independent; `local const` is still source-private.

Records compare by identity and cross Lua as userdata. A record assignment
copies the reference. `local` records, fields, methods, and nominal functions
are visible only through the defining module's permitted source collaboration
surface.

When private behavior belongs to a record, make it a **local method**, not a
free function whose first explicit parameter is that record:

```titan
local record Cursor
  index: integer
  limit: integer
end

local function Cursor:advance(): integer?
  if self.index >= self.limit then return nil end
  self.index = self.index + 1
  return self.index
end
```

Call `cursor:advance()`. This keeps ownership, mutation, and the receiver's
nominal type together, allows bound-method use when appropriate, and avoids a
facade helper that merely re-spells method dispatch.

## Unions and `case`

A union is a nominal closed set of tagged alternatives. A variant has a fixed
list of named payload parts and gets a constructor with those names. The old
single-type spelling `found(string)` means `found(value: string)`:

```titan
union Lookup
  found(string)
  moved(x: float, y: float, note: string?)
  stopped(end: integer)
  missing()
end

function move(): Lookup
  return Lookup.moved { y = 2, x = 1 } -- note receives nil
end

function describe_lookup(result: Lookup): string
  case result
  when found(text) then
    return "found " .. text
  when moved{vertical = y; x} then
    return x .. ", " .. vertical
  when stopped{finish = end} then
    return "stopped " .. finish
  when missing() then
    return "missing"
  end
end
```

Choose payload parts for data that belongs only to the variant. Keep a record
when it owns methods, mutable shared state, or a reusable domain type. A
variant is not a type, and its parts are not ordinary instance fields.

Construction and matching have different omission rules:

- `Lookup.moved(1, 2)` passes parts in declaration order. Direct named calls
  such as `Lookup.found{value = "Titan"}` use declared part names; explicit
  expressions evaluate in written order. Omitted arguments receive nil and
  must accept it through normal assignment conversion (`boolean` becomes false).
- `when moved(first)` binds only the first part. Positional binders can omit
  any suffix, including every part, and their names need not match declarations.
- `when moved{vertical = y; x}` selects named parts in any order. The alias is
  on the **left**; the part name is on the right. Unaliased `x` binds part `x`
  to local `x`. Commas/semicolons are optional separators. A match may omit any
  part regardless of its type. An unknown part is a type error; referencing
  the same part twice is a syntax error even with different aliases.
- Part names may be reserved words; local binder names may not. Always alias
  a keyword part, as in `finish = end` above. Variant payloads cannot use a
  `...: T` flextail, mix named and unnamed declarations, or duplicate part names.

A record payload remains one part: for `move(Point)`, write
`Movement.move({x = 1.0, y = 2.0})` or
`Movement.move{value = {x = 1.0, y = 2.0}}`. Bare braces select named calls,
not implicit unpacking of the record. A constructor saved in a function
variable is called positionally.

Each `when`/`else` body is a full independent block and may contain `defer` and
its own `catch`; all arm binders are visible in that catch. Case coverage is
not required: no match and no `else` is a no-op. A `Union?` scrutinee is
forced before dispatch; nil raises and does not select `else`. Union equality
is identity, not structural equality. Use **`titan-reflect`** for dynamic part
inspection and **`titan-json`** for the flat named-part JSON mapping.

## Interfaces are explicit nominal views

An Interface is a public, nonempty, type-only list of read-only fields and
bodyless method signatures. Interface fields use `name: T` and are implicitly
const; write `name: T?` for an optional field. Records use the same type-side
option spelling; `name?: T` is not accepted on fields.
Field and method names share one namespace:

```titan
interface Reader
  name: string
  function read(): string?
end

record Buffer
  const name: string
  contents: string?
end

function Buffer:read(): string?
  local result? = self.contents
  self.contents = nil
  return result
end

function consume(reader: Reader): string?
  return reader:read()
end

function use_buffer(buffer: Buffer): string?
  return consume(buffer)
end
```

There is no `implements` clause. At a statically known conversion site Titan
checks visible members structurally, then constructs a **fresh wrapper of that
exact nominal Interface**. A required field needs a visible same-name const
record field whose type has the ordinary assignment adjustment; a mutable
field is insufficient. A union may satisfy a method-only Interface but never a
field-bearing one. Parameter spellings do not determine method satisfaction;
named calls through the wrapper use the Interface declaration's names. Direct
concrete method calls remain static.

Each conversion captures Interface fields in declaration order after their
checked adjustment. Reads use the snapshot, not a later record lookup, and all
Interface writes reject in Titan and Lua. Snapshotting is shallow: referenced
mutable objects remain shared. A generic parameter constrained by an Interface
exposes these field reads as well as its methods.

This is a direct outer conversion, not inheritance or subtyping. It does not
lift through Arrays, Maps, functions, or generic applications. If `R` satisfies
`I`, `{R}` is still not `{I}`; construct `{I}` one element at a time. Each
conversion is fresh, so retain one wrapper if stable identity (for example, as
a Map key) matters.

At a dynamic `value` or Lua boundary, Titan first accepts an already existing
wrapper of the exact Interface type. It can also wrap bare full userdata when
an initialized generated module has registered a witness for that exact
concrete/Interface pair. A real compiled wrapper site advertises its pair even
when that source path never runs; a matching method set or static `r is I`
alone does not. Witness registration is per Lua state and first-writer wins.
Each successful witnessed conversion returns a fresh wrapper; the exact-wrapper
fast path preserves the existing wrapper.

The same leaf governs a present `I?`, strict Interface-typed Array/Map reads,
Interface Array writers, constrained generic carriers, callable results, and
genuine Lua sinks. Options accept nil before discovery; containers are not
traversed or converted wholesale.

This is compiler-witnessed nominal discovery, not structural reflection.
Dynamic `is I` observes non-nil witness presence without invoking or validating
the entry. Conversion calls a present entry without checking that the candidate
is a Titan record/union or that the entry is a function; debug/native code that
forges metatables has opted out of Titan's safety contract. An Interface can be
explicitly checked/downcast to a visible concrete nominal type; the wrapper
retains the original object.

## Modules, visibility, and initialization

Import syntax is static namespace binding:

```titan
local model = import "app.model"
```

The alias is a prefix, not a first-class value. It is not Lua `require` and
cannot be re-exported. Circular imports are compile-time errors.

Canonical short imports are:

```text
coroutine uv async timer io fs net ssl url http websocket os peg string test lua gc math iteration reflect sqlite3 json
```

They mean the corresponding `titan.*` logical modules.

Lua always loads Titan standard modules by qualified name, such as
`require "titan.fs"`; it does not replace Lua's own `os`, `io`, `math`, or
`string` libraries. Application modules keep the same dotted identity in both
languages (`import "app.model"`, `require "app.model"`).

Most declarations and all function/method bodies are placement-independent.
A module-variable declaration is the important frontier: its annotation and
initializer see only earlier ordinary Titan imports and earlier module variables,
although nominal types, aliases, and callable declarations are known module-wide.
Unbound `foreign import "header.h"` directives populate the complete ordered C
environment. Values use the readonly, shadowable builtin `ffi`; foreign types
use their separate unqualified namespace. Imported declarations/macros are
available throughout the module, including earlier initializers. A written
module-variable initializer must be a compile-time constant. Put computed one-time work in the
single final root `do ... end` initializer.

An initialized `const` module variable is read-only immediately. A
module variable without an initializer, mutable or const, must have an explicit
type accepted by the same missing-nil rule as an omitted mutable local. For an initializer-less const variable, only its owning module's directly executing root initializer may assign it; nested blocks keep
that authority, but nested functions/lambdas and importing modules do not. The
owner initializer may assign conditionally or more than once—this is an
initialization region, not definite single assignment. Public const module
variables remain readable from Titan and Lua, while writes reject.

An ordinary import sees only the producer's public interface, even when module
resolution happens to select source. Append the terminal `.titan` marker to the
written import name to request source collaboration explicitly:

```titan
local model = import "app.model.titan"
```

The marker is not part of the logical module name: this still imports
`app.model`, looks for `app/model/model.titan` and then `app/model.titan`, and
uses `app.model` in manifests and native protocols. It is stripped before
standard-library shorthand expansion, so `import "string.titan"` requests
source for logical module `titan.string`. Public library clients still use
ordinary compiled imports; in particular `uv.titan` is not an adapter escape hatch. A marked import never falls back to `.so`, `.a`,
or Windows `.dll` providers; compilation fails if no matching source module exists.

Only that explicit, loader-proven source import exposes the producer's `local`
declarations. The capability is **direct only**: another module's import does
not grant private access, and binary providers and Lua remain public-only. A
dotted logical module name whose final component is `titan`, such as
`app.titan`, is forbidden because that spelling always means a marked import of
`app`. Bare logical module `titan` and an interior component such as
`app.titan.child` remain valid. A repeated marker such as
`import "app.titan.titan"` therefore strips once and rejects the forbidden
logical name `app.titan`. The reservation is only for logical module keys:
valid roots such as `app.titan.left` and `app.titan.right` may still derive the
physical provider prefix `app.titan` (`app/titan.so` and `app/titan.a` on Linux
and macOS, or `app/titan.dll` on Windows).

A folder module is still one logical module. For `pkg.name`, the main is
`pkg/name/name.titan`; every immediate sibling `.titan` file is a contributor.
All contributors share one namespace, one state, one checker/codegen pass, one
initializer, and one artifact. Top-level `local` is module-private, not
file-private. Contributors are not importable submodules. The main declarations
come first, contributor basenames follow deterministic numeric-byte order, and
the main's optional initializer comes last. Do not use filename order as a
hidden dependency mechanism.

### Replacing compiled dependencies

A separate shared provider is checked at load time against this consumer's
used declarations, after the ABI check. Used function signatures include
parameter names, erased parameter/result types, variadic input, and flexible
results. Used variables preserve erased type and constness; module declarations
may be reordered. Referenced records preserve the complete ordered public field
shape; unions preserve ordered public variants and named payloads. Concrete
methods/statics are checked only when used, including by implicit Interface
conversion. A referenced Interface preserves its complete ordered fields and
methods. Nominal aliases retain both their exposure and canonical owner.

Private record fields may change for accessor-only consumers. Imported record
literals require the provider's raw-construction capability, so adding private
fields or overriding `new` rejects those literal consumers even when the new
callable signature is unchanged. Ordinary constructor calls require only the
public `new` signature, except when fresh native storage is fused into the
record: that optimization also requires raw-construction capability to preserve
ownership. Providers built before this capability need rebuilding for newly
compiled literal consumers; older consumers do not distinguish
same-signature overrides from ordinary compatible `new` replacements. Private union
variants may change unless the consumer relied on complete coverage for a
non-fallthrough proof; invalidating that proof fails at load time. Ordinary
unmatched cases still do nothing. An independently terminating `else` needs no
closed-inventory assumption; an unreachable falling-through `else` does.

Keep `mod.func()` as a direct native call and `mod.func` as the canonical
function value. Separate shared dependencies resolve moved variable/closure
slots through the selected logical provider. Within one Lua state, an already
initialized module wins before any selected DSO filename is opened, including
providers embedded in an executable, linked from an archive, or initialized
through `package.loadlib`. Each new dynamic consumer checks its own requirements
against that canonical provider. Source/archive dependencies linked into the same
binary keep fixed native bindings and require that exact linked provider's state.
Native pointers, callable-tag caches, and Interface arrays belong to per-state
module payloads, so another Lua state cannot overwrite them.

Replacing a file does not hot-reload an initialized module. Validate replacement
files in a fresh process with the consumer unchanged; also exercise plugins
against an already initialized host provider when that is the deployment model.
Compiler cache validity and rebuilding affected consumers are separate decisions. See
[`binary-compatibility.md`](../../../doc/language/binary-compatibility.md).

Native bootstrap code can use a newly generated logical module's
`const char *<mangled>_abi_value(void)` query without Lua, allocation, or module
initialization. Its immutable ABI string belongs to the provider; do not free
it or unload the image while using it. Call it with its C signature, never
through `package.loadlib` or `titan._loadlib`. The Windows loader requires this
query and checks it before calling Lua metadata entries or the initializer;
existing Unix ABI-2 providers may omit it. The existing Lua-callable `_abi`
entry, Unix loading behavior, compiled-code ABI `2`, and language-server API
`1` remain unchanged.

## Errors, `catch`, and `defer`

Use options for ordinary absence and errors for exceptional failure or violated
assumptions. `raise expression` raises any value after boxing it to `value`.
A bare `raise` inside a catch rethrows the original value **and original
traceback**.

Titan has no `try`. `catch` is a trailer on an already existing block:

```titan
local fs = import "fs"

function first_line_or_empty(path: string): string
  local file = fs.open(path, "r")
  defer file:close()
  return file:read_until("\n", true) or ""
catch
  -- `error: value` and `traceback: string` are read-only here.
  return ""
end
```

The same trailer can attach to a function or lambda body, loop body, each
`if`/`elseif`/`else` arm, each union arm/else, the root module initializer, or
an explicit `do` block. The protected body and catch are **sibling scopes**.
Locals declared in the body are not visible in the catch because the body may
have failed before initializing them. A catch that falls through handles the
error; use bare `raise` to propagate it.

Do not introduce `do ... end` solely to “enable catch”. Use one only when a
smaller protection or lexical scope is genuinely intended. Current source
syntax has no user-facing `finally` clause; use `defer` for deterministic
cleanup.

`defer statement` registers cleanup on the **current statement-list block**.
Acquire first, register immediately, then proceed. It runs on fallthrough,
`return`, `break`, and error. Multiple defers in one block run LIFO. Return
values are evaluated and saved before cleanup. If cleanup raises, that new
error replaces the pending return, break, or error.

A deferred statement sees declarations already in scope at its registration
point, not locals declared later. A defer in a loop belongs to that iteration's
body; a defer in an `if` or `case` arm belongs only to that arm. Use
`defer do ... end` only when one logical cleanup contains several statements:

```titan
function cleanup_example(flush_pending: function (): (),
                         close_resource: function (): ())
  defer do
    flush_pending()
    close_resource()
  end
end
```

A deferred statement cannot return from the enclosing function or break an
outer loop.

## Core standard library

Prefer a standard-library operation when its documented semantics match the
work. These summaries are not exhaustive: before writing a delimiter scanner,
pattern matcher/substituter, or another common helper absent from the inventory,
check the owning `doc/language/standard-library-*.md` chapter linked below.
Keep application policy such as empty-field filtering, size limits, or stricter
validation around the existing operation. Retain custom code when its required
semantics differ; name that difference rather than inferring an API is absent
from this cartridge alone.

### `string`: bytes, conversion, building, packing, regex

Use the canonical module name:

```titan
local string = import "string"
```

The import binding `string` does not conflict with the primitive `string` type
in annotations. Primitive type words are contextual identifiers and retain their
meaning in type positions. Choose another import name only for an actual term
naming conflict or a name that adds meaning, not to avoid the type spelling.

All positions and lengths are **bytes**, generally one-based. Embedded NUL is
ordinary data except where a documented C-style format forbids it. Important
signatures:

```text
function len(subject: string): integer
function sub(subject: string, first: integer, last: integer?): string
function reverse(subject: string): string
function lower(subject: string): string
function upper(subject: string): string
function rep(subject: string, count: integer,
             separator: string?): string
function byte(subject: string, first: integer?,
              last: integer?): (...: integer)
function char(...: integer): string
function find(subject: string, needle: string,
              init: integer?): (integer?, integer?)
function tostring(candidate: value): string
function format(format_string: string, ...: value): string
```

`find` is a literal byte search, not Lua-pattern or regex search. Success
returns one-based first and inclusive last; failure returns nil, nil. `sub`
uses Lua index normalization. `lower`/`upper` are bytewise C-locale operations,
not Unicode case folding. `tostring` deliberately uses Lua conversion and can
invoke `__tostring`; ordinary typed `string` parameters never coerce numbers.

`format` supports Lua 5.5 conversion flags, widths, and precisions. `%d` formats
an integer in decimal; `%x`/`%X` use lowercase/uppercase hexadecimal. For a known
byte in `0..255`, `string.format("%02x", byte)` produces exactly two lowercase
hex digits, including a leading zero. Numeric conversions check their operands;
numeric strings are not accepted as numbers. `%s` uses `string.tostring`.

Use the synchronous linear-time writer instead of repeatedly concatenating a
growing result or inventing a chunk-array helper:

```titan
local string = import "string"

local function join_lines(lines: {string}): string
  local output = string.writer()
  for index = 1, #lines do
    output:write(lines[index])
    output:write("\n")
  end
  return output:drain()
end
```

`string.reader(contents)` and `string.writer()` provide synchronous
in-memory Reader/Writer records with idempotent `close`. `pack`, `packsize`,
and `unpack` implement Lua 5.5 binary formats with typed checked dynamic
operands.

Compiled regexes are byte-oriented and separate from Lua string patterns:

```titan
local string = import "string"

local function first_word(subject: string): string?
  local words = string.compile_regex("[A-Za-z_][A-Za-z0-9_]*")
  local found? = words:match(subject)
  if not found then return nil end
  return found:whole()
end
```

`Regex:match` is a leftmost search unless `^` anchors it. `Regex:gmatch`
yields nonnil `RegexMatch` records; `Regex:gsub` takes exactly a
`function (string): (string)` callback receiving the whole match. Load **Titan PEGs**
when implementing a real grammar or structured parser.

For ordinary searches, validation, iteration, splitting, and replacement, the
source-expression conveniences use a private weak regex-compilation cache:

```text
function match(subject: string, expression: string,
               init: integer?): RegexMatch?
function gmatch(subject: string, expression: string,
                init: integer?): function (): (RegexMatch?)
function matches(subject: string, pattern: string):
    function (): (string?, ...: string?)
function split(subject: string, delimiter: string?): function (): (string?)
function gsub(subject: string, expression: string,
              replacement: function (string): (string),
              maximum: integer?): (string, integer)
```

`match` returns a typed match or nil; use `^` and `$` for whole-string validation.
`matches` projects whole matches or capture tuples; an unmatched first capture
terminates a generic `for`, so use `gmatch` when that capture can be optional.
`gsub` passes the whole match to its replacement function, not capture arguments.

Use `split` rather than a custom delimiter-search loop when the contracts match:

```titan
local string = import "string"

function nonempty_comma_fields(subject: string): {string}
  local fields: {string} = {}
  for field in string.split(subject, ",") do
    if field ~= "" then fields[#fields + 1] = field end
  end
  return fields
end
```

A supplied delimiter is a **regex**, not a literal search string. Comma, slash,
and ampersand are literal regex bytes; a literal dot needs `"\\."` in Titan
source. Captures in the delimiter are ignored. Leading, adjacent, and trailing
delimiters yield empty fields; an empty subject with a supplied delimiter yields
one empty field. An empty string is a real item and only nil ends the iterator.
The example skips empty fields as caller policy and does not trim
whitespace. With nil or omitted delimiter, `string.split(subject)` iterates
individual bytes and yields nothing for an empty subject. Zero-width delimiters
make byte progress rather than looping forever. A custom literal splitter for
arbitrary delimiters cannot be replaced blindly with regex splitting.

### `math`: typed numerical operations

Import the module:

```titan
local math = import "math"
```

The ordinary transcendental/numeric surface is float-oriented: `abs`, `acos`,
`asin`, `atan`, `ceil`, `cos`, `deg`, `exp`, `floor`, `fmod`, `log`, `log2`,
`log10`, `max`, `min`, `modf`, `rad`, `sin`, `sqrt`, and `tan` take float
operands and return one or more floats. `frexp(float)` instead returns
`(float, integer)`, and `ldexp(float, integer)` takes an integer exponent and
returns float. Integer arguments convert to float at a float argument sink.
Operations such as `ceil`, `floor`, `abs`, and `max` still return float; do not
assume Lua's dynamically selected integer result.

Constants are `pi: float`, `huge: float`, `maxinteger: integer`, and
`mininteger: integer`. `ult(a, b)` compares integers as unsigned values.

```titan
local math = import "math"

function numeric_sample(): boolean
  local root = math.sqrt(81)       -- integer argument becomes float
  local parsed? = math.tointeger("0xff")
  return root == 9.0 and (parsed or 0) == 255
end
```

`tonumber(candidate, base?)` returns `value?` because a successful value may be
integer or float. `tointeger(candidate)` returns `integer?` and is usually the
simpler API when an integer is required.

`random()` returns a float in `[0,1)`; bounded forms return integer, but the
static result is `value` because one declaration serves both shapes. A typed
sink can strictly project the known form:

```titan
local math = import "math"

function random_sample(): boolean
  math.randomseed(17, 29)
  local unit: float = math.random()
  local die: integer = math.random(1, 6)
  return unit >= 0.0 and unit < 1.0 and die >= 1 and die <= 6
end
```

The generator matches Lua 5.5's xoshiro256** stream and is not cryptographic.

### `iteration`: typed collection iteration

Import the module. Its public generic signatures are:

```text
function next<|K, V|>(map: {K: V}, key: K?): (K?, V?)
function pairs<|K, V|>(map: {K: V}):
    (function ({K: V}, K?): (K?, V?), {K: V}, nil, nil)
function ipairs<|T|>(array: {T}):
    (function ({T}, integer): (integer?, T?), {T}, integer, nil)
```

Types normally infer from the collection. Map traversal order is unspecified.
See the generic-`for` and hole behavior above.

### `io`: stream Interfaces, printing, lines, shell commands

Import `io` by its short name. Its seven type-only Interfaces are the useful
vocabulary formed from these methods:

```text
read(): string?
read_until(delimiter: string, chop: boolean?): string?
write(data: string)
close()
```

The combinations are `Reader`, `Writer`, `Closer`, `ReaderWriter`,
`ReaderCloser`, `WriterCloser`, and `ReaderWriterCloser`. Concrete records such
as `fs.File`, string readers/writers, process streams, and network connections
satisfy the appropriate Interfaces structurally at each typed conversion.

Automatic Option force keeps ordinary stream code direct:

```titan
local io = import "io"

function copy_chunks(reader: io.Reader, writer: io.Writer)
  for chunk in reader:read do
    writer:write(chunk)
  end
end
```

An empty string is a real chunk; only nil is EOF. `io.lines(reader:
io.ReaderCloser)` transfers close ownership to the generic iterator, reads
newline-delimited lines with the delimiter chopped, and closes after EOF,
`break`, return, or error. Do not also manage the same closer independently
while the iterator owns it.

`io.print(...: value)` converts with `string.tostring`, joins with tabs, appends
a newline, and performs one `os.stdout` write. `io.popen(command)` intentionally
runs `/bin/sh -c` on Linux and macOS or the system `cmd.exe /d /s /c` on
Windows; commands use that shell's syntax. It gives writable stdin plus one
readable byte stream merging stdout and stderr, and must be drained before
waiting when output can fill a pipe. Use `os.spawn` for direct executable/argv
control or separate stdout/stderr. Close and Task cancellation do not guarantee
descendant termination.
These operations may suspend; load **`titan-async`** for scheduling and process
ownership.

### `fs`: files, paths, metadata, and watching

Import `fs` by its short name. High-value APIs:

```text
function open(path: string, mode: string): fs.File
function read_file(path: string): string
function write_file(path: string, data: string)

function File:read(max_bytes: integer?): string?
function File:read_until(delimiter: string,
                         chop: boolean?): string?
function File:write(data: string): integer
function File:flush()
function File:close()
function File:is_closed(): boolean

function stat(path: string): fs.Stat?
function lstat(path: string): fs.Stat?
function realpath(path: string): string
function list(path: string): {string}
function mkdir(path: string)
function unlink(path: string)
function rmdir(path: string)
function rename(from: string, to: string)
```

(The `fs.` qualifier in the signature list denotes the imported types; inside
the module source they are written `File` and `Stat`.)

Modes are the familiar `r`, `w`, `a`, and `+` families, with optional `b`.
File contents are binary strings. `File:read()` defaults to 64 KiB and returns
nil only when no bytes are available at EOF. `read_until` is delimiter-aware
across chunks. Always close application-owned Files; Runtime teardown does not
own operating-system file descriptors:

```titan
local fs = import "fs"

function replace(path: string, contents: string)
  local file = fs.open(path, "w")
  defer file:close()
  file:write(contents)
  file:flush()
end
```

`stat` follows symlinks and `lstat` inspects the link. A missing path is nil;
other errors raise. `Stat` fields are `size`, `kind`, `mode`, `device`, `inode`,
`modified_seconds`, and `modified_nanoseconds`; kind is `"file"`,
`"directory"`, `"symlink"`, or `"other"`. `list` omits `.`/`..` and does not
promise order. Compare the opaque `device`/`inode` pair only for physical-file
identity; either field may be negative because it carries an unsigned host bit
pattern. Paths reject embedded NUL; contents do not.

`tmpname` creates an empty file owned by the caller; `tmpdir`, `homedir`,
`pwd`, and `chdir` provide synchronous directory helpers. Restore a temporary
process-wide `chdir` with `defer`.

`fs.watcher()` exposes `watch`, `stop`, `is_watching`, `clear`, and `poll`, with
`WatcherEvent.created/deleted/modified/error`. It is Runtime-bound,
notifications are hints, one raw notification maps to one public event, and
Tasks mutating one Watcher must coordinate externally. Load **Titan async**
before changing watcher behavior or callback ownership.

Classification may suspend while callbacks append to the fresh notification
Array. If the current drain retires a registration and that fresh Array
contains a notification for it, the same `poll` takes the complete fresh batch
in callback order and repeats. This preserves one-to-one event mapping and
cross-registration order while preventing an already-copied notification for a
retired registration from leaking into the next `poll`. A fresh batch containing
only live registrations remains buffered for the next call.

### `os`: clocks, calendar, environment, paths, signals, processes

Import the short Titan module:

```titan
local os = import "os"
```

Synchronous core:

```text
function clock(): float
function difftime(later: integer, earlier: integer): float
function date(format: string?, timestamp: integer?): value
function time(year: integer?, month: integer?, day: integer?,
              hour: integer?, min: integer?, sec: integer?,
              isdst: boolean?): integer
function setlocale(locale: string?, category: string?): string?
function getenv(name: string): string?
function setenv(name: string, contents: string)
function unsetenv(name: string)
function cwd(): string
function chdir(path: string)
function homedir(): string
function tmpdir(): string
function hostname(): string
function exepath(): string
function pid(): integer
function ppid(): integer
```

`clock` is consumed CPU time, not wall time. `date` returns either string or an
`os.Date` record through `value`. Exact nominal recovery can use an annotated
strict projection after a test:

```titan
local os = import "os"

function epoch_year(): integer
  local result = os.date("!*t", 0)
  if result is os.Date then
    local epoch: os.Date = result
    return epoch.year
  end
  raise "expected calendar date"
end
```

`is` does not narrow `result`; the annotation performs the strict exact-record
projection. This is safe because nominal `value is/as os.Date` and strict
projection all require the exact `os.Date` identity.

Use named calls for calendar construction:

```titan
local os = import "os"

function example_noon(): integer
  return os.time { year = 2026, month = 7, day = 31 }
end
```

Environment, locale, and working-directory state are process-global; coordinate
changes and restore temporary state.

Async/process APIs include `wait_signal`, graceful `exit`, `spawn`,
`Process:wait/kill/is_running`, and `InputStream`/`OutputStream` operations.
`spawn(file, args, ...: SpawnOption)` executes `file` directly; args omit
`argv[0]`. By default it captures all three child descriptors. Options choose
capture, parent inheritance, or merged output. `with_env(name, contents)` returns
a `SpawnOption` that overrides one variable only in the child; all others are
inherited, and the parent environment remains unchanged. Parent-facing `process.stdin`
is an `OutputStream?`; stdout/stderr are `InputStream?`. Drain captured output
concurrently with input and wait when pipe capacity can matter. Closing a
process watcher does not kill or reap its child. Load **Titan async** for these
ownership and cancellation rules.

## Compile with `titanc`

Use an installed ABI-matched Titan/Lua 5.5 toolchain. Run from the source-tree
root and pass dotted **module names**, never `.titan` paths.

A minimal application tree:

```text
scratch/
  calc.titan
  check.titan
```

```titan
-- calc.titan
function twice(number: integer): integer
  return number * 2
end
```

```titan
-- check.titan
local calc = import "calc"

function main(args: {string}): integer
  if calc.twice(21) == 42 then return 0 else return 1 end
end
```

Compile and run on Linux or macOS:

```sh
(cd scratch && titanc check && ./check)
```

The exact exported `main(args: {string}): integer` makes a standalone
executable. `args[1]` is the first user argument; there is no index 0 entry.
Any other `main` signature is an ordinary library function.

Without an exact `main`, a single root on Linux or macOS builds paired
shared/static providers and a Lua shim:

```sh
(cd scratch && titanc calc)
(cd scratch && lua -e 'assert(require("calc").twice(21) == 42)')
```

Experimental Windows library builds emit DLL providers and Lua shims, with no paired
Titan archive; `--static` and selected Titan archive providers are unsupported.
Compilation is serial even when `--jobs` is larger than one. The `check` program
above produces `bin/check.exe` and `lib/titan/0.6/check.dll`; `--launcher-name`
changes only the launcher basename. Windows uses the matched controlled Lua DLL
and its SDK, not an ordinary stock Windows Lua build. Keep that Lua DLL beside
the Lua interpreter, compiler frontend, and application launcher EXEs. Follow
the [Windows build guide](../../../doc/implementation/windows-build.md) for
toolchain, layout, native dependencies, and experimental limitations.

Use the matched installed `lua`. A dotted module maps dots to directories;
`titanc app.check` finds folder `app/check/check.titan` before flat
`app/check.titan`. `--tree ROOT` changes the source root. Useful driver options
include:

```text
-j N / --jobs N       bound generated-C object compilation
--static              Linux/macOS: prefer Titan .a dependencies; not linker -static
--launcher-name NAME  Windows standalone/test EXE basename
--test                build a native Titan test executable
--no-uv-bootstrap     explicit standalone/test Runtime ownership mode
-v                    show safely quoted native tool commands
--pretty-print         opt in to clang-format for generated C/headers
```

`--tree` redirects source lookup, not ordinary generated C/object output:
those files remain beside the selected source. Different working directories
alone cannot isolate builds that share sources. Stage separate source copies
for application/test modes or other configurations that must not overwrite
each other's objects; let the build system own their invalidation. For a
standalone delivery claim, check a relocated executable with the compiler and
Titan provider unavailable. `--static` is a preference and can still select a
DSO, so successful compilation alone does not prove provider independence.

The compiler typechecks all requested roots and transitive dependencies before
emitting C. Explicit command-line roots are selected from source; ordinary
dependencies prefer compiled providers, then source, but expose only their
public interfaces either way. `--test` deliberately changes ordinary dependency
lookup to source-first with compiled fallback on a clean miss; it does not
change that public-only visibility. Spell a collaborating dependency as
`import "name.titan"`; that import requires source and exposes locals without
changing the logical name. Command-line roots themselves remain unsuffixed
logical names. To test compiler Lua edits without reinstalling them, run the
prefix's `busted --run=checkout` from the repository root with command-scoped
`TITAN_ROCKS_ROOT="$PREFIX" TITAN_PROBE_CACHE_DISABLE=1`. The `.busted`
profile selects checkout Lua after the LuaRocks launcher, and the existing root
option preserves the installed headers and runtime libraries. The profile's
Busted helper also prepares direct checker C-header lookup through the existing
driver APIs and rejects a missing root option. Default Busted
runs and installed CLI consumers such as `titanc` still require reinstalling
compiler edits. Reinstall after runtime or standard-library changes as well.
`make test` installs the current compiler and provider before the complete
suite; keep its canonical environment free of the focused root override.

## Standard-library implementation taste: keep the architecture direct

For changes inside Titan's standard library, use these review rules in addition
to the language rules:

- **Put private record behavior on the record.** Prefer
  `local function Owner:operation(...)` to a free helper whose first argument
  is `Owner`.
- **Use the real owner and public composition boundary.** `titan.uv` is a
  public callback API and the sole owner of libuv FFI. Consumers use ordinary
  `import "uv"` plus generic `async` await/subscription primitives. Do not
  import `uv.titan`, native libuv headers/types/helpers, or private Runtime
  state from another module. Do not add forwarding aliases, duplicate checks,
  or extra state fields merely to avoid the existing direct flow.
- **Honor the supported trust/concurrency model.** Do not harden one imagined
  race when the API requires callers to serialize all mutations. Partial
  rechecks imply guarantees the rest of the object does not provide.
- **Model one operation once.** One native notification should create one raw
  owned event and later one public event. Split logically different phases
  such as “stop accepting events” and “close the native handle”; do not add
  alias indexes, generations, snapshot rollback, operation queues, or fencing
  without a real documented contract.
- **Complete an ownership-retirement boundary.** When classification can yield,
  detach the current callback batch before mapping it. If mapping retires an
  owner and the fresh batch contains that retired owner, take the complete fresh
  batch in order and continue. Do not filter, discard, merge, or reorder raw
  events; leave a live-owner-only fresh batch for the next consumer call.
- **Map dense data densely.** Allocate one result, write `out[index] =
  transform(in[index])`, and return it. Do not make a mapper mutate a caller's
  output Array when one-to-one construction is the semantics.
- **Do not defend against impossible async preemption.** Titan Task/libuv code
  is cooperative. Unrelated loop events cannot preempt ordinary Titan
  statements. Explicit low-level calls with synchronous callbacks, such as
  `uv.walk` and Windows TTY read startup, follow their documented timing;
  they are direct calls rather than preemption. Load **Titan async** before
  reasoning about callback order.
- **Keep foreign worker code C-only.** `async.run_foreign` is the one explicit
  worker-pool escape from main-loop Titan execution: the worker performs only
  its C `f(arg)`, never touches Titan/Lua state, and retains native ownership
  through the loop-thread after-work callback.
- **Cleanup remains owned until terminal native completion.** Cancellation
  does not license dropping a callback owner or double-closing a libuv handle.
  One-shot callbacks settle their exact await capability, while explicit
  `Task:resume(token)` may wake only the matching `async.suspend(token, ...)`;
  do not paper over an early-resume bug with consumer-side generations.

The current filesystem watcher demonstrates the preferred local-method and
dense-drain shape:

```text
local function Watcher:drain_notifications(): {WatcherEvent}
  local notifications = self.notifications
  self.notifications = {}
  local events: {WatcherEvent} = {}
  while #notifications > 0 do
    for index = 1, #notifications do
      events[#events + 1] = self:map_notification(notifications[index])
    end

    local crosses_retirement = false
    for index = 1, #self.notifications do
      if self.notifications[index].registration.index == 0 then
        crosses_retirement = true
        break
      end
    end
    if not crosses_retirement then return events end

    -- Take the whole follow-on batch to preserve callback order across owners.
    notifications = self.notifications
    self.notifications = {}
  end
  return events
end
```

## Authority and drift checks

This cartridge is the operational default; do not read every link before an
ordinary edit. When a rule is uncertain, an API is changing, or source and prose
disagree, resolve it at the narrow owner:

- language overview and runnable examples:
  [`doc/language/index.md`](../../../doc/language/index.md) and
  [`doc/quick-tour.md`](../../../doc/quick-tour.md);
- type relations, automatic conversion, Options, and dynamic boundaries:
  [`types.md`](../../../doc/language/types.md),
  [`option-types.md`](../../../doc/language/option-types.md), and
  [`expressions.md`](../../../doc/language/expressions.md);
- declarations and data modeling:
  [`functions.md`](../../../doc/language/functions.md),
  [`spread-expressions.md`](../../../doc/language/spread-expressions.md),
  [`closures.md`](../../../doc/language/closures.md),
  [`const-values.md`](../../../doc/language/const-values.md),
  [`generics.md`](../../../doc/language/generics.md),
  [`arrays-maps.md`](../../../doc/language/arrays-maps.md),
  [`records.md`](../../../doc/language/records.md),
  [`unions.md`](../../../doc/language/unions.md), and
  [`interfaces.md`](../../../doc/language/interfaces.md);
- module visibility and physical source shape:
  [`modules.md`](../../../doc/language/modules.md),
  [`source-import-visibility.md`](../../../doc/language/source-import-visibility.md),
  and [`folder-modules.md`](../../../doc/language/folder-modules.md);
- errors, cleanup, and project idiom:
  [`error-handling.md`](../../../doc/language/error-handling.md),
  [`defer.md`](../../../doc/language/defer.md), and
  [`doc/style-guide.md`](../../../doc/style-guide.md);
- core libraries:
  [`string`](../../../doc/language/standard-library-string.md),
  [`math`](../../../doc/language/standard-library-math.md),
  [`iteration`](../../../doc/language/standard-library-iteration.md),
  [`io`](../../../doc/language/standard-library-io.md),
  [`fs`](../../../doc/language/standard-library-fs.md), and
  [`os`](../../../doc/language/standard-library-os.md).

For a public feature change, the language manual defines user behavior and the
matching chapter under [`doc/implementation/`](../../../doc/implementation/index.md)
defines compiler/runtime mechanics. Inspect the owning source and focused tests
as executable evidence, then update both manuals with the code. Changes to this
skill tree should rerun the lightweight cartridge and routing matrix in
[`EVALUATION.md`](EVALUATION.md).

## Native production source coverage

For opt-in executable-line coverage, use `titanc --coverage DIRECTORY` with
repeated `--coverage-module NAME` for the complete production inventory, including
modules no test currently imports. Selected names require source; omit test
owners/helpers and `titan.test`, and split mixed test/production modules. The mode
owns separate C/object/header/image/notes paths, uses GCC 14+ with matching gcov,
and performs a real attribution probe before compilation. Clang and Windows
CLANG64 fail clearly for this initial backend. Keep source directives enabled.

Use the installed host `titan-coverage seal`, `run`, and `report` commands after
building. Each run needs a fresh directory; wait for all children to exit, retain
run receipts/counters, and preserve failing or incomplete collection. Reporting
uses pinned gcovr 8.4; local coverage needs no Codecov credentials and CI uploads
separately. It covers Titan executable lines only, not generated-C
branch/function percentages. Staged builds use `--coverage-root` and repeated
`--coverage-source-map STAGE=TRACKED`; compiled/tracked bytes must agree. Changed
coverage settings require a fresh directory. `--incremental` retains isolated
receipt-checked objects but callers must invalidate dependent inline helpers;
the repository coverage recipe rebuilds without that option. Sealing rejects
bare carriage returns in source; LF and CRLF work. See
[`native coverage`](../../../doc/language/native-coverage.md) for commands and
[`implementation`](../../../doc/implementation/native-coverage.md) for ownership.

## Before finishing

- Recheck exports versus `local`, module-variable constant/order rules, and
  source-versus-binary visibility. Ordinary imports stay public-only even when
  source wins; private collaboration requires a terminal `.titan` marker and a
  real source module.
- For a public C type, prove the complete graph uses only contextual portable
  primitives/pointers/functions/owners; keep every imported/header-dependent C
  type private.
- Recheck const-local RHS requirements, nil-bearing mutable omissions, owner
  initializer authority, shallow const fields/Interface snapshots, and exact
  mutable versus const Array tags. Treat mutable-to-const copy elision as valid
  only under the checker-proven no-escape/final-use builder shape.
- Remove ceremonial `as` casts; then verify that every remaining one really
  requests broader dynamic conversion, a downcast, or FFI behavior.
- Recheck Option preservation (`name?`) versus fail-fast force, especially for
  false-capable bases.
- Recheck fixed/variadic/flexible call shape, tail-only spreads, inclusive
  range bounds, evaluate-once carriers, and finite `T?` versus open `T`
  consumption.
- Recheck Array versus Map constructor shape, holes, deterministic Array
  length, and typed read guards. For Maps, verify raw-hit-first `__index`,
  absent-key-only `__newindex`, exact-integer `__len`, scoped Map table `__eq`,
  and intentionally raw `value`/`value` equality.
- Put private nominal behavior on local methods and keep state transitions
  direct.
- Register cleanup immediately after acquisition; do not invent a block merely
  for `catch`/`defer`.
- Load the specialist skill before tests, async/libuv, networking, FFI/Lua, or
  PEG work. Keep tests in Titan's native test layer unless the behavior truly
  belongs to the compiler/build boundary.
- If a user-visible language or standard-library API changes, update the
  authoritative language and implementation manuals and the owning tests in
  the same change.
