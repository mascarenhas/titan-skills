---
name: titan-json
description: Encode and decode JSON with Titan's titan.json module, choose null and schema policies, map records and unions, and diagnose structured failures. Use for Titan JSON code and JSON-library maintenance, not unrelated JSON configuration files or JSON libraries in other languages.
---

# Titan JSON

Read `titan-programmer` first. Ordinary JSON use needs this cartridge, not every
implementation specialist. The named and structural schema recipes below are
ordinary use. Add `titan-reflect` when designing schemas beyond those recipes
or changing reflected construction, `titan-pegs` when changing the JSON grammar
or captures, and `titan-tester` for native tests. Add `titan-ffi` only when
touching native numeric conversion or another actual foreign boundary.

`titan.json` is synchronous and string-based. It does not require an async
Runtime. Import `"json"` or `"titan.json"`; Lua requires `"titan.json"`.

## Public surface and selection

```text
encode(subject: value, ...: EncodeOption): string
decode(source: string, target: reflect.Type?, ...: DecodeOption): value

EncodeOption.tag_field(name: string)
EncodeOption.null_value(value)
EncodeOption.max_depth(integer)
EncodeOption.max_bytes(integer)
EncodeOption.max_nodes(integer)

DecodeOption.tag_field(name: string)
DecodeOption.null_value(value)
DecodeOption.max_depth(integer)
DecodeOption.max_bytes(integer)
DecodeOption.max_nodes(integer)
DecodeOption.ignore_unknown_fields(boolean)

Error.code: string
Error.message: string
Error.position: integer?
Error.line: integer?
Error.column: integer?
Error.path: string
-- All Error fields are const.
```

Use `decode(text)` for dynamic JSON data: scalars, Titan `{value}` Arrays, and
`{string: value}` Maps. Use `decode(text, descriptor)` to construct a requested
schema, then recover its result at an ordinary typed sink. Options without a
schema require the explicit placeholder `decode(text, nil, option, ...)`.
Repeated options use the last occurrence. There is no `decode<|T|>`, public AST,
automatic type-token inference, or custom codec registry.

Do not infer failure from a nil result: decoding JSON null succeeds with nil.
Expected failures raise `json.Error`. Unexpected runtime failures keep their
original error/traceback. A raw `value` result cannot be indexed or used as an
Array until the caller supplies a precise typed view.

## Nulls: decide whether loss is acceptable

The default null value is nil. Array holes encode as null, but nil tails shorten
the decoded Array and nil Map entries disappear:

| Decode then encode | Default result |
| --- | --- |
| `[1,null,3]` | `[1,null,3]` |
| `[1,null,null]` | `[1]` |
| `[null]` | `[]` |
| `{"x":null}` | `{}` |

Preserve source positions during conversion: assign `out[index]`, never
`out[#out + 1]` after a null. This loss is the maintainer's chosen default,
not a reason to add an implicit wrapper or change Array length semantics.

Use an explicit nonnil sentinel for lossless dynamic nulls. Save this complete
example as `json_nulls.titan`:

```titan
local json = import "json"

local record NullToken
end

function main(args: {string}): integer
  local token = NullToken.new()
  local values: {value} = json.decode("[1,null,null]", nil,
    json.DecodeOption.null_value(token))
  if #values ~= 3 then return 1 end
  local text = json.encode(values, json.EncodeOption.null_value(token))
  if text ~= "[1,null,null]" then return 2 end
  return 0
end
```

Reuse the same reference token. Comparison is raw `value` equality before
ordinary encode dispatch, without `__eq` or `__tostring`. False, zero, and
empty strings work as sentinels but also replace equal real data, including
`0` versus `0.0`; do not test their presence by truthiness. NaN is invalid;
nil restores default behavior. Sentinels never rewrite object keys or generated
union tags.

Sentinels apply to untyped decoding and `is_value` leaves. Explicit nil/Option
targets still consume null as nil. Concrete Array/Map element schemas consume
null as absence; a foreign sentinel must not enter `{integer}`. Required scalar,
record-field, root, and nonnullable union-payload targets reject null. Missing
nil-admitting record fields and union parts become nil and never become the sentinel: source
absence and explicit null are different inputs.

## Records, unions, and exact schemas

Encoding inspects actual values. It emits public record fields in declaration
order, string-keyed Map entries in byte order, and Arrays in `1..#array` order.
Empty Arrays and empty Maps remain `[]` and `{}`. Integer Maps are not guessed
to be Arrays; actual non-string keys fail. A typed Map target must admit string
keys (`is_string` or `is_value`) even for an empty object.

Union objects contain a discriminator (default key `tag`) and each declared
payload part by name:

