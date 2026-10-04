from csv_agent.evidence import Evidence, extract_evidence
from csv_agent.table import Table
from csv_agent.tools import CsvTools

TABLE = Table(
    columns=["name", "category", "stock"],
    rows=[
        {"name": "マウス", "category": "周辺機器", "stock": "0"},
        {"name": "モニター", "category": "ディスプレイ", "stock": "12"},
        {"name": "キーボード", "category": "周辺機器", "stock": "35"},
    ],
)
TOOLS = CsvTools(TABLE)


def evidence(name: str, **arguments: object) -> Evidence:
    return extract_evidence(TABLE, name, arguments, TOOLS.call(name, arguments))


def test_search_rows_marks_returned_rows_without_cells() -> None:
    result = evidence("search_rows", query="モニター", limit=1)

    assert result == Evidence(rows={2}, cells=set())


def test_filter_rows_marks_returned_rows_and_tested_column() -> None:
    result = evidence("filter_rows", column="stock", operator="==", value="0")

    assert result == Evidence(rows={1}, cells={(1, "stock")})


def test_aggregate_min_marks_picked_row_and_column() -> None:
    result = evidence("aggregate", column="stock", operation="min")

    assert result == Evidence(rows={1}, cells={(1, "stock")})


def test_aggregate_sum_with_filter_marks_filtered_rows_and_both_columns() -> None:
    result = evidence("aggregate", column="stock", operation="sum", filter_column="category", filter_value="周辺機器")

    assert result == Evidence(rows={1, 3}, cells={(1, "stock"), (3, "stock"), (1, "category"), (3, "category")})


def test_aggregate_count_without_filter_marks_all_rows() -> None:
    result = evidence("aggregate", column="name", operation="count")

    assert result.rows == {1, 2, 3}


def test_error_result_has_no_evidence() -> None:
    result = evidence("filter_rows", column="missing", operator="==", value="0")

    assert result == Evidence(rows=set(), cells=set())


def test_get_schema_has_no_evidence() -> None:
    assert evidence("get_schema") == Evidence(rows=set(), cells=set())
