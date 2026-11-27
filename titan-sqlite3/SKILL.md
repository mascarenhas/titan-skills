---
name: titan-sqlite3
description: Use when querying SQLite databases, running SQL statements, transactions, or row mapping in Titan. Covers titan.sqlite3 async connections, :memory:/file DBs, prepared statements, Blob binding, cursors, Row:fill, transactions, and Connection handoff; pair with titan-programmer and titan-async, use titan-stdlib for fs files and titan-json for JSON.
---

# Titan SQLite (`titan.sqlite3`)

Embedded SQLite 3.53.4 (`SQLITE_THREADSAFE=1`, `SQLITE_OPEN_FULLMUTEX`, private inside `titan.so`/`titan.a`). Import as `local sqlite3 = import "sqlite3"` (Lua: `require "titan.sqlite3"`). Pair with `skill://titan-programmer` (`.titan` rules, `const`-field factories), `skill://titan-async` (Tasks, cancellation, Runtime), and `skill://titan-thread` (`TransferValue`, cross-state handoff).

## Non-negotiable invariants

1. **Native-only & active async Task required:** Absent on `--target browser`. DB ops and `:close()` run on libuv's worker pool via `async.run_foreign` inside an async Task (`main` runs in one automatically; Lua callers must schedule/drive the Runtime). Only `Row:get`, `Row:fill`, `to_transfer_payload`, and `from_transfer_payload` are synchronous.
2. **One in-flight op per `Connection`; active `Cursor` locks execution:** Overlapping calls on one `Connection` raise `sqlite3.Error` before submission; separate connections run concurrently. While a `Cursor` is active, new `execute`/`query` and transaction changes raise, and its `Statement` cannot close until the `Cursor` ends/closes (preparing other statements, closing idle ones, and `get_autocommit()` stay allowed when idle).
3. **LIFO `defer :close()` (`Cursor` -> `Statement` -> `Connection`):** `close()` is idempotent and completes during cancellation unwind. Closing a `Connection` with open statements **raises** and leaves it usable. Ordinary GC performs **no** DB I/O; Lua-state close synchronously finalizes statements/cursors, rolls back open transactions, waits for any in-flight worker, and closes connections.
4. **Exact positional binding & `Blob` vs UTF-8 `string`:** `execute`/`query` require SQLite's exact parameter count (trailing `nil`s count via `#...`; repeated named placeholders share a slot; `?5` needs 5 args); mismatch raises before mutating bindings. `string` must be valid UTF-8 with no NUL (`TEXT`); wrap binary/NUL bytes in `sqlite3.Blob(bytes)` (`Blob("")` != `NULL`). `NaN`, infinities, and other composites are rejected.
5. **`execute` vs `query` & owned `Row` snapshots:** `execute(...)` requires `SQLITE_DONE` and raises on `SQLITE_ROW`—use `query` for `SELECT` or `RETURNING` (`RETURNING` may already have modified rows before `execute` raises). `Row` is a copied snapshot outliving `Cursor`/`Statement`/`Connection`; `#row.columns` is exact column count (dense `const {Column}`—trailing `NULL`s never shorten it; `row:get(i)` returns `nil` for `NULL`).
6. **Typed factories for `const` records vs mutable `Row:fill`:** `Row:fill(target)` uses reflection (`skill://titan-reflect`) on an existing **mutable** record matching unique column names 1-to-1 with public fields (`local` fields ignored; `const` rejected; `boolean` accepts integer `0`/`1` only; failed conversion can leave earlier fields mutated). Use a typed factory (`Note(row:get(1), row:get(2))`) for `const` fields, duplicate columns, validation, or atomic construction.
7. **Manual-handoff `Connection` transfer (no `discard_transfer_payload`):** Detach rejects closed/busy connections, active cursors, or **any** open statement (even idle), moving `:memory:`, open transactions, and savepoints intact. Adopt each payload **exactly once** and adopt-and-close locally on failed delivery (replaying double-closes/UAFs; abandoning leaks). Statements/cursors are non-transferable.

## Binding, storage-class, and transaction tables

| Titan arg | SQLite binding | `Row:get(i)` | `Row:fill` target field |
| --- | --- | --- | --- |
| `nil` | `NULL` | `nil` | Nil-admitting (`nil`, `value`, `T?`) |
| `boolean` | `INTEGER` `0`/`1` | `integer` | `boolean`/`boolean?` (`0`/`1` only) |
| `integer` | 64-bit `INTEGER` | `integer` | Dynamic (`integer` or `float`) |
| finite `float` | `REAL` (keeps tag) | `float` | Dynamic (`float`, exact integral `integer`) |
| UTF-8 `string` (no NUL) | `TEXT` | copied `string` | `string`/`string?` (`cell is string`) |
| `sqlite3.Blob(bytes)` | `BLOB` (explicit len) | `sqlite3.Blob` | `Blob`/`Blob?` (`cell is Blob`) |

*`Column` (`const name: string`, `const declared_type: string?`) keeps duplicates and `nil` `declared_type` for expressions (never alters conversion). All-`NULL` rows are non-nil `Row`s.*

| Transaction call | In autocommit | In active transaction |
| --- | --- | --- |
| `db:set_autocommit(false)` | `BEGIN DEFERRED` | no-op |
| `db:set_autocommit(true)` | no-op | `COMMIT` (failed `COMMIT` may leave tx active) |
| `db:commit()` / `db:rollback()` | no-op | `COMMIT` / `ROLLBACK` -> autocommit |

*`db:get_autocommit()` queries SQLite live (sees SQL `BEGIN`/`COMMIT`/`ROLLBACK` and auto-rollbacks). Close cursors before tx changes; use SQL `SAVEPOINT`/`RELEASE` for nesting.*

## Connections, statements, cursors, errors, and cancellation

