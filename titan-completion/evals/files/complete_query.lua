-- Seeded completion query helper with known defects to repair.
local M = {}

-- BUG: Naive string slicing instead of compiler caret preparation.
function M.prepare_caret(filename, source_text, caret_byte)
  local before = source_text:sub(1, caret_byte)
  local after = source_text:sub(caret_byte + 1)
  local prefix = before:match("([%w_]*)$") or ""
  local start_byte = caret_byte - #prefix
  local text = before:sub(1, start_byte) .. "__dummy" .. after
  return {
    text = text,
    kind = "lexical",
    prefix = prefix,
    replacement_start = start_byte,
    replacement_end = caret_byte,
    request = {
      filename = filename,
      kind = "lexical",
      prefix = prefix,
      caret_byte = caret_byte,
      start_byte = start_byte,
      end_byte = caret_byte,
      analysis_start_byte = start_byte,
      analysis_end_byte = start_byte + 7,
      name = "__dummy",
    },
  }
end

-- BUG: Does not reverse transformed offsets back to original byte offsets.
function M.map_to_original_byte(_request, analysis_byte)
  return analysis_byte
end

-- BUG: Regex grep instead of parser-backed dependency discovery.
function M.extract_dependencies(files)
  local out = {}
  for _, item in ipairs(files) do
    for mod in item.contents:gmatch('import%s+"([^"]+)"') do
      out[#out + 1] = { module_name = mod, source_required = false }
    end
  end
  return out
end

-- BUG: Regex candidate scraping without compiler analysis_only checking or state restoration.
function M.query_completion(opts)
  local prepared, reason = M.prepare_caret(opts.filename, opts.source, opts.caret)
  if not prepared then return nil, reason end
  local candidates = {}
  local by_name = {}
  for ident in opts.source:gmatch("([%a_][%w_]*)") do
    if not by_name[ident] then
      local row = { name = ident, kind = 6, detail = "unknown", lookup_domain = "value", available = true }
      candidates[#candidates + 1] = row
      by_name[ident] = row
    end
  end
  return {
    kind = prepared.kind,
    quality = "unresolved",
    prefix = prepared.prefix,
    replacement_start = prepared.replacement_start,
    replacement_end = prepared.replacement_end,
    request = prepared.request,
    candidates = candidates,
    by_name = by_name,
    scopes = {},
  }
end

return M