```text
-- Declarations: idle(), count(integer), point(x: integer, y: integer)
Message.idle()       -> {"tag":"idle"}
Message.count(3)     -> {"tag":"count","value":3}
Message.point(2, 3)  -> {"tag":"point","x":2,"y":3}
```

A single unnamed payload is named `value`; a single explicitly named part uses
that name too. Encode parts in declaration order. Decode keys in any order,
use `VariantType.parts` names/types, and call `UnionValue:get(i)` with a 1-based
part ordinal. Missing nil-admitting parts become nil independently of a null
sentinel; other missing parts fail. Parts whose value is nil still encode as
null. Extra envelope members are rejected even with
`ignore_unknown_fields(true)`. Each record/Map part remains nested under its
own key. Without a schema these objects remain Maps.

Use matching `EncodeOption.tag_field("kind")` and
`DecodeOption.tag_field("kind")` to change the discriminator for every nested
union in a call. The selected discriminator must not collide with any declared
part of the selected variant; collisions raise `invalid_union`. A part named
`tag` is valid when another discriminator is selected. Escape discriminator
keys as normal JSON strings and count the generated discriminator value in
node budgets. There is no extra synthetic payload-object depth.

Save this complete nominal composition as `json_model.titan`:

```titan
local json = import "json"
local reflect = import "reflect"

record Person
  const name: string
  note: string?
end

union Message
  person(Person)
  idle()
end

function main(args: {string}): integer
  local original = Message.person(Person.new("Ada", nil))
  local text = json.encode(original)
  local schema = reflect.Type.is_named(
    reflect.NamedType.new("json_model.Message"))
  local decoded: Message = json.decode(text, schema)
  if json.encode(decoded) ~= text then return 1 end
  return 0
end
```

The nominal name includes the actual module name. That module must already be
initialized; JSON does not import it. Unknown names raise `unknown_type` rather
than silently adopting `NamedType:resolve`'s `is_value` fallback.

Automatic record decoding finds the public synthesized static `new`, validates
all named arguments, then invokes it once. Missing required booleans are errors,
not false defaults. Const fields are initialized by this constructor; do not
allocate a record and try to fill it with reflected setters. A local record or
a record containing any local field has no public `new`: encoding its public
view can work, but automatic decoding raises `constructor_unavailable`. Do not
guess factories or expose private storage.

When maintaining the constructor call, retain `arity` independently of the
`{value}` argument Array and use `callable(...arguments[1, arity])` to preserve
trailing/all-nil slots. Reflected public field getters take one-based public
ordinals, not zero-based logical field indices. Union runtime tags can have gaps
from private arms: search `VariantType.tag`, never `variants[tag + 1]`. An active
private arm is an encode error.

Structural schemas use the existing reflection API. This complete module
decodes a const integer Array:

```titan
local json = import "json"
local reflect = import "reflect"

function read_numbers(source: string): const {integer}
  local schema = reflect.Type.is_array(
    reflect.ArrayTypeConstness.is_const(), reflect.Type.is_integer())
  return json.decode(source, schema)
end
```

`Type.is_array` takes constness **before** its element descriptor;
`Type.is_map` takes key then value descriptors. Decoded mutable Arrays are created through
`{value}` storage, preserving its construction-time Lua-writer policy even after
a typed projection; later typed reads still guard each nonnil element. Const
results reject writes, and maybe-const targets produce mutable Arrays.

Recursive nominal schemas resolve lazily. Generic arguments remain erased:
`Box<|Person|>` and `Box<|string|>` share a descriptor, and erased `T` may look like
declared `value`. Its output is dynamic JSON data. An outer nominal cast cannot
prove those leaves; use an explicit application conversion when specialization
matters. Do not introduce a specialization registry as an implementation repair.

Interface encoding serializes captured public fields through
`InterfaceValue:get`, not the unwrapped concrete receiver. Interface decoding,
functions, threads, pointers, owned foreign storage, and opaque userdata have
no default representation. Methods/statics are not serialized. Cycles fail;
shared acyclic references serialize independently.

## Syntax, numbers, and errors

Accept one complete RFC 8259 document. Reject comments, trailing commas/data,
BOM, malformed tokens, duplicate decoded keys, invalid UTF-8, lone surrogates,
and unescaped controls. Surrogate pairs combine; embedded NUL uses `\u0000`;
Unicode is not normalized. Titan strings are bytes, so encoding must reject
invalid UTF-8 rather than silently repairing it.

Dynamic integer-form tokens remain exact integers; fractional/exponent tokens
become floats. Integer targets use exact decimal normalization and range checks,
not a rounded float (especially above `2^53`). Finite float conversion allows
rounding but rejects overflow and nonzero underflow to zero; preserve negative
zero and retain a decimal/exponent marker when encoding an integral float.
Nonfinite input floats fail. Numeric helpers must not change the process-global
locale. Full-range integers are emitted as numbers, with interoperability limits
documented for consumers that cannot represent them exactly.

