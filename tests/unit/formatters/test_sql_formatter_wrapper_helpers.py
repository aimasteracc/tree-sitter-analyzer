"""Tests for uncovered paths in _sql_formatter_wrapper_helpers.py (58% -> 85%+)."""

from __future__ import annotations

from types import SimpleNamespace

from tree_sitter_analyzer.formatters._sql_formatter_wrapper_helpers import (
    convert_analysis_result_to_sql_elements,
    create_sql_element_from_dict,
    element_to_dict,
)
from tree_sitter_analyzer.models import (
    SQLFunction,
    SQLIndex,
    SQLProcedure,
    SQLTable,
    SQLTrigger,
    SQLView,
)


def _noop_extractor(raw_text, name):
    return {}


def _make_element(
    name="test",
    element_type="table",
    start_line=1,
    end_line=10,
    raw_text="CREATE TABLE test (id INT);",
    language="sql",
):
    return SimpleNamespace(
        name=name,
        element_type=element_type,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
        language=language,
    )


class TestElementToDict:
    def test_full_attributes(self):
        el = SQLTable(
            name="users",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE users (id INT);",
            language="sql",
        )
        d = element_to_dict(el)
        assert d["name"] == "users"
        assert d["start_line"] == 1
        assert d["end_line"] == 5
        assert d["raw_text"] == "CREATE TABLE users (id INT);"
        assert d["language"] == "sql"

    def test_missing_attributes_use_defaults(self):
        el = SimpleNamespace()
        d = element_to_dict(el)
        assert d["name"] == str(el)
        assert d["start_line"] == 0
        assert d["end_line"] == 0
        assert d["raw_text"] == ""
        assert d["language"] == "sql"

    def test_sql_type_fallback(self):
        el = SimpleNamespace(name="x", sql_type="view")
        d = element_to_dict(el)
        assert d["type"] == "view"


