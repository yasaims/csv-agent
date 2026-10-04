import json
import subprocess
from pathlib import Path

import ollama
import pytest

from csv_agent.evaluation import EvalCase, is_correct, load_cases, main, run_case
from csv_agent.table import Table
from tests.unit.fakes import ScriptedClient, answer, tool_call

PRODUCTS_CASES = Path(__file__).parents[2] / "evals" / "products.json"


@pytest.fixture
def table(tmp_path: Path) -> Table:
    path = tmp_path / "data.csv"
    path.write_text("name,price\nマウス,2980\n", encoding="utf-8")
    return Table.from_csv(path)


def test_is_correct_requires_all_keywords_and_ignores_thousands_separators() -> None:
    assert is_correct("価格は2,980円です", ["2980"])
    assert not is_correct("価格は2,980円です", ["2980", "マウス"])


def test_bundled_cases_load() -> None:
    assert load_cases(PRODUCTS_CASES)


def test_run_case_records_pass_and_tools(table: Table) -> None:
    client = ScriptedClient(tool_call("search_rows", {"query": "マウス"}), answer("2980円です"))
    case = EvalCase(id="c", question="q", expected=["2980"], expected_tools=["search_rows"])

    result = run_case(table, case, "m", 0, client=client)

    assert result.passed and result.used_expected_tools
    assert result.tools_called == ["search_rows"]


def test_run_case_records_error_as_failure(table: Table) -> None:
    case = EvalCase(id="c", question="q", expected=["2980"])

    result = run_case(table, case, "m", 0, client=ScriptedClient(ollama.ResponseError("down", 500)))

    assert not result.passed and "down" in (result.error or "")


def test_main_runs_every_model_and_writes_jsonl(table: Table, tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps([{"id": "c", "question": "q", "expected": ["2980"]}]), encoding="utf-8")
    output = tmp_path / "out.jsonl"
    client = ScriptedClient(answer("2980"), answer("2980"), answer("x"), answer("x"))

    exit_code = main(
        [str(csv_path), str(cases_path), "--models", "a", "b", "--repeats", "2", "-o", str(output)], client=client
    )

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert exit_code == 0
    assert [(r["model"], r["passed"]) for r in records] == [("a", True), ("a", True), ("b", False), ("b", False)]


def test_record_saves_run_and_registers_then_resets_baseline(
    table: Table, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    Path("cases.json").write_text(json.dumps([{"id": "c", "question": "q", "expected": ["2980"]}]), encoding="utf-8")
    args = ["data.csv", "cases.json", "--models", "a"]

    assert main([*args, "--record"], client=ScriptedClient(answer("2980"))) == 0
    assert main([*args, "--reset-baseline", "new rules"], client=ScriptedClient(answer("x"))) == 0

    baseline = json.loads(Path("evals/records/baseline.json").read_text(encoding="utf-8"))
    assert len(list(Path("evals/records/runs").glob("*.json"))) == 2
    assert baseline["a"]["accuracy"] == 0 and baseline["a"]["reason"] == "new rules"
    out = capsys.readouterr().out
    assert "Baseline registered: a" in out and "Baseline RESET: a" in out


def test_record_refuses_when_every_run_of_a_model_failed(
    table: Table, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("cases.json").write_text(json.dumps([{"id": "c", "question": "q", "expected": ["2980"]}]), encoding="utf-8")

    exit_code = main(
        ["data.csv", "cases.json", "--models", "a", "--record"],
        client=ScriptedClient(ollama.ResponseError("down", 500)),
    )

    assert exit_code == 1
    assert not Path("evals/records").exists()