- **`connect`/`prepare`:** `connect(name)` opens R/W creating missing files (`":memory:"` private in-memory, `""` temp DB, no NUL). `prepare(sql)` compiles **one** SQL statement (trailing whitespace/comments/empty `;` OK; empty/NUL/multi-statement rejected). Every `execute`/`query` resets/clears prior bindings first; finalizing a `Statement` closes it even on delayed SQLite errors.
- **`execute`/`query`/`Cursor`:** `Statement:execute(...: value): integer` returns `sqlite3_changes64` from latest `INSERT`/`UPDATE`/`DELETE` (`CREATE TABLE`/empty `SELECT` do not reset it). `Statement:query(...: value): Cursor` runs step 1, captures `Cursor.columns` (`const {Column}`), and buffers row 1. Stream via `for row in cursor:fetch do ... end`: exhaustion returns `nil` and releases execution (subsequent fetches return `nil`; fetching an explicitly closed cursor raises). Failed fetch closes cursor and retires execution; early `cursor:close()` resets without rolling back tx.
- **Errors & cancellation:** Raise `sqlite3.Error` (`const message: string`, `const code: integer?`, `const extended_code: integer?`, `const operation: string`; wrapper validation leaves codes `nil`; cleanup errors append details while keeping primary error; busy/locked never auto-retry). Pending cancel prevents new work; already-accepted ops finish before cancellation delivers (a write/`COMMIT` may have succeeded). Cancel keeps its async reason; worker submission failure raises `async.OperationError`.

```titan
local io = import "io"
local sqlite3 = import "sqlite3"

record Note
  const id: integer
  const body: string
  const raw: sqlite3.Blob?
end

record DraftRow
  id: integer
  active: boolean
  tag: string?
end

local function note_from_row(row: sqlite3.Row): Note
  local raw?: sqlite3.Blob = row:get(3)
  return Note(row:get(1), row:get(2), raw)
end

local function insert_batch(db: sqlite3.Connection)
  local ins = db:prepare("INSERT INTO notes(body, active, raw) VALUES (?, ?, ?) RETURNING id")
  defer ins:close()
  db:set_autocommit(false)
  do
    local cur = ins:query("alpha", true, sqlite3.Blob("\0\1\2"))
    defer cur:close()
    local _: integer = cur:fetch():get(1)
  end
  do
    local cur = ins:query("beta", false, nil)
    defer cur:close()
    local _? = cur:fetch()
  end
  db:commit()
catch
  if not db:get_autocommit() then db:rollback() end
  raise
end

function main(args: {string}): integer
  local db = sqlite3.connect(":memory:")
  defer db:close()
  local ddl = db:prepare("CREATE TABLE notes(id INTEGER PRIMARY KEY, body TEXT, active INTEGER, raw BLOB)")
  defer ddl:close()
  ddl:execute()

  insert_batch(db)

  local sel = db:prepare("SELECT id, body, raw FROM notes ORDER BY id")
  defer sel:close()
  local cur = sel:query()
  defer cur:close()
  local notes: {Note} = {}
  for row in cur:fetch do notes[#notes + 1] = note_from_row(row) end
  cur:close()

  local q2 = db:prepare("SELECT id, active, NULL AS tag FROM notes WHERE id = ?")
  defer q2:close()
  local c2 = q2:query(1)
  defer c2:close()
  local draft = DraftRow(0, false, nil)
  c2:fetch():fill(draft)
  io.print(#notes, notes[1].body, #notes[1].raw.bytes, draft.active)
  return 0
end
```

## Transferring connections between states

`Connection` implements `:to_transfer_payload(): string` and `.from_transfer_payload(payload: string): Connection` for `transfer.TransferValue.from_value(db)` (alias `async.TransferValue`) and transferred closures (`skill://titan-thread`). Both hooks are synchronous (later work uses the receiving state's worker pool). Close every cursor and statement before detaching; detached source aliases behave as closed (`close()` is a no-op). Follow shared manual-handoff rules (`skill://titan-thread`): avoid lossy `async.Receiver` without an adoption protocol, and recover failed delivery via `Connection.from_transfer_payload(payload)` (or `policy:to_value()`) + `:close()`.

```titan
local io = import "io"
local sqlite3 = import "sqlite3"
local transfer = import "transfer"

function main(args: {string}): integer
  local src = sqlite3.connect(":memory:")
  defer src:close()
  do local s = src:prepare("CREATE TABLE kv(k TEXT)"); defer s:close(); s:execute() end
  src:set_autocommit(false)
  do local s = src:prepare("INSERT INTO kv VALUES (?)"); defer s:close(); s:execute("ok") end

  local dst: sqlite3.Connection = transfer.TransferValue.from_value(src):to_value()
  defer dst:close()
  dst:commit()
  local q = dst:prepare("SELECT k FROM kv"); defer q:close()
  local cur = q:query(); defer cur:close()
  local val: string = cur:fetch():get(1)
  io.print(val)
  return 0
end
```

## Pre-delivery verification checklist

- [ ] Every `Connection`, `Statement`, and `Cursor` uses LIFO `defer :close()`; cursors close before tx changes and all statements close before `db:close()` or transfer.
- [ ] `SELECT`/`RETURNING` use `query`, never `execute`; binary/non-UTF-8/NUL bytes wrap in `sqlite3.Blob(bytes)`.
- [ ] `const`-field records use typed factories (`row:get(i)`, `#row.columns`); `Row:fill` targets mutable records with unique 1-to-1 public fields only.
- [ ] Explicit transactions roll back on `catch` (`if not db:get_autocommit() then db:rollback() end; raise`).
- [ ] Transferred `Connection` payloads adopt once with explicit failed-delivery adopt-and-close recovery; code runs natively (never `--target browser`).
