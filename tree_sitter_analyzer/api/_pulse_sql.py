"""Pulse 上下文的固定参数化 SQL；执行和快照生命周期由 pulse 模块负责。"""

_PULSE_SQL = """
WITH
target AS (
    SELECT id, name, kind, file_path, language, line, end_line
    FROM   ast_symbol_rows
    WHERE  id = :symbol_id
),
callers AS (
    SELECT e.caller_name AS name, e.file_path AS file, e.caller_line AS line,
           COALESCE(a.mod_count_30d, 0) AS hot30
    FROM   edges e
    JOIN   target t
    LEFT   JOIN ast_symbol_rows cs ON cs.name = e.caller_name AND cs.file_path = e.file_path
                                   AND cs.line = e.caller_line
    LEFT   JOIN ast_symbol_activation a ON a.symbol_id = cs.id
                                      AND a.activation_state IS NOT 'pending'
                                      AND a.activation_state IS NOT 'disabled'
    WHERE  e.kind = 'calls'
    AND    (e.callee_symbol_id = t.id
            OR (e.callee_symbol_id IS NULL AND e.callee_name = t.name
                AND e.callee_resolved_file = t.file_path))
    ORDER  BY hot30 DESC, e.id
    LIMIT  :max_callers
),
callees AS (
    SELECT e.id AS edge_id, e.callee_name AS name,
           COALESCE(cs.file_path, NULLIF(e.callee_resolved_file, '')) AS file,
           cs.line AS line, e.callee_resolution AS resolution
    FROM   edges e
    JOIN   target t ON e.caller_name = t.name AND e.file_path = t.file_path
                       AND e.caller_line = t.line
    LEFT   JOIN ast_symbol_rows cs ON cs.id = e.callee_symbol_id
        OR (e.callee_symbol_id IS NULL AND cs.file_path = e.callee_resolved_file
            AND cs.name = e.callee_name
            AND (SELECT count(*) FROM ast_symbol_rows candidate
                 WHERE candidate.file_path = cs.file_path AND candidate.name = cs.name) = 1)
    WHERE  e.kind = 'calls'
    ORDER  BY (cs.id IS NOT NULL) DESC, e.id
    LIMIT  :max_callees
),
file_imports AS (
    SELECT i.module_path AS module, NULL AS file
    FROM   ast_imports i
    JOIN   target t ON i.file_path = t.file_path
    LIMIT  :max_imports
),
imported_by AS (
    SELECT DISTINCT e.file_path AS importer
    FROM   edges e
    JOIN   target t
    WHERE  e.kind = 'imports'
    AND    (e.callee_resolved_file = t.file_path
            OR (t.language = 'python' AND e.target_node_id = :module_node))
    ORDER  BY e.file_path
    LIMIT  20
),
git_heat AS (
    SELECT a.last_modified_commit AS last_commit,
           a.last_commit_msg      AS commit_msg,
           a.last_modified_at     AS at,
           a.mod_count_30d        AS mod_30d,
           a.mod_count_90d        AS mod_90d,
           a.mod_count_all        AS mod_all,
           a.git_state            AS state
    FROM   ast_symbol_activation a
    JOIN   target t ON a.symbol_id = t.id
    WHERE  a.activation_state IS NOT 'pending'
    AND    a.activation_state IS NOT 'disabled'
    AND    a.git_state IS NOT NULL
    LIMIT  1
),
siblings AS (
    SELECT r.name, r.kind, r.line
    FROM   ast_symbol_rows r
    JOIN   target t ON r.file_path = t.file_path
    WHERE  r.kind IN ('function','method','class')
    AND    r.id <> t.id
    ORDER  BY r.line
    LIMIT  :max_siblings
),
docstring_cte AS (
    SELECT SUBSTR(json_extract(s.value, '$.docstring'), 1, 200) AS raw
    FROM   ast_index i
    JOIN   target t ON i.file_path = t.file_path
    JOIN   json_each(CASE WHEN json_valid(i.symbols_json)
                          THEN i.symbols_json ELSE '{}' END, '$.symbols') s
    WHERE  s.type = 'object' AND json_extract(s.value, '$.name') = t.name
    AND    json_extract(s.value, '$.line') = t.line
    LIMIT  1
),
comments_cte AS (
    SELECT c.line, c.text, c.kind
    FROM   ast_symbol_comments c
    JOIN   target t ON c.symbol_id = t.id
    ORDER  BY c.line
    LIMIT  :max_comments
)
SELECT
    (SELECT json_object('id',id,'name',name,'kind',kind,'file',file_path,
                        'line',line,'end_line',end_line,'language',language)
     FROM target) AS target_json,
    (SELECT json_group_array(
        json_object('name',name,'file',file,'line',line,'hot30',hot30))
     FROM callers) AS callers_json,
    (SELECT json_group_array(
        json_object('edge_id',edge_id,'name',name,'file',file,'line',line,'resolution',resolution))
     FROM callees) AS callees_json,
    (SELECT json_group_array(json_object('module',module,'file',file))
     FROM file_imports) AS imports_json,
    (SELECT json_group_array(importer) FROM imported_by) AS imported_by_json,
    (SELECT json_object('commit',last_commit,'commit_msg',commit_msg,'at',at,
                        'mod_30d',mod_30d,'mod_90d',mod_90d,'mod_all',mod_all,
                        'state',state)
     FROM git_heat) AS git_heat_json,
    (SELECT json_group_array(json_object('name',name,'kind',kind,'line',line))
     FROM siblings) AS siblings_json,
    (SELECT raw FROM docstring_cte) AS docstring_raw,
    (SELECT json_group_array(json_object('line',line,'text',text,'kind',kind))
     FROM comments_cte) AS comments_json
"""
