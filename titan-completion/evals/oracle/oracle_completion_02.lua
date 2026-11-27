-- Independent Stage-B oracle for completion-02-closed-world-descriptors-analysis.
local driver = require("titan-compiler.driver")
local completion = require("titan-compiler.completion")
local types = require("titan-compiler.types")

local function fail(msg)
  io.stderr:write("FAIL: " .. tostring(msg) .. "\n")
  os.exit(1)
end

local function check(cond, msg)
  if not cond then fail(msg) end
end

local cwi = dofile("./closed_world_index.lua")
check(type(cwi) == "table", "closed_world_index.lua must return a module table")
for _, fn in ipairs({
  "assert_compiler_versions",
  "capture_saved_source",
  "capture_archive_catalog",
  "query_closed_world",
  "probe_closed_world_rejection",
  "inspect_analysis_only_generics",
}) do
  check(type(cwi[fn]) == "function", "missing exported function: " .. fn)
end

-- 1. Compiler version guard (LANGUAGE_SERVER_API_VERSION == 1 + rejection of mismatch).
do
  local vers = cwi.assert_compiler_versions()
  check(type(vers) == "table", "assert_compiler_versions must return a table")
  check(vers.ls_api == 1, "expected ls_api == 1")
  check(vers.completion == 1 and vers.transform == 1, "expected completion/transform == 1")
  check(type(vers.project_cache) == "number" and vers.project_cache >= 1, "expected integer project_cache version")
  check(type(vers.header_cache) == "number" and vers.header_cache >= 1, "expected integer header_cache version")

  local orig_api = driver.LANGUAGE_SERVER_API_VERSION
  driver.LANGUAGE_SERVER_API_VERSION = 999
  local ok_mismatch = pcall(cwi.assert_compiler_versions)
  driver.LANGUAGE_SERVER_API_VERSION = orig_api
  check(not ok_mismatch, "assert_compiler_versions must reject mismatched driver.LANGUAGE_SERVER_API_VERSION")
end

-- 2. Saved detached descriptor publication via projectcache + completion.describe (body-free, scalar facts + docs).
local provider_src = [[
--- Provider utilities.
-- @module prov_mod

--- Secret generic box.
local record Hidden<|T|>
  item: T
end

--- Hidden helper.
local function secret_fn(): integer
  return 7
end

--- Public counter.
record Meter
  const label: string
  count: integer
end
]]

local saved_prov
do
  local sentinel_imp, sentinel_reg = { _s = 1 }, { _s = 2 }
  driver.imported, types.registry = sentinel_imp, sentinel_reg
  saved_prov = cwi.capture_saved_source("prov_mod", "/nonexistent_disk/prov_mod.titan", provider_src)
  check(driver.imported == sentinel_imp and types.registry == sentinel_reg,
    "capture_saved_source must restore driver.imported and types.registry")

  check(type(saved_prov) == "table" and type(saved_prov.payload) == "string", "missing encoded payload")
  check(type(saved_prov.entry) == "table" and saved_prov.entry.ast == nil,
    "decoded compact entry must be body-free (ast == nil)")
  check(type(saved_prov.facts) == "table" and saved_prov.facts.version == completion.VERSION,
    "completion.describe must return version == completion.VERSION")
  check(type(saved_prov.facts.documentation) == "table"
        and saved_prov.facts.documentation.summary:find("Provider utilities", 1, true) ~= nil,
    "completion.describe must retain detached module documentation")

  local fact_by_name = {}
  for _, row in ipairs(saved_prov.facts.candidates) do
    fact_by_name[row.name] = row
    for k, v in pairs(row) do
      if k == "documentation" then
        check(type(v) == "table", "documentation must be detached table")
      else
        check(type(v) ~= "table", "described candidate field " .. k .. " must be scalar")
      end
    end
  end
  check(fact_by_name.secret_fn ~= nil and fact_by_name.Hidden ~= nil and fact_by_name.item ~= nil and fact_by_name.Meter ~= nil,
    "completion.describe must materialize both private and exported members")