class TestConvertAnalysisResultToSqlElements:
    def _make_result(self, elements):
        return SimpleNamespace(elements=elements)

    def _convert(self, result):
        return convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=_noop_extractor,
            extract_procedure_info=_noop_extractor,
            extract_function_info=_noop_extractor,
            extract_trigger_info=_noop_extractor,
            extract_index_info=_noop_extractor,
        )

    def test_table_element(self):
        el = _make_element("users", element_type="table")
        sqls = self._convert(self._make_result([el]))
        assert len(sqls) == 1
        assert isinstance(sqls[0], SQLTable)
        assert sqls[0].name == "users"

    def test_view_element(self):
        el = _make_element("user_view", element_type="view")
        sqls = self._convert(self._make_result([el]))
        assert len(sqls) == 1
        assert isinstance(sqls[0], SQLView)

    def test_procedure_element(self):
        el = _make_element("update_user", element_type="procedure")
        sqls = self._convert(self._make_result([el]))
        assert len(sqls) == 1
        assert isinstance(sqls[0], SQLProcedure)

    def test_function_element(self):
        el = _make_element("calc_total", element_type="sql_function")
        sqls = self._convert(self._make_result([el]))
        assert len(sqls) == 1
        assert isinstance(sqls[0], SQLFunction)

    def test_trigger_element(self):
        el = _make_element("audit_trig", element_type="trigger")
        sqls = self._convert(self._make_result([el]))
        assert len(sqls) == 1
        assert isinstance(sqls[0], SQLTrigger)

    def test_index_element(self):
        el = _make_element("idx_email", element_type="index")
        sqls = self._convert(self._make_result([el]))
        assert len(sqls) == 1
        assert isinstance(sqls[0], SQLIndex)

    def test_unknown_type_skipped(self):
        el = _make_element("unknown", element_type="cursor")
        sqls = self._convert(self._make_result([el]))
        assert sqls == []

    def test_sql_element_passthrough(self):
        table = SQLTable(
            name="existing",
            start_line=1,
            end_line=5,
            raw_text="CREATE TABLE existing (id INT);",
            language="sql",
        )
        sqls = self._convert(self._make_result([table]))
        assert len(sqls) == 1
        assert sqls[0] is table

    def test_extractor_populates_columns(self):
        el = _make_element(
            "users", element_type="table", raw_text="CREATE TABLE users (id INT);"
        )

        def extract_columns(raw_text, name):
            return {"columns": ["id", "name"], "constraints": ["PRIMARY KEY"]}

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=extract_columns,
            extract_view_info=_noop_extractor,
            extract_procedure_info=_noop_extractor,
            extract_function_info=_noop_extractor,
            extract_trigger_info=_noop_extractor,
            extract_index_info=_noop_extractor,
        )
        assert sqls[0].columns == ["id", "name"]
        assert sqls[0].constraints == ["PRIMARY KEY"]

    def test_view_extractor_populates_source_tables(self):
        el = _make_element(
            "v", element_type="view", raw_text="CREATE VIEW v AS SELECT * FROM t1;"
        )

        def extract_view(raw_text, name):
            return {"source_tables": ["t1"], "columns": ["id"]}

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=extract_view,
            extract_procedure_info=_noop_extractor,
            extract_function_info=_noop_extractor,
            extract_trigger_info=_noop_extractor,
            extract_index_info=_noop_extractor,
        )
        assert isinstance(sqls[0], SQLView)
        assert sqls[0].source_tables == ["t1"]
        assert sqls[0].dependencies == ["t1"]

    def test_procedure_extractor_populates_params(self):
        el = _make_element(
            "sp", element_type="procedure", raw_text="CREATE PROCEDURE sp() BEGIN END"
        )

        def extract_proc(raw_text, name):
            return {"parameters": ["p1"], "dependencies": ["t1"]}

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=_noop_extractor,
            extract_procedure_info=extract_proc,
            extract_function_info=_noop_extractor,
            extract_trigger_info=_noop_extractor,
            extract_index_info=_noop_extractor,
        )
        assert isinstance(sqls[0], SQLProcedure)
        assert sqls[0].parameters == ["p1"]
        assert sqls[0].dependencies == ["t1"]

    def test_function_extractor_populates_return_type(self):
        el = _make_element(
            "fn",
            element_type="sql_function",
            raw_text="CREATE FUNCTION fn() RETURNS INT",
        )

        def extract_fn(raw_text, name):
            return {"parameters": [], "return_type": "INT", "dependencies": []}

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=_noop_extractor,
            extract_procedure_info=_noop_extractor,
            extract_function_info=extract_fn,
            extract_trigger_info=_noop_extractor,
            extract_index_info=_noop_extractor,
        )
        assert isinstance(sqls[0], SQLFunction)
        assert sqls[0].return_type == "INT"

    def test_trigger_extractor_populates_timing(self):
        el = _make_element(
            "trg",
            element_type="trigger",
            raw_text="CREATE TRIGGER trg BEFORE UPDATE ON t FOR EACH ROW",
        )

        def extract_trg(raw_text, name):
            return {
                "timing": "BEFORE",
                "event": "UPDATE",
                "table_name": "t",
                "dependencies": ["t"],
            }

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=_noop_extractor,
            extract_procedure_info=_noop_extractor,
            extract_function_info=_noop_extractor,
            extract_trigger_info=extract_trg,
            extract_index_info=_noop_extractor,
        )
        assert isinstance(sqls[0], SQLTrigger)
        assert sqls[0].trigger_timing == "BEFORE"
        assert sqls[0].trigger_event == "UPDATE"
        assert sqls[0].table_name == "t"

    def test_index_extractor_populates_unique(self):
        el = _make_element(
            "idx", element_type="index", raw_text="CREATE UNIQUE INDEX idx ON t (c)"
        )

        def extract_idx(raw_text, name):
            return {"table_name": "t", "columns": ["c"], "is_unique": True}

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=_noop_extractor,
            extract_procedure_info=_noop_extractor,
            extract_function_info=_noop_extractor,
            extract_trigger_info=_noop_extractor,
            extract_index_info=extract_idx,
        )
        assert isinstance(sqls[0], SQLIndex)
        assert sqls[0].is_unique is True
        assert sqls[0].indexed_columns == ["c"]
        assert sqls[0].dependencies == ["t"]

    def test_index_no_table_name_no_dependency(self):
        el = _make_element(
            "idx", element_type="index", raw_text="CREATE INDEX idx ON t (c)"
        )

        def extract_idx(raw_text, name):
            return {"table_name": "", "columns": [], "is_unique": False}

        result = self._make_result([el])
        sqls = convert_analysis_result_to_sql_elements(
            result,
            extract_table_columns=_noop_extractor,
            extract_view_info=_noop_extractor,
            extract_procedure_info=_noop_extractor,
            extract_function_info=_noop_extractor,
            extract_trigger_info=_noop_extractor,
            extract_index_info=extract_idx,
        )
        assert sqls[0].dependencies == []

    def test_multiple_elements(self):
        elements = [
            _make_element("users", element_type="table"),
            _make_element("v", element_type="view"),
            _make_element("sp", element_type="procedure"),
        ]
        sqls = self._convert(self._make_result(elements))
        assert len(sqls) == 3
        assert isinstance(sqls[0], SQLTable)
        assert isinstance(sqls[1], SQLView)
        assert isinstance(sqls[2], SQLProcedure)

    def test_empty_elements(self):
        sqls = self._convert(self._make_result([]))
        assert sqls == []


