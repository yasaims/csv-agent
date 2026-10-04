import io
from pathlib import Path

import ollama
import pytest

from csv_agent.cli import main
from tests.unit.fakes import ScriptedClient, answer, tool_call


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "data.csv"
    path.write_text("name,price\nマウス,2980\n", encoding="utf-8")
    return path


def test_question_argument_prints_single_answer(csv_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(csv_path), "安い商品は?"], client=ScriptedClient(answer("マウスです")))

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "マウスです"


def test_model_option_is_passed_to_client(csv_path: Path) -> None:
    client = ScriptedClient(answer("ok"))

    main([str(csv_path), "q", "--model", "qwen3.5:4b"], client=client)

    assert client.requests[0]["model"] == "qwen3.5:4b"


def test_verbose_option_prints_tool_calls_to_stderr(csv_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = ScriptedClient(tool_call("search_rows", {"query": "マウス"}), answer("ok"))

    main([str(csv_path), "q", "-v"], client=client)

    assert "search_rows" in capsys.readouterr().err


def test_without_question_answers_each_line_until_exit(
    csv_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("一つ目\n\n二つ目\nexit\n三つ目\n"))
    client = ScriptedClient(answer("回答1"), answer("回答2"))

    exit_code = main([str(csv_path)], client=client)

    assert exit_code == 0
    assert len(client.requests) == 2
    out = capsys.readouterr().out
    assert "回答1" in out and "回答2" in out


def test_missing_csv_file_returns_error_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(tmp_path / "missing.csv"), "q"], client=ScriptedClient())

    assert exit_code == 1
    assert "missing.csv" in capsys.readouterr().err


def test_unreachable_ollama_returns_error_code(csv_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(csv_path), "q"], client=ScriptedClient(ConnectionError("refused")))

    assert exit_code == 1
    assert "refused" in capsys.readouterr().err


def test_ollama_server_error_returns_error_code(csv_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(csv_path), "q"], client=ScriptedClient(ollama.ResponseError("bad tool call", 500)))

    assert exit_code == 1
    assert "bad tool call" in capsys.readouterr().err


def test_interactive_session_continues_after_ollama_server_error(
    csv_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("一つ目\n二つ目\n"))
    client = ScriptedClient(ollama.ResponseError("bad tool call", 500), answer("回答2"))

    exit_code = main([str(csv_path)], client=client)

    assert exit_code == 0
    assert "回答2" in capsys.readouterr().out
