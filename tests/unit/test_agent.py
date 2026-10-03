import json
from typing import Any

import pytest

from csv_agent.agent import DEFAULT_MODEL, AgentStepLimitError, CsvAgent
from csv_agent.table import Table
from tests.unit.fakes import ScriptedClient, answer, tool_call

TABLE = Table(
    columns=["name", "price"],
    rows=[{"name": "マウス", "price": "2980"}, {"name": "モニター", "price": "32800"}],
)


def test_default_model_is_qwen35_9b() -> None:
    client = ScriptedClient(answer("ok"))

    CsvAgent(TABLE, client=client).ask("質問")

    assert DEFAULT_MODEL == "qwen3.5:9b"
    assert client.requests[0]["model"] == "qwen3.5:9b"


def test_ask_returns_model_answer_when_no_tool_is_called() -> None:
    agent = CsvAgent(TABLE, client=ScriptedClient(answer("2件です")))

    assert agent.ask("何件?") == "2件です"


def test_system_prompt_includes_csv_columns() -> None:
    client = ScriptedClient(answer("ok"))

    CsvAgent(TABLE, client=client).ask("質問")

    system = client.requests[0]["messages"][0]
    assert system["role"] == "system"
    assert "name" in system["content"] and "price" in system["content"]


def test_agent_offers_csv_tools_to_model() -> None:
    client = ScriptedClient(answer("ok"))

    CsvAgent(TABLE, client=client).ask("質問")

    assert [f.__name__ for f in client.requests[0]["tools"]] == ["get_schema", "search_rows", "filter_rows", "aggregate"]


def test_tool_result_is_sent_back_before_final_answer() -> None:
    client = ScriptedClient(
        tool_call("aggregate", {"column": "price", "operation": "max"}),
        answer("最も高いのはモニターです"),
    )

    result = CsvAgent(TABLE, client=client).ask("一番高い商品は?")

    assert result == "最も高いのはモニターです"
    tool_message = client.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_name"] == "aggregate"
    assert json.loads(tool_message["content"])["row"]["name"] == "モニター"


def test_on_tool_call_receives_name_arguments_and_result() -> None:
    seen: list[tuple[str, dict[str, Any], str]] = []
    client = ScriptedClient(tool_call("get_schema", {}), answer("ok"))

    CsvAgent(TABLE, client=client, on_tool_call=lambda *args: seen.append(args)).ask("質問")

    assert seen[0][0] == "get_schema"
    assert seen[0][1] == {}
    assert json.loads(seen[0][2])["row_count"] == 2


def test_ask_raises_when_step_limit_is_exceeded() -> None:
    client = ScriptedClient(*[tool_call("get_schema", {}) for _ in range(3)])
    agent = CsvAgent(TABLE, client=client, max_steps=3)

    with pytest.raises(AgentStepLimitError):
        agent.ask("質問")


def test_follow_up_question_keeps_previous_turns() -> None:
    client = ScriptedClient(answer("マウスです"), answer("2980円です"))
    agent = CsvAgent(TABLE, client=client)

    agent.ask("安い商品は?")
    agent.ask("その価格は?")

    contents = [m["content"] for m in client.requests[1]["messages"]]
    assert contents[-3:] == ["安い商品は?", "マウスです", "その価格は?"]
