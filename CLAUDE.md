# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Sample agent that answers questions about a single small CSV using a local Ollama model (`qwen3.5:9b` default) via tool calling. Python >= 3.14, managed with uv.

## Commands

```bash
uv sync
uv run csv-agent data/products.csv "質問"            # one-shot; omit question for interactive mode
uv run csv-agent data/products.csv "..." -v --model qwen3.5:4b --think
uv run pytest                                        # unit tests only (ollama marker excluded by default)
uv run pytest -m ollama                              # end-to-end tests against a running local Ollama
uv run pytest tests/unit/test_tools.py::test_name    # single test
uv run csv-agent-eval data/products.csv evals/products.json --models qwen3.5:9b qwen3.5:4b --repeats 3 -o results.jsonl
uv run csv-agent-eval data/products.csv evals/products.json --models qwen3.5:9b --repeats 3 --record   # save to evals/records/
uv run csv-agent-eval ... --reset-baseline "reason"   # make this run the baseline of the evaluated models
uv run csv-agent-eval-check                            # what the PR workflow reports
```

## Evaluation records

- Runs are committed under `evals/records/runs/` and matched to code by a fingerprint of `src/`, `data/`, `evals/` (minus records) and `uv.lock`, CRLF-normalized. Edits elsewhere (tests, docs, CI) don't require re-evaluation.
- `evals/records/baseline.json` holds one baseline per model, written only when a model has none or on `--reset-baseline`.
- `.github/workflows/eval-check.yml` runs `csv-agent-eval-check` on PRs: reports missing evaluation, regressions beyond 5 pt, and baseline changes vs the target branch. It never fails the PR.

## Architecture

Flow: `cli.py` → `CsvAgent` (`agent.py`) ⇄ Ollama chat API → `CsvTools` (`tools.py`) → `Table` (`table.py`) / `Retriever` (`retriever.py`).

- `CsvAgent` keeps conversation history, injects the schema (`CsvTools.get_schema()`) into the system prompt, and loops over tool calls up to `max_steps` (raises `AgentStepLimitError`). The client is injected via the `ChatClient` protocol.
- `CsvTools` public methods (`search_rows`, `filter_rows`, `aggregate`, `get_schema`) are passed to Ollama directly as Python functions, so **their signatures and docstrings are the tool schema the model sees**. Tools return JSON strings; errors are returned as JSON (not raised) so the model can retry.
- `Retriever` is BM25 (`rank-bm25`) over per-row `column: value | ...` documents. Tokenization: NFKC, ASCII words kept, Japanese runs split into character bigrams (no embeddings / no Japanese tokenizer).
- `filter_rows` / `aggregate` exist for exact conditions and arithmetic that BM25 can't answer; `aggregate` filters by equality only.

## Tests

- `tests/unit`: contract-level tests. The agent loop uses `tests/unit/fakes.py` `ScriptedClient`, which returns real `ollama.ChatResponse` objects (`answer()`, `tool_call()` helpers).
- `tests/integration`: marked `ollama`; skipped if the model is unavailable; answers checked by keywords against `data/products.csv`, so results may vary.