class TestCreateSqlElementFromDict:
    def test_table(self):
        result = create_sql_element_from_dict(
            {
                "type": "table",
                "name": "t",
                "start_line": 1,
                "end_line": 5,
                "raw_text": "CREATE TABLE t (id INT);",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLTable)
        assert result.name == "t"

    def test_create_table_prefix(self):
        result = create_sql_element_from_dict(
            {
                "type": "create_table",
                "name": "ct",
                "start_line": 1,
                "end_line": 5,
                "raw_text": "CREATE TABLE ct (id INT);",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLTable)
        assert result.name == "ct"

    def test_view(self):
        result = create_sql_element_from_dict(
            {
                "type": "view",
                "name": "v",
                "start_line": 1,
                "end_line": 3,
                "raw_text": "CREATE VIEW v AS SELECT 1;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLView)

    def test_create_view_prefix(self):
        result = create_sql_element_from_dict(
            {
                "type": "create_view",
                "name": "cv",
                "start_line": 1,
                "end_line": 3,
                "raw_text": "CREATE VIEW cv AS SELECT 1;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLView)

    def test_procedure(self):
        result = create_sql_element_from_dict(
            {
                "type": "procedure",
                "name": "sp",
                "start_line": 1,
                "end_line": 10,
                "raw_text": "CREATE PROCEDURE sp() BEGIN END;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLProcedure)

    def test_create_procedure_prefix(self):
        result = create_sql_element_from_dict(
            {
                "type": "create_procedure",
                "name": "csp",
                "start_line": 1,
                "end_line": 10,
                "raw_text": "CREATE PROCEDURE csp() BEGIN END;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLProcedure)

    def test_function(self):
        result = create_sql_element_from_dict(
            {
                "type": "function",
                "name": "fn",
                "start_line": 1,
                "end_line": 8,
                "raw_text": "CREATE FUNCTION fn() RETURNS INT;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLFunction)

    def test_create_function_prefix(self):
        result = create_sql_element_from_dict(
            {
                "type": "create_function",
                "name": "cfn",
                "start_line": 1,
                "end_line": 8,
                "raw_text": "CREATE FUNCTION cfn() RETURNS INT;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLFunction)

    def test_trigger(self):
        result = create_sql_element_from_dict(
            {
                "type": "trigger",
                "name": "trg",
                "start_line": 1,
                "end_line": 6,
                "raw_text": "CREATE TRIGGER trg BEFORE UPDATE ON t;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLTrigger)

    def test_create_trigger_prefix(self):
        result = create_sql_element_from_dict(
            {
                "type": "create_trigger",
                "name": "ctrg",
                "start_line": 1,
                "end_line": 6,
                "raw_text": "CREATE TRIGGER ctrg BEFORE UPDATE ON t;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLTrigger)

    def test_index(self):
        result = create_sql_element_from_dict(
            {
                "type": "index",
                "name": "idx",
                "start_line": 1,
                "end_line": 1,
                "raw_text": "CREATE INDEX idx ON t (c);",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLIndex)

    def test_create_index_prefix(self):
        result = create_sql_element_from_dict(
            {
                "type": "create_index",
                "name": "cidx",
                "start_line": 1,
                "end_line": 1,
                "raw_text": "CREATE INDEX cidx ON t (c);",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLIndex)

    def test_unknown_type_falls_back_to_table(self):
        result = create_sql_element_from_dict(
            {
                "type": "unknown",
                "name": "x",
                "start_line": 1,
                "end_line": 1,
                "raw_text": "SOME SQL;",
                "language": "sql",
            }
        )
        assert isinstance(result, SQLTable)
        assert result.name == "x"

    def test_exception_returns_none(self):
        result = create_sql_element_from_dict(None)
        assert result is None

    def test_missing_fields_uses_defaults(self):
        result = create_sql_element_from_dict({"type": "table"})
        assert isinstance(result, SQLTable)
        assert result.name == "unknown"
        assert result.start_line == 0
        assert result.end_line == 0
        assert result.raw_text == ""
        assert result.language == "sql"

    def test_all_dict_factory_types_produce_correct_classes(self):
        type_expected = {
            "table": SQLTable,
            "view": SQLView,
            "procedure": SQLProcedure,
            "function": SQLFunction,
            "trigger": SQLTrigger,
            "index": SQLIndex,
        }
        for type_name, expected_cls in type_expected.items():
            result = create_sql_element_from_dict(
                {
                    "type": type_name,
                    "name": f"test_{type_name}",
                }
            )
            assert isinstance(result, expected_cls), f"Failed for {type_name}"
