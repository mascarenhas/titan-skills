---
name: titan-json
description: Use when encoding, decoding, or validating RFC 8259 JSON in Titan with titan.json, null policies, or schemas. Covers dynamic value decoding, null_value sentinels, record/union typed mapping, tag_field, limits, and json.Error diagnostics; use titan-protobuf for binary Proto3 wire data, titan-reflect for general reflection, skip non-Titan JSON files.
---

# Titan JSON (`titan.json`)

Synchronous compact RFC 8259 JSON encoder and reflection-directed decoder (native & browser complete; needs no async Runtime). Import `local json = import "json"` (Lua: `require "titan.json"`).
Pair with `skill://titan-programmer` for core syntax/`T?`/`value`/`catch`. Peers: `skill://titan-reflect` (custom descriptor walks), `skill://titan-protobuf` (binary Proto3), `skill://titan-pegs` (`titan/json/parser.titan` maintenance), `skill://titan-tester`.

## Non-negotiable invariants

1. **Explicit `nil` placeholder & catch `json.Error`:** `encode(subject: value, ...: EncodeOption): string`, `decode(source: string, target: reflect.Type?, ...: DecodeOption): value`. Pass `nil` for `target` when giving `DecodeOption`s without a schema (`json.decode(s, nil, opt)`). Last repeated option wins; invalid options raise `invalid_option` pre-parse. Never test `result == nil` for failure (`decode("null")` succeeds with `nil`): catch `json.Error` and re-raise unrelated errors with bare `raise`.
2. **Default `null` drops container absence; use a record sentinel for lossless dynamic nulls:** Default `null -> nil` drops trailing Array nulls (`[1,null,null]` -> `[1]`, `[null]` -> `[]`) and null Map entries (`{"x":null}` -> `{}`), preserving interior Array holes (`[1,null,3]`). For lossless dynamic/`is_value` nulls, pass one shared empty `record NullToken end` to both `DecodeOption.null_value(tok)` and `EncodeOption.null_value(tok)` (raw equality; `NaN` -> `invalid_option`; `nil` restores default). Sentinels never apply to Option/`nil`/concrete elements, keys, or union tags; missing fields/parts decode as `nil`.
3. **No `decode<|T|>`; initialized modules only:** Dynamic `decode` yields scalars, `{value}` Arrays, and `{string: value}` Maps (project to concrete types at typed sinks). Typed `decode` takes a `reflect.Type` (`reflect.Type.is_named(reflect.NamedType("mod.Type"))`, `Type.is_array(constness, elem)`, `Type.is_map(key, val)`). `decode` never imports modules (`unknown_type` if unregistered—never falls back to `is_value`). Generic type args are erased (`Box<|Person|>` decodes `T` dynamically as `value`).
4. **Records decode via public static `new`; union envelopes stay strict:** Record decoding invokes `RecordType:public_constructor()` once (requires fixed params, 1 result of target record, no flexret; else `constructor_unavailable`), mapping JSON keys to `new`'s parameter names (not fields directly). Records with `local` fields need a compatible public `new` to decode (encoding public fields works either way). `DecodeOption.ignore_unknown_fields(true)` applies **only to records** (ignored members still undergo syntax/budget checks); extra union keys always fail, and encoding an active `local` variant raises `private_variant`.
5. **Strict RFC 8259, UTF-8, and exact numeric kinds:** Rejects comments, trailing commas/data, UTF-8 BOM, unescaped controls, lone surrogates, invalid UTF-8 (on both encode & decode; NUL round-trips as `\u0000`), duplicate object keys (including post-`\u` decoding and `null`-valued keys), and non-finite floats (`NaN`, `±inf`). Dynamic integer-form tokens -> exact 64-bit `integer` (overflow raises); fraction/exponent tokens -> finite `float` (integral floats encode with decimal/exponent to stay `float`). Integer schemas validate exact decimal values (`1.0`, `1e3`) without binary float rounding above `2^53`; float schemas reject overflow and nonzero underflow to zero while preserving `-0.0`.
6. **Budgets & independent PEG stack:** Defaults: `max_bytes` = **16 MiB**, `max_nodes` = **1,000,000** (counts root, nulls, generated union tags, ignored record fields), `max_depth` = **32** (nested JSON containers: scalar root = 0, root Array/object/union = 1; identical on native & browser with no extra browser cap). All require positive integers (`<= math.maxinteger`); exceeding raises `limit_exceeded`. `json` never modifies `peg.set_max_stack`; deep sibling nesting may require the caller to raise `peg.set_max_stack`.

## Encoding, null, and schema matrix

| Titan value / input | JSON / behavior | Key rule |
| --- | --- | --- |
| `nil` / `boolean` / `integer` / finite `float` / UTF-8 `string` | `null` / `true`/`false` / decimal / escaped string | Full 64-bit ints emit as numbers; non-UTF-8 strings fail. |
| Mutable or `const` Array | `[...]` (`1..#arr`) | Empty -> `[]`; interior holes -> `null`; `const` target -> `const {T}`, `const?` -> mutable. |
| `{string: V}` Map | `{...}` (byte-sorted keys) | Raw entries (no `__pairs`); non-string key -> `invalid_map_key`; Map schema needs `is_string`/`is_value` key even for `{}`. |
| `record` | `{...}` (public fields in decl order) | `local` fields/methods/statics omitted; missing nil-admitting params -> `nil` (required `boolean` cannot omit). |
| `union` | `{"tag":"arm", ...}` | Single unnamed part -> `"value"`; empty arm -> `{"tag":"arm"}`; custom key via matching `tag_field`. |
| `interface` | `{...}` (captured public fields) | **Encoding only** (does not unwrap concrete receiver); decoding unsupported. |
| Callables, threads, raw/owned C, opaque userdata, cycles | Raises | Acyclic shared references encode independently; inputs never mutated. |

