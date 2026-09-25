---
name: titan-ffi
description: Use Titan's C FFI, source-defined C callbacks, Lua interoperability, the titan.lua escape hatch, or the trusted Lua C API boundary. Covers foreign imports, local C types, pointers, arrays, owned storage, casts, C expressions, macros/enums, rooting, and lifetimes. Do not invoke merely because an implementation is C-backed when no foreign or Lua/C boundary is touched.
---

# Titan FFI and Lua escape hatches

Use this skill when Titan code imports a C header, handles a C value, writes a C
callback, crosses the Lua boundary, dynamically loads Lua code, or touches the
Lua C API. Titan is a statically typed, ahead-of-time compiler to C. It is not
Lua with annotations, and neither `value` nor Lua nor C turns off the need to
design a typed boundary.

Load `titan-programmer` first for core language rules. Also load `titan-async`
when a native callback participates in asynchronous ownership, and
`titan-tester` when adding or changing behavior tests.

The two escape hatches in this skill are equally powerful:

* `foreign import` emits direct C operations. It has C's memory unsafety and C's
  undefined behavior.
* `titan.lua` can compile and execute arbitrary Lua or load Lua/C/Titan modules
  in the current Lua state. It can bypass most static structure just as surely
  as the FFI can.

Use both **sparingly**. Keep each escape hatch in one small owner module, convert
immediately to ordinary Titan types, and expose a typed Titan API. Prefer an
existing Titan standard module or a typed Lua callable over a new raw boundary.
An explicit Lua environment is a Lua upvalue choice, not a security sandbox;
never execute untrusted source or bytecode merely because the result will later
be cast.

## Start with the right tool

Before writing code, classify the job:

| Need | Preferred mechanism |
| --- | --- |
| Call an ordinary C declaration in a header | `foreign import "header.h"`, then `ffi.member` |
| Store a fixed C object or buffer owned by Titan | `.new()` / `.new_array(...)`, normally with an explicit `owned` type when it escapes |
| Pass a C callback implemented in a small C-only body | top-level restricted `foreign function` |
| Pass an ordinary Titan closure to C | **unsupported**; redesign around a restricted foreign function or a narrowly justified C shim |
| Call a Lua function already supplied as a value | give it a Titan function type and call it normally |
| Compile Lua text/binary, execute a Lua file, or load a Lua/C/Titan module | `local lua = import "lua"` |
| Configure weak maps, finalizers, or the collector | `local gc = import "gc"`, not raw metatable/Lua-stack code |
| Perform a stack-oriented `lua_*` operation | avoid in application code; it is a narrow audited standard-library exception, described below |
| Wrap libuv or another async callback API | use this skill for the C surface and the async skill for Task/Runtime ownership; cancellation does not end native ownership |

Do not add a C forwarding function merely because C looks more familiar. If
Titan can spell the operation through the imported header, keep the call,
conversion, ownership, and error translation in Titan. Hand-written C is for a
real exceptional boundary, such as an opaque layout or a required unsupported
function-like macro, and the adjacent comment must say why it exists.

## Non-negotiable boundary rules

1. A foreign namespace is compile-time-only. It cannot be stored, passed,
   returned, or exported.
2. Header-dependent C types are nonexportable implementation types. Public
   interfaces may use only Titan's contextual C primitives and recursively
   portable pointer, foreign-function-pointer, and owned graphs built from
   them. An imported typedef remains nonexportable even when it resolves to a
   portable primitive.
   A C function pointer boxes as lightuserdata through Titan's toolchain
   portability cast. Portable function-pointer types can occupy module,
   record, union, and Option slots and return through Lua/strict stack entries.
   Boxing does not retain the C signature: recovery from arbitrary `value`
   requires an explicit unsafe `as` cast.
3. C pointers are nullable and borrowed unless a documented C API says
   otherwise. A pointer is not an owner or a GC root.
4. A Titan string passed to C is immutable borrowed bytes valid for the call,
   not a buffer C may retain or modify.
5. Use `owned *T` / `owned T[]` for inline C storage whose lifetime belongs to
   Titan's GC. The owner has no automatic resource finalizer.
6. C arrays and pointers are 0-based. Titan Arrays are 1-based and are not C
   arrays.
7. Let a typed destination perform Titan's direct coercion. Add `as` only to
   request a different semantic operation, make an unsafe assertion explicit,
   or select the type of a C variadic argument.
8. A C scalar stays in its exact C type until a real boundary converts it.
   Numeric crossings are checked against the active target, `lua_Integer`, and
   `lua_Number`; do not assume host widths.
9. A C-mode operator has C promotions and C undefined/implementation-defined
   behavior. Cast to a Titan number before the operator when Titan/Lua numeric
   semantics are intended.
10. An ordinary Titan function is not a C callback. A source `foreign function`
    is a restricted raw-C body, not a hidden adapter.
11. The built-in `L` is the current call's `lua_State *`. Never save or return
    it. A `foreign function` does not receive `L` implicitly.
12. A raw Lua stack slot is a root only while it is below the current stack top.
    A copied C pointer or `TValue *` is not a root, and stack growth may move the
    slots.
13. Keep the original Titan owner reachable for every API-documented extended
    borrow or callback data address. This does not by itself extend the ordinary
    string-to-C conversion beyond its call-only contract.
14. Prefer `titan.lua`, `titan.gc`, typed Maps/Arrays, and ordinary typed
    callable values over scattered raw `lua_*` calls.

The readonly ordinary-function builtin `M` is the current module marker.
`M.member` selects current-module members, including local/keyword-named ones;
`M as foreign *Udata` exposes its borrowed userdata pointer. It is not an
ordinary pointer expression. Foreign functions receive neither `L` nor `M`.

# The C FFI

## `foreign import`: compile-time declarations, direct C calls

A foreign import is an unbound top-level directive. All its declarations join
the module-wide C environment. Values use the builtin `ffi` binding:

```titan
foreign import "stdio.h"

function hello(name: string): integer
  return ffi.printf("hello, %s\n", name)
end
```

The compiler preprocesses and parses the module's ordered header environment at
compile time. Generated C includes that environment and emits a plain C call;
there is no run-time reflection or libffi layer. `ffi` is a readonly namespace binding, not a
value. Ordinary declarations may shadow it; unqualified foreign type lookup
remains independent of the term binding. The old bound import syntax is rejected.

Header spelling controls resolution:

* an absolute path is read directly and emitted as a quoted absolute include;
* a relative header found beside the canonical `.titan` source is a quoted
  include and gets ordinary C quoted-include origin behavior;
* `titan/ffi.h` comes from the active Titan SDK and is emitted as an angle
  include;
* another relative spelling is treated as a system/angle header.

Use the same native policy for checking and compilation:

```sh
TITAN_EXTRA_CPPFLAGS='-I/opt/widget/include -DWIDGET_API=2' \
TITAN_EXTRA_LDFLAGS='-L/opt/widget/lib -lwidget' \
  titanc app.main
```

For a simple library name, `titanc app.main -lwidget` is convenient. CPP flags
supply declarations; link flags or `-l` supply implementations. `titanc` takes
dotted module names, not `.titan` paths.

Every source module generates `A.ffi.h`. It includes explicit `.titan` source
dependencies' `.ffi.h` files first, then direct foreign directives in module
order. Folder modules use main directives followed by bytewise-sorted
contributors. Ordinary Titan imports do not inherit C declarations. The compiler
parses that combined environment once; include guards, macro state, ordinary
redeclarations, and tag scopes follow normal C semantics. All final `ffi`
names, macros, and complete types are visible even in earlier module-variable
initializers. Ordinary Titan aliases and variables keep their earlier-import
and earlier-variable restrictions.

An explicit source dependency's C environment is transitive. Its private Titan
members still require a direct explicit `.titan` import. Generated C includes
`A.ffi.h` before `A.titan.h` when present; the latter contains foreign-function
C declarations and eligible inline bodies. Both source-adjacent header paths are compiler-owned;
do not author either file. Conflicts caused by combining a consumer's headers
with imported source declarations may be reported by final C compilation.

### What an imported namespace contains

An imported namespace can contain:

* callable C functions, including header-defined `static`/`inline` functions;
* C variables and arrays;
* supported enum constants and object-like macro values;
* C typedefs and eligible named file-scope `struct`/`union` tags;
* types for the dedicated `foreign T.new()`, `.new_array(n)`, `.sizeof`, and
  `.alignof` expressions; same-named C values do not interfere.

The C type and value namespaces are distinct. `extern int count` gives a value
`ffi.count`; it does not make `ffi.count` a type. Assigning directly to an imported
C variable name is rejected. Mutation through an imported array element,
pointer, or aggregate field is supported; use a C setter for a scalar global.

Member selectors, foreign type names, and named argument labels accept keyword
spellings. A header member, field, tag, or named parameter spelled `when`,
`type`, or `repeat` remains available as `ffi.when`, `value.repeat`, and so on.
Titan declaration positions that use `AnyName` also admit keyword names; bare
expression names still follow the reserved-word rules.

## Supported C types and where they may appear

Titan and foreign types have separate syntactic/name-resolution categories.
Write `foreign int`, `foreign float`, `foreign *size_t`, and similar types at
ordinary annotated sinks. Inside foreign signatures/types, use unqualified C
names: `void`, `bool`, `char`, `signed char`, `unsigned char`, `short`,
`unsigned short`, `int`, `unsigned int`, `long`, `unsigned long`, `long long`,
`unsigned long long`, `float`, `double`, and `long double`. These target-profile
primitives need no header. `bool` means C `_Bool`, not Titan `boolean`.

C names never have `ffi.` or module qualification in type syntax. Titan type
parameters/aliases/nominals are independent; a Titan record named `int` is
legal. Group nested foreign constructors: `foreign *(*int)` and
`foreign *(function(int): int)`. A foreign function type is already a pointer.

`foreign type Name = foreigntype` declares a real raw C typedef, always local
and without a `local` modifier. Forward aliases resolve in dependency order;
cycles and ordinary C name conflicts are errors. The typedef is emitted in the
module's `.ffi.h` and inherited by unqualified foreign name through explicit
source imports and their transitive C headers. Ordinary imports do not acquire
it, and it is absent from Titan type-member metadata.

Runtime identity is nominal by declaring header and C declaration; the same
declaration shares owned/callable identity across Titan modules, including
source imports and forced headers. Separate anonymous declaration sites remain
distinct. Use compatible declarations and build settings across those modules,
as when programming in C. Titan does not fingerprint preprocessing conditions
or certify C ABI compatibility for these identities.

