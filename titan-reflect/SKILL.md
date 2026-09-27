---
name: titan-reflect
description: Inspect Titan and Lua values, query nominal schemas, resolve named type descriptors, and access public record or Interface fields with titan.reflect. Use for runtime reflection, erased generic descriptors, reflected callables, and reflection-library maintenance.
---

# Titan reflect

Read `titan-programmer` first. Add `titan-tester` for reflection tests and
`titan-ffi` when touching raw entry pointers, C descriptors, or the library's
native implementation. Ordinary reflection uses the typed API directly:

```titan
local reflect = import "reflect"

function read_public_field(candidate: value, name: string): value
  local inspected = reflect.inspect(candidate)
  case inspected
  when is_record(record_value) then
    for i = 1, record_value.n_fields do
      if record_value.type.fields[i].name == name then
        return record_value:get(i)
      end
    end
  when is_interface(interface_value) then
    for i = 1, interface_value.n_fields do
      if interface_value.type.fields[i].name == name then
        return interface_value:get(i)
      end
    end
  end
  raise "public field not found: " .. name
end
```

The authoritative sources are the
[public contract](../../../doc/language/standard-library-reflect.md),
[implementation chapter](../../../doc/implementation/standard-library-reflect.md),
[module](../../../titan/reflect.titan), and
[native tests](../../../spec/stdlib/titan/reflect/tests.titan).

## Runtime values and field access

`inspect(v: value): Value` classifies 19 runtime kinds. Use `case` to unpack
the result. Integer and float variants preserve the actual Lua tag; an
integral float is still `is_float`. A written `v is integer` test has broader
conversion semantics and is unsuitable for implementing this classification.

Container variants carry the original container in their named `value` part, using
`{value}`, `const {value}`, or `{value: value}`. Inspection does not recover
erased element arguments or clone the container. `ArrayTypeConstness` spells
its variants `is_mutable`, `is_const`, and `is_maybe_const`. Build structural
schemas directly with `Type.is_array(constness, element)` or
`Type.is_map(key, value)`. Their case arms bind named parts `is_const` and
`elem_descriptor`, or `key_descriptor` and `value_descriptor`; there are no
ArrayValue/MapValue or ArrayType/MapType wrapper records.

`RecordValue:get(i)` and `set(i, v)` use **1-based public descriptor ordinals**,
matching the inspected wrapper's `.type.fields[i]`; `n_fields` counts public fields. The separate
`FieldType.index` is a 0-based logical field index and can have gaps from local
fields. Do not pass it to these methods. Both bounds are checked, const writes
raise, and mutable writes use the declared field's normal Lua-boundary
conversion. For example, integer fields accept integral floats but reject
fractional ones. Failed conversion leaves the field unchanged.

`InterfaceValue:get(i)` reads a captured const field. `.value` is the Interface
wrapper used as its method receiver; `.wrapped` is the concrete record or
union, useful for a separate `inspect`. There is no Interface setter.

`UnionValue.tag` is a 0-based runtime tag. `n_parts` includes nil parts;
`get(i)` boxes the 1-based part and checks `1..n_parts`. An empty variant has
zero parts, while a nullable single part containing nil has one. Public
`VariantType.parts` contains ordered `VariantPartType` records with `name`
and `type`; unnamed source payloads have name `value`. Public descriptors
omit private variants. Public tags form a dense zero-based range before all
private tags, even when local declarations are interleaved in source. Match
`VariantType.tag` and account for a private active tag outside the public range;
record field index gaps do not imply union tag gaps. Inspection still exposes a
private active variant's tag, arity, and readable parts without publishing its
private schema.

## Nominal lookup and generic erasure

The public lookup API is `find_nominal(name: string): NominalType?`. Match its
`is_record`, `is_union`, or `is_interface` variant. There are no
`record_descriptor`, `union_descriptor`, or `interface_descriptor` functions.
Lookup does not import a module; an unregistered name returns nil. Preserve
that optional result with an explicit `NominalType?` local or `local result?`.

`NamedType:resolve()` looks up the named nominal and returns the corresponding
`Type` variant, falling back to `Type.is_value()` for an unknown name.
`Type:resolve()` delegates for `is_named` and `is_foreign_named` receivers;
every other descriptor is returned unchanged. Neither operation recursively
expands a whole schema.

