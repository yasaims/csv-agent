# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Sample agent that answers questions about a single small CSV using a local Ollama model (`qwen3.5:9b` default) via tool calling. Python >= 3.14, managed with uv.

## Dev Rules

- TDD (Test Driven Development)
- If you are main agent, you can spawn `code-implementer` subagents to handle implementation tasks.

## Commands

@README.md

## Evaluation before PR

- **Before creating a pull request, use the `evaluate-before-pr` skill** (`.claude/skills/evaluate-before-pr/`).

## Architecture

Flow: `cli.py` → `CsvAgent` (`agent.py`) ⇄ Ollama chat API → `CsvTools` (`tools.py`) → `Table` (`table.py`) / `Retriever` (`retriever.py`).

- `CsvAgent` keeps conversation history, injects the schema (`CsvTools.get_schema()`) into the system prompt, and loops over tool calls up to `max_steps` (raises `AgentStepLimitError`). The client is injected via the `ChatClient` protocol.
- `CsvTools` public methods (`search_rows`, `filter_rows`, `aggregate`, `get_schema`) are passed to Ollama directly as Python functions, so **their signatures and docstrings are the tool schema the model sees**. Tools return JSON strings; errors are returned as JSON (not raised) so the model can retry.
- `Retriever` is BM25 (`rank-bm25`) over per-row `column: value | ...` documents. Tokenization: NFKC, ASCII words kept, Japanese runs split into character bigrams (no embeddings / no Japanese tokenizer).
- `filter_rows` / `aggregate` exist for exact conditions and arithmetic that BM25 can't answer; `aggregate` filters by equality only.

## Tests

- `tests/unit`: contract-level tests. The agent loop uses `tests/unit/fakes.py` `ScriptedClient`, which returns real `ollama.ChatResponse` objects (`answer()`, `tool_call()` helpers).
- `tests/integration`: marked `ollama`; skipped if the model is unavailable; answers checked by keywords against `data/products.csv`, so results may vary.