`owned foreigntype` is a Titan constructor whose operand resolves to a C pointer
or array. An outer `const`, including one inherited through an alias, is
rejected because Titan cannot allocate and initialize const owned storage
together. Ordinary `type Owner = owned *Item` aliases are valid; ownership must
never be erased into a C typedef. Foreign alias RHS types, foreign signatures,
and locals in foreign bodies cannot contain owned values. An ordinary alias
may contain raw foreign components within genuine Titan constructors, but
`type X = (foreign int)` is rejected because grouping alone does not change its
outer category.

Imported and contextual C types remain distinct C types:

| C family | Titan spelling/use |
| --- | --- |
| `void` | contextual C call result and allocation validation |
| `_Bool`, character and integer types | distinct C integer types |
| `float`, `double`, `long double` | distinct C floating types |
| `T *` | `foreign *T`, or `foreign *int` and similar portable pointers |
| `const T *` | `foreign const *T`, or a portable contextual pointee |
| C function pointer | imported typedef, or `foreign function(P...): R` |
| C `T[N]` | inferred fixed C array at a direct initialized local sink; no written sized annotation |
| borrowed `T *` array view | `foreign T[]` at a direct initialized local sink |
| `struct` / `union` | imported typedef or eligible file-scope tag name |
| one Titan-GC-owned object | `owned *T` |
| counted Titan-GC-owned array | `owned T[]` |
| Lua internal value | exact imported `TValue` from `titan/ffi.h` |

`foreign *T` requires a C pointee. `foreign *integer` and pointers to Titan records, Arrays, or
Maps are errors. A C `union` is unrelated to a Titan `union`; Titan
records/unions are nominal GC userdata, not C aggregate layouts.

Header-dependent C types can be used in local functions, locals, local aliases,
and eligible private state, but cannot be serialized through a public
interface. A public type may recursively contain only contextual C primitives,
pointers or const pointers to portable C types, structural `foreign function(...): ...` pointers whose parameters/results are portable, and `owned` forms over
portable allocatable payloads. Imported typedefs, aggregates, arrays, enums,
and imported function-pointer typedefs remain excluded from public compiled
interfaces even when their C definition resolves to a portable primitive or
function signature.
This is wrong:

```text
foreign import "widget.h"

-- WRONG: a public compiled-module signature leaks a header-local C type.
function raw_widget(): foreign *widget
  return ffi.widget_current()
end
```

Wrap it behind Titan types instead:

```c
/* widget.h */
#include <stddef.h>
typedef struct widget widget;
typedef struct widget_info {
  size_t bytes;
  int ready;
} widget_info;

widget *widget_open(const char *name);
int widget_get_info(widget *w, widget_info *out);
void widget_close(widget *w);
```

```titan
foreign import "widget.h"

record Info
  bytes: integer
  ready: boolean
end

function inspect(name: string): Info?
  local handle = ffi.widget_open(name)
  if not handle then return nil end
  defer ffi.widget_close(handle)

  -- Direct `.new()` inference for a complete struct selects zeroed automatic
  -- C storage. Passing the mutable local to `widget_info *` takes its address.
  local raw = foreign widget_info.new()
  if ffi.widget_get_info(handle, raw) ~= 0 then return nil end
  return Info.new(raw.bytes, raw.ready ~= 0)
end
```

The return and record are ordinary public Titan types. The constructor argument
slot performs the checked `size_t -> integer` adjustment. The C-mode comparison
`raw.ready ~= 0` already produces a Titan `boolean`; there is no C-integer-to-
boolean coercion. No public caller needs the header.

Private nominal fields/parts can embed complete fixed non-GC C structs, unions,
and fixed arrays by copy. Reads borrow an interior object/element pointer;
keep the nominal owner reachable for every use. Binding `const` is shallow:
it prevents replacement, not writes through a mutable pointee. Explicit C
qualifiers still apply. Incomplete objects, embedded FAMs and recursively
GC-bearing aggregates are rejected; exact `TValue` and Lua `Udata *` themselves
remain traced slots. Unsized `foreign T[]` fields/parts are uncounted pointers.
Public foreign-type export restrictions remain in force.

Native C numeric fields and optional values remain exact until a real
Lua/`value`/reflection boundary requires checked boxing; reading a wide value
there may fail without invalidating the nominal. General `T?` and aggregate
boxing eligibility are separate from fixed nominal storage. A boxable pointer
does not make its pointee dynamically verifiable.

`foreign T.sizeof` and `foreign T.alignof`, including primitive foreign types,
produce Titan `integer` after a checked conversion from the target's exact
`size_t`:

```titan
function primitive_layout(): integer
  return foreign int.sizeof + foreign int.alignof
end
```

A C tag and value can share a name. Use `ffi.stat(...)` for the function and
`foreign stat.new()` / `foreign stat.sizeof` for the type. Do not introduce a
header alias merely to bypass a same-name value. Ordinary mutable locals may
omit an RHS only for a nil-bearing annotation such as `foreign *Item`; const
locals still require an initializer.

Titan binding constness is distinct from C pointee constness and from a const
Array qualifier:

```text
const pointer: foreign *Item = acquire()  -- binding is const; pointee may be mutable
local view: foreign const *Item           -- mutable binding, pointer to const C Item
const { foreign *Item }                   -- const Titan Array of mutable C pointers
```

A const local whose value is inline C struct/union or fixed-array storage
cannot mutate a field/element, take a mutable address, or use mutable automatic
array decay through that binding. This rule is shallow: a pointer or `owned`
value ends the inline-storage walk, so const prevents replacing the binding but
does not freeze an independently mutable pointee. C `foreign const *T` continues to
control pointee qualification.

## C calls, function pointers, and arity

A direct foreign call uses C arity, not Titan's ordinary fixed-call adjustment.
Positional missing and surplus expressions are errors. A final statically finite
multiple-result call can provide exactly the remaining arguments, but a
run-time-open flexible result sequence cannot cross the C call boundary.

A fixed nonvariadic declaration supports Titan named-call syntax only when the
active prototype supplies one complete, unique list of parameter names:

```c
int clamp_int(int value, int low, int high);
```

```titan
foreign import "api.h"

function clamp(input: integer): integer
  return ffi.clamp_int {
    high = 100,
    value = input,
    low = 0,
  }
end
```

The labels are exact C parameter names. Named omission produces `nil` and is
legal only if that parameter accepts nil; an omitted pointer may become `NULL`,
but an omitted C integer is an error. Old-style `f()`, unnamed/partially named
prototypes, duplicate/conflicting names, C variadics, and function-pointer
calls do not support named syntax.

C variadic calls check the fixed prefix, then use every extra argument's static
C/Titan type and C default promotions. Titan does not check a format string and
cannot forward a Titan `...` run into C `...`. Choose exact C types explicitly
for numeric variadic arguments:

```titan
foreign import "stdio.h"

local function print_count(n: integer)
  -- `%lld` requires the matching promoted C type; a bare Titan integer uses
  -- the configured lua_Integer type, which must not be guessed from the host.
  ffi.printf("%lld\n", n as foreign long long)
end
```

Prefer a nonvariadic C API or a typed wrapper when possible.

A foreign C function name is not a Titan first-class function. It may be called
directly or converted to an exactly compatible C function-pointer type:

```c
typedef int (*callback)(int);
int add_one(int value);
int apply(callback fn, int value);
```

```titan
foreign import "callbacks.h"

local function apply_one(): integer
  local cb: foreign callback = ffi.add_one
  return ffi.apply(cb, 41)
end
```

A C function-pointer value is callable with ordinary parentheses, uses strict C
arity, and raises if it is `NULL`. It is still not a Titan function value and
cannot cross through `value`. Function pointers do not support named calls.

## Coercions and casts: use the destination first

Titan has no general subtyping and does not search conversion chains. The
checker chooses one exact identity, one direct outer coercion, one gradual view,
or one callable adjustment at each typed sink. A numeric, Option, C-pointer, or
Interface conversion does not automatically lift through an Array, Map,
function, or nominal field.

In ordinary code, prefer the implicit checked conversion supplied by the
receiving type:

```titan
foreign import "api.h"

function current_count(): integer
  return ffi.current_count()       -- checked C integer -> Titan integer
end

local function set_count(n: integer)
  ffi.set_count(n)                 -- checked Titan integer -> C parameter type
end
```

Do not mechanically write `as integer` on every C result or `as foreign api_int` on every
C argument. Use `as` when it communicates a real choice:

* select Titan semantics before an operator;
* select the exact C type of a variadic argument;
* request a checked conversion outside a typed sink;
* copy a C string pointer to a Titan string;
* perform a deliberately unsafe raw-pointer assertion or identity erasure.

The important direct edges are:

| Source | Target / effect |
| --- | --- |
| C integer | Titan `integer`, range-checked |
| Titan `integer` | C integer, target-range-checked; `_Bool` accepts only 0 or 1 |
| C float | Titan `float`, checked when narrowing to `lua_Number` |
| Titan `integer` or `float` | C float, checked when needed |
| C pointer (including function pointer) | `boolean`; null is false |
| `nil` | contextual C pointer `NULL` |
| C array or counted owner | compatible element pointer |
| non-function object pointer | compatible `void *` |
| `void *` | compatible non-character object pointer directly; character pointer only by explicit written cast |
| C function pointer ↔ C `void *` | only by an explicit written portability cast |
| mutable C local/formal | compatible mutable pointer out-parameter |
| another by-value C object expression | compatible `foreign const *T` for one call |
| Titan `string` | borrowed `char *` / `void *` for a call |
| C `char *` / `void *` | `string` by explicit NUL-terminated copy |
| counted owned character array | `string` by explicit exact-length binary copy |
| boxable C scalar / object or function pointer | `value`; pointers become lightuserdata, using the portability cast for function pointers |
| owned C storage | `value`; remains full userdata with exact owner identity |
| exact C `TValue` | Titan `value`, and vice versa |
| Lua-internal `Udata *` | the same full-userdata `value`, and vice versa |

Numeric values stay raw until one of these boundaries. The configured compiler
supplies widths, ranks, signedness, float range, `size_t`, `ptrdiff_t`,
`lua_Integer`, and `lua_Number`. Narrowing, boxing, `sizeof`, and pointer
difference are checked rather than silently truncated. Written C-integer to
C-integer casts are the deliberate exception: they retain C signed/unsigned
conversion semantics.

Every partial written cast has an `is` predicate twin. `e is T` evaluates `e`
once and asks whether `e as T` would finish without a cast error; it neither
converts nor narrows the variable's type in a branch.

### `value` is not C's `void *` and not TypeScript `any`

`value` stores an arbitrary Lua-representable value. It is useful at a genuine
dynamic edge, but typed operations still need a projection. Its two projections
are intentionally different:

```titan
local function strict(v: value): integer
  local n: integer = v   -- strict: requires a Lua integer tag
  return n
end

local function dynamic(v: value): integer
  return v as integer    -- dynamic: also converts an integral in-range float
end
```

