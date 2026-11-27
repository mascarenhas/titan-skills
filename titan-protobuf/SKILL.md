---
name: titan-protobuf
description: Use when serializing Titan data to Proto3 wire bytes, schemas, or portable codecs with titan.protobuf. Covers records, unions, anonymous tuples, protobuf.portable and titan-protobuf.mjs browser copying, generated codecs, buffers, and nesting limits; use titan-json for JSON, titan-thread for channels/transfer, titan-ffi for raw browser handles.
---

# Titan Protocol Buffers (`titan.protobuf`)

Synchronous Proto3 wire encoder/decoder, schema emitter, and target-neutral portable codecs (native & browser complete). Import `local protobuf = import "protobuf"` (Lua: `require "titan.protobuf"`).
Pair with `skill://titan-programmer` and `skill://titan-reflect` (for `reflect.Type` descriptors). Peers: `skill://titan-ffi` (browser `bindings`, C `titan_protobuf_buffer`), `skill://titan-thread` (`titan.transfer` cross-state packets), `skill://titan-json` (text JSON), `skill://titan-tester`.

## Non-negotiable invariants

1. **Declaration order = wire tags; direct decoding bypasses `new`:** Ordinary `serialize`, `deserialize`, `deserialize_nominal`, and `schema` require a **public** record or union whose members are **all public** (`local` fields/variants fail; `const` fields work). Record fields number `1, 2, ...` in declaration order (skipping reserved `19000..19999`), so reordering breaks wire compatibility. Ordinary decoding constructs fresh values directly via `reflect` **without** invoking user-defined `new`.
2. **Raw byte strings & explicit present scalars:** `string` encodes as `optional bytes` (no UTF-8 check; NUL-safe). Absent Options/`nil` emit no bytes, while **present scalars always emit even for `0`/`false`/`""`**, and decoding requires every non-optional field to be present. `integer` -> `optional sint64` (ZigZag), `float` -> `optional double`, Arrays -> nested slot messages (preserving interior `nil` holes, separating empty `[]` from absent `nil`, storing `const` flag at field 2 for `const?` targets).
3. **Upfront-validated `protobuf.portable`:** `protobuf.portable(fields, dynamic?, text?)` validates the entire reachable graph upfront, rejecting Maps, Interfaces, callables, **all foreign types**, local nominals, hooked records, and packet resources. `value` slots accept only nominals reachable from `fields` + `dynamic` (no demand loading; else `is not in this portable codec`). Public records with `local` fields encode public fields and decode via a matching-name public `new` (else encode-only). `text` paths (`"2"`, `"mod.Rec.field"`, `"mod.Union.arm.part"`) affect only `describe()`.
4. **Browser `titan-protobuf.mjs` peer:** Copy `$PREFIX/lib/titan-browser/0.6/titan-protobuf.mjs` with app assets and pass `codec:describe()` (`is_string`) + `codec:encode(...)` (`is_bytes`) to JS `portable(desc[, sharedTypes])`. JS types: `nil` -> `null`, `integer` -> 64-bit **`BigInt`**, `float` -> `Number`, unmarked `string` -> **`Uint8Array`**, `text` -> JS `string` (strict UTF-8/16), Array -> `Array` (`const` -> `Object.freeze`), nominals -> `codec.types[fqtn]` / `.variants[arm]` instances (plain objects rejected; extra args throw `type_mismatch`). Send live handles/callables separately.
5. **128-level nesting limit & 2 GiB wire cap:** Shared `TITAN_CODEC_DEPTH_LIMIT = 128` across native, browser, `schema`, `portable`, `titan-protobuf.mjs`, and `transfer` (max **127** chained records under a nominal root, **126** under an anonymous/`portable` root field; deeper raises `protobuf: nesting exceeds 128 levels`). Messages `> 2 GiB` raise. Cycles raise; shared acyclic graphs copy independently.
6. **Initialized types, generated codecs, and transfer hooks:** `deserialize`/`deserialize_nominal` never import modules (only `transfer.TransferValue:to_value()` preloads on demand). The compiler emits native codecs for eligible all-public records (`<= 64` fields) and unions (`<= 63` parts/variant) without transfer hooks (`use_generated_codecs(false)` forces reflection for diagnostics; generated errors abbreviate paths past 16 levels with `...`). Calling `serialize` directly on a hooked record as root uses structural public-data rules (hooks fire when nested or via `titan.transfer`); standalone calls open no packet scope, so `thread.Sender`/`Receiver` raise outside `titan.transfer`.

