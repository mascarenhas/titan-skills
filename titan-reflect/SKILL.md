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
  when is_record: record_value then
    for i = 1, record_value.n_fields do
      if record_value.descriptor.fields[i].name == name then
        return record_value:get(i)
      end
    end
  when is_interface: interface_value then
    for i = 1, interface_value.n_fields do
      if interface_value.descriptor.fields[i].name == name then
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

Container wrappers expose the original container through `.val`, using
`{value}`, `const {value}`, or `{value: value}`. Inspection does not recover
erased element arguments or clone the container. `ArrayTypeConstness` spells
its variants `is_mutable`, `is_const`, and `is_maybe_const`.

`RecordValue:get(i)` and `set(i, v)` use **1-based public descriptor ordinals**,
matching `descriptor.fields[i]`; `n_fields` counts public fields. The separate
`FieldType.index` is a 0-based storage index and can have gaps from local
fields. Do not pass it to these methods. Both bounds are checked, const writes
raise, and mutable writes use the declared field's normal Lua-boundary
conversion. For example, integer fields accept integral floats but reject
fractional ones. Failed conversion leaves the field unchanged.

`InterfaceValue:get(i)` reads a captured const field. `.val` is the Interface
wrapper used as its method receiver; `.wrapped` is the concrete record or
union, useful for a separate `inspect`. There is no Interface setter.

`UnionValue.tag` is a 0-based runtime tag and `.payload` is the correctly boxed
payload, or nil for an empty variant. Public descriptor Arrays omit private
variants but retain original tags: search `VariantType.tag`, not
`variants[tag + 1]`. Inspection still exposes a private active variant's tag
and payload; it does not expose its private descriptor.

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
such as `Box<integer>` and `Box<string>` share the base nominal name.
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

`MethodType.callable(receiver, ...)` takes the corresponding inspected `.val`
first; its fixed parameter metadata describes the declared arguments without
that receiver. Static callables take ordinary arguments, and a variant's
callable constructs that variant. These calls retain ordinary dynamic callable
checks and argument/result adjustment. Public record/union methods and statics
are sorted by name; Interface methods retain declaration order.

Titan, Lua, and Lua C function wrappers all retain callable `.val` fields of
type `(...: value) -> (...: value)`. Use `.val` for ordinary invocation.
`TitanFunctionValue.lua_entry` and `LuaCFunctionValue.entry` are typed
`foreign (*lua_State) -> int` pointers; `native_entry` is a `*void` address
without a callable Titan signature. Raw entry invocation belongs at an audited
FFI/Lua boundary, not in ordinary introspection examples.

Owned C wrappers retain their owner in `.val` and expose a borrowed `payload`
address plus byte `size`; counted Arrays also expose `count`. The raw pointer
alone neither roots the owner nor owns an external resource. `is_raw_pointer`
does not establish a pointee type, address validity, or lifetime.

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
and GC barrier. A union's `TITAN_MT_PAYLOAD` reader similarly boxes its actual
variant payload, including private variants.

Public behavior belongs in the native `spec/stdlib/titan/reflect/` suite;
generated-C, metadata-publication, and boundary-plan assertions belong in
compiler Busted tests. Cover private gaps, const/bounds/type rejection,
unchanged state after a rejected write, explicit named resolution, erased
generic signatures, and callable results. To prove a write barrier, store a
fresh collectable value through a helper that returns before collection and
exercise minor GC against an aged receiver. An independently rooted constant
string followed by a full collection does not establish that property.
