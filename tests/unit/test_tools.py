import json

import pytest

from csv_agent.table import Table
from csv_agent.tools import CsvTools

TABLE = Table(
    columns=["name", "category", "price"],
    rows=[
        {"name": "ワイヤレスマウス", "category": "周辺機器", "price": "2980"},
        {"name": "4Kモニター", "category": "ディスプレイ", "price": "54800"},
        {"name": "USB-Cハブ", "category": "周辺機器", "price": "4580"},
    ],
)


@pytest.fixture
def tools() -> CsvTools:
    return CsvTools(TABLE)


def test_get_schema_reports_row_count_and_column_types(tools: CsvTools) -> None:
    schema = json.loads(tools.get_schema())

    assert schema["row_count"] == 3
    assert [(c["name"], c["type"]) for c in schema["columns"]] == [
        ("name", "text"),
        ("category", "text"),
        ("price", "number"),
    ]


def test_search_rows_returns_matching_rows_with_one_based_row_numbers(tools: CsvTools) -> None:
    results = json.loads(tools.search_rows("モニター"))

    assert results[0] == {"row": 2, "name": "4Kモニター", "category": "ディスプレイ", "price": "54800"}


def test_search_rows_respects_limit(tools: CsvTools) -> None:
    assert len(json.loads(tools.search_rows("周辺機器", limit=1))) == 1


def test_search_rows_on_empty_table_returns_empty_list() -> None:
    tools = CsvTools(Table(columns=["name"], rows=[]))

    assert json.loads(tools.search_rows("anything")) == []


@pytest.mark.parametrize(
    ("column", "operator", "value", "expected_rows"),
    [
        ("category", "==", "周辺機器", [1, 3]),
        ("category", "!=", "周辺機器", [2]),
        ("price", ">", "4580", [2]),
        ("price", "<=", "4580", [1, 3]),
        ("name", "contains", "モニター", [2]),
    ],
)
def test_filter_rows_returns_rows_satisfying_condition(
    tools: CsvTools, column: str, operator: str, value: str, expected_rows: list[int]
) -> None:
    result = json.loads(tools.filter_rows(column, operator, value))

    assert [row["row"] for row in result["rows"]] == expected_rows
    assert result["matched_rows"] == len(expected_rows)


def test_filter_rows_compares_numbers_numerically(tools: CsvTools) -> None:
    # "54800" < "9000" as strings, so a string comparison would return no rows.
    result = json.loads(tools.filter_rows("price", ">", "9000"))

    assert [row["name"] for row in result["rows"]] == ["4Kモニター"]


def test_filter_rows_limit_truncates_rows_but_reports_total(tools: CsvTools) -> None:
    result = json.loads(tools.filter_rows("category", "==", "周辺機器", limit=1))

    assert len(result["rows"]) == 1
    assert result["matched_rows"] == 2


@pytest.mark.parametrize(
    ("args", "message_part"),
    [
        (("unknown", "==", "x"), "Unknown column"),
        (("price", "~", "1"), "Unknown operator"),
        (("name", ">", "1"), "numeric"),
    ],
)
def test_filter_rows_reports_errors_as_json(tools: CsvTools, args: tuple[str, ...], message_part: str) -> None:
    result = json.loads(tools.filter_rows(*args))

    assert message_part in result["error"]


def test_aggregate_count_applies_equality_filter(tools: CsvTools) -> None:
    result = json.loads(tools.aggregate("name", "count", "category", "周辺機器"))

    assert result["result"] == 2


@pytest.mark.parametrize(("operation", "expected"), [("sum", 62360), ("mean", 20786.67), ("min", 2980)])
def test_aggregate_numeric_operations(tools: CsvTools, operation: str, expected: float) -> None:
    result = json.loads(tools.aggregate("price", operation))

    assert result["result"] == expected


def test_aggregate_max_includes_the_matching_row(tools: CsvTools) -> None:
    result = json.loads(tools.aggregate("price", "max"))

    assert result["result"] == 54800
    assert result["row"] == {"row": 2, "name": "4Kモニター", "category": "ディスプレイ", "price": "54800"}


@pytest.mark.parametrize(
    ("args", "message_part"),
    [
        (("unknown", "count"), "Unknown column"),
        (("price", "median"), "Unknown operation"),
        (("name", "sum"), "not numeric"),
        (("price", "max", "category", "食品"), "No rows"),
    ],
)
def test_aggregate_reports_errors_as_json(tools: CsvTools, args: tuple[str, ...], message_part: str) -> None:
    result = json.loads(tools.aggregate(*args))

    assert message_part in result["error"]


def test_call_dispatches_by_tool_name(tools: CsvTools) -> None:
    result = json.loads(tools.call("aggregate", {"column": "price", "operation": "min"}))

    assert result["result"] == 2980


@pytest.mark.parametrize(
    ("name", "arguments"),
    [("drop_table", {}), ("aggregate", {"col": "price"})],
)
def test_call_reports_invalid_calls_as_json_error(tools: CsvTools, name: str, arguments: dict[str, object]) -> None:
    result = json.loads(tools.call(name, arguments))

    assert "error" in result


def test_functions_are_exposed_by_name(tools: CsvTools) -> None:
    assert [f.__name__ for f in tools.functions] == ["get_schema", "search_rows", "filter_rows", "aggregate"]
