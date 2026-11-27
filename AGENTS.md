# Titan Skills Maintainer & Authoring Guide

Rules for agents and contributors authoring, updating, or reviewing skills in `titan-skills`. Ground every technical claim in the pinned Titan release's `doc/language/`, `doc/implementation/`, and `doc/style-guide.md`.

## 1. Topology & Hard Size Caps

This repository maintains **17 skills** and **5 `references/*.md` files**. Every file must stay strictly within its hard line and byte cap (enforced by `scripts/check_skills.lua`; shorter is better—never pad):

| Skill | `SKILL.md` Cap (L / B) | `references/*.md` Cap (L / B) |
| --- | --- | --- |
| `titan-programmer` | `<= 420 L` / `<= 20,000 B` | — |
| `titan-stdlib` | `<= 400 L` / `<= 19,000 B` | — |
| `titan-ffi` | `<= 420 L` / `<= 20,000 B` | `runtime-lua-c-api.md` (`<= 220 L` / `11,000 B`), `browser-wasm-c-imports.md` (`<= 180 L` / `9,000 B`) |
| `titan-async` | `<= 400 L` / `<= 19,000 B` | `uv-and-native-adapters.md` (`<= 260 L` / `13,000 B`) |
| `titan-networking` | `<= 390 L` / `<= 18,500 B` | `http-and-tls-details.md` (`<= 180 L` / `9,000 B`) |
| `titan-tester` | `<= 330 L` / `<= 16,000 B` | `titan-repo-suites.md` (`<= 220 L` / `11,000 B`) |
| `titan-pegs` | `<= 330 L` / `<= 16,000 B` | — |
| `titan-thread` | `<= 290 L` / `<= 14,000 B` | — |
| `titan-application` | `<= 310 L` / `<= 15,000 B` | — |
| `titan-package` | `<= 270 L` / `<= 13,000 B` | — |
| `titan-protobuf` | `<= 250 L` / `<= 12,000 B` | — |
| `titan-sqlite3` | `<= 230 L` / `<= 11,000 B` | — |
| `titan-json` | `<= 250 L` / `<= 12,000 B` | — |
| `titan-language-server` | `<= 220 L` / `<= 10,500 B` | — |
| `titan-websocket` | `<= 210 L` / `<= 10,000 B` | — |
| `titan-reflect` | `<= 190 L` / `<= 9,000 B` | — |
| `titan-completion` | `<= 90 L` / `<= 4,500 B` | — |

## 2. Frontmatter & Two-Clause Prompt-Blind Descriptions

Frontmatter contains **only** `name` (exact directory name) and `description` (`160–380` chars; hard spec ceiling `<= 1024`):
- **Clause 1 (`<= 110` chars — survives cold catalog truncation):** Imperative trigger (`Use when ...` / `Load before ...`) + concrete user-intent nouns and cues (`.titan`, SQLite/SQL, Proto3, C headers/Canvas/DOM, TCP/TLS/HTTP, PEG/DSL).
- **Clause 2 (implicit intents + explicit negative boundary):** Cover phrasings that omit Titan module names, ending with an explicit exclusion (`use titan-X for Y / skip Z`) to prevent over-invocation.

## 3. Structure, Salience & Compression Rules

- **Single H1 (`# <Title>`):** Follow with a 2–3 line scope + peer-skill routing DAG using `skill://<name>` (never relative `../../../doc/...` links outside `titan-skills`; cite Titan manual paths in inline code).
- **Page-1 upfront salience (`Lines 1–80`):** Place `## Non-negotiable invariants` (5–8 high-signal traps) and every conditional `MUST read skill://<name>/references/<file>.md when ...` trigger in the first 80 lines.
- **Subtract filler, keep exact semantics:** Omit general CS/Lua basics and verbatim API signature dumps. If using a concept anchor, keep it to `<= 6` words paired immediately with exact Titan syntax and boundary rules. Prefer compact Lua->Titan delta or decision tables over prose; never include multi-line invalid Lua blocks.
- **Single-owner deduplication:** Replace cross-domain rules owned by another skill with a 1-line `skill://<name>` pointer.
- **Code fences:** Every ```` ```titan ```` block must compile cleanly (`titanc`), using `-- file: <path>` markers for multi-file examples and companion ```` ```c ```` / ```` ```javascript ```` fixtures where needed. Use ```` ```text ```` for signature fragments or invalid examples.
- **Pre-delivery checklist:** End each `SKILL.md` with 4–6 concrete verification checkboxes.
- **No embedded evals:** Never include `## Evaluation` headings or tracked `EVALUATION.md` run logs inside skills.

## 4. Non-Negotiable Core Idioms (Issue #61)

Keep these five invariants front-loaded and consistent across skills:
1. **Private state on exported records:** Store internal/native handles in `local` fields on exported `record`s with a public factory or custom `Record.new(...)`; never invent Titan-side `RawX` + `{integer: X}` ID registries (genuine external C/OS/wire descriptors remain valid).
2. **Default `record` fields to `const`:** Declare `const f: T` / `local const f: T` by default; mutate only when needed.
3. **Explicit `defer :close()` + sync `gc.finalizable` fallback:** Pair resource acquisition immediately with LIFO `defer obj:close()`. Register non-capturing, synchronous, idempotent `gc.finalizable` **only** on genuine external handles (never GC-owned memory, never async `fs.File:close()` or yielding calls inside `__gc`).
4. **Exact `#arr` and hole-safe reads:** Append with `arr[#arr + 1] = val` (no shadow `count`), read hole-prone slots with `local x? = arr[i]`, and never use `{integer: T}` as an Array.
5. **Thin primitive-only C FFI & browser `bindings.js` boundaries:** Keep both native C shims and browser JS `bindings.js` strictly to raw library primitives and host bridge mechanics (marshalling, pinning, handle/listener lifecycle, raw event forwarding); keep application rendering, scene/UI composition, styling, state machines, and event policy in `.titan`.

## 5. Prompt-Blind Evaluations

Store structured eval suites in `<skill-name>/evals/evals.json` (with starter inputs under `<skill-name>/evals/files/` and harnesses under `<skill-name>/evals/oracle/`):
- Prompts and `evals/files/**` fixtures must never leak `skill://`, canonical skill names (`titan-*`), or unprompted `import "titan.<mod>"` scaffolds; keep zero symlinks and zero PEM keys/certs under `<skill>/evals/`.
- Keep `assertions[].check` and `judge_rubric` blind to arm names (`skill://`, `baseline`, `candidate`, `skill-descriptions.db`), with `assertions[].critical` strictly in `{"standard", "issue61_idiom"}`.
- Run evals in isolated clean workspaces mounting **only** `SKILL.md` and `references/` (excluding `evals/`, `README.md`, `AGENTS.md`, `titan/AGENTS.md`, and ambient skills/memory).

## 6. Mandatory Mechanical Gate

Before finishing any edit, run:

```sh
"$PREFIX/bin/lua" scripts/check_skills.lua --prefix "$PREFIX" --evals [skill...]
```

The gate checks YAML frontmatter, `name == dir`, description lengths (`160–380`, Clause 1 `<= 110`), hard line/byte caps for all 17 `SKILL.md` + 5 `references/*.md` files, `H1 == 1`, zero `## Evaluation` headings, `skill://` and relative Markdown links, target-aware multi-file ```` ```titan ```` compile+run verification, `--evals` suite schema/symlink/PEM/zero-leak/blind-judge hygiene, and `git diff --check`. When adding or renaming a skill, update `README.md`, `AGENTS.md`, `scripts/check_skills.lua`, and (when pinning in `titan`) `titan/AGENTS.md` together.
