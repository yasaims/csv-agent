import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[dict[str, str]]

    @classmethod
    def from_csv(cls, path: str | Path) -> "Table":
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError(f"CSV has no header row: {path}")
            columns = list(reader.fieldnames)
            rows = [{col: row.get(col) or "" for col in columns} for row in reader]
        return cls(columns=columns, rows=rows)

    def row_text(self, index: int) -> str:
        row = self.rows[index]
        return " | ".join(f"{col}: {row[col]}" for col in self.columns)