An implicit `value -> T`, a typed Array read, and a typed Map read use a strict
guard. A written `value as/is T`, a genuine Lua argument/write, or a result from
a non-Titan Lua callable uses broad target-directed dynamic coercion. For
example, a dynamic integer target accepts `2.0`, and a dynamic boolean target
applies Lua truthiness. Container crossings check only the outer proxy/table;
typed reads check contents later.

A raw C pointer is the dangerous exception. Object and function pointers
box as lightuserdata, by implicit coercion or written `as value`, but the
carrier has no pointee or C-signature tag. Therefore:

* implicit `value -> foreign *T` is rejected;
* typed Array/Map reads that would need to establish a raw pointer are rejected;
* Lua-callable results cannot dynamically establish a raw pointer;
* `v as foreign *T` is allowed only as an explicit unsafe lightuserdata/nil
  assertion, and `v is foreign *T` can test only that outer representation—not the
  address, alignment, lifetime, or pointee.

Do not use `value` as an untyped pointer registry.

### Contextual object-pointer conversion

C libraries often cast between related opaque object pointers. Titan does not
model that as inheritance. A destination pointer type must be explicit, and the
configured C compiler validates that exact directional cast:

```titan
foreign import "uv.h"

local function close_tcp(tcp: foreign *uv_tcp_t)
  ffi.uv_close(tcp, nil)       -- parameter supplies *uv_handle_t
end

local function handle_of(tcp: foreign *uv_tcp_t): foreign *uv_handle_t
  return tcp                  -- return type supplies the destination
end
```

This applies at annotated locals, assignments, returns, C arguments, pointer
calls, explicit casts, and typed C variadic arguments. Both sides must be C
object pointers after array decay. Qualifiers may be added but not discarded.
A qualification-preserving `void *` to non-character object-pointer edge is an
ordinary coercion; a character-pointer target requires an explicit written
cast. C function pointers cross to or from `void *` only through an explicit
written portability cast. Direct object-pointer/function-pointer crossings
remain rejected, and no global "compatible pointer" relation is created.

With a header-defined `ffi.callback`, the shape is:

```text
local object: foreign *int = opaque_void             -- ordinary typed sink
local bytes = opaque_void as foreign *char           -- character case is written
local erased = callback as foreign *void             -- written portability cast
local recovered = erased as foreign callback       -- written portability cast
```

The round trip preserves only the C address representation. It does not root a
callback owner, adapt a Titan closure, or make the pointer callable after its
native lifetime ends.

### Options do not compose arbitrary conversions

Ordinary Titan options are automatically forced in a bare-value typed context;
a presence test does not narrow the static type, and adding `optional as T`
after every check is normally noise. However, Titan inserts only one direct
outer conversion. An optional owner cannot both force `Owner? -> Owner` and
then decay `Owner -> *T` in one C argument. Make the intermediate owner typed:

```titan
foreign import "consumer.h"


local function consume(maybe: (owned *int)?)
  if maybe ~= nil then
    local owner: owned *int = maybe  -- ordinary checked Option force
    ffi.consume_int(owner)           -- owner-to-pointer adjustment
  end
end
```

Do not turn this into a structural conversion rule for `{Owner?}`, a
function component, or a public API.

## Strings, pointers, and lifetime

Passing a Titan string to `char *` or `void *` gives C the address of its
immutable internal bytes. No copy is made. The generated call keeps the string
rooted while all arguments are prepared and the call runs. C must not mutate,
free, reallocate, or retain that pointer.

Casting a C `char *` or `void *` to `string` checks non-NULL and copies through
the first NUL:

```titan
foreign import "stdlib.h"

function path(): string?
  local p = ffi.getenv("PATH")
  if not p then return nil end
  return p as string
end
```

The copy does not make the source allocation owned by Titan; follow the C API's
release rule if it returned allocated memory. A `void * as string` is only valid
when it really points to a NUL-terminated byte sequence.

Pointers are nullable and truthy by nullness:

```titan
foreign import "stdio.h"

function exists(path: string): boolean
  local file = ffi.fopen(path, "r")
  if not file then return false end
  defer ffi.fclose(file)
  return true
end
```

A raw pointer has no automatic owner. If C allocates it, pair it with the exact
release function immediately and `defer` cleanup after successful acquisition.
For an API-documented extended borrow into an owner, record, Array, Map, union,
Interface, or function, keep the original Titan value reachable for the whole
borrow. Retaining only the pointer does not retain the GC object.

The ordinary public `string -> char *` / `void *` contract remains call-only.
Application code should make the native API copy the bytes or allocate an
explicit native owner rather than retaining Titan's internal string pointer.
Titan's standard library has a narrow trusted exception for native APIs whose
reviewed contract borrows immutable stable bytes asynchronously: it keeps the
exact original string in traced callback-owner state until the one terminal
callback and never mutates, frees, or reallocates the bytes. Do not infer this
exception from `const char *` alone or teach it as a general application FFI
technique.

A written cast of a Titan Array, Map, record, union, Interface, or function to
C `void *` exposes a borrowed native GC identity. Arrays/Maps expose their
backing `Table *`; records/unions expose `Udata *`; Interfaces expose their
wrapper; a function exposes its collectable GC object and can fail if the boxed
value is noncollectable. These are internal runtime addresses, not payload
layouts. Do not dereference, mutate, free, or reallocate them. Arbitrary `value`
does not receive this identity cast, and Option is not unwrapped by it.

## C arrays, automatic storage, and owned storage

C indexing is 0-based. The base may be:

* a raw C pointer: NULL-checked, otherwise **not bounds-checked**;
* a known fixed C array: bounds-checked against its extent;
* a counted `owned T[]`: bounds-checked against its allocation count;
* a flexible-array member while count provenance remains on its allocated
  parent.

`#array` works only for a known fixed array, counted owner, or count-preserving
flexible-array-member projection. It does not work on a raw pointer or an
uncounted `T[]` borrowed view.

Direct C aggregates and fixed arrays need an initializer; `.new()` and
`.new_array(...)` request zeroed storage, and the direct local declaration's
target chooses its representation. A mutable pointer local in an ordinary
Titan function may omit its RHS and starts as NULL, but every const local and
every local in a restricted source-written foreign function requires an
initializer expression list.
For a complete non-GC-bearing struct or union:

| Direct declaration | Representation |
| --- | --- |
| `local x = foreign T.new()` | automatic block-local `foreign T` |
| `local x: foreign T = foreign T.new()` | automatic block-local `foreign T` |
| `local x: owned *T = foreign T.new()` | GC-owned inline C object |
| `local x: foreign *T = foreign T.new()` | pointer into a hidden frame-rooted owner |
| other calls, except the direct nominal destinations below | `owned *T` |

A directly nested fresh `.new`/`.new_array` argument to a synthesized record
constructor or union variant can instead initialize final nominal storage.
Fixed aggregate/array destinations copy or zero in place. A const pointer/array
record field or immutable union part can own an aligned trailing array/FAM;
`Record.new(foreign T.new_array(n))` then uses one userdata allocation. Keep the
fresh expression at the direct call site; aliases, previously allocated owners,
first-class constructors and mutable pointer fields retain ordinary behavior.
Arguments and size failures occur in lexical order (including named arguments).
Empty tails have distinct non-null addresses; borrowed views remain uncounted.
Initialize native handles only after the final owner exists, never before a copy.
See `doc/language/nominal-storage.md` for examples and
`doc/implementation/nominal-storage.md` for lowering and review invariants.

For a positive integer literal or eligible object-like integer macro count:

```titan
foreign import "geometry.h"

local function examples(count: integer)
  local fixed = foreign Point.new_array(4)          -- inferred fixed Point array, automatic
    local view: foreign Point[] = foreign Point.new_array(4) -- uncounted borrowed pointer view
  local pointer: foreign *Point = foreign Point.new_array(4) -- borrowed automatic backing
  local owner: owned Point[] = foreign Point.new_array(count)

  fixed[0].x = 10
  local fixed_length = #fixed                 -- 4
  local owner_length = #owner                 -- run-time count
end
```

A dynamic or zero inferred count produces an `owned T[]`. An explicit borrowed
pointer or `foreign T[]` uses automatic backing for a positive constant and
hidden owned backing otherwise, rooted only for that function frame. Proven
integer object-like macros participate using their exact target-profile value;
there is no size threshold or general constant-expression folding.
A pointer can still dangle if returned, stored by C, or captured beyond the
backing lifetime. Use an explicit owner whenever storage escapes. A whole C
array is not assignable or returnable.

Automatic structs/unions/fixed arrays have ordinary C block lifetime and no
escape analysis. They also cannot transitively contain GC-bearing FFI storage.
The compiler spills automatic aggregate bytes across catchable Titan calls so
mutation completed before a caught error stays visible; this does not extend
lifetime.

### Source-written owners

An owner is Lua full userdata with zeroed inline C payload:

```titan
local function allocate(n: integer): integer
  local one: owned *int = foreign int.new()
  local many: owned int[] = foreign int.new_array(n)

  local pointer: foreign *int = one -- borrowed pointer to one payload
  pointer[0] = 7 as foreign int
  many[0] = 42 as foreign int
  return #many
end
```

`owned *T` owns one object of payload type `T`; the `*` marks ownership rather
than adding a payload pointer layer. Thus `owned *(*T)` owns one `T *` object,
and `owned (*T)[]` owns an array whose elements are `T *`.

`owned` accepts a complete allocatable C object. It rejects `void`,
direct functions, incomplete aggregates, Titan types, nested owners, and C
array-typedef payloads. `owned T[4]` is not a spelling; use `owned T[]` and an
allocation count. An owner may be used in aliases, signatures, eligible
record/union slots, options, Titan Arrays/Maps, and other boxed structures. It
may cross a public interface only when its complete payload graph is portable;
an owner over an imported/header-dependent type remains private.

An owner is automatically rooted like other Titan GC values. Passing it to a
compatible pointer gives C a borrowed payload address while the owner remains
reachable. It can itself cross through `value`; a counted `owned T[]` reports
its length with `#`, while a scalar `owned *T` has no length or indexing. It
needs no parallel storage alias or wrapper record merely to keep it alive.
Retain a record only when it carries distinct logical length, offset,
callback state, asynchronous lifetime, or another real invariant. Qualifiers
may be added but not discarded. The userdata has no `__gc` resource action:
collection frees the inline bytes, but it does not call `close`, `free`,
`SSL_free`, `uv_close`, or any library-specific destructor.
If the inline object controls another resource, implement explicit idempotent
cleanup. Use `titan.gc.finalizable` only as a reachability fallback on an
appropriate table/full userdata, never as the primary prompt cleanup path or to
race an outstanding async callback.

Counted owned `char`, `signed char`, and `unsigned char` arrays have a
binary-safe explicit string conversion. It copies the exact allocation length,
including embedded and trailing NULs:

```titan
local function four_bytes(): string
  local bytes: owned unsigned char[] = foreign unsigned char.new_array(4)
  bytes[0] = 65 as foreign unsigned char
  bytes[1] = 0 as foreign unsigned char
  bytes[2] = 66 as foreign unsigned char
  bytes[3] = 0 as foreign unsigned char
  return bytes as string       -- exactly "A\0B\0"
end
```

Casting the owner to `foreign *char` first and then to `string` instead uses the
NUL-terminated rule and would stop at the first zero.

### Flexible-array members

For a complete struct ending in `E field[]`, use `foreign T.new(count)`, not `foreign T.new()`
or `T.new_array`:

```c
/* packet.h */
typedef unsigned char byte;
typedef struct Packet {
  unsigned int kind;
  byte payload[];
} Packet;
```

```titan
foreign import "packet.h"

local function packet(n: integer)
  local owner: owned *Packet = foreign Packet.new(n)
  owner.payload[0] = 1 as foreign byte
  local capacity = #owner.payload
end
```

A nonnegative literal may select aligned automatic backing; a dynamic count or
explicit owner/pointer selects one owner userdata. Negative counts and
`size_t` extent overflow are checked. `#parent.field` and checked indexing work
while the original automatic/owned parent carries count provenance. Converting
the parent to raw `foreign *Packet` erases it. Titan never constructs an array of
variably extended structs.

## Structs, unions, fields, and assignment storage

A named file-scope `struct Tag` or `union Tag` is available as `foreign Tag` even when
the header has no typedef. Titan renders the exact `struct Tag`/`union Tag`
spelling and does not invent a typedef. A real same-named typedef takes
precedence. Anonymous aggregates, enum tags, and prototype-only tags do not get
this convenient type alias. A forward-declared tag may be used behind a
pointer; by-value use, fields, allocation, `sizeof`, and `alignof` require a
visible complete definition.

Complete aggregate fields are accessed with `.` in Titan. The compiler emits C
`.` for a value and `->` for a pointer or owner:

```titan
foreign import "point.h"

local function sum(): integer
  local p = foreign Point.new()
  p.x = 10
  p.y = 20
  return p.x + p.y
end
```

Here `p.x + p.y` is a C-mode expression and the final return performs the
checked C result conversion. Cast the operands first if Titan wrapping/numeric
semantics are required. Bitfields retain C rules; cast a bitfield to an
ordinary C or Titan integer before using it in C operators because its declared
width affects promotion. Anonymous fields are not exposed.

A by-value aggregate assignment receiver must denote persistent addressable
storage. Imported objects, C locals/formals, pointer pointees, owners, and
nested fields/elements rooted in those forms work. A call/cast temporary does
not:

```text
local p: foreign Point = ffi.make_point()
p.x = 1                  -- valid: persistent local
ffi.make_point().x = 2     -- rejected: by-value aggregate temporary
```

Reading a temporary is valid. Extracting a pointer field from a temporary and
mutating its pointee is also valid because the pointee, not the temporary, owns
the final field. For assignment, Titan freezes the full left receiver/index
chain before evaluating the right side, defers the final NULL/bounds check until
after the right side, and stores multiple assignments left-to-right. Do not
rely on C's unspecified argument evaluation order: Titan preserves source
left-to-right evaluation even for C calls/operators.

## C operator mode

An operator enters C mode when a supported combination contains a C scalar,
pointer, or array. Important forms are:

| Titan syntax | C-mode behavior |
| --- | --- |
| unary `-`, `~` | C numeric promotion / bitwise complement |
| `+ - * / %` | C arithmetic; pointer +/- integer and pointer difference where valid |
| `< <= > >=` | C arithmetic or compatible object-pointer comparison |
| `== ~=` | C equality (`~=` emits `!=`), including pointer/null cases |
| `& \|` and binary `~` | C bitwise AND/OR/XOR |
| `<< >>` | C promoted shifts |

`//`, `^`, `and`, `or`, `not`, concatenation, and `#` never acquire C operator
meaning. Arrays decay before classification. `owned` is a Titan userdata and
must first adjust to a pointer context.

C mode deliberately keeps C behavior:

```text
-- If a and b are C int values:
local q = a / b   -- -7 / 3 is -2 in C, not Titan floor division
local r = a % b   -- -7 % 3 is -1 in C, not Titan modulo
```

It also keeps unsigned wrap, potential signed-overflow undefined behavior,
division-by-zero undefined behavior, invalid-shift undefined behavior, and
implementation-defined right shift. Titan integer arithmetic uses Lua-faithful
semantics instead. Choose before the operation:

```text
local titan_total = (ffi.total() as integer) + 1  -- Titan integer `+`
local c_total = ffi.total() + 1                   -- C-mode `+`, then later conversion
```

Mixed Titan `integer`/`float` operands enter C mode as the configured
`lua_Integer`/`lua_Number`; they are not first narrowed to the other C operand's
original type. Unsupported combinations are errors, not a fallback: no
floating remainder, aggregate operators, arithmetic on `void *`, function
pointer arithmetic/order, incomplete-object pointer arithmetic, or pointer
multiply/divide/bitwise/shift.

## Macros and enums

Read `errno` only after a C API reports failure under its documented contract,
and save it before another native call. A classifier such as
`uv_guess_handle` does not promise that its leftover `errno` explains an
unknown result. When several metadata probes contribute independent evidence,
perform each required probe and retain each failure separately.

Titan imports a bounded set of object-like macro values:

* supported integer constant expressions;
* typed dereferenced accessors such as common `errno` expansions;
* a fully expanded outer cast to a supported C integer, float, object pointer,
  or function pointer, while generated C still emits the public macro name;
* a pure dotted identifier path used as a projected aggregate field.

For a projected field macro, the final module-wide macro environment wins, just
as C preprocessing happens before field lookup. A live macro takes precedence
over a same-named physical field. An unsupported active macro is terminal; the
checker must not silently use the physical field that C would rewrite.

**Function-like macros are unsupported.** This includes conveniences such as
`luaL_dostring`. Prefer the underlying ordinary function. If no ordinary API
exists, add one tiny namespaced C inline wrapper in an author-owned header and
comment why the macro cannot be called directly; do not build a broad shim
layer.

Enum constants are C integer members, not Titan integers. The configured
compiler chooses and verifies their exact expression carrier. Enum object types
are checked lazily on first by-value use; the complete selected ordinary
carrier must fit `lua_Integer`. An unused wide enum is inert. Every enumerator
is checked independently, so an in-range enumerator from an otherwise wide enum
may still work. Its C carrier remains through C operators until a real Titan
boundary converts it. Only an enumerator-to-its-own-enum adjustment is implicit.
`__int128` is not a supported carrier.

Use imported names rather than copying platform constants:

```titan
foreign import "uv.h"

local function cancelled(status: foreign int): boolean
  return status == ffi.UV_ECANCELED
end
```

If the actual header exposes the status as an ordinary C integer rather than
that illustrative typedef, keep its exact imported type. Do not manufacture a
Titan enum alias from guessed values. Enum tags themselves are not published as
tag-only source aliases; use a real header typedef when a value type must be
named.

# Source-defined foreign functions and callbacks

## A restricted C entry, not a Titan closure adapter

A top-level `foreign function` defines one plain C ABI function in Titan source:

```c
/* sort_api.h */
#include <stddef.h>
typedef struct Item {
  int key;
} Item;

typedef int item_order;
typedef item_order (*item_compare)(const Item *left, const Item *right);
void sort_items(Item *items, size_t count, item_compare compare);
```

```titan
foreign import "sort_api.h"

foreign function compare_items(left: const *Item,
                               right: const *Item): item_order
  if left.key < right.key then return -1 end
  if left.key > right.key then return 1 end
  return 0
end

local function sort(items: owned Item[], count: foreign size_t)
  ffi.sort_items(items, count, compare_items)
end
```

The declaration is a C function designator. It can be called directly or used
where an exactly compatible C function pointer is expected. It is not a Titan
`function(P...): R`, cannot be boxed in `value`, cannot travel through Lua, and gets
no Titan callable adjustment.

The source-written callback-pointer type is already a pointer:

```text
foreign type Compare = function (const *Item, const *Item): item_order
foreign type Notify = function (*Item): void

local callback: foreign Compare = compare_items
```

Therefore `foreign *(function(...): ...)` means a pointer to a function pointer, not
another spelling for one callback.

A foreign definition is source-private. Its own module and a **direct importer
whose import spelling ends in `.titan`** may name it. It is absent from
`.so`/`.a` type metadata, Lua module members, ordinary imports, transitive
source imports, and binary imports. Physical co-residence in one provider does
not make it public. Do not design an installed API around a consumer reaching
another module's foreign function.

Each source module owns a compiler-generated source-adjacent `.ffi.h` for the
ordered C environment. A module defining foreign functions also owns `.titan.h`
for their prototypes and eligible inline bodies. A folder module uses its
canonical main's path. The compiler prepares required headers before compiling
source peers. These paths are reserved and are not installed/binary interfaces.

## Signature and body limits

Every parameter and the optional one result must be a direct C type. Complete
structs/unions can pass by value; incomplete types require pointers. Titan
`integer`, `string`, `boolean`, `value`, `owned`, direct arrays/functions,
multiple/flexible results, and variadic parameters are not foreign-signature
types. Omit the result annotation, or write `: void`, for
C `void`.

The body is a deliberately closed raw-C subset. It may use:

* parameters and direct-C locals; a mutable local with an explicit nil-bearing
  pointer type may omit its initializer, which supplies `NULL`; aggregates,
  scalars, and const locals require an initializer;
* imported C namespaces and their functions, values, fields, types, size and
  alignment;
* other foreign functions in the module or through an explicit `.titan`
  source import;
* C calls, casts, C-mode operators, field/index access, assignment;
* `do`, `if`/`elseif`/`else`, `while`, `repeat`, numeric `for`, `break`, and
  one C return value.

It cannot see ordinary Titan module variables, functions, records, unions,
methods, or ordinary members of an imported Titan module. It also has no:

* implicit `L` (Lua state) or ordinary module state;
* `raise`, `catch`, or `defer`;
* generic `for`, `case`, lambdas, bound methods, Titan constructors;
* concatenation, `is`, Titan `and`/`or`/`not`, variadics/flexible results;
* `.new()` / `.new_array()` Lua-owned allocation.

Foreign-body literals are C values: booleans are `_Bool`, an integer literal is
normally C `int`, a float is normally C `double`, a string literal is static
`const char *`, and nil is contextual `NULL`. Conditions use C scalar truth.
Numeric `for` uses C comparison/addition; a literal zero step is rejected, and
a computed step has a trusted nonzero precondition.