end

-- 3. Build a real multi-module static archive pkg.a (pkg.api + pkg.sibling) in /tmp,
--    capture driver.completion_binary_catalog after importing ONLY pkg.api, then DELETE pkg.a!
local tmp_root = "/tmp/ew6_comp02_archive_" .. tostring(math.random(100000, 999999))
os.execute("rm -rf " .. tmp_root .. " && mkdir -p " .. tmp_root .. "/src/pkg " .. tmp_root .. "/build")

local function write_file(path, text)
  local f = assert(io.open(path, "wb"))
  f:write(text)
  f:close()
end

write_file(tmp_root .. "/src/pkg/api.titan", "function ping(): integer return 1 end\n")
write_file(tmp_root .. "/src/pkg/sibling.titan", "--- Unimported sibling answer.\nfunction answer(): integer return 42 end\n")

local ok_build = os.execute(
  "titanc -q --tree " .. tmp_root .. "/src -o " .. tmp_root .. "/build pkg.api pkg.sibling"
)
check(ok_build == true or ok_build == 0, "failed to compile real pkg.a archive for completion-02")

local archive_cap
do
  local prev_bin_path = driver.TITAN_BIN_PATH
  local sentinel_imp, sentinel_reg = { _s = 3 }, { _s = 4 }
  driver.imported, types.registry = sentinel_imp, sentinel_reg

  archive_cap = cwi.capture_archive_catalog(tmp_root .. "/build", "pkg.api")

  check(driver.TITAN_BIN_PATH == prev_bin_path, "capture_archive_catalog must restore driver.TITAN_BIN_PATH")
  check(driver.imported == sentinel_imp and types.registry == sentinel_reg,
    "capture_archive_catalog must restore driver.imported and types.registry")
  check(type(archive_cap) == "table" and type(archive_cap.catalog) == "table", "missing catalog")
  check(archive_cap.imported_keys == nil or archive_cap.imported_keys["pkg.sibling"] == nil,
    "unimported static archive sibling must NOT be imported into driver.imported")
  check(archive_cap.catalog["pkg.api"] ~= nil and archive_cap.catalog["pkg.api"].kind == "static",
    "catalog must contain pkg.api with kind='static'")
  check(archive_cap.catalog["pkg.sibling"] ~= nil and archive_cap.catalog["pkg.sibling"].kind == "static",
    "catalog must capture unimported static-archive sibling pkg.sibling")
end

-- DELETE the archive and source tree completely before closed-world queries!
os.execute("rm -rf " .. tmp_root)