## API selection & Proto3 wire mapping

| API | Purpose & arity / policy |
| --- | --- |
| `serialize(v): string` / `deserialize(b, desc): value` / `deserialize_nominal(b, name, is_union): value` | All-public record/union wire bytes (`serialize` checks runtime values lazily; `schema(desc)` walks declared types eagerly). |
| `serialize_fields(fields, ...)` / `deserialize_fields(b, fields)` | Ordered anonymous tuple (`const {reflect.Type}`) without wrapper record; exact arg/return count preserving interior/trailing `nil`s (`{}` -> `""` / 0 values). |
| `portable(fields, dynamic?, text?): PortableCodec` | Pure copied-data codec (`:encode(...)`, `:decode(b)`, `:describe()` JSON schema); supports public views of records with `local` fields. |
| `*_to_buffer(buf, ...)` / `deserialize_*_buffer(data, len, ...)` | Zero-string-alloc FFI entries over `titan_protobuf_buffer` (`titan-runtime/transfer.h`); pair `titan_protobuf_buf_init_heap` + `defer ffi.titan_protobuf_buf_free_heap(buf)`; keep `data` alive across decode; never cache interior `data` across reservations. |

**Wire types:** `boolean` (`optional bool`), `integer` (`optional sint64`), `float` (`optional double`), `string` (`optional bytes`), foreign signed/unsigned int (`sint64`/`uint64` width-checked), foreign `float`/`double` (`float`/`double`), foreign `long double` (`bytes` C `%La` hex), foreign ptr (`fixed64` address only—caller owns pointee lifetime).
**Aggregate & rejected types:** Record/C struct -> nested message; union -> `oneof` variant messages by public ordinal; Array/fixed C array -> repeated slot messages (fixed C array verifies exact length); `value` -> `TitanValue` (`bool=1`, `sint64=2`, `double=3`, `bytes=4`, `TitanValue_Nominal=5`, `Array=6`). **Rejected:** Maps, Interfaces, callables, `owned` C storage, C unions, incomplete/FAM C aggregates.

## Nominal codecs, anonymous tuples, and diagnostics

- **Wire decode rules:** Skips unknown fields, takes last repeated scalar, merges repeated singular messages/Array slots, replaces earlier union arms with later ones; rejects malformed framing, groups, wrong wire types, out-of-range ints, missing required fields, unrecognized union tags, and `> 2 GiB` messages.
- **Error paths:** Nested encode/decode failures append ` at <path>` matching `json.Error.path` (`$` root, `["field"]`, `[1]` 1-based Array/anonymous field; `value` adds no segment). `"protobuf: "` is reserved; user errors without it propagate unchanged. Replaying for path attribution never re-invokes transfer hooks, resource callbacks, `new`, or module loaders.

```titan
-- file: pb_wire.titan
local protobuf = import "protobuf"
local reflect = import "reflect"

record Note
  const seq: integer
  const payload: string
end

union Event
  note(Note)
  ping(seq: integer)
end

local const TUPLE_FIELDS: const {reflect.Type} = {
  reflect.Type.is_integer(),
  reflect.Type.is_option(reflect.Type.is_string()),
}

function main(args: {string}): integer
  local orig = Event.note(Note(7, "hi\0raw"))
  local bytes = protobuf.serialize(orig)
  local target = reflect.Type.is_named(reflect.NamedType("pb_wire.Event"))
  local decoded: Event = protobuf.deserialize(bytes, target)
  case decoded
  when note(n) then
    if n.seq ~= 7 or #n.payload ~= 6 then return 1 end
  else
    return 2
  end

  local proto = protobuf.schema(target)
  if #proto == 0 then return 3 end

  -- Anonymous tuple preserves explicit trailing nil
  local wire = protobuf.serialize_fields(TUPLE_FIELDS, 42, nil)
  local id: integer, label?: string = protobuf.deserialize_fields(wire, TUPLE_FIELDS)
  if id ~= 42 or label ~= nil then return 4 end
  return 0
end
```