## Dynamic decoding, null sentinels, and diagnostics

- **Options:** `EncodeOption` (`tag_field`, `null_value`, `max_depth`, `max_bytes`, `max_nodes`); `DecodeOption` adds `ignore_unknown_fields(boolean)`.
- **`json.Error` (`const` fields):** `code: string` (stable label, e.g. `expected_value`, `trailing_input`, `duplicate_key`, `invalid_utf8`, `unknown_field`, `unknown_type`, `unknown_variant`, `missing_field`, `invalid_union`, `constructor_unavailable`, `limit_exceeded`, `invalid_option`, `cycle`), `message: string`, `position: integer?` (1-based byte offset; `#source + 1` at EOF), `line: integer?`, `column: integer?` (CR/LF/CRLF = 1 line ending; `nil` on encode/option errors), `path: string` (`$` root, `$["people"][2]["name"]`; syntax errors report `$`).

```titan
local json = import "json"

local record NullToken
end

local function parse_port_or_nil(text: string): integer?
  local cfg: {string: value} = json.decode(text, nil, json.DecodeOption.max_depth(8))
  local port?: integer = cfg["port"]
  return port
catch
  if not (error is json.Error) then raise end
  local err: json.Error = error
  if err.code == "" or err.path == "" then raise "missing diagnostics" end
  return nil
end

function main(args: {string}): integer
  -- Lossless dynamic nulls via a dedicated record sentinel
  local tok = NullToken()
  local arr: {value} = json.decode("[1,null,null]", nil, json.DecodeOption.null_value(tok))
  if #arr ~= 3 or arr[3] ~= tok then return 1 end
  if json.encode(arr, json.EncodeOption.null_value(tok)) ~= "[1,null,null]" then return 2 end

  local port? = parse_port_or_nil('{"port":8080}')
  if port ~= 8080 then return 3 end
  if parse_port_or_nil('{"port":8080,}') ~= nil then return 4 end
  return 0
end
```

## Typed record, union, and container schemas

- **Descriptor order:** `reflect.Type.is_array(constness, elem)` takes `ArrayTypeConstness` (`is_mutable()`, `is_const()`, `is_maybe_const()`) **before** `elem`; `reflect.Type.is_map(key, val)` takes key then value. Decoded mutable Arrays use `{value}` writer storage with strict typed reads.
- **Unions & `tag_field`:** Matching `EncodeOption.tag_field` / `DecodeOption.tag_field` apply to all nested unions in a call. If `tag_field` collides with a declared part name of the active variant, encode and decode raise `invalid_union`. Decode accepts union keys in any order; missing nil-admitting parts become `nil`. Without a union schema, `{"tag":...}` decodes as a plain Map.
- **Recursive schemas:** Resolve lazily through `reflect.NamedType("mod.Type")`. Qualified names must include the actual module name (e.g. `"json_model.Message"` when the file is `json_model.titan`).

```titan
-- file: json_model.titan
local json = import "json"
local reflect = import "reflect"

record Person
  const name: string
  const note: string?
end

union Event
  joined(Person)
  count(integer)
  ping(x: integer, y: integer)
  idle()
end

function main(args: {string}): integer
  local original = Event.joined(Person("Ada", nil))
  local text = json.encode(original, json.EncodeOption.tag_field("kind"))
  if text ~= '{"kind":"joined","value":{"name":"Ada","note":null}}' then return 1 end

  local event_schema = reflect.Type.is_named(reflect.NamedType("json_model.Event"))
  local restored: Event = json.decode(text, event_schema, json.DecodeOption.tag_field("kind"))
  case restored
  when joined(who) then
    if who.name ~= "Ada" or who.note ~= nil then return 2 end
  else
    return 3
  end

  local const_ints = reflect.Type.is_array(
    reflect.ArrayTypeConstness.is_const(), reflect.Type.is_integer())
  local nums: const {integer} = json.decode("[1, 2e2, 3.0]", const_ints)
  if #nums ~= 3 or nums[2] ~= 200 or nums[3] ~= 3 then return 4 end
  return 0
end
```

## Pre-delivery verification checklist

- [ ] Options without a schema pass explicit `nil` (`json.decode(text, nil, opt)`), and callers catch `json.Error` (re-raising non-`json.Error` with bare `raise`) instead of testing `== nil`.
- [ ] Dynamic callers preserving trailing Array nulls or `null` Map values use one shared `NullToken` record on both `DecodeOption.null_value` and `EncodeOption.null_value`.
- [ ] Nominal schema strings use exact `"<module>.<Type>"` for already-initialized modules, and records with `local` fields provide a compatible public `new`.
- [ ] Union calls use matching `tag_field` options with no payload-part name collisions, and never expect `ignore_unknown_fields` to ignore extra union keys.
- [ ] Deep sibling workloads set explicit `max_depth` and, where needed, raise `peg.set_max_stack` without assuming `json` alters the PEG stack.