-- 4. Detached closed-world completion against BOTH detached source entry AND deleted static-archive sibling,
--    with disk-blocking I/O adapter and transient_caches=true!
do
  local consumer_src_1 = 'local p = import "prov_mod.titan"\nfunction f(x: p.Hidden<|integer|>) x. end'
  local caret_1 = assert(consumer_src_1:find("x.", 1, true)) + 1 -- 0-based byte right after "x."

  local sentinel_imp, sentinel_reg = { _s = 5 }, { _s = 6 }
  driver.imported, types.registry = sentinel_imp, sentinel_reg

  local q1 = cwi.query_closed_world({
    modname = "consumer1",
    filename = "./consumer1.titan",
    source = consumer_src_1,
    caret = caret_1,
    cached_source_entries = { prov_mod = saved_prov.entry },
    cached_binary_interfaces = archive_cap.catalog,
  })
  check(driver.imported == sentinel_imp and types.registry == sentinel_reg,
    "query_closed_world must restore driver.imported and types.registry")
  check(q1.ok == true, "closed-world source-import query failed: " .. tostring(q1.error_message))
  check(q1.by_name.item ~= nil and q1.by_name.item.detail == "integer",
    "closed-world completion must specialize p.Hidden<|integer|>.item from detached descriptor without disk reads")
  check(q1.transient_probe_cache_disabled == true,
    "transient_caches=true must disable persistent native probe cache directory")

  -- Complete unimported sibling from deleted pkg.a using cached_binary_interfaces!
  local consumer_src_2 = 'local sib = import "pkg.sibling"\nfunction g() local v = sib. end'
  local caret_2 = assert(consumer_src_2:find("sib.", 1, true)) + 3

  local q2 = cwi.query_closed_world({
    modname = "consumer2",
    filename = "./consumer2.titan",
    source = consumer_src_2,
    caret = caret_2,
    cached_source_entries = { prov_mod = saved_prov.entry },
    cached_binary_interfaces = archive_cap.catalog,
  })
  check(q2.ok == true, "closed-world static sibling query failed: " .. tostring(q2.error_message))
  check(q2.by_name.answer ~= nil and q2.by_name.answer.detail == "function (): integer",
    "closed-world completion must resolve deleted archive sibling pkg.sibling.answer")

  -- Reject source-capability escalation on captured binary AND reject missing modules!
  local ok_esc, err_esc = cwi.probe_closed_world_rejection(
    { cached_binary_interfaces = archive_cap.catalog },
    "pkg.sibling",
    { kind = "source-import" }
  )
  check(ok_esc == false and err_esc:find("absent from completion catalog", 1, true) ~= nil,
    "source-import escalation on captured binary must fail closed: " .. tostring(err_esc))

  local ok_miss, err_miss = cwi.probe_closed_world_rejection(
    { cached_binary_interfaces = archive_cap.catalog },
    "totally.missing",
    nil
  )
  check(ok_miss == false and err_miss:find("absent from completion catalog", 1, true) ~= nil,
    "uncaptured module must fail closed without disk reads: " .. tostring(err_miss))
end

-- 5. analysis_only=true preserves applied generic types on checked AST calls and case bindings without erasure!
do
  local gen_src = [[
record Box<|T|>
  item: T
end
union Maybe<|T|>
  none()
  some(T)
end
function id<|T|>(x: T): T
  return x
end
function demo(m: Maybe<|integer|>): integer
  local b = Box<|integer|>.new(42)
  local v = id<|integer|>(b.item)
  case m
  when some(n) then return n + v
  when none() then return v
  end
end
]]
  local sentinel_imp, sentinel_reg = { _s = 7 }, { _s = 8 }
  driver.imported, types.registry = sentinel_imp, sentinel_reg

  local info = cwi.inspect_analysis_only_generics("gen_demo", "./gen_demo.titan", gen_src)

  check(driver.imported == sentinel_imp and types.registry == sentinel_reg,
    "inspect_analysis_only_generics must restore driver.imported and types.registry")
  check(info.is_analysis_only == true, "checked AST must carry _analysis_only == true")
  check(info.record_typeparams and info.record_typeparams.Box == 1,
    "analysis_only AST must retain written record typeparams (not erased to 0)")

  local saw_box_ctor, saw_id_call = false, false
  for _, c in ipairs(info.call_types or {}) do
    if c.call_type == "gen_demo.Box<|integer|>"
       and c.callee_type == "function (integer): gen_demo.Box<|integer|>" then
      saw_box_ctor = true
    end
    if c.call_type == "integer" and c.callee_type == "function (integer): integer" then
      saw_id_call = true
    end
  end
  check(saw_box_ctor, "analysis_only AST must preserve applied generic constructor type gen_demo.Box<|integer|>")
  check(saw_id_call, "analysis_only AST must preserve applied generic call callee_type function (integer): integer (not value)")

  local saw_case_int = false
  for _, bt in ipairs(info.case_binding_types or {}) do
    if bt == "integer" then saw_case_int = true end
  end
  check(saw_case_int, "analysis_only AST must preserve concrete case payload binding type 'integer' (not erased 'value')")
end

print("oracle_completion_02 PASS")