Descriptors expose the shared erased runtime schema. Distinct specializations
such as `Box<|integer|>` and `Box<|string|>` share the base nominal name.
Unconstrained parameters hydrate to `Type.is_value()`. Interface-constrained
parameters hydrate to `Type.is_named` for the **outer constraint Interface**;
generic arguments are erased, and the caller explicitly invokes `:resolve()`
to obtain its `is_interface` descriptor. Do not add eager constraint expansion,
specialization registries, or cyclic descriptor shells to this contract.

Array, Map, and callable structure around erased parameters remains visible.
Option hydration preserves eligible bases, collapses nested Options, and
collapses an unconstrained `T?` to `is_value`, which already includes nil.
`FunctionType` has fixed `param_descriptors`/`return_descriptors` and
optional `vararg_descriptor`/`flexret_descriptor`; absent tails are nil. Zero
fixed results with no flexible tail means zero results, not one nil result.

## C declaration references

`Type` has 26 variants. Recursive C metadata uses `is_foreign_named`, whose
`ForeignNamedType.name` is the compiler's qualified declaration key. Its
`:resolve()` returns one retained struct, union, or typedef descriptor; it
does not eagerly traverse pointers or typedefs. The reference retains its own
hydration's declaration table across later inspection and GC. An unknown key
raises `unknown foreign type <name>`; it does not use Titan nominal lookup's
`is_value` fallback. Keep this C serializer mechanism separate from generic
erasure and explicit Interface-constraint resolution.

## Reflected callables and C addresses

`MethodType.callable(receiver, ...)` takes the corresponding inspected `.value`
first; its fixed parameter metadata describes the declared arguments without
that receiver. Static callables take ordinary arguments, and a variant's
callable constructs that variant. These calls retain ordinary dynamic callable
checks and argument/result adjustment. Public record/union methods and statics
are sorted by name; Interface methods retain declaration order.

Titan, Lua, and Lua C function variants carry a callable `value` part of type
`function (...: value): (...: value)`. Select parts with named case binders,
for example `when is_titan_function{callable = value, signature = type}`.
The `type` part requires an alias because it is a reserved word.
`lua_entry` and `entry` are typed `foreign function (*lua_State): int`
pointers; `native_entry` is a `foreign *void` address without a callable
Titan signature. Raw invocation belongs at an audited FFI/Lua boundary.

Owned C variants retain their owner in `value` and expose a borrowed `payload`
address plus byte `size`; counted Arrays also expose `count`. Keep the owner
reachable while using the pointer. `is_raw_pointer` establishes no pointee
type, address validity, or lifetime. Pure foreign scalar/pointer/Array/function
and typedef schemas likewise use named Type parts, while resolver owners,
shared nominal/callable/owned schemas, and recursive C aggregate descriptors
remain records. Consult the public inventory for exact part names.

## Maintaining and testing the implementation

Nominal metatable type tags preserve the declared generic metadata for
hydration; accessors continue to use erased runtime types. Callable identity
tags, provider export metadata, and shared nominal identity retain their
existing representations. Do not erase the nominal schema before hydration,
which owns the public erasure rules above.

Record and Interface field access uses generated typed accessors cached with a
traced declaring-module owner in private `FieldType` fields. The metatable
publishes that owner under `TITAN_MT_MOD`. Keep access direct; do not recreate
name lookup or inspect `__index` closure upvalues for the owner. Reads require
normal compiler boxing; writes require the existing dynamic conversion plan
and GC barrier. A union's `TITAN_MT_PAYLOAD` reader accepts a positive 1-based part index and
boxes that actual variant's part, including private variants. Index 0 queries
the tag and -1 the arity; never infer either from uservalue slots/counts.
Generated accessors own the native-payload/dense-UV mapping. Native wide C
numbers may fail checked boxing only when observed; rejected writes preserve
old state. Aggregate/array reads expose borrowed lightuserdata pointers, whose
nominal owner must remain live; this does not add general aggregate boxing.

Public behavior belongs in the native `spec/stdlib/titan/reflect/` suite;
generated-C, metadata-publication, and boundary-plan assertions belong in
compiler Busted tests. Cover private record-field index gaps, dense public-first
union tags and private active variants, const/bounds/type rejection,
unchanged state after a rejected write, explicit named resolution, erased
generic signatures, and callable results. To prove a write barrier, store a
fresh collectable value through a helper that returns before collection and
exercise minor GC against an aged receiver. An independently rooted constant
string followed by a full collection does not establish that property.