`Error.code` is a stable category/grammar label. `message` is explanatory;
`position`, `line`, and `column` are optional one-based source byte locations.
CRLF is one newline; CR and LF work independently, EOF is `#source + 1`, and
columns do not count Unicode display width. Encoding/option errors have no
input position. `path` uses `$`, quoted member names, and one-based Array
indices. Syntax errors use `$` until a semantic path is available.

The defaults are 16 MiB of text, 1,000,000 JSON values, and depth 32. Depth,
byte, and node options require positive integers.
Depth counts nested JSON containers: scalar roots have depth zero, a root
Array/object has depth one, and union envelopes count as objects. Node limits
include every JSON value, including nulls, generated union tags, source positions
later lost to nil, and ignored record members. Exceeding them raises `limit_exceeded`; invalid settings raise
`invalid_option`. A configured depth budget does not guarantee that a document
fits PEG matching-stack/capture-recursion or decoder/encoder traversal space.
JSON never changes the shared PEG stack; do not relabel independent
engine/runtime errors as bad JSON or a JSON limit failure. Applications own
`peg.set_max_stack` policy for their workloads; nested sibling lists can need
more matching-stack space than single-child chains at the same depth.
Common grammar labels are `expected_value`, `expected_object_key`,
`expected_colon`, `expected_array_separator`, `expected_object_separator`, and
`trailing_input`; malformed UTF-8 and duplicate decoded names use `invalid_utf8`
and `duplicate_key`. Use the actual raised code rather than matching message
wording.

## Parser maintenance and validation

Use the public PEG module and load `titan-pegs` for grammar work. Compile one
stable Relabel grammar in the final module initializer. Use anchored
`Pattern:match` with end-of-input, preserve committed labels at exact expectation
sites, and compute `peg.line_column` once on error. A leftmost search or grammar
compilation per decode is not the parser contract.

Keep a nonnil private `Node` for each value and a `Member` per object entry.
Use ordinary delayed folds with fresh accumulator factories and one captured
node per reducer call. Object keys and values are sibling captures, paired by
fresh typed per-object state holding a pending key and duplicate-name set.
Do not wrap each member value in another delayed function/group capture;
that needlessly consumes a recursion layer at every object depth.
Never pass a whole wide list into one callback, hold a mutable
constant accumulator across calls, or eagerly finalize every child into retained
match-time results. Local match-time budget guards return only success and
update per-call state on committed paths. They do not yield or mutate state
inside predicates. PEGs alone do not guarantee linear time: retain disjoint
prefixes, iterative sibling tails, consuming repetitions, and bounded rescans.

Capture byte positions; decode each string once with a writer; keep numeric
spans until conversion. Retain path components rather than repeatedly building
path strings. Parsing/node construction is linear apart from ordinary expected
Map lookup costs. Encoder key sorting has a separate complexity bound. List
width and nested capture recursion are separate test dimensions.

Public JSON behavior belongs in `spec/stdlib/titan/json/tests/`, the explicit
`json.tests` native root, outside LuaCov. Only Titan's short-import normalization
belongs in the compiler parser spec. Packaging specs own provider inventories,
metadata/shims, and rollback. After refreshing the canonical provider, run:

```sh
make titan-stdlib-test TITAN_FILTER='^json[.]tests[.]'
make titan-stdlib-test-run
make test
```

The run-only target does not rebuild or reinstall. Root owns shared builds;
use an isolated worktree/toolchain for concurrent experiments. Inspect the
selected-case summary, not only exit status. Include null/default/sentinel
matrix, constructor arity, sparse/private union tags, exact locations, numeric
and Unicode boundaries, cycles/sharing, limits, wide folds, warmed scaling, and
GC pressure. Exercise arrays and objects at 128 with the default PEG stack and
mixed nesting with siblings at 128 with an explicitly configured stack, restoring
the suite's default stack afterward. Cover configured depth rejection, the
unchanged default depth 32, and independent PEG resource failures.
Test actual public behavior instead of inspecting generated JSON
module source from a Lua wrapper.

Read deeper authority when changing a contract or resolving an edge case:

- [Human API and examples](../../../doc/language/standard-library-json.md).
- [Implementation and complexity](../../../doc/implementation/json-library.md).
- [Public declarations](../../../titan/json/json.titan) and
  [native tests](../../../spec/stdlib/titan/json/tests/tests.titan).
- [Cartridge evaluation cases](../titan-programmer/EVALUATION.md).

Keep human explanations in the language manual and implementation mechanics in
its companion. Update this skill with the operational consequences; do not turn
the language manual into an agent checklist or duplicate it wholesale here.
