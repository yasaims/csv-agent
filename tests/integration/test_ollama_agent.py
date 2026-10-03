"""End-to-end checks against a real local Ollama server. Run with: uv run pytest -m ollama"""

import re
from pathlib import Path

import ollama
import pytest

from csv_agent.agent import DEFAULT_MODEL, CsvAgent
from csv_agent.table import Table

pytestmark = pytest.mark.ollama

PRODUCTS_CSV = Path(__file__).parents[2] / "data" / "products.csv"


@pytest.fixture(scope="module")
def table() -> Table:
    try:
        ollama.Client().show(DEFAULT_MODEL)
    except (ConnectionError, ollama.ResponseError) as e:
        pytest.skip(f"Ollama model {DEFAULT_MODEL} is not available: {e}")
    return Table.from_csv(PRODUCTS_CSV)


def digits_only(text: str) -> str:
    return re.sub(r"[,，]", "", text)


def test_answers_lookup_from_retrieved_row(table: Table) -> None:
    answer = CsvAgent(table).ask("ポータブルSSDの価格はいくらですか?")

    assert "15800" in digits_only(answer)


def test_answers_aggregate_question_exactly(table: Table) -> None:
    answer = CsvAgent(table).ask("オーディオカテゴリの商品の在庫数の合計は?")

    assert "20" in digits_only(answer)


def test_lists_rows_matching_condition(table: Table) -> None:
    answer = CsvAgent(table).ask("在庫が0の商品の名前を教えてください。")

    assert "スマートスピーカー" in answer
