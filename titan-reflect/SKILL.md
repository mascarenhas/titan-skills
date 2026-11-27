---
name: titan-reflect
description: Use when inspecting Titan/Lua runtime values, querying nominal schemas, or accessing fields via titan.reflect. Covers Value/Type unions, erased generic descriptors, public_constructor, native projections/construct, and reflected callables; use titan-programmer for plain is/as checks, titan-json/titan-protobuf for serialization.
---

# Titan Reflection (`titan.reflect`)

Synchronous runtime inspection, initialized nominal schema lookup, public field access, native projections, and dynamic construction (native & browser complete). Import `local reflect = import "reflect"` (Lua: `require "titan.reflect"`).
Pair with `skill://titan-programmer` (use plain `is`/`as` for known static types). Peers: `skill://titan-json`, `skill://titan-protobuf`, `skill://titan-ffi` (raw entry pointers / C lifetimes), `skill://titan-tester`.

## Non-negotiable invariants

1. **Exact runtime tags (`inspect`), not dynamic `is`:** `reflect.inspect(v: value): Value` classifies 19 exact Lua tags (`3` -> `is_integer`, `3.0` -> `is_float`; unlike `v is integer`, which accepts `3.0`). `Value` describes runtime instances; `Type` describes static schemas.
2. **1-based public ordinals, never `FieldType.index`:** `RecordValue:get(i)`/`set(i, v)`/`project(i)` and `InterfaceValue:get(i)` index `1..n_fields` matching `.type.fields[i]`. `FieldType.index` is a 0-based logical index with gaps from `local` fields—never pass it to `get`/`set`/`project`. `set` rejects `const` fields, applies Lua-boundary conversion, runs GC barriers, and leaves old state intact on error. Interfaces have no setter (`.value` = Interface receiver, `.wrapped` = concrete owner).
3. **Dense public-first union tags & private active arms:** `UnionValue.tag` is 0-based; public variants occupy dense `0..#variants - 1` ahead of all `local` variants (even if interleaved in source). Match `VariantType.tag`. An active `local` arm has no entry in `.type.variants`, though `tag`, `n_parts` (counting `nil` parts), and `get(1..n_parts)` remain observable.
4. **Initialized modules only; no `Type` equality contract:** `find_nominal(fqtn): NominalType?` queries initialized modules only (never imports; misses return `nil` uncached; bind `local found? = ...`). `NamedType:resolve()` returns `is_record`/`is_union`/`is_interface` or falls back to `Type.is_value()` on miss (strict codecs must call `find_nominal`). `ForeignNamedType:resolve()` resolves one step or raises `unknown foreign type <name>`. `Type:resolve()` resolves one step only. Never compare `Type` with `==` or use as Map keys—always `case`.
5. **Erased generic descriptors:** `Box<|integer|>` and `Box<|string|>` share nominal name `mod.Box`. Unconstrained `T` erases to `Type.is_value()` (`T?` collapses to `is_value()`); constrained `T: I` appears as `Type.is_named` for outer `I` (call `:resolve()` for `is_interface`). Structural container/callable shapes survive (`{T}` -> Array of `is_value`). `is_array`/`is_const_array`/`is_map` return the original container directly as `{value}`/`const {value}`/`{value: value}` without copying or recovering element types.
6. **`public_constructor()` vs. direct `construct`:** `RecordType:public_constructor(): StaticFunctionType?` finds public static `new` without calling it, returning a descriptor only for fixed params, no flexret, and 1 result of that record (params need not match fields). `RecordType:construct(fields)` / `UnionType:construct(tag, parts)` allocate directly **without** calling `new` (initializing `const` fields; rejecting records with `local` fields or private tags). Check **both** `is_public` and `all_public` (a `local` record can have `all_public == true`).
7. **Reflected callables & owned C rooting:** Alias reserved `type` in `case` (`when is_titan_function{signature = type}`). `MethodType.callable(receiver, ...)` takes `.value` first (`param_names`/`param_descriptors` omit receiver). Record/union `methods`/`statics` are name-sorted; Interface `methods` keep declaration order. Root the original `value` (not the variadic `callable` part) for long-lived callbacks. Keep owned C `.value` rooted while using `.payload`; `is_raw_pointer` has no pointee type/lifetime.

## `Value` and `Type` quick map

