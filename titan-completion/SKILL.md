---
name: titan-completion
description: Use ONLY when editing compiler Lua completion.lua, checker/completion.lua, or detached completion descriptors. Covers caret transforms, checker observation points, analysis_only, completion_closed_world catalogs, and C enum bounds; NEVER load to run/query titan-language-server (use titan-language-server instead) or for .titan app code.
---

# Titan Compiler Completion Internals

Compiler-Lua implementation only (`titan-compiler/completion.lua`, `checker/completion.lua`, `driver.lua`); **do NOT load `skill://titan-language-server` for pure compiler-Lua completion tasks**. Read `doc/implementation/{completion,documentation-comments}.md` and `doc/implementation/driver.md#language-server-compiler-api`. Never load for LSP queries or `.titan` app code.

## Non-negotiable invariants

1. **Versions & neutrality:** Keep `driver.LANGUAGE_SERVER_API_VERSION = 1` prerelease; bump `completion.VERSION` (`1`), `TRANSFORM_VERSION` (`1`), `projectcache.VERSION`, or `cdriver.HEADER_CACHE_VERSION` when persisted schemas change. Reuse the ordinary lexer/parser/checker with a marked dummy name—never add syntax or alter ordinary checking.
2. **Caret transforms (`prepare`/`original_byte`/`dependencies`):** Take 0-based UTF-8 byte boundary (`nil, reason` on UTF-8 splits, comments, unrelated strings). Replace active name keeping `.`/`:`, receiver chains, and args; identify hole by request filename + transformed span (never spelling). Multiword C primitives are one leaf after `foreign`/`owned`/`foreign type Name =`, and in `foreign function` also after `:`/`as` (respecting keywords as member/arg names). Imports (`kind = "import"`) leave source unchanged for host catalog ranking; map edits via captured UTF-16 indices.
3. **Checker observation (`checker/completion.lua`):** Capture `lexical`/`type`/`dot`/`colon`/`foreign` at `completion_lexical`, `completion_qualified_type`, `completion_members`, `completion_foreign`, and `completion_finish` while scopes and initializer frontier are live—before dummy lookup failure and `M.member` rewrite. Resolve receiver chains; reuse owner specialization, `.titan` source-private visibility, interface views, dot/colon splits, and C macro-field precedence (`ffi` shadowing never hides C types). Never reconstruct from hover text, occurrences, or text left of `.`/`:`.
4. **C enum values:** Prove target-`int` enumerators via target integer evaluator or existing checker validation (`HEADER_CACHE_VERSION` stores expressions + ordinals). Never trust host-Lua values or run per-candidate probes; omit unproven entries (`quality = "partial"`).
5. **`analysis_only` & closed-world prep:** `analysis_only = true` reaches checker so ASTs keep applied generics and `case` bindings without erasure while freezing decls/interfaces/detached owners and running `completion_finish` (never feed analysis ASTs to codegen). Private prep combines `analysis_only`, `completion_closed_world`, `source_overrides`, `cached_source_entries`, `cached_binary_interfaces` (`embedded`/`dynamic`/`static`), `transient_caches = true`, and private I/O/cache adapter under the compiler permit—restoring `driver.imported`/`types.registry` only for same target owner. Missing descriptors return incomplete, never disk reads/hydration.
6. **Saved descriptors & SQL boundary:** Saved indexing alone publishes `completion.describe(entry)` (scalar facts + detached `documentation`) and `driver.completion_binary_catalog(context)` (all modules of finalized selected static archives + finalized contextual binary owner views under `analysis_only` without competing views; never unselected archives or manufactured imports). Source-private capability needs compact entry + `.ffi.h` plan, not `source_manifest`. SQL `SELECT`s read materialized scalar rows without calling `completion.lua`, decoding, walking ASTs, or taking the permit; never promote unsaved results on save.

## Verification checklist

- [ ] Update `spec/checker/completion_spec.lua`, `spec/documentation_spec.lua`, and driver/projectcache suites.
- [ ] Test empty/mid-token holes, standalone refs, scope order, `.titan` visibility, generic specialization, C aggregates/macros/multiword primitives/enums, and detached prep rejecting disk reads.
- [ ] Assert checked call/constructor applied generic types under `analysis_only`, not just declared signatures.
- [ ] Run normal compiler regressions to prove ordinary checking and codegen stay unchanged.