The body is inside the unsafe C boundary. Pointer dereference/index and
function-pointer calls do **not** get ordinary Titan FFI NULL/bounds checks.
Arithmetic, casts, and shifts retain C undefined or implementation-defined
behavior. The compiler still evaluates operands and arguments once,
left-to-right.

### Private nominal callback fields

For compiler/runtime maintenance only, a restricted foreign function with a
direct `foreign import "titan/ffi.h"` can use
`ffi.titan_record_field(owner, "LocalRecord", "field")`. Literal names select
a current-module record and its canonical field, including private fields.
The compiler supplies the physical native/UV access: never hardcode a nominal
`uv` index from source field order. Traced fields yield a by-value `foreign TValue`; raw fields yield exact C
values, and aggregates/arrays yield borrowed pointers. Native optional fields
are not supported by this private intrinsic. The owner is evaluated once, but the
intrinsic neither checks its runtime type nor roots it. Preserve the native
registration/root protocol. Foreign functions using it stay out of inline
headers. Module, closure, Interface and coroutine UV protocols are separate.

## Callback design limits

An ordinary Titan function or capturing lambda is never adapted to C:

```text
-- WRONG: C cannot call this closure ABI.
local delta = 10
local callback = function (x: foreign item_order): foreign item_order return x + delta end
ffi.install(callback)
```

Use a restricted `foreign function` only when the callback can operate entirely
through its C parameters and C-visible state. If C supplies a `void *data`
field, that address is still merely borrowed. Keep the actual owner reachable
until the C library guarantees that no callback can occur, and do not assume a
Titan record can be reconstructed portably from an arbitrary `void *`.

When a callback needs Lua, give its foreign signature an explicit
`foreign *lua_State` from the C protocol. A foreign function has no generated
Titan error frame or GC-root frame. A Lua API call that longjmps follows that
API's C contract; Titan cannot run `defer` or translate it to `raise` inside the
foreign body.

The FFI also supplies no cross-thread Lua attachment or synchronization. A C-only
foreign callback may obey its library's thread contract, but a callback that
touches a `lua_State`, Titan GC object, or generated Titan entry must run under
the owning runtime/thread protocol. Do not call into Lua/Titan from an arbitrary
native worker thread.

Titan's standard filesystem/uv/HTTP/coroutine callbacks use private
`titan/ffi.h` bridges to recover generated `CClosure`, `Udata`, and native-entry
internals before calling exact compiler-generated entries. This compiler/runtime-
private callback set is separate from ordinary trusted modules that use narrow
Lua C API operations. It is an audited compiler/runtime
contract, **not** a general callback recipe. Do not copy it into application
code or make it a public ABI. If the restricted body cannot express the
boundary, pause and design one narrow C shim rather than constructing a second
untyped callback runtime.

For async native APIs, cancellation of the waiting Task does not terminate the
C request. The complete callback owner—including strings, buffers, callback
closure, and native allocation—must remain rooted until terminal completion and
close. A finalizer must not race an outstanding callback. The async skill owns
the Runtime/Task protocol; this skill's contribution is to preserve the native
owner and borrowed-lifetime contract.

# Lua interoperability

## The ordinary Lua boundary is already powerful

A compiled Titan library is required from Lua as a module userdata:

```lua
local mod = require "app.widget"
local answer = mod.compute(21)
```

Lua must use qualified standard-module names such as `require "titan.lua"`,
`require "titan.fs"`, and `require "titan.string"`. Bare `require "titan"`
returns native support, not the standard modules. A Titan import is different:
`local fs = import "fs"` uses compiler sugar for `titan.fs`, and the same
applies to all the other stdlib modules.

Canonical boundary representations are:

| Titan type | Lua representation / accepted input |
| --- | --- |
| `integer` | Lua integer; a genuine Lua input may be an integral in-range float |
| `float` | Lua float; Lua integer converts |
| `boolean` | dynamic input uses Lua truthiness; only nil/false are false |
| `string` | Lua string only, never automatic number-to-string |
| mutable Array `{T}` | canonical mutable Titan userdata proxy, never a plain table |
| const Array `const { T }` | distinct canonical read-only Titan userdata proxy |
| Map `{K: V}` | the same ordinary Lua table, including its identity and metatable |
| record | exact nominal Titan userdata |
| union | exact opaque nominal Titan userdata |
| Interface | exact wrapper userdata, or bare full userdata whose metatable advertises a compiler-witnessed wrapper entry for that Interface |
| function type | any boxed value; callability is deferred to call time |
| `T?` | nil or dynamic conversion of `T` |
| `value` | unchanged Lua value |

A container crossing is shallow. A Map boundary checks "table" and an Array
boundary checks the exact qualified canonical proxy; neither walks contents.
Lua can mutate a
Map directly or attach ordinary table metamethods. Titan Map reads return a raw
hit first and follow `__index` only on a miss; either result then passes the
same strict typed value guard. Writes update/delete raw-present keys without
`__newindex`, while raw-absent keys follow ordinary `__newindex` function or
target chains, including an absent-key nil assignment. Metamethod policy is not
a Titan value converter, so a float `2.0` supplied to an integer-valued Map by
raw mutation or `__index` still fails the later strict integer-tag read.

Only an exact integer-key Map admits `#`: it invokes `__len` when present and
strictly requires an exact Lua integer result, while the no-metamethod path
keeps Lua's ordinary border semantics. Map/Map and Map/`value` comparison in
either orientation begin with identity/raw equality; when both run-time values
are tables, Lua selects the left `__eq` and falls back to the right, interpreting
the result by Lua truthiness. Two `value` operands deliberately remain raw
equality even when both contain tables with `__eq`.

A Lua write through a mutable Array proxy dynamically converts a nonnil element
with the writer installed when the Array was constructed; nil deletes before
conversion. A const Array proxy has no writer: ordinary assignment and
mutating stock Lua 5.5 `table.*` operations fail, while indexing and `#`
remain available. A plain Lua table can never impersonate either Array tag,
and dynamic conversion never changes the qualifier. `rawget`, `rawset`, and
`rawlen` require a real table and reject either proxy.

A module and record use metatables for checked member writes. Unknown members
raise rather than returning nil; public const module variables and const record
fields remain readable but their write cases explicitly raise. Interface
fields are read-only shallow snapshots captured when the wrapper is built, and
every Interface write rejects. Records/unions/Interfaces and modules are
userdata, not tables; their protected metatables and nominal identities matter.
Debug-library or native mutation of private metatables, user values, or closure
upvalues opts out of Titan's safety contract.

That escape hatch includes Interface discovery entries. Generated code
raw-stores a wrapper witness at
`concrete_metatable[target_Interface_metatable]` only for pairs seen at real
static wrapper sites, preserving any existing non-nil entry. Dynamic `is`
checks only presence. Conversion calls a present value with the candidate
userdata and trusts its one result, without validating record identity,
callability, or the returned wrapper. Never forge or replace these entries in
ordinary FFI code; debug/native code that does so owns the resulting Lua call
errors, side effects, and representation safety.

A Lua callable can be accepted directly through a typed Titan function:

```titan
function apply(transform: function (integer): (integer), n: integer): integer
  return transform(n)
end
```

```lua
local app = require "app"
assert(app.apply(function (n) return n * 10 end, 5) == 50)
```

The callability check is deferred. Lua closures, C functions, and tables with
`__call` can work; a noncallable value raises when invoked. Results from a
non-Titan Lua callable are dynamically converted to the static result demand.
Use this route instead of reaching for `lua_pcall` or raw stack operations.

Lua calls of Titan functions use Titan's fixed-call adjustment: missing
arguments are nil-filled then converted, fixed surplus arguments are ignored,
and declared variadics collect extras. Multiple and flexible returns cross as
Lua multiple values. Errors raised in either direction are ordinary Lua errors.
Each Lua state owns an independent Titan module instance; do not put semantic
per-state data in mutable C globals.

## `titan.lua`: the public dynamic loading escape hatch

Import the module by its qualified name:

```titan
local lua = import "lua"
```

It exposes four APIs:

```text
function load(chunk: string, name: string?, env: value):
  function(...: value): (...: value)

function load_from_reader(reader: io.Reader, name: string?, env: value):
  function(...: value): (...: value)

function dofile(filename: string, ...: value): (...: value)

function require(modname: string): value
```

There is no compiler `lua` short alias, no Lua-module `import`, and no special
replacement of Lua's global `load`, `dofile`, or `require`.

### `load`

`load` compiles all bytes as Lua text or binary. It uses an explicit length, so
embedded NUL is not silently truncated. Invalid source/bytecode raises instead
of returning `(nil, message)`. It returns a genuinely flexible callable and
does not execute it.

`name` is the diagnostic chunk name; nil/omission uses the chunk string. A
nonnil `env` replaces the compiled closure's first upvalue. For ordinary text
that is `_ENV`; for binary it is simply the first upvalue, whatever its debug
name, and a chunk with no upvalues ignores it. The value need not be a Map.
This is not a sandbox guarantee.

```titan
local lua = import "lua"

function evaluate(): integer
  local env: {string: value} = { ["answer"] = 40 }
  local chunk = lua.load("return answer + ...", "=formula", env)
  local raw: value = chunk(2)
  return raw as integer
end
```

Keep the dynamic region small: establish the Map at the boundary, execute one
reviewed chunk, convert the result once, and return to typed Titan. Do not pass
`value` through the rest of an application because the source happens to be
Lua.

### `load_from_reader`

This consumes `reader:read` as a generic-for iterator. Every nonnil string,
including `""`, contributes exact bytes; nil is EOF. Reader methods may yield,
so a yielding reader must run inside the normal async Task/loop discipline.
The loader never closes the Reader, on success or failure: it is borrowed.

### `dofile`

`dofile` asynchronously opens and reads the file through `titan.fs`, compiles it
with chunk name `@filename`, forwards every flexible argument, and forwards
every result including inner nils. It owns and closes its File on load errors,
run-time errors, and success. Because filesystem operations may yield, invoke it
inside an async Task/Runtime.

### `require`

`titan.lua.require` uses Lua's registry-backed `package.loaded` table. It
preserves preload searcher 1, replaces blocking source searcher slot 2 with an
asynchronous `package.path` pass, and then calls searchers 3 onward. The source
pass can load Lua source and generated Titan shims; C modules use Lua's C
searchers. Searchers and loaders themselves run through Titan's non-yieldable
Lua-callable path and must not attempt to yield.

A truthy cached value returns immediately. A loader's nonnil result is stored;
if it and `package.loaded[name]` remain nil, true is installed. False deliberately
causes the next call to reload. A simultaneous or recursive load of the same
name raises `module 'name' is already being loaded`; it does not duplicate the
load or hide a scheduler wait. The guard is cleared after success/error so a
later retry works.

A typed plugin boundary can be narrow even though `require` returns `value`:

