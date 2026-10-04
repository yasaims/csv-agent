import json
from typing import Any

import ollama
from fastapi.testclient import TestClient

from csv_agent.gui.server import create_app
from csv_agent.table import Table
from tests.unit.fakes import ScriptedClient, answer, tool_call

TABLE = Table(
    columns=["name", "stock"],
    rows=[{"name": "マウス", "stock": "0"}, {"name": "モニター", "stock": "12"}],
)


def make_client(*responses: Any) -> TestClient:
    return TestClient(create_app(TABLE, client=ScriptedClient(*responses), model="test-model", context_limit=lambda: 4096))


def ask(client: TestClient, question: str) -> list[dict[str, Any]]:
    response = client.post("/api/ask", json={"question": question})
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_table_endpoint_returns_columns_and_rows() -> None:
    response = make_client().get("/api/table")

    assert response.json() == {"columns": ["name", "stock"], "rows": TABLE.rows}


def test_status_endpoint_returns_model_and_context() -> None:
    response = make_client().get("/api/status")

    assert response.json() == {"model": "test-model", "context_limit": 4096, "context_tokens": 0}


def test_ask_streams_tool_event_then_answer_with_evidence() -> None:
    final = answer("マウスです")
    final.prompt_eval_count, final.eval_count = 300, 5
    client = make_client(tool_call("filter_rows", {"column": "stock", "operator": "==", "value": "0"}), final)

    events = ask(client, "在庫0は?")

    assert [e["type"] for e in events] == ["tool", "answer"]
    assert events[0]["name"] == "filter_rows"
    assert events[0]["evidence"] == {"rows": [1], "cells": [[1, "stock"]]}
    assert events[1] == {
        "type": "answer",
        "content": "マウスです",
        "evidence": {"rows": [1], "cells": [[1, "stock"]]},
        "context_tokens": 305,
        "context_limit": 4096,
    }


def test_ask_streams_error_event_when_model_fails() -> None:
    events = ask(make_client(ollama.ResponseError("model not found")), "質問")

    assert events[-1]["type"] == "error"
    assert "model not found" in events[-1]["message"]


def test_index_page_is_served() -> None:
    response = make_client().get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_reset_endpoint_starts_a_new_conversation() -> None:
    first = answer("ok")
    first.prompt_eval_count = 100
    client = make_client(first)
    ask(client, "質問")

    assert client.post("/api/reset").status_code == 204
    assert client.get("/api/status").json()["context_tokens"] == 0
