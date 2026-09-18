---
name: titan-completion
description: Change or review Titan compiler completion contexts, detached completion descriptors, or their language-server integration. Use for caret transforms, scope/member enumeration, isolated source analysis and captured dependency catalogs; not for ordinary Titan application code.
---

# Titan compiler completion

Read [the completion API](../../../doc/implementation/completion.md) for exact
entry points and scalar contracts, and the
[driver analysis API](../../../doc/implementation/driver.md#language-server-compiler-api)
when changing descriptor or resolver ownership. Keep the prerelease
`LANGUAGE_SERVER_API_VERSION` at 1; change descriptor/transform versions when
persisted facts or source mapping changes.

Use the ordinary lexer/parser and narrow checker observation points. Preserve
`.` and `:` when replacing the complete active name with a dummy. Identify the
hole by its request filename and transformed span; spelling alone is not an
identity. Keep editor text untouched and map edits using the captured unsaved
buffer. Multiword foreign primitives have one replacement leaf. Imports use the
parser's canonical module names and the host's eligible captured catalog.

Obtain lexical visibility while the symbol table's real scopes and initializer
frontier are alive. Resolve complete receiver chains before enumerating members.
Reuse owner specialization, direct source-private access, constrained/interface
views and final C macro-field precedence. A shadowed `ffi` is an ordinary value;
the foreign type namespace remains independent. Never reconstruct these rules
from hover strings, occurrences or the identifier to the left of a separator.
Respect foreign-function visibility in lexical and module-member contexts. For
C enums, use the exact target integer evaluator or an existing ordinary-checker
validation marker; never trust host-Lua numeric values or issue native probes
per candidate. Omit unproven values and retain partial quality.

Private preparation owns fresh entries, a declared registry, an I/O provider and
transient graph/probe writes. It uses `completion_closed_world` with captured
source and binary descriptors, and `transient_caches` for native probes. Retain
the shared compiler permit because driver/type registries and parser state are
process-local. Missing descriptors give an incomplete result; they do not
justify reading a newer dependency or waiting for workspace hydration.

`analysis_only` must reach the checker: return source-level checked terms with
applied generic types, without runtime erasure. Keep declaration freezing,
interface validation, detached owner snapshots and completion finalization in
both modes. Ordinary compilation still lowers for the coder; analysis ASTs are
not code-generation input. Test the actual constructor/call expression type,
not only a declared module signature that survives erasure.

Saved indexing alone publishes compact descriptors and scalar saved facts.
Capture all modules from finalized selected static providers, including
unimported siblings, while preserving embedded and actual selection precedence.
Do not treat every inspected provider-cache entry as a selected archive or
populate ordinary imports merely to capture their descriptors.
Source-private capability requires a real compact source entry and ordered FFI
header plan, not the equality-only source manifest. Completion SELECTs consume
already materialized scalar rows; preparation owns parsing/checking/decoding.
Neither path promotes an unsaved result on save.

Keep regressions in `spec/checker/completion_spec.lua` for transforms and checker
facts, and in existing driver/projectcache suites for general cache/resolver
contracts. Exercise empty/mid-token holes, standalone references, scope ordering,
source visibility, generic specialization, C aggregates/macros and detached
preparation with disk dependency reads rejected. Run the normal compiler
regressions too: completion options must leave ordinary checking unchanged.