| Surface | Variants / shapes | Key rules |
| --- | --- | --- |
| `Value` scalars & containers | `is_nil`, `is_integer`, `is_float`, `is_boolean`, `is_string`, `is_array`, `is_const_array`, `is_map` | Any Lua table -> `is_map`; containers keep original identity. |
| `Value` nominals | `is_record(RecordValue)`, `is_union(UnionValue)`, `is_interface(InterfaceValue)` | Typed `get`/`set`/`project`; `local` members hidden from descriptors. |
| `Value` callables & opaque | `is_titan_function`, `is_lua_function`, `is_lua_c_function`, `is_owned_foreign_pointer`, `is_owned_foreign_array`, `is_lua_userdata`, `is_lua_thread`, `is_raw_pointer` | Function `value` is `function(...: value): (...: value)`; raw `lua_entry`/`entry`/`native_entry` require FFI discipline. |
| `Type` builders | `is_array(ArrayTypeConstness, elem)`, `is_map(k, v)`, `is_option(base)`, `is_named(NamedType(fqtn))`, `is_function(FunctionType)` | `ArrayTypeConstness`: `is_mutable()`, `is_const()`, `is_maybe_const()`. Empty `return_descriptors` + `nil` `flexret_descriptor` = 0 results. |
| `Type` C descriptors | `is_foreign_{void,named,integer,float,pointer,array,struct,union,typedef}`, `is_owned_foreign_{pointer,array}` | Recursive C types break cycles via `is_foreign_named(ForeignNamedType)` (retains hydration table). |

## Field access, native projections, and direct construction

- **Native `project(i)` & `construct`:** `project(i)` uses 1-based ordinals and losslessly projects C storage: C ints -> 64-bit `integer` bits (u64 `> INT64_MAX` -> negative `integer`), `float`/`double` -> `float`, `long double` -> `%La` hex (`strtold` back), pointers -> raw lightuserdata (no traversal), complete C structs & fixed arrays -> recursive `const {value}` (named bitfields in order, no padding). C unions, FAMs, and `>64`-bit ints raise only when projected/constructed. Trailing `nil`s may be omitted in `construct`.
- **Variant parts:** `VariantType.parts` holds `VariantPartType(name, type)`; a single unnamed payload has `name == "value"`.

```titan
-- file: reflect_demo.titan
local reflect = import "reflect"

record Account
  local secret: integer
  const owner: string
  balance: integer
end

function Account.new(owner: string, balance: integer): Account
  return { secret = 99, owner = owner, balance = balance }
end

record Point
  const x: integer
  const y: integer
end

function add_one(n: integer): integer return n + 1 end

function main(args: {string}): integer
  local acc = Account("Ada", 10)
  case reflect.inspect(acc)
  when is_record(rec) then
    -- Public ordinal 1 ("owner") has 0-based FieldType.index == 1 (after local secret at 0)
    if rec.n_fields ~= 2 or rec.type.all_public then return 1 end
    if rec.type.fields[1].name ~= "owner" or rec.type.fields[1].index ~= 1 then return 2 end
    rec:set(2, 25.0) -- Lua-boundary conversion: integral float -> integer
    if acc.balance ~= 25 then return 3 end
    local ctor? = rec.type:public_constructor()
    if ctor == nil or #ctor.param_names ~= 2 then return 4 end
  else return 5 end

  local found? = reflect.find_nominal("reflect_demo.Point")
  if found == nil then return 6 end
  case found
  when is_record(pt_desc) then
    if not (pt_desc.is_public and pt_desc.all_public) then return 7 end
    local built: Point = pt_desc:construct({ 3, 4 })
    if built.x ~= 3 or built.y ~= 4 then return 8 end
  else return 9 end

  case reflect.inspect(add_one)
  when is_titan_function { signature = type } then
    if #signature.param_descriptors ~= 1 then return 10 end
  else return 11 end
  return 0
end
```

## Pre-delivery verification checklist

- [ ] `RecordValue:get`/`set`/`project` and `InterfaceValue:get` take 1-based public ordinals (`1..n_fields`), never 0-based `FieldType.index`.
- [ ] `find_nominal` preserves `nil` (`local found?`); `Type` values are inspected with `case` (never `==` or Map keys).
- [ ] Direct `construct` checks both `is_public` and `all_public`; records with `local` fields use `public_constructor()`.
- [ ] Function `case` arms alias `type` (`{signature = type}`), and long-lived callable roots retain original `value`.
- [ ] Union inspection matches `VariantType.tag` and handles active `local` tags outside `variants`.