```titan
local lua = import "lua"

function run_plugin(name: string, input: string): string
  local raw_module: value = lua.require(name)
  local plugin = raw_module as {string: value}
  local raw_transform: value = plugin["transform"]
  local transform = raw_transform as function (string): (string)
  return transform(input)
end
```

The Map cast checks only that the module value is a table; the read and call
establish the requested pieces. A written cast to a function preserves the
boxed value and defers callability until invocation, so `raw_transform is
function(string): string` is not a useful eager "is callable" test—it is total at
that dynamic boundary and the call may still fail. For a stable plugin
protocol, prefer a Titan module and static `import`; use this dynamic design
only when run-time Lua discovery is the actual requirement.

# The Lua C API: trusted exception, not general FFI v1

## Support status

Importing `lua.h` exposes declarations, and every ordinary Titan
function/method/lambda has a read-only built-in `L` typed as the current
`lua_State *`. That does **not** make the raw Lua C API a supported safe general
binding. Its stack effects, allocation, callbacks, and longjmp behavior need
API-specific knowledge that ordinary FFI declarations do not encode.

The project currently permits a narrow audited exception in private code of
`titan.peg`, `titan.string`, `titan.lua`, `titan.iteration`, `titan.gc`, and
`titan.test`. Treat this section as a review checklist for that trusted code,
not permission to scatter `lua_*` calls through applications. Prefer:

* a typed Lua callable passed into Titan;
* `titan.lua` for compilation/loading;
* `titan.gc` for weak maps/finalizers/collector control;
* typed Titan Arrays/Maps followed by one narrow metatable operation;
* an existing owner module's audited helper.

A `foreign function` gets no built-in `L`; an explicit C parameter or other C
declaration must supply a state. Never store, return, replace, or use an old
`L` after its current call contract.

## The stack transaction pattern

Every new or modified trusted helper that pushes anything should use one explicit
transaction, even though a few older reviewed standard-library paths still rely
on their entry frame's `LUA_MINSTACK` reserve:

1. snapshot the exact entry top;
2. install `defer lua_settop(L, saved)` immediately;
3. reserve the complete maximum temporary effect with `lua_checkstack` before
   the first push;
4. keep a path-by-path stack ledger;
5. copy every surviving collectable result into traced Titan `value` or another
   traced Titan owner before restoring the top;
6. retain no raw stack address or borrowed Lua pointer across an operation that
   may allocate, run Lua, invoke a metamethod/callback, longjmp, or resize the
   stack.

This exact helper from `titan/lua.titan` is the model:

```titan
foreign import "lua.h"
foreign import "titan/ffi.h"

local function global_value(name: string): value
  local top = ffi.lua_gettop(L)
  defer ffi.lua_settop(L, top)
  if ffi.lua_checkstack(L, 1) == 0 then
    raise "cannot reserve Lua stack for global lookup"
  end
  ffi.lua_getglobal(L, name)
  return ffi.lua_totvalue(L, -1)
end
```

`lua_getglobal` may invoke `__index`, allocate, call user code, or raise. The
pushed slot roots its value until top restoration; `ffi.lua_totvalue` copies it
into Titan's traced `value` representation so it survives that restoration.
Do not replace the one authoritative `lua_settop` with a guessed series of
pops on normal paths while leaving exceptional paths unbalanced.

The model for compiling a chunk is similarly explicit:

```text
local top = ffi.lua_gettop(L)
defer ffi.lua_settop(L, top)
if ffi.lua_checkstack(L, 2) == 0 then
  raise "cannot reserve Lua stack for chunk loading"
end

local status = ffi.luaL_loadbufferx(
  L, chunk, #chunk as foreign size_t, chunkname, nil)
if status ~= ffi.LUA_OK then
  local failure: value = ffi.lua_totvalue(L, -1)
  raise failure
end

if env ~= nil then
  ffi.lua_pushtvalue(L, env)
  if not ffi.lua_setupvalue(L, -2, 1) then
    -- On failure lua_setupvalue leaves the supplied value on the stack.
    ffi.lua_settop(L, -2)
  end
end

local callable: value = ffi.lua_totvalue(L, -1)
return callable as LuaChunk
```

Every branch accounts for its exact effect. The input string is passed with an
explicit length. The error/function is traced before cleanup. The optional
upvalue has different pop behavior on success and failure.

## Current trusted-operation ledger

When reviewing existing trusted standard-library code, start from these known
obligations; adding a new operation requires a fresh stack/allocation/error/
callback/borrow audit.

| Operation | Effect and obligation |
| --- | --- |
| `lua_gettop` | no stack effect; snapshot entry height |
| `lua_checkstack` | no stack effect; reserve the full maximum before pushes; success may relocate stack slots |
| `ffi.lua_pushtvalue` | pushes one already traced semantic Titan/Lua value |
| `lua_getglobal`, `lua_getfield` | push one; may invoke metamethod/user code, allocate, or raise depending on target |
| `lua_getmetatable` | pushes one only when a metatable exists |
| `lua_setmetatable` | pops the metatable; use only on the exact typed value and ledger both paths |
| `lua_rawset` | pops key and value, retains table; public API performs the write barrier |
| `lua_next` | pops current key; on success pushes next key and item, on exhaustion nothing; invalid key may longjmp |
| `luaL_loadbufferx` / `luaL_loadstring` | pushes exactly one function on success or one error object on failure; may allocate/longjmp |
| `lua_pcallk` | effect depends on fixed nargs/nresults and error path; current use is one exact nonyieldable helper factory only |
| `lua_setupvalue` | success installs/pops top value; missing upvalue returns null and leaves it |
| `luaL_tolstring` | pushes one string; may call `__tostring`, allocate, or raise; trace before cleanup |
| `lua_type` | net zero |
| `lua_topointer` | net zero; returned address is identity-only, borrowed, never dereference it |
| `ffi.lua_totvalue` | net zero; copies selected slot into traced Titan `value` |
| `lua_gc` | net zero; whole-state control, forbidden/unavailable in a finalizer |
| `lua_settop(L, saved)` | authoritative cleanup to the saved entry height |

`luaL_dostring` and many conveniences are function-like macros and are not
general FFI-callable. Do not expand the trusted surface merely to mimic the
Lua manual. Centralize an operation in the module that owns the semantic policy.
For example, weak `__mode` manipulation belongs in `titan.gc`; modules that
already happen to import `lua.h` must not duplicate it.

## Rooting and relocation model

Keep these facts separate:

* Lua heap objects are non-moving, but the Lua **stack array can relocate**.
  Save integer indices or stack offsets according to the API contract, not raw
  `StkId`/`TValue *` across a growth/call.
* Every value in a live stack slot below `L->top` is a GC root. Restoring top
  destroys that temporary root.
* A C local holding `TString *`, `Udata *`, `Table *`, `GCObject *`, a raw
  address, or a copied `TValue` is not automatically visible to Lua's collector
  merely because C still has bits. In ordinary generated Titan code the coder
  creates shadow roots for GC-bearing values; raw Lua-stack code must respect
  the explicit transaction.
* A fresh object must become reachable from a traced stack slot, Titan local,
  module/record/container field, or another traced object before another
  allocation or collector poll.
* A write of a young collectable into an old Lua object needs the correct Lua
  API/internal write barrier. Prefer public API setters. Do not hand-write
  internal `TValue` stores in Titan source.
* A pushed Titan value is a root only until top restoration. Copy a result to a
  Titan `value` first; do not keep a pointer into its string/userdata/stack
  representation.
* User functions and metamethods invoked from current trusted modules run only
  through a non-yieldable boundary. A yield attempt is an error, not a
  continuation that suspends the native Titan frame.
* A Lua C API function that longjmps does not run C cleanup. Trusted ordinary
  Titan functions rely on their generated error boundary and a `defer` that can
  run when the call is translated back; a restricted `foreign function` has no
  such Titan frame.

Semantic state belongs in the Lua registry or GC-traced Lua/Titan objects, not
mutable translation-unit C globals. That is what gives each Lua state an
independent module instance and makes multi-state loading correct.

# Ownership and cleanup review

Classify every native value before coding:

| Value | Owner / lifetime |
| --- | --- |
| Titan string passed to C | Titan GC owner; borrowed immutable byte pointer for call only |
| raw C pointer returned by C | external API-defined; usually borrowed or paired with exact free/close |
| automatic `foreign T` / inferred fixed C array | current C block; no escape analysis |
| pointer selected from direct local `.new()` | hidden owner rooted for current function frame only |
| explicit `owned *T` / `owned T[]` | Titan full userdata reachable through ordinary GC roots; inline bytes only |
| nominal embedded object/array or fresh tail | bytes belong to final nominal userdata; projections borrow and do not retain it |
| pointer into an owner | borrowed; owner must remain reachable |
| C malloc/OpenSSL/etc. pointer stored inside owner | still needs the library's explicit destructor; owner collection alone is insufficient |
| Lua stack slot | root only while below current top in current state |
| lightuserdata | address bits only; no pointee tag, root, or destructor |
| C callback registration | library owns ability to call; Titan must retain callback state until deregistration/terminal completion |
| async request after Task cancellation | still natively live until terminal callback/close |

Acquire, then install cleanup immediately:

```text
local handle = ffi.open_resource()
if not handle then raise "open_resource failed" end
defer ffi.close_resource(handle)
```

Multiple defers run LIFO on fallthrough, return, break, or error. Use explicit
close/release so failures are reported at the owning call site. A reachability
finalizer is nondeterministic, cannot yield or collect, may resurrect its
value, and reports errors as warnings. It is a fallback, not prompt cleanup.

When C retains a Titan-backed pointer, a local source expression is not a
lifetime proof. Store the original owner/string/record in the callback/request
owner that remains traced. When C retains only its own allocation, store the
raw handle plus an explicit terminal marker and ensure cleanup is idempotent.
Never invent a duplicate boolean close flag when the native API already has an
authoritative state query, and never call a native close twice.

# Review patterns and anti-patterns

## Prefer these rewrites

### Public raw C type -> private native state plus public Titan value

**Wrong:** export `foreign *Handle`, `foreign size_t`, or `owned *Context`; each graph
depends on a foreign header namespace.

**Right:** keep it in a local function/private eligible record, expose a
nominal Titan record/Interface/option, and convert counts/status/errors at the
owner module boundary. A deliberately public `foreign *void`, `foreign *int`, structural
`foreign function(*void): void`, or portable owner is different: it is legal precisely
because its entire C type graph is contextual and serializable.

### `value` everywhere -> one dynamic edge

**Wrong:** represent a stable plugin or C result as `value` through several
layers, repeatedly cast fields, and use `value` as a pointer bag.

**Right:** accept/load one `value`, validate/cast once to a Map or callable
shape, translate into ordinary Titan records/unions, and keep the rest typed.
Remember that implicit projection is strict while written `as` is dynamic.