## Portable codecs & browser `titan-protobuf.mjs` peer

- **Public views:** A public record with `local` fields serializes its public fields in order; decoding requires `RecordType:public_constructor()` whose parameters are each named after a public field (unused public fields are validated and discarded; without it, decode raises `has no public constructor over its public fields`). Public unions with `local` arms encode public arms and raise `protobuf: private union variant` on an active private arm.
- **`describe()` & `text` paths:** Returns deterministic JSON `{"fields":[...],"nominals":{...}}` (`"bytes"` vs `"text"`, `["option",T]`, `["array",constness,T]`, `["nominal",fqtn]`, omitting local members). `text` paths may traverse Options/Arrays and must terminate at `string` (never `value`) inside the closed set.
- **Browser JS peer (`titan-protobuf.mjs`):** Share class tables across matching codecs via `portable(desc, first.types)`. Subclasses of generated classes encode as their base nominal. Peer errors throw `TypeError` with `.code` (`invalid_utf8`, `type_mismatch`, `integer_range`, `missing_field`, `unknown_type`, `unknown_variant`, `cycle`, `limit_exceeded`, `malformed_wire`, `invalid_description`) and `.path`, reaching Titan as catchable `BrowserError` (`thrown` keeps `code`/`path`); Titan codec errors reject JS with `TITAN_BROWSER_TITAN` without poisoning the instance.

```titan
-- file: pb_portable.titan
local protobuf = import "protobuf"
local reflect = import "reflect"

record Sensor
  local calibration: integer
  const label: string
  const celsius: float
end

function Sensor.new(label: string, celsius: float): Sensor
  return { calibration = 1, label = label, celsius = celsius }
end

record Tag
  const code: string
end

function main(args: {string}): integer
  local fields: const {reflect.Type} = {
    reflect.Type.is_named(reflect.NamedType("pb_portable.Sensor")),
    reflect.Type.is_value(),
  }
  local dyn: const {reflect.Type} = {
    reflect.Type.is_named(reflect.NamedType("pb_portable.Tag")),
  }
  local text_paths: const {string} = {
    "pb_portable.Sensor.label",
    "pb_portable.Tag.code",
  }
  local codec = protobuf.portable(fields, dyn, text_paths)
  local wire = codec:encode(Sensor("roof", 21.5), Tag("ok"))
  local s: Sensor, extra: value = codec:decode(wire)
  local t: Tag = extra
  if s.label ~= "roof" or s.celsius ~= 21.5 or t.code ~= "ok" then return 1 end
  if #codec:describe() == 0 then return 2 end
  return 0
end
```

## Pre-delivery verification checklist

- [ ] Wire-compatible records keep field declaration order stable; ordinary `serialize`/`deserialize`/`schema` roots are all-public records/unions.
- [ ] Cross-target and browser JS copying uses `protobuf.portable` with every dynamic nominal declared in `dynamic`, `text` paths ending at `string`, and `titan-protobuf.mjs` copied from `$PREFIX/lib/titan-browser/0.6/`.
- [ ] JS bindings pass `BigInt` for `integer`, `Uint8Array` for unmarked `string`, and `codec.types[fqtn]` instances (never plain JS objects); live handles/callables travel separately.
- [ ] Public records with `local` fields decoded under `portable` define a public `new` whose parameter names match public fields.
- [ ] Graph nesting stays within 127 records (nominal root) / 126 records (anonymous/`portable` root), with no cycles or standalone `thread.Sender`/`Receiver` fields.
