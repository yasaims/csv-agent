import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Browser, Error, Page, expect, sync_playwright

from csv_agent.gui.server import create_app
from csv_agent.table import Table
from tests.unit.fakes import ScriptedClient, answer

pytestmark = pytest.mark.gui

TABLE = Table(columns=["name", "stock"], rows=[{"name": "マウス", "stock": "0"}])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def client() -> ScriptedClient:
    return ScriptedClient(answer("一つ目の回答"), answer("二つ目の回答"))


@pytest.fixture
def url(client: ScriptedClient) -> Iterator[str]:
    port = _free_port()
    app = create_app(TABLE, client=client, model="test-model", context_limit=lambda: 4096)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Error:
            pytest.skip("Chromium for Playwright is not installed (uv run playwright install chromium-headless-shell)")
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser, url: str) -> Iterator[Page]:
    page = browser.new_page()
    page.goto(url)
    expect(page.locator(".msg.agent")).to_have_count(1)
    yield page
    page.close()


def ask(page: Page, question: str, expected_answer: str) -> None:
    page.fill("#input", question)
    page.press("#input", "Enter")
    expect(page.locator(".bubble", has_text=expected_answer)).to_be_visible()


def test_new_button_clears_chat_and_starts_new_conversation(page: Page, client: ScriptedClient) -> None:
    ask(page, "一つ目", "一つ目の回答")

    page.click("#new-chat")

    expect(page.locator(".msg.user")).to_have_count(0)
    expect(page.locator(".msg.agent")).to_have_count(1)
    ask(page, "二つ目", "二つ目の回答")
    assert [m["role"] for m in client.requests[-1]["messages"]] == ["system", "user"]