### Redundant casts -> destination-driven conversion

**Wrong:** `return ffi.count() as integer` when the declared return already is
`integer`, or `ffi.set(n as foreign api_int)` when its header typedef supplies `api_int`.

**Right:** `return ffi.count()` and `ffi.set(n)`. Keep `as` when choosing C versus
Titan operator behavior, numeric variadic ABI, or an unsafe explicit edge.

### Lua C API for loading -> `titan.lua`

**Wrong:** duplicate `luaL_loadbufferx`, package searchers, registry cache, and
stack cleanup in an application module.

**Right:** call `titan.lua.load`, `load_from_reader`, `dofile`, or `require`.
Use a typed callable result and convert dynamic values immediately.

### Raw Lua table construction -> typed Titan container

**Wrong:** call `lua_createtable`, recover it through `value`, and recast it to
a placeholder Map merely to build ordinary internal state.

**Right:** construct the semantic Titan Array or Map directly. If only a
metatable operation is missing, push that same typed value through the one
audited helper and perform only the narrow operation. Use `titan.gc` for weak
maps/finalizers.

### Ordinary closure as C callback -> restricted foreign entry

**Wrong:** expect a captured Titan lambda to decay to `int (*)(...)`.

**Right:** write a `foreign function` with direct C parameters and a C-only
body when possible. If it cannot reach the required state safely, design a
small explicit C boundary; do not forge compiler closure internals.

### Borrowed pointer used as owner -> retain the owner

**Wrong:** cast an owner/string/record to a pointer, store only the pointer in a
long-lived callback, then allow the Titan value to become unreachable.

**Right:** store the actual traced owner in the request/registration record for
the complete C borrow, and derive/reacquire the pointer when needed.

### Hidden backing escapes -> explicit owner

**Wrong:** `local p: foreign *T = foreign T.new()` followed by returning `p` or asking C to
retain it.

**Right:** keep `local owner: owned *T = foreign T.new()` in a traced long-lived
owner and pass its payload pointer only while that owner remains reachable.

### Owner mistaken for destructor -> explicit release

**Wrong:** assume `owned *SSL_CTX` calls `SSL_CTX_free` when collected.

**Right:** understand that the userdata owns inline bytes only. If a field
holds an external handle, implement `close`/`free`, clear the marker before
release, and optionally add an idempotent reachability fallback when the value
is eligible.

### C integer operation assumed to be Titan arithmetic -> convert first

**Wrong:** rely on floor division, modulo, wrapping signed arithmetic, or
normalized shifts while one operand is a C integer.

**Right:** cast once to `integer` before the operator when Titan semantics are
required; otherwise review the expression as C, including UB.

### Macro workaround becomes a shim layer -> one justified bridge

**Wrong:** mirror constants, structs, and every library call in hand-written C
because one function-like macro is unavailable.

**Right:** import all ordinary declarations directly. Write one namespaced
inline function around only the unsupported macro/opaque fact and document the
exception.

### Ad hoc stack pops -> saved-top transaction

**Wrong:** balance normal branches with `lua_pop` calls while errors,
metamethods, or a missing upvalue take different paths.

**Right:** snapshot `lua_gettop`, immediately `defer lua_settop`, reserve the
maximum, keep an explicit ledger, and trace survivors before restoration.

### Lua as convenient implementation language -> typed Titan first

**Wrong:** generate/load Lua to avoid modeling a closed operation in Titan, or
use `titan.lua.require` for a module known at compile time.

**Right:** use Titan records/unions/functions and static `import`. Load Lua only
when dynamic Lua execution or run-time Lua module discovery is the actual
feature. Review loaded code with the same seriousness as native C.

# Explicit unsupported-feature wall

Do not infer support from similar C/Lua syntax. The current boundary does **not**
support:

* header-dependent/imported C types in an exported/serialized Titan type tree
  (the documented portable contextual primitive/pointer/function/owner closure
  is supported);
* C module namespaces as first-class values;
* pointers to non-FFI Titan types;
* arbitrary compiler-extension headers outside Titan's C99 parser subset;
* general function-like macros;
* arbitrary object-like macro expressions or arbitrary call-containing object
  macros (only the documented bounded forms work);
* automatic adaptation of Titan functions/closures to a C callback ABI;
* imported/source foreign functions as Titan first-class functions or Lua
  members;
* foreign variadic parameters, flexible results, multiple results, or a
  Titan `...` forwarded to a C variadic call;
* a by-value C aggregate or C array in `value` or a `TValue`-backed slot;
* a dynamically verified raw C pointee type from lightuserdata (only an unsafe
  written assertion checks the outer representation);
* structural casts between Titan records/unions/Interfaces and C structs or
  unions;
* direct object-pointer/function-pointer conversion without the explicit
  `void *` portability round trip;
* ownership adoption of a C-allocated pointer; v1 has borrowed pointers and
  Titan-owned inline userdata only;
* owner allocation of `void`, incomplete aggregates, direct functions, nested
  owners, C array typedef payloads, or arbitrary flexible-array arrays;
* written fixed C-array annotations (`foreign T[N]` or `owned T[N]`);
* whole-C-array assignment or return;
* a count/length after a flexible-array parent has decayed to raw pointer;
* bounds checks on raw C pointer indexing;
* automatic destructor calls for `owned` payloads;
* general public safe access to the stack-oriented Lua C API;
* yielding through the current typed Lua-callable/native boundary;
* treating `titan.lua`'s environment as a security sandbox;
* importing a Lua module with Titan `import` (use static Titan import or
  `titan.lua.require` according to intent);
* first-class access to the private compiler/runtime `CClosure`/`Udata` callback
  protocol as an application ABI;
* automatic format-string validation for C variadic calls;
* wide `__int128` enum carriers;
* source aliases for enum tags, anonymous aggregates, or prototype-local tags;
* reliable writeability inference from every header-derived C `const`
  subobject in v1—Titan binding constness still blocks mutation through its own
  inline aggregate/array storage, but the C compiler may reject additional
  field assignments from imported qualifier details.

When a requested design needs one of these, stop. Either reshape the typed
boundary, use an existing higher-level module, add one reviewed narrow shim, or
ask the maintainer about the intended architecture. Do not pile casts,
lightuserdata registries, duplicate owners, or callback dispatch tables around
a missing feature.

# Validation workflow

For an FFI change:

1. Read the actual header under the active feature macros. Identify ownership,
   nullability, callback lifetime, thread/yield behavior, and exact release API.
2. Order foreign directives for the intended C preprocessing environment;
   `ffi` itself is available throughout the module. Put ordinary Titan imports
   and prerequisite module variables before initializers that use them.
3. Sketch the public Titan API first. For each public C type, prove recursively
   that its graph is built only from contextual primitives and portable
   pointer/function/owner constructors; keep every imported type private.
4. Classify every C object as automatic, borrowed pointer, explicit owner, or
   externally allocated resource. Mark exactly where each lifetime ends.
5. Mark every conversion and operator as Titan, C, strict `value` projection,
   dynamic `value as`, or unsafe pointer assertion.
6. For callbacks, prove the exact C function-pointer type and the terminal point
   after which no callback can occur. If async, prove ownership beyond
   cancellation.
7. For raw Lua API code, write the stack-effect table before code. Identify
   allocation, longjmp, metamethod/callback, yield, and borrowed-pointer effects
   for every operation.
8. Compile against the real configured C toolchain and link inputs. Do not
   validate only syntax or a hand-written approximation of the header.
9. Put compiler/type-system assertions in checker specs, generated-C/runtime
   behavior in coder specs, C parser behavior in its root specs, and public
   standard-library behavior in the native Titan suite. Do not run library API
   behavior under LuaCov.
10. If user-visible behavior changes, update both the language and
    implementation manuals in the same change.

A minimal local header fixture is often the best focused test: give it exact
prototypes/types/macros, compile a small Titan module through the normal
checker/coder helper, and exercise the generated native result. Test both the
accepted path and the tempting unsafe/rejected path. For platform headers,
retain a focused real-header canary as well as synthetic deterministic cases.

# Source map for deeper work

This skill is self-contained for normal boundary work. When changing the
compiler, runtime contract, or standard modules, use this map rather than
searching by analogy.

## Authoritative user documentation

* `doc/language/ffi.md` — foreign import, type families, calls, conversions,
  strings, arrays, owners, linking, platform limitations.
* `doc/language/c-ffi-expressions.md` — tag names, target-directed allocation,
  pointer probes, operators, macros, field projections.
* `doc/language/const-values.md` — binding constness, inline C storage,
  qualified Arrays, and Lua write boundaries.
* `doc/language/foreign-functions.md` — restricted source C functions,
  visibility, generated headers, body subset.
* `doc/language/types.md` — normative boundary matrix, strict versus dynamic
  `value`, direct coercions, written `as`/`is`.
* `doc/language/option-types.md` — automatic force/introduction and the limited
  composition rules.
* `doc/language/lua-interop.md` — Lua representations, module/record/container
  behavior, Lua callable dispatch, multiple states.
* `doc/language/standard-library-lua.md` — `titan.lua` API and async require
  semantics.
* `doc/language/standard-library-gc.md` — weak maps, finalizers, collector
  actions.
* `doc/style-guide.md`, especially “Keep Lua and C machinery behind narrow
  audited boundaries,” “Acquire, then defer the close,” and finalizer rules.

## Implementation documentation

* `doc/implementation/ffi-internals.md` — complete import/type/lowering pipeline.
* `doc/implementation/c-ffi-expressions.md` — C declarators, target profile,
  compile probes, operators/macros/allocation.
* `doc/implementation/const-values.md` — const lvalue checks, Array tags/casts,
  and generated Lua const-write paths.
* `doc/implementation/foreign-functions.md` — restricted checker, source
  headers, callback migrations.
* `doc/implementation/type-relations-and-boundaries.md` — checker-owned plans
  and checked scalar conversions.
* `doc/implementation/lua-interop-internals.md` — dynamic/strict entries,
  module/container representations, registry and loader paths.
* `doc/implementation/lua-library.md` — `titan.lua` stack/root and async loader
  implementation.
* `doc/implementation/ffi-lua-api-followup.md` — explicit unsupported status
  and trusted raw-API ledger.
* `doc/implementation/values-and-gc.md` — roots, stack relocation, barriers,
  native call handoff.

## Compiler and runtime sources

* `c-parser/{cpp,c99,ctypes,cdefines,cdriver}.lua` — preprocessing, parsing,
  declarations, macros, includes.
* `titan-compiler/{foreigntypes,cdeclarator,csemantics,cprobe,cpreamble}.lua` —
  C type conversion, exact declarators, target traits, compiler probes, shared
  preamble.
* `titan-compiler/types.lua` — `Type.C*`, coercion/guard/dynamic/written plans,
  export rejection and TValue representation.
