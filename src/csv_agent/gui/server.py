import argparse
import asyncio
import json
import threading
import webbrowser
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

import ollama
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from csv_agent.agent import DEFAULT_MODEL, AgentStepLimitError, ChatClient, CsvAgent
from csv_agent.evidence import Evidence, extract_evidence
from csv_agent.table import Table

STATIC_DIR = Path(__file__).parent / "static"

ContextLimit = Callable[[], int | None]


class Question(BaseModel):
    question: str


def lookup_context_limit(model: str) -> int | None:
    """Context length of the loaded model, else the model's trained maximum, else None."""
    try:
        for loaded in ollama.ps().models:
            if loaded.model == model and loaded.context_length:
                return loaded.context_length
        info = ollama.show(model).modelinfo or {}
    except (ConnectionError, ollama.ResponseError):
        return None
    return next((int(v) for k, v in info.items() if k.endswith(".context_length")), None)


def _line(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode()


def create_app(
    table: Table,
    client: ChatClient | None = None,
    model: str = DEFAULT_MODEL,
    think: bool = False,
    context_limit: ContextLimit | None = None,
) -> FastAPI:
    get_context_limit = context_limit or (lambda: lookup_context_limit(model))
    # The agent is shared across requests; tool events go to the queue of the request being answered.
    on_event: Callable[[dict[str, Any]], None] = lambda event: None
    evidence = Evidence()

    def on_tool_call(name: str, arguments: dict[str, Any], result: str) -> None:
        found = extract_evidence(table, name, arguments, result)
        evidence.update(found)
        on_event({"type": "tool", "name": name, "arguments": arguments, "evidence": found.to_json()})

    agent = CsvAgent(table, client=client, model=model, think=think, on_tool_call=on_tool_call)
    busy = threading.Lock()
    app = FastAPI(title="csv-agent")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/table")
    def get_table() -> dict[str, Any]:
        return {"columns": table.columns, "rows": table.rows}

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        return {"model": model, "context_limit": get_context_limit(), "context_tokens": agent.context_tokens}

    @app.post("/api/reset", status_code=204)
    def reset() -> None:
        if not busy.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="The agent is answering a question")
        try:
            agent.reset()
        finally:
            busy.release()

    @app.post("/api/ask")
    async def ask(body: Question) -> StreamingResponse:
        if not busy.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="The agent is already answering a question")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        def run() -> None:
            nonlocal on_event
            on_event = lambda event: loop.call_soon_threadsafe(queue.put_nowait, event)
            evidence.rows.clear()
            evidence.cells.clear()
            try:
                content = agent.ask(body.question)
                on_event(
                    {
                        "type": "answer",
                        "content": content,
                        "evidence": evidence.to_json(),
                        "context_tokens": agent.context_tokens,
                        "context_limit": get_context_limit(),
                    }
                )
            except (ConnectionError, AgentStepLimitError, ollama.ResponseError) as e:
                on_event({"type": "error", "message": str(e)})
            finally:
                busy.release()
                loop.call_soon_threadsafe(queue.put_nowait, None)

        async def stream() -> AsyncIterator[bytes]:
            task = loop.run_in_executor(None, run)
            while (event := await queue.get()) is not None:
                yield _line(event)
            await task

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chat with a CSV file in a pixel-art web GUI.")
    parser.add_argument("csv", help="Path to the CSV file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--think", action="store_true", help="Enable the model's thinking mode")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        table = Table.from_csv(args.csv)
    except (OSError, ValueError) as e:
        print(f"Failed to load CSV: {e}")
        return 1
    app = create_app(table, model=args.model, think=args.think)
    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    print(f"csv-agent GUI: {url}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0
