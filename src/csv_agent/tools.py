import json
import operator as op
from collections.abc import Callable, Mapping
from statistics import mean
from typing import Any

from csv_agent.retriever import Retriever
from csv_agent.table import Table

OPERATIONS = ("count", "sum", "mean", "min", "max")
NUMERIC_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">": op.gt,
    ">=": op.ge,
    "<": op.lt,
    "<=": op.le,
}
TEXT_OPERATORS: dict[str, Callable[[str, str], bool]] = {
    "==": op.eq,
    "!=": op.ne,
    "contains": lambda cell, value: value.lower() in cell.lower(),
}


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _error(message: str) -> str:
    return _to_json({"error": message})


def _parse_number(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _clean_number(value: float) -> int | float:
    value = round(value, 2)
    return int(value) if value.is_integer() else value


class CsvTools:
    """Tools the agent can call. Every tool returns a JSON string, including errors."""

    def __init__(self, table: Table) -> None:
        self._table = table
        self._retriever = Retriever([table.row_text(i) for i in range(len(table.rows))]) if table.rows else None

    @property
    def functions(self) -> list[Callable[..., str]]:
        return [self.get_schema, self.search_rows, self.filter_rows, self.aggregate]

    def _numbered_row(self, index: int) -> dict[str, Any]:
        return {"row": index + 1, **self._table.rows[index]}

    def _unknown_column(self, column: str) -> str:
        return _error(f"Unknown column: {column}. Available columns: {self._table.columns}")

    def call(self, name: str, arguments: Mapping[str, Any]) -> str:
        function = next((f for f in self.functions if f.__name__ == name), None)
        if function is None:
            return _error(f"Unknown tool: {name}")
        try:
            return function(**arguments)
        except TypeError as e:
            return _error(f"Invalid arguments for {name}: {e}")

    def get_schema(self) -> str:
        """Get the column names, column types, example values and row count of the CSV.

        Returns:
            JSON describing the CSV structure.
        """
        columns = []
        for col in self._table.columns:
            values = [row[col] for row in self._table.rows if row[col].strip()]
            is_number = bool(values) and all(_parse_number(v) is not None for v in values)
            columns.append(
                {"name": col, "type": "number" if is_number else "text", "examples": list(dict.fromkeys(values))[:3]}
            )
        return _to_json({"row_count": len(self._table.rows), "columns": columns})

    def search_rows(self, query: str, limit: int = 5) -> str:
        """Search CSV rows relevant to a keyword query.

        Args:
            query: Keywords to look for, such as product names or categories.
            limit: Maximum number of rows to return.

        Returns:
            JSON list of matching rows with their 1-based row numbers.
        """
        if self._retriever is None:
            return _to_json([])
        indices = self._retriever.search(query, k=int(limit))
        return _to_json([self._numbered_row(i) for i in indices])

    def filter_rows(self, column: str, operator: str, value: str, limit: int = 20) -> str:
        """Return all rows whose column satisfies a condition. Numbers are compared numerically.

        Args:
            column: Column to test.
            operator: One of ==, !=, >, >=, <, <=, contains.
            value: Value to compare against.
            limit: Maximum number of rows to return.

        Returns:
            JSON with the total number of matched rows and the matching rows with their 1-based row numbers.
        """
        if column not in self._table.columns:
            return self._unknown_column(column)

        if operator in TEXT_OPERATORS:
            text_test = TEXT_OPERATORS[operator]
            matches = [i for i, row in enumerate(self._table.rows) if text_test(row[column].strip(), value.strip())]
        elif operator in NUMERIC_OPERATORS:
            target = _parse_number(value)
            if target is None:
                return _error(f"Value {value!r} is not numeric")
            numeric_test = NUMERIC_OPERATORS[operator]
            matches = []
            for i, row in enumerate(self._table.rows):
                if not row[column].strip():
                    continue
                cell = _parse_number(row[column])
                if cell is None:
                    return _error(f"Column {column} is not numeric")
                if numeric_test(cell, target):
                    matches.append(i)
        else:
            return _error(f"Unknown operator: {operator}. Use one of {[*TEXT_OPERATORS, *NUMERIC_OPERATORS]}")

        rows = [self._numbered_row(i) for i in matches[: int(limit)]]
        return _to_json({"matched_rows": len(matches), "rows": rows})

    def aggregate(self, column: str, operation: str, filter_column: str = "", filter_value: str = "") -> str:
        """Compute an exact aggregate over a column, optionally on rows where filter_column equals filter_value.

        Args:
            column: Column to aggregate.
            operation: One of count, sum, mean, min, max.
            filter_column: Optional column used to filter rows. Empty string means no filter.
            filter_value: Value that filter_column must equal exactly.

        Returns:
            JSON with the result. min and max also include the matching row.
        """
        for col in (column, filter_column):
            if col and col not in self._table.columns:
                return self._unknown_column(col)
        if operation not in OPERATIONS:
            return _error(f"Unknown operation: {operation}. Use one of {list(OPERATIONS)}")

        rows = self._table.rows
        matches = [i for i, row in enumerate(rows) if not filter_column or row[filter_column] == filter_value]
        result: dict[str, Any] = {"column": column, "operation": operation, "matched_rows": len(matches)}
        if operation == "count":
            return _to_json(result | {"result": len(matches)})

        non_empty = [i for i in matches if rows[i][column].strip()]
        numbered = [(n, i) for i in non_empty if (n := _parse_number(rows[i][column])) is not None]
        if len(numbered) < len(non_empty):
            return _error(f"Column {column} is not numeric")
        if not numbered:
            return _error("No rows matched the filter")

        numbers = [n for n, _ in numbered]
        match operation:
            case "sum":
                result["result"] = _clean_number(sum(numbers))
            case "mean":
                result["result"] = _clean_number(mean(numbers))
            case "min" | "max":
                pick = min if operation == "min" else max
                value, i = pick(numbered, key=lambda pair: pair[0])
                result |= {"result": _clean_number(value), "row": self._numbered_row(i)}
        return _to_json(result)