* `titan-compiler/checker/c_types.lua` plus `type_syntax.lua`,
  `expressions.lua`, `calls.lua`, `statements.lua`, and `declarations.lua` —
  source checks and allocation/callback rules.
* `titan-compiler/coder/{calls,expressions,declarations,values}.lua` — C calls,
  casts, owners, fields/indexes, raw foreign bodies and rooting.
* `titan-runtime/titan/ffi.h` — private typed Lua bridges; portable primitives
  are contextual language types and are not typedefs in this header. Do not
  treat every internal declaration as a public application API.
* `titan/lua.titan` — the public dynamic-loading escape hatch;
  `titan/gc.titan` — its typed public collector/finalizer policy boundary.
* `titan/{iteration,test}.titan`, `titan/peg/native.titan`, and
  `titan/string/string.titan` — other audited Lua-stack examples.
* `titan/fs.titan`, `titan/uv/*.titan`, `titan/http/native.titan`, and
  `titan/coroutine.titan` — private source foreign callbacks; study only with
  their ownership/runtime docs, not as generic application templates.

## Focused specs

* Parser/type extraction: `spec/{cpp,ctypes,cdefines,cdriver,foreigntypes}_spec.lua`
  plus `spec/{cdeclarator,csemantics,cprobe}_spec.lua`.
* Checker contracts: `spec/checker/c_ffi_*_spec.lua` and
  `spec/checker/foreign_functions_spec.lua`.
* End-to-end generated C/runtime: `spec/coder/c_ffi_*_spec.lua` and
  `spec/coder/foreign_functions_spec.lua`.
* Dynamic boundary relations: checker/coder `type_relations_soundness_spec.lua`,
  `type_tests_spec.lua`, and relevant contextual-value/callable specs.
* Public `titan.lua` behavior: `spec/stdlib/titan/lua/tests/*.titan` in the
  aggregate native Titan suite.
* GC behavior: `spec/stdlib/titan/peg/tests/gc_test.titan`, the native GC owners,
  and focused runtime GC specs.

# Evaluation cases for this skill

Use fresh agents with no session context. Each answer should explain the
boundary, not merely produce code that happens to compile.

## Eval 1 — Public wrapper with C out-parameter

**Prompt:** A header returns `client *client_open(const char *)`, fills
`struct client_info { size_t bytes; int active; }` through
`int client_info(client *, struct client_info *)`, and has
`void client_close(client *)`. Design public Titan `inspect(name: string):
Info?`. A tempting draft exports the pointer and declares an uninitialized C
struct local.

**Pass criteria:** imports the header locally; keeps pointer/C struct private;
uses `.new()` at a direct local sink; lets the mutable local address-adjust to
the out pointer; installs `defer client_close` immediately after successful
open; converts to a public Titan record; handles NULL/status; no unnecessary
cast at already typed return/argument sinks.

**Fail signals:** public C type, `local raw: foreign Info` without initializer,
`value` pointer storage, missing close, or hand-written forwarding C.

## Eval 2 — Pointer lifetime review

**Prompt:** Review code that calls `register_name(name)` where the C header takes
`const char *` but retains it until `unregister`, while `name` is a Titan string
local. Fix the ownership design.

**Pass criteria:** states that the public string-to-C conversion is borrowed
immutable call-lifetime storage and rejects retaining it in ordinary application
code. Changes the native API to copy the bytes or gives registration an explicit
native owner, with exact unregister/terminal cleanup. It may identify the
standard library's narrow audited stable-string-borrow exception, but does not
recommend or generalize it and never claims the raw pointer roots the string.

## Eval 3 — Callback temptation

**Prompt:** A C library wants `typedef int (*cb)(int, void *)`. The draft passes
a capturing Titan lambda and boxes its record in `value` to recover from
`void *`. Propose a supported design and list limitations.

**Pass criteria:** rejects automatic closure adaptation and typed recovery from
lightuserdata; uses a source `foreign function` only if a C-only body and stable
C-visible data suffice, with exact `foreign function(...): ...` type; otherwise calls
for one narrow reviewed C bridge/redesign. Keeps the actual owner reachable
until deregistration. Notes foreign body cannot see Titan functions/state,
allocate owners, catch/defer, or receive implicit `L`.

## Eval 4 — Automatic versus owned arrays

**Prompt:** Explain the types/lifetimes of `local a = foreign Point.new_array(4)`,
`local b: foreign Point[] = ...`, `local p: foreign *Point = ...`, and
`local o: owned Point[] = foreign Point.new_array(n)`. Which may be returned to C
for later use?

**Pass criteria:** `a` is fixed automatic `[4]`, checked and length-aware; `b`
is an uncounted borrowed view; pointer/view targets use automatic backing for
an eligible positive constant array count and hidden owned backing otherwise,
with the latter owner rooted only for the frame; `o` is an explicit counted GC
owner. None of the raw pointers alone proves escape safety; long-term
C use requires retaining `o` (or another true external owner) for the complete
borrow. Notes 0-based indexing and `#` only for fixed/counted forms.

## Eval 5 — C versus Titan arithmetic

**Prompt:** Review `(ffi.read_i32() + 1) / 3` where the author expects Titan
wrapping addition and floor division. Also review `printf("%d", n)` for Titan
`integer n`.

**Pass criteria:** identifies C operator mode and its promotions/UB/truncating
`/`; casts the C result to Titan `integer` before Titan operations (and uses
`//` when floor division is intended); selects an exact promoted C integer type
matching `%d` for the C variadic argument or avoids the variadic API; states
format strings are unchecked.

## Eval 6 — Macro and enum boundary

**Prompt:** A header exposes an ordinary enum constant, an outer-cast signal
handler macro, a field alias macro, and a function-like `LIB_INIT(x)` macro.
An agent copies all constants and writes a large C shim.

**Pass criteria:** uses supported enum/object-like members and public field
spelling directly; leaves carrier/range checks to the target compiler; wraps
only `LIB_INIT` in one tiny namespaced author-owned inline C function if no
ordinary API exists; orders foreign directives so the combined C environment
has the intended macro state; flags function-like macros and `__int128` enum
carriers as unsupported.

## Eval 7 — `value` boundary precision

**Prompt:** A Lua plugin returns `{ transform = function(...) ... end }` with a
metatable that supplies `__index`, `__newindex`, `__len`, and `__eq`. Write a
Titan dynamic loader, explain which metamethods affect typed Map operations and
comparisons, and explain strict versus dynamic conversions. The draft uses
implicit `value -> foreign *Context` for a lightuserdata field and assumes two raw
`value` operands invoke table `__eq`.

**Pass criteria:** uses `titan.lua.require`, casts once to `{string: value}`,
reads/casts the function and calls through a typed callable, converts results at
the boundary, and rejects implicit raw-pointer recovery. Explains that the Map
cast is shallow; raw hits bypass `__index`; misses use it; and both paths apply
the same strict typed result guard. A present-key nil write deletes directly,
while an absent-key nil write still invokes `__newindex`. Exact integer-Map
length uses `__len` with an exact integer-tag result or a no-metamethod border.
Map/Map, Map/`value`, and `value`/Map table comparisons use raw equality then
left/right `__eq` with Lua truthiness only when the dynamic operand is a table;
`value`/`value` stays raw. Also explains that written `value as` is dynamic and
a function cast defers callability. Warns Lua loading is an escape hatch, not a
sandbox or default module mechanism.

## Eval 8 — Raw Lua stack audit

**Prompt:** Review a trusted standard-module helper that calls `lua_getglobal`,
keeps `TValue *slot = ...`, calls a user metamethod, then manually pops once and
returns the slot's string pointer.

**Pass criteria:** rejects the raw slot/pointer across allocation/user code and
return; snapshots top, immediately defers exact restoration, reserves maximum
stack space, copies the result with `ffi.lua_totvalue` into traced Titan state,
and derives any borrowed bytes only while the owner remains rooted. Notes stack
relocation, metamethod/longjmp behavior, nonyieldability, and that raw C API use
is not a general application feature.

## Eval 9 — Owner is not destructor

**Prompt:** A private Titan record holds a raw OpenSSL `SSL_CTX *`. A draft
changes it to `owned *openssl.SSL_CTX`, assumes GC will call `SSL_CTX_free`, and
allows an async callback to outlive Task cancellation.

**Pass criteria:** first notes that OpenSSL's opaque/incomplete `SSL_CTX` is not
an eligible owned payload; even a complete owned payload would own only inline
bytes and would not invent a library destructor. Keeps the raw library handle
behind a traced Titan callback owner, requires explicit idempotent
`SSL_CTX_free` at the authoritative terminal point, and retains the complete
owner through callback/close despite cancellation. Does not race it with a
finalizer; any eligible finalizer is only a nonyielding reachability fallback,
not prompt cleanup.

## Eval 10 — Unsupported API honesty

**Prompt:** Ask whether Titan supports arbitrary Lua C API calls, C function
pointer values in `value`, ordinary closures as callbacks, adopted malloc
pointers, function-like macros, and either portable contextual or imported C
types in exported interfaces.

**Pass criteria:** clearly says the first five are unsupported as general
features, allows the documented recursive portable C closure in public
interfaces, and rejects imported/header-dependent C types there. Distinguishes
the audited standard-library Lua C API exception, restricted source foreign
functions, explicitly unsafe lightuserdata assertion, and narrow hand-written
shim option. It does not invent wrappers, tags, or ownership machinery and
directs a design question to the maintainer when the boundary cannot be
reshaped.

# Final boundary checklist

Before approving code, answer all of these explicitly:

* What is the public Titan type? Is every exposed C component in the portable
  contextual closure, with header-dependent C and Lua implementation types
  hidden?
* Is each pointer nullability, mutability, ownership, and lifetime documented?
* Is every retained borrowed pointer accompanied by its reachable original
  owner?
* Is storage automatic, hidden-frame-backed, explicit `owned`, or external—and
  can it escape its lifetime?
* Does each numeric/operator expression intentionally use Titan or C semantics?
* Is each `as` necessary, and is every raw-pointer cast visibly unsafe?
* Are C calls exact-arity, and do C variadic argument types match their real ABI?
* Are macro/enum assumptions validated by the active header/toolchain?
* Can a callback occur after cancellation, unregister, close, or finalization?
* If Lua is used, why is a static Titan module or typed callable insufficient?
* If a Lua table is viewed as a Map, are raw hits, metamethod fallbacks, strict
  result tags, exact integer length, scoped Map equality, and raw
  `value`/`value` equality distinguished?
* If the raw Lua API is used, where are the saved top, maximum reservation,
  per-path ledger, traced survivor, nonyielding rule, and borrowed-pointer audit?
* Are cleanup and tests located at the owning layer?

If any answer is implicit, the boundary is not ready for review.
