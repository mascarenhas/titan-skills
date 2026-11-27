#!/usr/bin/env lua
-- Mechanical gate for titan-skills (frontmatter, line/byte caps, H1/Evaluation
-- hygiene, skill:// and relative Markdown links, target-aware multi-file
-- ```titan compile+run verification, and git diff --check).
--
-- Usage:
--   lua scripts/check_skills.lua [--prefix <SDK>] [--skip-compile] [--repo <DIR>] [--keep-tmp] [skill...]

local CANONICAL_SKILLS = {
  { name = "titan-programmer",      max_lines = 420, max_bytes = 20000, refs = {} },
  { name = "titan-stdlib",          max_lines = 400, max_bytes = 19000, refs = {} },
  { name = "titan-ffi",             max_lines = 420, max_bytes = 20000, refs = {
      ["runtime-lua-c-api.md"]      = { max_lines = 220, max_bytes = 11000 },
      ["browser-wasm-c-imports.md"] = { max_lines = 180, max_bytes =  9000 },
    } },
  { name = "titan-async",           max_lines = 400, max_bytes = 19000, refs = {
      ["uv-and-native-adapters.md"] = { max_lines = 260, max_bytes = 13000 },
    } },
  { name = "titan-networking",      max_lines = 390, max_bytes = 18500, refs = {
      ["http-and-tls-details.md"]   = { max_lines = 180, max_bytes =  9000 },
    } },
  { name = "titan-tester",          max_lines = 330, max_bytes = 16000, refs = {
      ["titan-repo-suites.md"]      = { max_lines = 220, max_bytes = 11000 },
    } },
  { name = "titan-pegs",            max_lines = 330, max_bytes = 16000, refs = {} },
  { name = "titan-thread",          max_lines = 290, max_bytes = 14000, refs = {} },
  { name = "titan-application",     max_lines = 310, max_bytes = 15000, refs = {} },
  { name = "titan-package",         max_lines = 270, max_bytes = 13000, refs = {} },
  { name = "titan-protobuf",        max_lines = 250, max_bytes = 12000, refs = {} },
  { name = "titan-sqlite3",         max_lines = 230, max_bytes = 11000, refs = {} },
  { name = "titan-json",            max_lines = 250, max_bytes = 12000, refs = {} },
  { name = "titan-language-server", max_lines = 220, max_bytes = 10500, refs = {} },
  { name = "titan-websocket",       max_lines = 210, max_bytes = 10000, refs = {} },
  { name = "titan-reflect",         max_lines = 190, max_bytes =  9000, refs = {} },
  { name = "titan-completion",      max_lines =  90, max_bytes =  4500, refs = {} },
}

local SKILL_BY_NAME = {}
for _, spec in ipairs(CANONICAL_SKILLS) do
  SKILL_BY_NAME[spec.name] = spec
end

local STDLIB_MODULES = {}
for _, m in ipairs({
  "async", "browser", "coroutine", "fs", "gc", "http", "io", "iteration",
  "json", "lua", "math", "net", "os", "path", "peg", "protobuf", "reflect",
  "sqlite3", "ssl", "string", "test", "thread", "timer", "transfer", "url",
  "uv", "websocket",
}) do
  STDLIB_MODULES[m] = true
end

local DESC_MIN_CHARS = 160
local DESC_MAX_CHARS = 380
local CLAUSE1_MAX_CHARS = 110

local function sh_quote(s)
  return "'" .. s:gsub("'", "'\\''") .. "'"
end

local function read_file(path)
  local f, err = io.open(path, "rb")
  if not f then return nil, err end
  local data = f:read("a")
  f:close()
  return data
end

local function write_file(path, data)
  local f, err = io.open(path, "wb")
  if not f then return nil, err end
  f:write(data)
  f:close()
  return true
end

local function file_exists(path)
  local f = io.open(path, "rb")
  if f then f:close(); return true end
  return false
end

local function run_capture(cmd)
  local tmp_out = os.tmpname()
  local ok, why, code = os.execute(cmd .. " >" .. sh_quote(tmp_out) .. " 2>&1")
  local out = read_file(tmp_out) or ""
  os.remove(tmp_out)
  local exit_code
  if type(ok) == "number" then
    exit_code = ok
  elseif ok == true then
    exit_code = 0
  elseif why == "exit" then
    exit_code = code or 1
  else
    exit_code = 128 + (code or 1)
  end
  return exit_code == 0, exit_code, out
end

local function split_lines(text)
  local norm = text:gsub("\r\n", "\n")
  local lines = {}
  local pos = 1
  local len = #norm
  while pos <= len do
    local nl = norm:find("\n", pos, true)
    if nl then
      lines[#lines + 1] = norm:sub(pos, nl - 1)
      pos = nl + 1
    else
      lines[#lines + 1] = norm:sub(pos)
      break
    end
  end
  return lines
end

local function count_lines(text)
  local norm = text:gsub("\r\n", "\n")
  local n = 0
  for _ in norm:gmatch("\n") do n = n + 1 end
  if #norm > 0 and norm:sub(-1) ~= "\n" then n = n + 1 end
  return n
end

local function dirname(path)
  local d = path:match("^(.*)/[^/]+$")
  return d or "."
end

local function normalize_path(path)
  local is_abs = path:sub(1, 1) == "/"
  local parts = {}
  for comp in path:gmatch("[^/]+") do
    if comp == "." or comp == "" then
      -- skip
    elseif comp == ".." then
      if #parts > 0 and parts[#parts] ~= ".." then
        parts[#parts] = nil
      elseif not is_abs then
        parts[#parts + 1] = ".."
      end
    else
      parts[#parts + 1] = comp
    end
  end
  local joined = table.concat(parts, "/")
  if is_abs then return "/" .. joined end
  return joined == "" and "." or joined
end

local function join_path(a, b)
  if b:sub(1, 1) == "/" then return normalize_path(b) end
  if a == "." or a == "" then return normalize_path(b) end
  return normalize_path(a .. "/" .. b)
end

local function list_dir(dir)
  local ok, _, out = run_capture("ls -1A " .. sh_quote(dir))
  if not ok then return nil end
  local entries = {}
  for line in out:gmatch("[^\r\n]+") do
    entries[#entries + 1] = line
  end
  table.sort(entries)
  return entries
end

local function is_dir(path)
  local ok = run_capture("test -d " .. sh_quote(path))
  return ok
end

local function mkdir_p(path)
  local ok, _, out = run_capture("mkdir -p " .. sh_quote(path))
  if not ok then error("mkdir -p failed for " .. path .. ": " .. out) end
end

local function mktemp_dir()
  local ok, _, out = run_capture("mktemp -d /tmp/check_skills_XXXXXX")
  if not ok then error("mktemp -d failed: " .. out) end
  return (out:gsub("%s+$", ""))
end

local function rm_rf(path)
  if path and path:match("^/tmp/check_skills_") then
    run_capture("rm -rf " .. sh_quote(path))
  end
end

-- Parse YAML frontmatter (expects only top-level `name` and `description`).
local function parse_frontmatter(lines)
  if lines[1] ~= "---" then
    return nil, "missing opening '---' YAML frontmatter on line 1"
  end
  local close_line
  for i = 2, #lines do
    if lines[i] == "---" then
      close_line = i
      break
    end
  end
  if not close_line then
    return nil, "unterminated YAML frontmatter (missing closing '---')"
  end
  local fields = {}
  local order = {}
  local i = 2
  while i < close_line do
    local line = lines[i]
    if line:match("^%s*$") or line:match("^%s*#") then
      i = i + 1
    else
      local key, rest = line:match("^([%w_%-]+):%s*(.*)$")
      if not key then
        return nil, string.format("malformed frontmatter line %d: %s", i, line)
      end
      if fields[key] ~= nil then
        return nil, string.format("duplicate frontmatter key '%s' on line %d", key, i)
      end
      local val
      if rest == ">" or rest == "|-" or rest == ">-" or rest == "|" then
        local chunks = {}
        i = i + 1
        while i < close_line and (lines[i]:match("^%s+") or lines[i]:match("^%s*$")) do
          chunks[#chunks + 1] = (lines[i]:gsub("^%s+", ""))
          i = i + 1
        end
        val = table.concat(chunks, rest:sub(1, 1) == ">" and " " or "\n"):gsub("%s+$", "")
      else
        val = rest:gsub("%s+$", "")
        if (#val >= 2) and ((val:sub(1, 1) == '"' and val:sub(-1) == '"') or
                            (val:sub(1, 1) == "'" and val:sub(-1) == "'")) then
          val = val:sub(2, -2)
        end
        i = i + 1
      end
      fields[key] = val
      order[#order + 1] = key
    end
  end
  return { fields = fields, order = order, end_line = close_line }
end

local function extract_clause1(desc)
  -- Sentence 1 ends at the first period followed by whitespace (avoiding
  -- dotted tokens like `.titan`, `titan.sqlite3`, `v0.6.2`).
  local s = desc:match("^(.-%.)%s+")
  if s then return s end
  return desc
end

-- GitHub-style heading anchor slugifier.
local function slugify_heading(text)
  local s = text:gsub("`", ""):gsub("%*%*", ""):gsub("%*", ""):gsub("_", "_")
  s = s:gsub("%[([^%]]+)%]%([^%)]+%)", "%1")
  s = s:lower()
  s = s:gsub("[^%w%s%-_]", "")
  s = s:gsub("%s+", "-")
  s = s:gsub("^%-+", ""):gsub("%-+$", "")
  return s
end

-- Parse markdown structure: headings, anchors, fenced blocks, non-code lines.
local function parse_markdown(text, start_line)
  local lines = split_lines(text)
  local headings = {}
  local anchors = {}
  local anchor_counts = {}
  local blocks = {}
  local prose_lines = {} -- { line_no, text } outside fenced code blocks

  local in_fence = false
  local fence_char, fence_len, fence_lang, fence_start, fence_body
  local section_id = 0

  for i = (start_line or 1), #lines do
    local line = lines[i]
    if not in_fence then
      local f_ticks, info = line:match("^%s*(```+)%s*(.-)%s*$")
      if f_ticks then
        in_fence = true
        fence_char = "`"
        fence_len = #f_ticks
        fence_lang = (info:match("^(%S+)") or ""):lower()
        fence_start = i
        fence_body = {}
      else
        local f_tildes, info2 = line:match("^%s*(~~~+)%s*(.-)%s*$")
        if f_tildes then
          in_fence = true
          fence_char = "~"
          fence_len = #f_tildes
          fence_lang = (info2:match("^(%S+)") or ""):lower()
          fence_start = i
          fence_body = {}
        else
          prose_lines[#prose_lines + 1] = { line = i, text = line }
          local hashes, title = line:match("^(#+)%s+(.-)%s*$")
          if hashes then
            local level = #hashes
            title = title:gsub("%s+#+%s*$", "")
            if level <= 2 then section_id = section_id + 1 end
            local base = slugify_heading(title)
            local count = anchor_counts[base] or 0
            anchor_counts[base] = count + 1
            local slug = count == 0 and base or (base .. "-" .. count)
            anchors[slug] = true
            headings[#headings + 1] = { line = i, level = level, title = title, slug = slug }
          end
        end
      end
    else
      local close_pat = fence_char == "`" and "^%s*(```+)%s*$" or "^%s*(~~~+)%s*$"
      local closing = line:match(close_pat)
      if closing and #closing >= fence_len then
        blocks[#blocks + 1] = {
          index = #blocks + 1,
          line = fence_start,
          end_line = i,
          lang = fence_lang,
          section_id = section_id,
          body = table.concat(fence_body, "\n") .. (#fence_body > 0 and "\n" or ""),
        }
        in_fence = false
      else
        fence_body[#fence_body + 1] = line
      end
    end
  end
  return {
    lines = lines,
    headings = headings,
    anchors = anchors,
    blocks = blocks,
    prose_lines = prose_lines,
    unclosed_fence = in_fence and fence_start or nil,
  }
end

local anchor_cache = {}
local function get_file_anchors(abs_path)
  if anchor_cache[abs_path] then return anchor_cache[abs_path] end
  local data = read_file(abs_path)
  if not data then return nil end
  local parsed = parse_markdown(data, 1)
  anchor_cache[abs_path] = parsed.anchors
  return parsed.anchors
end

-- Strip inline backtick spans so relative link regex ignores code examples.
local function strip_inline_code(line)
  local out = {}
  local i = 1
  local len = #line
  while i <= len do
    local s, e = line:find("`+", i)
    if not s then
      out[#out + 1] = line:sub(i)
      break
    end
    out[#out + 1] = line:sub(i, s - 1)
    local ticks = line:sub(s, e)
    local cs, ce = line:find(ticks, e + 1, true)
    if cs then
      i = ce + 1
    else
      out[#out + 1] = line:sub(s)
      break
    end
  end
  return table.concat(out)
end

local function check_links(repo_dir, rel_file, parsed, is_full_run, add_err)
  local link_count = 0
  local file_dir = dirname(rel_file)

  for _, entry in ipairs(parsed.prose_lines) do
    local lno = entry.line
    local line = entry.text

    -- 1. Check all `skill://...` references (both plain and in inline backticks).
    for raw in line:gmatch("skill://([^%s%)%]`'\">,;:]+)") do
      -- Strip any trailing punctuation that might cling to a bare URI.
      local uri = raw:gsub("[%.,;:!%?]+$", "")
      -- Ignore template placeholders such as `skill://<name>/...` or `skill://titan-X`.
      if not uri:find("<", 1, true) and not uri:find("*", 1, true)
         and not uri:match("^titan%-X") then
        link_count = link_count + 1
        local path_part, anchor = uri:match("^([^#]+)#(.+)$")
        if not path_part then path_part = uri end
        local skill_name, subpath = path_part:match("^([^/]+)/(.+)$")
        if not skill_name then skill_name = path_part end
        local spec = SKILL_BY_NAME[skill_name]
        if not spec then
          add_err(string.format("%s:%d: unknown skill:// target '%s'", rel_file, lno, skill_name))
        else
          local target_rel = subpath and (skill_name .. "/" .. subpath) or (skill_name .. "/SKILL.md")
          local target_abs = join_path(repo_dir, target_rel)
          if subpath then
            if not file_exists(target_abs) then
              -- Allow referencing canonical sibling references when they aren't
              -- yet written only if not doing a full repo run and subpath is
              -- declared in CANONICAL_SKILLS.
              local ref_name = subpath:match("^references/(.+)$")
              if not (not is_full_run and ref_name and spec.refs[ref_name]) then
                add_err(string.format("%s:%d: broken skill:// path 'skill://%s' (missing %s)",
                  rel_file, lno, uri, target_rel))
              end
            elseif anchor then
              local target_anchors = get_file_anchors(target_abs)
              if target_anchors and not target_anchors[anchor:lower()] then
                add_err(string.format("%s:%d: broken skill:// anchor '#%s' in %s",
                  rel_file, lno, anchor, target_rel))
              end
            end
          else
            if is_full_run and not file_exists(target_abs) then
              add_err(string.format("%s:%d: missing target skill file %s", rel_file, lno, target_rel))
            elseif anchor and file_exists(target_abs) then
              local target_anchors = get_file_anchors(target_abs)
              if target_anchors and not target_anchors[anchor:lower()] then
                add_err(string.format("%s:%d: broken skill:// anchor '#%s' in %s",
                  rel_file, lno, anchor, target_rel))
              end
            end
          end
        end
      end
    end

    -- 2. Check relative Markdown links `[text](target)` outside inline code.
    local plain = strip_inline_code(line)
    for target in plain:gmatch("%[[^%]]*%]%(([^%)%s]+)[^%)]*%)") do
      if not target:match("^https?://") and not target:match("^mailto:")
         and not target:match("^skill://") then
        link_count = link_count + 1
        if target:sub(1, 1) == "#" then
          local anchor = target:sub(2):lower()
          if not parsed.anchors[anchor] then
            add_err(string.format("%s:%d: broken local anchor '%s'", rel_file, lno, target))
          end
        else
          local rel_target, anchor = target:match("^([^#]+)#(.+)$")
          if not rel_target then rel_target = target end
          local resolved_rel = join_path(file_dir, rel_target)
          if resolved_rel:sub(1, 2) == ".." or resolved_rel:sub(1, 1) == "/" then
            add_err(string.format("%s:%d: relative link escapes repo root: '%s'", rel_file, lno, target))
          else
            local resolved_abs = join_path(repo_dir, resolved_rel)
            if not file_exists(resolved_abs) and not is_dir(resolved_abs) then
              add_err(string.format("%s:%d: broken relative link '%s' (-> %s)",
                rel_file, lno, target, resolved_rel))
            elseif anchor and file_exists(resolved_abs) then
              local target_anchors = get_file_anchors(resolved_abs)
              if target_anchors and not target_anchors[anchor:lower()] then
                add_err(string.format("%s:%d: broken anchor '#%s' in link '%s'",
                  rel_file, lno, anchor, target))
              end
            end
          end
        end
      end
    end
  end

  return link_count
end

local function check_whitespace_and_conflicts(rel_file, lines, add_err)
  for i, line in ipairs(lines) do
    if line:match("[ \t]+$") then
      add_err(string.format("%s:%d: trailing whitespace", rel_file, i))
    end
    if line:match("^<<<<<<< ") or line:match("^>>>>>>> ") then
      add_err(string.format("%s:%d: conflict marker", rel_file, i))
    end
  end
end

-- Extract companion fixture filename from line 1 of a c/js/mjs block.
local function detect_companion_file(block)
  local first = block.body:match("^([^\n]*)") or ""
  if block.lang == "c" or block.lang == "h" then
    local p = first:match("^/%*%s*file:%s*([%w%._/%-]+)%s*%*/")
           or first:match("^/%*%s*([%w%._/%-]+%.[ch])%s*%*/")
           or first:match("^//%s*file:%s*([%w%._/%-]+)")
           or first:match("^//%s*([%w%._/%-]+%.[ch])")
    if p then return p, block.body end
  elseif block.lang == "javascript" or block.lang == "js" or block.lang == "mjs" then
    local p = first:match("^//%s*file:%s*([%w%._/%-]+)")
           or first:match("^//%s*([%w%._/%-]+%.m?js)")
    if p then return p, block.body end
  end
  return nil
end

local function validate_rel_fixture_path(p)
  if not p or p == "" or p:sub(1, 1) == "/" or p:sub(-1) == "/" then return false end
  if not p:match("^[%w%._/%-]+$") then return false end
  for comp in p:gmatch("[^/]+") do
    if comp == "." or comp == ".." then return false end
  end
  return true
end

-- Split a ```titan block on `-- file: <path>` markers.
local function extract_titan_files(body)
  local files = {}
  local order = {}
  local current_path = nil
  local current_lines = {}
  local has_markers = false

  for _, line in ipairs(split_lines(body)) do
    local fpath = line:match("^%-%-%s*file:%s*(.-)%s*$")
    if fpath then
      has_markers = true
      if current_path then
        files[current_path] = table.concat(current_lines, "\n") .. "\n"
      end
      current_path = fpath
      order[#order + 1] = fpath
      current_lines = {}
    else
      current_lines[#current_lines + 1] = line
    end
  end
  if has_markers then
    if current_path then
      files[current_path] = table.concat(current_lines, "\n") .. "\n"
    end
    return files, order, true
  end
  return nil, nil, false
end

local function has_public_main(src)
  for _, line in ipairs(split_lines(src)) do
    if line:match("^%s*function%s+main%s*%(") then return true end
  end
  return false
end

local function has_public_tests(src)
  local imports_test = src:match('import%s+"test"') or src:match("import%s+'test'")
  if not imports_test then return false end
  for _, line in ipairs(split_lines(src)) do
    if line:match("^%s*function%s+test_[%w_]*%s*%(") then return true end
  end
  return false
end

local function strip_target_variant(rel_titan)
  local base = rel_titan:gsub("%.titan$", "")
  for _, lbl in ipairs({ "native", "browser", "linux", "darwin", "windows" }) do
    local suf = "." .. lbl
    if base:sub(-#suf) == suf then
      base = base:sub(1, -#suf - 1)
      break
    end
  end
  return base
end

local function compute_trees_and_modules(files, order)
  -- Collect non-stdlib imported logical names to distinguish `--tree src;tests`
  -- layouts from dotted package directories (`app/service.titan` -> `app.service`).
  local imported = {}
  for _, path in ipairs(order) do
    if path:match("%.titan$") then
      local src = files[path]
      for mod in src:gmatch('import%s+"([^"]+)"') do
        local clean = mod:gsub("%.titan$", "")
        if not STDLIB_MODULES[clean] then imported[clean] = true end
      end
      for mod in src:gmatch("import%s+'([^']+)'") do
        local clean = mod:gsub("%.titan$", "")
        if not STDLIB_MODULES[clean] then imported[clean] = true end
      end
    end
  end

  local tree_roots_set = {}
  local has_root_titan = false
  for _, path in ipairs(order) do
    if path:match("%.titan$") then
      local top, rest = path:match("^([^/]+)/(.+)$")
      if not top then
        has_root_titan = true
      else
        local stripped_mod = strip_target_variant(rest):gsub("/", ".")
        local full_mod = strip_target_variant(path):gsub("/", ".")
        if imported[stripped_mod] and not imported[full_mod] then
          tree_roots_set[top] = true
        elseif (top == "tests" or top == "test") and has_public_tests(files[path]) then
          tree_roots_set[top] = true
        end
      end
    end
  end

  if has_root_titan or next(tree_roots_set) == nil then
    tree_roots_set["."] = true
  end

  local trees = {}
  for t in pairs(tree_roots_set) do trees[#trees + 1] = t end
  table.sort(trees)

  local function logical_mod(path)
    local top, rest = path:match("^([^/]+)/(.+)$")
    if top and tree_roots_set[top] then
      return strip_target_variant(rest):gsub("/", ".")
    end
    return strip_target_variant(path):gsub("/", ".")
  end

  return trees, logical_mod
end

local function make_clean_env(prefix, browser_profile)
  local parts = {
    "env",
    "-u", "TITAN_PATH_0_6",
    "-u", "TITAN_PATH",
    "-u", "TITAN_SOURCE_PATH",
    "-u", "TITAN_TARGET",
    "-u", "TITAN_EXTRA_CPPFLAGS",
    "-u", "TITAN_NO_LINE_DIRECTIVES",
    "-u", "LUA_PATH",
    "-u", "LUA_CPATH",
    "-u", "LUA_PATH_5_5",
    "-u", "LUA_CPATH_5_5",
    "-u", "LUA_INIT",
    "-u", "LUA_INIT_5_5",
    "-u", "ROCKS_TREE",
    "-u", "TITANC",
    "TITAN_ROOT=" .. sh_quote(prefix),
    "TITANC=" .. sh_quote(join_path(prefix, "bin/titanc")),
  }
  if browser_profile and browser_profile ~= "" then
    parts[#parts + 1] = "TITAN_BUILD_PROFILE=" .. sh_quote(browser_profile)
  end
  return table.concat(parts, " ")
end

local function detect_browser_profile(prefix)
  local env_prof = os.getenv("TITAN_BUILD_PROFILE")
  if env_prof and env_prof ~= "" then return env_prof end
  local data = read_file(join_path(prefix, "lib/titan-browser/0.6/build-profile"))
  if data then
    local p = data:match("^%s*(%S+)")
    if p then return p end
  end
  return nil
end

local function compile_and_run_blocks(rel_file, parsed, prefix, keep_tmp, add_err)
  local titanc = join_path(prefix, "bin/titanc")
  local browser_run = join_path(prefix, "lib/titan-browser/0.6/titan-browser-run")
  local native_env = make_clean_env(prefix, nil)
  local browser_env = make_clean_env(prefix, detect_browser_profile(prefix))
  local checked_blocks = 0

  for idx, block in ipairs(parsed.blocks) do
    if block.lang == "titan" then
      checked_blocks = checked_blocks + 1
      local where = string.format("%s:%d (block #%d)", rel_file, block.line, checked_blocks)
      local directive = block.body:match("^%-%-%s*check:%s*([%w_%-,]+)")

      local parsed_files, parsed_order, multi = extract_titan_files(block.body)
      local files, order
      if multi and parsed_files and parsed_order then
        files, order = parsed_files, parsed_order
      else
        local fname = "snippet.titan"
        if has_public_main(block.body) then
          fname = "main.titan"
        elseif has_public_tests(block.body) then
          fname = "snippet_test.titan"
        end
        files = { [fname] = block.body }
        order = { fname }
      end
      -- Validate file paths and scan for companion C / JS fixtures in same section.
      local bad_path = false
      local foreign_headers = {}
      local uses_browser_api = false
      local has_native_variant = false
      local has_browser_variant = false
      local main_mod_file = nil
      local test_files = {}

      for _, fpath in ipairs(order) do
        if not validate_rel_fixture_path(fpath) then
          add_err(where .. ": invalid -- file: path '" .. tostring(fpath) .. "'")
          bad_path = true
        else
          local src = files[fpath]
          if fpath:match("%.native%.titan$") then has_native_variant = true end
          if fpath:match("%.browser%.titan$") then has_browser_variant = true end
          if src:match('import%s+"browser"') or src:match("import%s+'browser'")
             or src:match('foreign%s+import%s+"titan/browser%.h"') then
            uses_browser_api = true
          end
          for hdr in src:gmatch('foreign%s+import%s+"([^"]+)"') do
            foreign_headers[hdr] = true
          end
          if fpath:match("%.titan$") then
            if has_public_main(src) then main_mod_file = fpath end
            if has_public_tests(src) then test_files[#test_files + 1] = fpath end
          end
        end
      end

      if not bad_path then
        local companions = {}
        local browser_imports_mjs = nil
        -- Look at adjacent non-titan blocks in the same section without crossing another titan block.
        for dir = -1, 1, 2 do
          local j = idx + dir
          while parsed.blocks[j] and parsed.blocks[j].section_id == block.section_id
                and parsed.blocks[j].lang ~= "titan" do
            local cname, cbody = detect_companion_file(parsed.blocks[j])
            if cname and validate_rel_fixture_path(cname) and not files[cname] then
              if cname:match("%.h$") and foreign_headers[cname] then
                companions[cname] = cbody
              elseif cname:match("%.c$") then
                local stem = cname:gsub("%.c$", ".h")
                if foreign_headers[stem] or dir == -1 then
                  companions[cname] = cbody
                end
              elseif cname:match("%.m?js$") and (uses_browser_api or has_browser_variant) then
                if cbody:match("export%s+default") or cbody:match("%-%-imports") then
                  companions[cname] = cbody
                  browser_imports_mjs = cname
                end
              end
            end
            j = j + dir
          end
        end

        local targets = {}
        if directive and directive:find("native", 1, true) then
          targets[#targets + 1] = "native"
        end
        if directive and directive:find("browser", 1, true) then
          targets[#targets + 1] = "browser"
        end
        if #targets == 0 then
          if has_native_variant and has_browser_variant then
            targets = { "native", "browser" }
          elseif uses_browser_api or has_browser_variant then
            targets = { "browser" }
          else
            targets = { "native" }
          end
        end

        local compile_only_flag = directive and directive:find("compile%-only") ~= nil
        local tmp = mktemp_dir()
        local has_headers = false
        local c_sources = {}

        for _, fpath in ipairs(order) do
          local full = join_path(tmp, fpath)
          mkdir_p(dirname(full))
          assert(write_file(full, files[fpath]))
          if fpath:match("%.h$") then has_headers = true end
          if fpath:match("%.c$") then c_sources[#c_sources + 1] = full end
        end
        for cname, cbody in pairs(companions) do
          local full = join_path(tmp, cname)
          mkdir_p(dirname(full))
          assert(write_file(full, cbody))
          if cname:match("%.h$") then has_headers = true end
          if cname:match("%.c$") then c_sources[#c_sources + 1] = full end
        end
        table.sort(c_sources)

        local trees, logical_mod = compute_trees_and_modules(files, order)
        local tree_paths = {}
        for _, t in ipairs(trees) do
          tree_paths[#tree_paths + 1] = (t == ".") and tmp or join_path(tmp, t)
        end
        local tree_arg = table.concat(tree_paths, ";")

        local common_flags = { "--tree", sh_quote(tree_arg) }
        if has_headers then
          common_flags[#common_flags + 1] = "-I"
          common_flags[#common_flags + 1] = sh_quote(tmp)
        end
        for _, cs in ipairs(c_sources) do
          common_flags[#common_flags + 1] = "--c-source"
          common_flags[#common_flags + 1] = sh_quote(cs)
        end
        local common_str = table.concat(common_flags, " ")

        -- Collect unique logical module names for compile-only mode.
        local mod_seen, all_mods = {}, {}
        for _, fpath in ipairs(order) do
          if fpath:match("%.titan$") then
            local m = logical_mod(fpath)
            if not mod_seen[m] then
              mod_seen[m] = true
              all_mods[#all_mods + 1] = sh_quote(m)
            end
          end
        end

        for _, target in ipairs(targets) do
          local is_browser = (target == "browser")
          local out_dir = join_path(tmp, is_browser and "out-browser" or "out-native")
          mkdir_p(out_dir)
          local target_flag = is_browser and "--target browser " or ""
          local target_env = is_browser and browser_env or native_env

          local build_cmd, run_cmd
          if #test_files > 0 and not compile_only_flag then
            local tmods = {}
            for _, tf in ipairs(test_files) do tmods[#tmods + 1] = sh_quote(logical_mod(tf)) end
            local exe = join_path(tmp, is_browser and "test_app.mjs" or "test_app")
            build_cmd = string.format("%s %s -q %s--test %s -o %s --exe %s %s",
              target_env, sh_quote(titanc), target_flag, common_str,
              sh_quote(out_dir), sh_quote(exe), table.concat(tmods, " "))
            if is_browser then
              local imp = browser_imports_mjs
                and ("--imports " .. sh_quote(join_path(tmp, browser_imports_mjs)) .. " ") or ""
              run_cmd = string.format("%s %s --root %s %s%s",
                target_env, sh_quote(browser_run), sh_quote(tmp), imp, sh_quote(exe))
            else
              run_cmd = string.format("%s %s", target_env, sh_quote(exe))
            end
          elseif main_mod_file and not compile_only_flag then
            local main_mod = logical_mod(main_mod_file)
            local exe = join_path(tmp, is_browser and "app.mjs" or "app")
            build_cmd = string.format("%s %s -q %s%s -o %s --exe %s %s",
              target_env, sh_quote(titanc), target_flag, common_str,
              sh_quote(out_dir), sh_quote(exe), sh_quote(main_mod))
            if is_browser then
              local imp = browser_imports_mjs
                and ("--imports " .. sh_quote(join_path(tmp, browser_imports_mjs)) .. " ") or ""
              run_cmd = string.format("%s %s --root %s %s%s",
                target_env, sh_quote(browser_run), sh_quote(tmp), imp, sh_quote(exe))
            else
              run_cmd = string.format("%s %s", target_env, sh_quote(exe))
            end
          else
            build_cmd = string.format("%s %s -q %s-c %s -o %s %s",
              target_env, sh_quote(titanc), target_flag, common_str,
              sh_quote(out_dir), table.concat(all_mods, " "))
          end
          local ok, code, out = run_capture(build_cmd)
          if not ok then
            add_err(string.format("%s [%s compile failed, exit %d]:\n  cmd: %s\n  %s",
              where, target, code, build_cmd, (out:gsub("\n", "\n  "))))
          elseif run_cmd then
            local rok, rcode, rout = run_capture(run_cmd)
            if not rok then
              add_err(string.format("%s [%s run failed, exit %d]:\n  cmd: %s\n  %s",
                where, target, rcode, run_cmd, (rout:gsub("\n", "\n  "))))
            end
          end
        end

        if not keep_tmp then rm_rf(tmp) end
      end
    end
  end

  return checked_blocks
end

-- ============================================================================
-- Strict RFC 8259 JSON parser & --evals verification (eval-outline.md §4.1)
-- ============================================================================

local JSON_NULL = {}
local JSON_ARRAYS = setmetatable({}, { __mode = "k" })

local function is_json_array(v)
  return type(v) == "table" and JSON_ARRAYS[v] == true
end

local function is_json_object(v)
  return type(v) == "table" and JSON_ARRAYS[v] ~= true and v ~= JSON_NULL
end

local function parse_json(text)
  local pos = 1
  local len = #text

  local function skip_ws()
    while pos <= len do
      local b = text:byte(pos)
      if b == 0x20 or b == 0x09 or b == 0x0A or b == 0x0D then
        pos = pos + 1
      else
        break
      end
    end
  end

  local function fail(msg)
    local line = 1
    for _ in text:sub(1, pos - 1):gmatch("\n") do line = line + 1 end
    return nil, string.format("JSON parse error at line %d (byte %d): %s", line, pos, msg)
  end

  local parse_value

  local function parse_hex4()
    if pos + 3 > len then return nil, "truncated \\uXXXX escape" end
    local hex = text:sub(pos, pos + 3)
    if not hex:match("^[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$") then
      return nil, "invalid \\u escape '" .. hex .. "'"
    end
    pos = pos + 4
    return tonumber(hex, 16)
  end

  local function parse_string()
    pos = pos + 1 -- skip opening '"'
    local out = {}
    while pos <= len do
      local b = text:byte(pos)
      if b == 0x22 then -- '"'
        pos = pos + 1
        return table.concat(out)
      elseif b == 0x5C then -- '\'
        pos = pos + 1
        if pos > len then return fail("unterminated escape sequence") end
        local esc = text:byte(pos)
        pos = pos + 1
        if esc == 0x22 then out[#out + 1] = '"'
        elseif esc == 0x5C then out[#out + 1] = "\\"
        elseif esc == 0x2F then out[#out + 1] = "/"
        elseif esc == 0x62 then out[#out + 1] = "\b"
        elseif esc == 0x66 then out[#out + 1] = "\f"
        elseif esc == 0x6E then out[#out + 1] = "\n"
        elseif esc == 0x72 then out[#out + 1] = "\r"
        elseif esc == 0x74 then out[#out + 1] = "\t"
        elseif esc == 0x75 then -- 'u'
          local cp, herr = parse_hex4()
          if not cp then return fail(herr) end
          if cp >= 0xD800 and cp <= 0xDBFF then
            if text:sub(pos, pos + 1) ~= "\\u" then
              return fail("lone high surrogate in string")
            end
            pos = pos + 2
            local lo, lerr = parse_hex4()
            if not lo then return fail(lerr) end
            if lo < 0xDC00 or lo > 0xDFFF then
              return fail("invalid low surrogate in string")
            end
            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00)
          elseif cp >= 0xDC00 and cp <= 0xDFFF then
            return fail("lone low surrogate in string")
          end
          out[#out + 1] = utf8.char(cp)
        else
          return fail("invalid escape character")
        end
      elseif b < 0x20 then
        return fail("unescaped control character in string")
      else
        local start = pos
        while pos <= len do
          local nb = text:byte(pos)
          if nb == 0x22 or nb == 0x5C or nb < 0x20 then break end
          pos = pos + 1
        end
        out[#out + 1] = text:sub(start, pos - 1)
      end
    end
    return fail("unterminated string")
  end

  local function parse_number()
    local s, e = text:find("^%-?%d+%.?%d*[eE]?[+-]?%d*", pos)
    if not s then return fail("invalid number") end
    local raw = text:sub(s, e)
    if not raw:match("^%-?0$") and not raw:match("^%-?0%.[0-9]+$")
       and not raw:match("^%-?0[eE][+-]?[0-9]+$")
       and not raw:match("^%-?0%.[0-9]+[eE][+-]?[0-9]+$")
       and not raw:match("^%-?[1-9][0-9]*$")
       and not raw:match("^%-?[1-9][0-9]*%.[0-9]+$")
       and not raw:match("^%-?[1-9][0-9]*[eE][+-]?[0-9]+$")
       and not raw:match("^%-?[1-9][0-9]*%.[0-9]+[eE][+-]?[0-9]+$") then
      return fail("malformed number '" .. raw .. "'")
    end
    local num = tonumber(raw)
    if not num then return fail("number out of range '" .. raw .. "'") end
    pos = e + 1
    return num
  end

  local function parse_array()
    pos = pos + 1 -- skip '['
    local arr = {}
    JSON_ARRAYS[arr] = true
    skip_ws()
    if pos <= len and text:byte(pos) == 0x5D then -- ']'
      pos = pos + 1
      return arr
    end
    local n = 0
    while true do
      skip_ws()
      local v, err = parse_value()
      if err then return nil, err end
      n = n + 1
      arr[n] = v
      skip_ws()
      if pos > len then return fail("unterminated array") end
      local b = text:byte(pos)
      if b == 0x5D then -- ']'
        pos = pos + 1
        return arr
      elseif b == 0x2C then -- ','
        pos = pos + 1
      else
        return fail("expected ',' or ']' in array")
      end
    end
  end

  local function parse_object()
    pos = pos + 1 -- skip '{'
    local obj = {}
    skip_ws()
    if pos <= len and text:byte(pos) == 0x7D then -- '}'
      pos = pos + 1
      return obj
    end
    while true do
      skip_ws()
      if pos > len or text:byte(pos) ~= 0x22 then
        return fail("expected string key in object")
      end
      local k, kerr = parse_string()
      if kerr then return nil, kerr end
      if obj[k] ~= nil then
        return fail("duplicate object key '" .. k .. "'")
      end
      skip_ws()
      if pos > len or text:byte(pos) ~= 0x3A then -- ':'
        return fail("expected ':' after object key '" .. k .. "'")
      end
      pos = pos + 1
      skip_ws()
      local v, verr = parse_value()
      if verr then return nil, verr end
      obj[k] = v
      skip_ws()
      if pos > len then return fail("unterminated object") end
      local b = text:byte(pos)
      if b == 0x7D then -- '}'
        pos = pos + 1
        return obj
      elseif b == 0x2C then -- ','
        pos = pos + 1
      else
        return fail("expected ',' or '}' in object")
      end
    end
  end

  parse_value = function()
    skip_ws()
    if pos > len then return fail("unexpected end of JSON input") end
    local b = text:byte(pos)
    if b == 0x7B then return parse_object()
    elseif b == 0x5B then return parse_array()
    elseif b == 0x22 then return parse_string()
    elseif b == 0x2D or (b >= 0x30 and b <= 0x39) then return parse_number()
    elseif text:sub(pos, pos + 3) == "true" then pos = pos + 4; return true
    elseif text:sub(pos, pos + 4) == "false" then pos = pos + 5; return false
    elseif text:sub(pos, pos + 3) == "null" then pos = pos + 4; return JSON_NULL
    else
      return fail("unexpected token '" .. text:sub(pos, pos) .. "'")
    end
  end

  local root, err = parse_value()
  if err then return nil, err end
  skip_ws()
  if pos <= len then
    return fail("trailing data after root JSON value")
  end
  return root, nil
end

local function find_word_token(text, token, ignore_case)
  local hay = ignore_case and text:lower() or text
  local needle = ignore_case and token:lower() or token
  local hlen = #hay
  local init = 1
  while true do
    local s, e = hay:find(needle, init, true)
    if not s then return nil end
    local left_ok = (s == 1) or (not hay:sub(s - 1, s - 1):match("[%w_]"))
    local right_ok = (e == hlen) or (not hay:sub(e + 1, e + 1):match("[%w_]"))
    if left_ok and right_ok then return s, e end
    init = s + 1
  end
end

local function check_author_visible_leaks(where, text, add_err)
  if text:lower():find("skill://", 1, true) then
    add_err(where .. ": author-visible leak of 'skill://'")
  end
  for _, sk in ipairs(CANONICAL_SKILLS) do
    if find_word_token(text, sk.name, false) then
      add_err(string.format("%s: author-visible leak of skill name '%s'", where, sk.name))
    end
  end
  local imp = text:match('import%s*["\'](titan%.[%w_]+)["\']')
  if imp then
    add_err(string.format("%s: author-visible leak of unprompted 'import \"%s\"'", where, imp))
  end
end

local function check_blind_judge_text(where, text, add_err)
  if text:lower():find("skill://", 1, true) then
    add_err(where .. ": blind-judge violation ('skill://')")
  end
  if find_word_token(text, "baseline", true) then
    add_err(where .. ": blind-judge violation ('baseline')")
  end
  if find_word_token(text, "candidate", true) then
    add_err(where .. ": blind-judge violation ('candidate')")
  end
  if text:lower():find("skill-descriptions.db", 1, true) then
    add_err(where .. ": blind-judge violation ('skill-descriptions.db')")
  end
end

local function check_no_pem(where, data, add_err)
  local hdr = data:match("%-%-%-%-%-BEGIN%s+[A-Z0-9 ]+%-%-%-%-%-")
  if hdr then
    add_err(string.format("%s: forbidden PEM key/certificate block ('%s')", where, hdr))
  end
end

local function is_symlink(path)
  local ok = run_capture("test -L " .. sh_quote(path))
  return ok
end

local function check_string_array(where, field_name, val, allow_empty, add_err)
  if not is_json_array(val) then
    add_err(string.format("%s: required field '%s' must be a JSON array", where, field_name))
    return nil
  end
  if not allow_empty and #val == 0 then
    add_err(string.format("%s: field '%s' must be non-empty", where, field_name))
  end
  for idx, item in ipairs(val) do
    if type(item) ~= "string" or item == "" then
      add_err(string.format("%s: %s[%d] must be a non-empty string", where, field_name, idx))
    end
  end
  return val
end

local function check_skill_name_array(where, field_name, val, allow_empty, add_err)
  local arr = check_string_array(where, field_name, val, allow_empty, add_err)
  if not arr then return end
  for idx, item in ipairs(arr) do
    if type(item) == "string" and item ~= "" and not SKILL_BY_NAME[item] then
      add_err(string.format("%s: %s[%d] references unknown skill '%s'", where, field_name, idx, item))
    end
  end
end

local function check_evals_for_skill(repo_dir, spec, seen_case_ids, add_err)
  local evals_dir_rel = spec.name .. "/evals"
  local evals_dir_abs = join_path(repo_dir, evals_dir_rel)
  local evals_json_rel = evals_dir_rel .. "/evals.json"
  local evals_json_abs = join_path(repo_dir, evals_json_rel)

  if is_symlink(evals_dir_abs) then
    add_err(evals_dir_rel .. ": symlink forbidden under evals/")
    return 0, 0
  end
  if not is_dir(evals_dir_abs) then
    add_err("missing evals directory: " .. evals_dir_rel)
    return 0, 0
  end

  -- Reject any symlink anywhere under <skill>/evals/.
  local lok, _, lout = run_capture("find " .. sh_quote(evals_dir_abs) .. " -type l")
  if lok and lout ~= "" then
    for spath in lout:gmatch("[^\r\n]+") do
      add_err("symlink forbidden under evals/: " .. spath)
    end
  end

  -- Walk all regular files under <skill>/evals/ for PEM blocks and files/** leaks.
  local scanned_author_files = {}
  local fok, _, fout = run_capture("find " .. sh_quote(evals_dir_abs) .. " -type f | LC_ALL=C sort")
  if fok and fout ~= "" then
    local files_prefix = evals_dir_abs .. "/files/"
    for fpath in fout:gmatch("[^\r\n]+") do
      local fdata = read_file(fpath)
      if fdata then
        local rel_display = fpath
        if fpath:sub(1, #repo_dir + 1) == repo_dir .. "/" then
          rel_display = fpath:sub(#repo_dir + 2)
        end
        check_no_pem(rel_display, fdata, add_err)
        if fpath:sub(1, #files_prefix) == files_prefix then
          scanned_author_files[fpath] = true
          check_author_visible_leaks(rel_display, fdata, add_err)
        end
      end
    end
  end

  local raw, rerr = read_file(evals_json_abs)
  if not raw then
    add_err("missing " .. evals_json_rel .. ": " .. tostring(rerr))
    return 0, 0
  end

  local doc, jerr = parse_json(raw)
  if not doc then
    add_err(evals_json_rel .. ": " .. tostring(jerr))
    return 0, 0
  end
  if not is_json_object(doc) then
    add_err(evals_json_rel .. ": root JSON value must be an object")
    return 0, 0
  end
  if doc.skill_name ~= spec.name then
    add_err(string.format("%s: skill_name '%s' ~= dir '%s'",
      evals_json_rel, tostring(doc.skill_name), spec.name))
  end
  if not is_json_array(doc.evals) or #doc.evals == 0 then
    add_err(evals_json_rel .. ": 'evals' must be a non-empty JSON array")
    return 0, 0
  end

  local case_count = 0
  local assertion_count = 0

  for idx, c in ipairs(doc.evals) do
    local cwhere = string.format("%s:evals[%d]", evals_json_rel, idx)
    if not is_json_object(c) then
      add_err(cwhere .. ": case entry must be a JSON object")
    else
      case_count = case_count + 1
      if type(c.id) ~= "string" or c.id == "" then
        add_err(cwhere .. ": required field 'id' must be a non-empty string")
      else
        cwhere = string.format("%s (%s)", evals_json_rel, c.id)
        if seen_case_ids[c.id] then
          add_err(string.format("%s: duplicate case id '%s' (already defined in %s)",
            evals_json_rel, c.id, seen_case_ids[c.id]))
        else
          seen_case_ids[c.id] = evals_json_rel
        end
      end

      if type(c.prompt) ~= "string" or c.prompt == "" then
        add_err(cwhere .. ": required field 'prompt' must be a non-empty string")
      else
        check_author_visible_leaks(cwhere .. ".prompt", c.prompt, add_err)
      end

      local files_arr = check_string_array(cwhere, "files", c.files, true, add_err)
      if files_arr then
        for fidx, frel in ipairs(files_arr) do
          if type(frel) == "string" and frel ~= "" then
            if not validate_rel_fixture_path(frel) then
              add_err(string.format("%s: files[%d] invalid relative path '%s'", cwhere, fidx, frel))
            else
              local fabs = join_path(join_path(repo_dir, spec.name), frel)
              if is_symlink(fabs) then
                add_err(string.format("%s: files[%d] '%s' is a symlink", cwhere, fidx, frel))
              elseif not file_exists(fabs) then
                add_err(string.format("%s: files[%d] missing file '%s/%s'", cwhere, fidx, spec.name, frel))
              elseif not scanned_author_files[fabs] then
                scanned_author_files[fabs] = true
                local fdata = read_file(fabs)
                if fdata then
                  check_no_pem(spec.name .. "/" .. frel, fdata, add_err)
                  check_author_visible_leaks(spec.name .. "/" .. frel, fdata, add_err)
                end
              end
            end
          end
        end
      end

      if c.oracle_files ~= nil and c.oracle_files ~= JSON_NULL then
        local oracles = check_string_array(cwhere, "oracle_files", c.oracle_files, true, add_err)
        if oracles then
          for oidx, orel in ipairs(oracles) do
            if type(orel) == "string" and orel ~= "" then
              if not validate_rel_fixture_path(orel) then
                add_err(string.format("%s: oracle_files[%d] invalid relative path '%s'", cwhere, oidx, orel))
              else
                local oabs = join_path(join_path(repo_dir, spec.name), orel)
                if is_symlink(oabs) then
                  add_err(string.format("%s: oracle_files[%d] '%s' is a symlink", cwhere, oidx, orel))
                elseif not file_exists(oabs) then
                  add_err(string.format("%s: oracle_files[%d] missing file '%s/%s'", cwhere, oidx, spec.name, orel))
                end
              end
            end
          end
        end
      end

      check_string_array(cwhere, "expected_outputs", c.expected_outputs, false, add_err)

      if not is_json_object(c.verify) then
        add_err(cwhere .. ": required field 'verify' must be a JSON object")
      else
        check_string_array(cwhere .. ".verify", "commands", c.verify.commands, false, add_err)
        if c.verify.target ~= nil and type(c.verify.target) ~= "string" then
          add_err(cwhere .. ".verify: 'target' must be a string")
        end
      end

      if not is_json_array(c.assertions) or #c.assertions == 0 then
        add_err(cwhere .. ": required field 'assertions' must be a non-empty JSON array")
      else
        local seen_aids = {}
        for aidx, a in ipairs(c.assertions) do
          local awhere = string.format("%s.assertions[%d]", cwhere, aidx)
          if not is_json_object(a) then
            add_err(awhere .. ": assertion entry must be a JSON object")
          else
            assertion_count = assertion_count + 1
            if type(a.id) ~= "string" or a.id == "" then
              add_err(awhere .. ": required field 'id' must be a non-empty string")
            else
              awhere = string.format("%s.assertions[%s]", cwhere, a.id)
              if seen_aids[a.id] then
                add_err(awhere .. ": duplicate assertion id")
              end
              seen_aids[a.id] = true
            end
            if a.critical ~= "standard" and a.critical ~= "issue61_idiom" then
              add_err(string.format("%s: 'critical' must be 'standard' or 'issue61_idiom' (got '%s')",
                awhere, tostring(a.critical)))
            end
            if type(a.check) ~= "string" or a.check == "" then
              add_err(awhere .. ": required field 'check' must be a non-empty string")
            else
              check_blind_judge_text(awhere .. ".check", a.check, add_err)
            end
          end
        end
      end

      if type(c.judge_rubric) ~= "string" or c.judge_rubric == "" then
        add_err(cwhere .. ": required field 'judge_rubric' must be a non-empty string")
      else
        check_blind_judge_text(cwhere .. ".judge_rubric", c.judge_rubric, add_err)
      end

      check_skill_name_array(cwhere, "baseline_expected_skills", c.baseline_expected_skills, true, add_err)
      check_skill_name_array(cwhere, "candidate_expected_skills", c.candidate_expected_skills, false, add_err)
      check_skill_name_array(cwhere, "optional_skills", c.optional_skills, true, add_err)
      check_skill_name_array(cwhere, "forbidden_skills", c.forbidden_skills, true, add_err)

      local refs_arr = check_string_array(cwhere, "candidate_expected_references",
        c.candidate_expected_references, true, add_err)
      if refs_arr then
        for ridx, ref_path in ipairs(refs_arr) do
          if type(ref_path) == "string" and ref_path ~= "" then
            local rskill, rfile = ref_path:match("^([^/]+)/references/([^/]+)$")
            if not rskill or not SKILL_BY_NAME[rskill] or not SKILL_BY_NAME[rskill].refs[rfile] then
              add_err(string.format("%s: candidate_expected_references[%d] unknown reference '%s'",
                cwhere, ridx, ref_path))
            elseif not file_exists(join_path(repo_dir, ref_path)) then
              add_err(string.format("%s: candidate_expected_references[%d] missing file '%s'",
                cwhere, ridx, ref_path))
            end
          end
        end
      end
    end
  end

  return case_count, assertion_count
end

local function detect_default_prefix()
  local env_root = os.getenv("TITAN_ROOT")
  if env_root and env_root ~= "" and file_exists(join_path(env_root, "bin/titanc")) then
    return env_root
  end
  if arg and arg[-1] then
    local lua_bin = arg[-1]
    local parent = dirname(dirname(lua_bin))
    if file_exists(join_path(parent, "bin/titanc")) then
      return parent
    end
  end
  local ok, _, out = run_capture("titanc --print-root")
  if ok then
    local root = out:gsub("%s+$", "")
    if root ~= "" and file_exists(join_path(root, "bin/titanc")) then
      return root
    end
  end
  return nil
end

local function usage()
  io.stderr:write([[
Usage: lua scripts/check_skills.lua [options] [skill...]

Options:
  --prefix <SDK>   Titan SDK root containing bin/titanc (default: $TITAN_ROOT or Lua prefix)
  --skip-compile   Skip ```titan compile+run checks (run metadata, caps, links, diff only)
  --evals          Validate <skill>/evals/evals.json schema, files, symlinks, PEMs, zero-leak & blind-judge hygiene
  --check-root     Also check root README.md, AGENTS.md, .gitignore even when filtering skills
  --repo <DIR>     Path to titan-skills root (default: auto-detected from cwd or script path)
  --keep-tmp       Keep temporary compile workspaces under /tmp/check_skills_*
  -h, --help       Show this help
]])
end

local function main()
  local prefix = nil
  local skip_compile = false
  local check_evals = false
  local check_root = false
  local repo_dir = nil
  local keep_tmp = false
  local requested = {}

  local i = 1
  while i <= #arg do
    local a = arg[i]
    if a == "-h" or a == "--help" then
      usage()
      os.exit(0)
    elseif a == "--skip-compile" then
      skip_compile = true
    elseif a == "--evals" then
      check_evals = true
    elseif a == "--check-root" then
      check_root = true
    elseif a == "--keep-tmp" then
      keep_tmp = true
    elseif a == "--prefix" then
      i = i + 1
      prefix = arg[i]
      if not prefix then io.stderr:write("error: --prefix requires an argument\n"); os.exit(2) end
    elseif a:match("^%-%-prefix=") then
      prefix = a:match("^%-%-prefix=(.+)$")
    elseif a == "--repo" then
      i = i + 1
      repo_dir = arg[i]
      if not repo_dir then io.stderr:write("error: --repo requires an argument\n"); os.exit(2) end
    elseif a:match("^%-%-repo=") then
      repo_dir = a:match("^%-%-repo=(.+)$")
    elseif a:sub(1, 1) == "-" then
      io.stderr:write("error: unknown option '" .. a .. "'\n")
      usage()
      os.exit(2)
    else
      requested[#requested + 1] = a:gsub("/+$", "")
    end
    i = i + 1
  end

  if not repo_dir then
    if is_dir("titan-programmer") then
      repo_dir = "."
    elseif arg[0] then
      local script_parent = dirname(dirname(arg[0]))
      if is_dir(join_path(script_parent, "titan-programmer")) then
        repo_dir = script_parent
      else
        repo_dir = "."
      end
    else
      repo_dir = "."
    end
  end

  local is_full_run = (#requested == 0)
  local target_specs = {}
  if is_full_run then
    target_specs = CANONICAL_SKILLS
  else
    for _, name in ipairs(requested) do
      local spec = SKILL_BY_NAME[name]
      if not spec then
        io.stderr:write("error: unknown skill '" .. name .. "' (not in canonical 17-skill topology)\n")
        os.exit(2)
      end
      target_specs[#target_specs + 1] = spec
    end
  end

  if not skip_compile then
    prefix = prefix or detect_default_prefix()
    if not prefix or not file_exists(join_path(prefix, "bin/titanc")) then
      io.stderr:write("error: cannot locate bin/titanc; pass --prefix <SDK> or --skip-compile\n")
      os.exit(2)
    end
  end

  local errors = {}
  local function add_err(msg)
    errors[#errors + 1] = msg
  end

  local rows = {}

  -- Check root repo inventory and root docs on full run (or --check-root).
  if is_full_run or check_root then
    if is_full_run then
      local top_entries = list_dir(repo_dir) or {}
      for _, entry in ipairs(top_entries) do
        if is_dir(join_path(repo_dir, entry)) and file_exists(join_path(repo_dir, entry .. "/SKILL.md")) then
          if not SKILL_BY_NAME[entry] then
            add_err("unexpected skill directory outside canonical 17-skill topology: " .. entry)
          end
        end
      end
    end
    for _, doc in ipairs({ "README.md", "AGENTS.md" }) do
      local abs = join_path(repo_dir, doc)
      local data = read_file(abs)
      if not data then
        add_err("missing required root file: " .. doc)
      else
        local parsed = parse_markdown(data, 1)
        check_whitespace_and_conflicts(doc, parsed.lines, add_err)
        check_links(repo_dir, doc, parsed, is_full_run, add_err)
      end
    end
    if not file_exists(join_path(repo_dir, ".gitignore")) then
      add_err("missing required root file: .gitignore")
    end
  end
  local seen_case_ids = {}
  local total_eval_skills = 0
  local total_eval_cases = 0
  local total_eval_assertions = 0

  for _, spec in ipairs(target_specs) do
    local skill_rel = spec.name .. "/SKILL.md"
    local skill_abs = join_path(repo_dir, skill_rel)
    local eval_md = join_path(repo_dir, spec.name .. "/EVALUATION.md")
    if file_exists(eval_md) then
      add_err(spec.name .. "/EVALUATION.md must be deleted (historical logs belong in release archives)")
    end

    local data, rerr = read_file(skill_abs)
    if not data then
      add_err("missing " .. skill_rel .. ": " .. tostring(rerr))
    else
      local lines_count = count_lines(data)
      local bytes_count = #data
      if lines_count > spec.max_lines then
        add_err(string.format("%s: line count %d exceeds cap %d", skill_rel, lines_count, spec.max_lines))
      end
      if bytes_count > spec.max_bytes then
        add_err(string.format("%s: byte count %d exceeds cap %d", skill_rel, bytes_count, spec.max_bytes))
      end

      local all_lines = split_lines(data)
      check_whitespace_and_conflicts(skill_rel, all_lines, add_err)

      local fm, fm_err = parse_frontmatter(all_lines)
      local desc_len, c1_len = 0, 0
      if not fm then
        add_err(skill_rel .. ": " .. fm_err)
      else
        for _, k in ipairs(fm.order) do
          if k ~= "name" and k ~= "description" then
            add_err(string.format("%s: disallowed frontmatter key '%s' (only name and description allowed)", skill_rel, k))
          end
        end
        if fm.fields.name ~= spec.name then
          add_err(string.format("%s: frontmatter name '%s' ~= dir '%s'",
            skill_rel, tostring(fm.fields.name), spec.name))
        end
        local desc = fm.fields.description
        if not desc or desc == "" then
          add_err(skill_rel .. ": missing frontmatter description")
        else
          desc_len = #desc
          local c1 = extract_clause1(desc)
          c1_len = #c1
          if desc_len < DESC_MIN_CHARS or desc_len > DESC_MAX_CHARS then
            add_err(string.format("%s: description length %d outside %d..%d chars",
              skill_rel, desc_len, DESC_MIN_CHARS, DESC_MAX_CHARS))
          end
          if c1_len > CLAUSE1_MAX_CHARS then
            add_err(string.format("%s: description Clause 1 length %d exceeds %d chars ('%s')",
              skill_rel, c1_len, CLAUSE1_MAX_CHARS, c1))
          end
        end
      end

      local parsed = parse_markdown(data, fm and (fm.end_line + 1) or 1)
      if parsed.unclosed_fence then
        add_err(string.format("%s:%d: unclosed fenced code block", skill_rel, parsed.unclosed_fence))
      end

      local h1_count = 0
      for _, h in ipairs(parsed.headings) do
        if h.level == 1 then h1_count = h1_count + 1 end
        if h.level == 2 and h.title:lower():match("^evaluation") then
          add_err(string.format("%s:%d: forbidden '## %s' heading inside SKILL.md", skill_rel, h.line, h.title))
        end
      end
      if h1_count ~= 1 then
        add_err(string.format("%s: expected H1 == 1, found %d", skill_rel, h1_count))
      end

      local link_count = check_links(repo_dir, skill_rel, parsed, is_full_run, add_err)
      local block_count = 0
      if not skip_compile then
        block_count = compile_and_run_blocks(skill_rel, parsed, prefix, keep_tmp, add_err)
      end

      rows[#rows + 1] = string.format("%-44s %3d/%3d L  %5d/%5d B  desc=%3d(c1=%3d)  H1=%d  links=%2d  blocks=%d",
        skill_rel, lines_count, spec.max_lines, bytes_count, spec.max_bytes,
        desc_len, c1_len, h1_count, link_count, block_count)
    end

    -- Check references/ directory for this skill.
    local refs_dir = join_path(repo_dir, spec.name .. "/references")
    local expected_ref_names = {}
    for rname in pairs(spec.refs) do expected_ref_names[#expected_ref_names + 1] = rname end
    table.sort(expected_ref_names)

    if is_dir(refs_dir) then
      local actual = list_dir(refs_dir) or {}
      for _, fname in ipairs(actual) do
        if fname:match("%.md$") and not spec.refs[fname] then
          add_err(string.format("%s/references/%s: undeclared reference file", spec.name, fname))
        end
      end
    end

    for _, rname in ipairs(expected_ref_names) do
      local rcap = spec.refs[rname]
      local ref_rel = spec.name .. "/references/" .. rname
      local ref_abs = join_path(repo_dir, ref_rel)
      local rdata, rerr2 = read_file(ref_abs)
      if not rdata then
        add_err("missing declared reference " .. ref_rel .. ": " .. tostring(rerr2))
      else
        local rl = count_lines(rdata)
        local rb = #rdata
        if rl > rcap.max_lines then
          add_err(string.format("%s: line count %d exceeds cap %d", ref_rel, rl, rcap.max_lines))
        end
        if rb > rcap.max_bytes then
          add_err(string.format("%s: byte count %d exceeds cap %d", ref_rel, rb, rcap.max_bytes))
        end
        local rparsed = parse_markdown(rdata, 1)
        check_whitespace_and_conflicts(ref_rel, rparsed.lines, add_err)
        if rparsed.unclosed_fence then
          add_err(string.format("%s:%d: unclosed fenced code block", ref_rel, rparsed.unclosed_fence))
        end
        local rh1 = 0
        for _, h in ipairs(rparsed.headings) do
          if h.level == 1 then rh1 = rh1 + 1 end
          if h.level == 2 and h.title:lower():match("^evaluation") then
            add_err(string.format("%s:%d: forbidden '## %s' heading", ref_rel, h.line, h.title))
          end
        end
        if rh1 ~= 1 then
          add_err(string.format("%s: expected H1 == 1, found %d", ref_rel, rh1))
        end
        local rlinks = check_links(repo_dir, ref_rel, rparsed, is_full_run, add_err)
        local rblocks = 0
        if not skip_compile then
          rblocks = compile_and_run_blocks(ref_rel, rparsed, prefix, keep_tmp, add_err)
        end
        rows[#rows + 1] = string.format("%-44s %3d/%3d L  %5d/%5d B  (reference)       H1=%d  links=%2d  blocks=%d",
          ref_rel, rl, rcap.max_lines, rb, rcap.max_bytes, rh1, rlinks, rblocks)
      end
    end

    if check_evals then
      local cc, ac = check_evals_for_skill(repo_dir, spec, seen_case_ids, add_err)
      total_eval_skills = total_eval_skills + 1
      total_eval_cases = total_eval_cases + cc
      total_eval_assertions = total_eval_assertions + ac
    end
  end
  -- Run git diff --check when inside a git repository.
  local is_git = run_capture("git -C " .. sh_quote(repo_dir) .. " rev-parse --is-inside-work-tree")
  if is_git then
    local gok, _, gout = run_capture("git -C " .. sh_quote(repo_dir) .. " diff --check")
    if not gok then
      add_err("git diff --check failed:\n" .. gout)
    end
    local cok, _, cout = run_capture("git -C " .. sh_quote(repo_dir) .. " diff --cached --check")
    if not cok then
      add_err("git diff --cached --check failed:\n" .. cout)
    end
  end

  for _, row in ipairs(rows) do
    print(row)
  end

  if #errors > 0 then
    io.stderr:write(string.format("\nFAILED: %d error(s):\n", #errors))
    for idx, e in ipairs(errors) do
      io.stderr:write(string.format("  %d. %s\n", idx, e))
    end
    os.exit(1)
  end

  local mode_desc = skip_compile and "--skip-compile" or "compile+run enabled"
  if check_evals then
    print(string.format("\nEvals: %d skill(s), %d case(s), %d assertion(s) verified (0 leaks, 0 symlinks, 0 PEMs).",
      total_eval_skills, total_eval_cases, total_eval_assertions))
    mode_desc = mode_desc .. ", --evals"
  end
  print(string.format("\nPASS: %d file(s) verified (%s).", #rows, mode_desc))
end

main()
