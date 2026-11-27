-- Legacy Lua reference implementation of config-diff helpers.
-- Port the behavior to strongly typed Titan in `diff.titan`.

local M = {}

function M.is_present(v)
  return v and true or false
end

function M.format_value(v)
  if v == nil then return "nil" end
  if type(v) == "boolean" then return v and "true" or "false" end
  if type(v) == "number" or type(v) == "string" then return tostring(v) end
  return "<other>"
end

function M.merge_tags(prefix, ...)
  local out = {}
  for i = 1, #prefix do out[#out + 1] = prefix[i] end
  for i = 1, select("#", ...) do out[#out + 1] = select(i, ...) end
  return out
end

function M.slice_window(items, first, last)
  if first < 1 or last > #items or first > last then return end
  return table.unpack(items, first, last)
end

function M.diff_maps(keys, old_cfg, new_cfg)
  local changes = {}
  local counts = { added = 0, removed = 0, changed = 0 }
  for i = 1, #keys do
    local k = keys[i]
    local a, b = old_cfg[k], new_cfg[k]
    if a == nil and b ~= nil then
      counts.added = counts.added + 1
      changes[#changes + 1] = { key = k, summary = "+" .. M.format_value(b) }
    elseif a ~= nil and b == nil then
      counts.removed = counts.removed + 1
      changes[#changes + 1] = { key = k, summary = "-" .. M.format_value(a) }
    elseif a ~= b then
      counts.changed = counts.changed + 1
      changes[#changes + 1] = { key = k, summary = M.format_value(a) .. "->" .. M.format_value(b) }
    end
  end
  return changes, counts
end

return M
