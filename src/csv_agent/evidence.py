import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from csv_agent.table import Table


@dataclass
class Evidence:
    """CSV rows (1-based) and (row, column) cells a tool call relied on."""

    rows: set[int] = field(default_factory=set)
    cells: set[tuple[int, str]] = field(default_factory=set)

    def update(self, other: "Evidence") -> None:
        self.rows |= other.rows
        self.cells |= other.cells

    def to_json(self) -> dict[str, Any]:
        return {"rows": sorted(self.rows), "cells": [list(cell) for cell in sorted(self.cells)]}


def _row_numbers(rows: list[dict[str, Any]]) -> set[int]:
    return {row["row"] for row in rows if isinstance(row.get("row"), int)}


def _cells(rows: set[int], *columns: str) -> set[tuple[int, str]]:
    return {(row, column) for row in rows for column in columns if column}


def extract_evidence(table: Table, tool_name: str, arguments: Mapping[str, Any], result: str) -> Evidence:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return Evidence()
    if isinstance(data, dict) and "error" in data:
        return Evidence()

    match tool_name:
        case "search_rows" if isinstance(data, list):
            return Evidence(rows=_row_numbers(data))
        case "filter_rows":
            rows = _row_numbers(data.get("rows", []))
            return Evidence(rows=rows, cells=_cells(rows, arguments["column"]))
        case "aggregate" if "row" in data:
            rows = _row_numbers([data["row"]])
            return Evidence(rows=rows, cells=_cells(rows, arguments["column"]))
        case "aggregate":
            filter_column = arguments.get("filter_column", "")
            filter_value = arguments.get("filter_value", "")
            rows = {
                i + 1 for i, row in enumerate(table.rows) if not filter_column or row[filter_column] == filter_value
            }
            return Evidence(rows=rows, cells=_cells(rows, arguments["column"], filter_column))
    return Evidence()
