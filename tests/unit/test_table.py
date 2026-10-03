from pathlib import Path

import pytest

from csv_agent.table import Table


def write_csv(tmp_path: Path, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / "data.csv"
    path.write_text(text, encoding=encoding)
    return path


def test_from_csv_reads_header_and_rows(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "name,price\nりんご,100\nみかん,80\n")

    table = Table.from_csv(path)

    assert table.columns == ["name", "price"]
    assert table.rows == [
        {"name": "りんご", "price": "100"},
        {"name": "みかん", "price": "80"},
    ]


def test_from_csv_strips_utf8_bom_from_first_column(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "name,price\nりんご,100\n", encoding="utf-8-sig")

    table = Table.from_csv(path)

    assert table.columns == ["name", "price"]


def test_from_csv_rejects_file_without_header(tmp_path: Path) -> None:
    path = write_csv(tmp_path, "")

    with pytest.raises(ValueError):
        Table.from_csv(path)


def test_row_text_joins_column_value_pairs() -> None:
    table = Table(columns=["name", "price"], rows=[{"name": "りんご", "price": "100"}])

    assert table.row_text(0) == "name: りんご | price: 100"
