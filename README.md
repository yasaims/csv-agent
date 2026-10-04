# csv-agent

A small sample AI agent that answers questions about **a single small CSV file**, using a local [Ollama](https://ollama.com) model (`qwen3.5:9b` by default).

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Ollama running locally with the model pulled: `ollama pull qwen3.5:9b`

## Usage

```bash
uv sync

# One question
uv run csv-agent data/products.csv "在庫が0の商品は?"

# Interactive session (type exit or quit to leave)
uv run csv-agent data/products.csv

# Show tool calls, use another model, enable thinking mode
uv run csv-agent data/products.csv "一番高い商品は?" -v --model qwen3.5:4b --think
```

From Python:

```python
from csv_agent.agent import CsvAgent
from csv_agent.table import Table

agent = CsvAgent(Table.from_csv("data/products.csv"))
print(agent.ask("オーディオカテゴリの在庫合計は?"))
```

Thinking mode is off by default to keep responses fast.

## Evaluation

```bash
# Compare models on fixed questions
uv run csv-agent-eval data/products.csv evals/products.json --models qwen3.5:9b qwen3.5:4b --repeats 3

# Record the run in the repository (evals/records/) so the PR check can see it
uv run csv-agent-eval data/products.csv evals/products.json --models qwen3.5:9b --repeats 3 --record

# Replace the evaluated models' baselines with this run, e.g. after changing evaluation cases
uv run csv-agent-eval data/products.csv evals/products.json --models qwen3.5:9b --repeats 3 --reset-baseline "tightened expected keywords"
```

Before opening a PR, commit your code, run the evaluation with `--record`, and commit `evals/records/`.
The `eval-check` workflow then reports in the job summary (without failing the PR):

- whether a recorded run matches the PR's code (fingerprint of `src/`, `data/`, `evals/`, `uv.lock`),
- per-model accuracy against `evals/records/baseline.json` (a drop of more than 5 points is flagged),
- baselines registered or reset in the PR.

A model's first recorded run becomes its baseline automatically. Run `uv run csv-agent-eval-check` to see the same report locally.

## Tests

```bash
uv run pytest            # unit tests (no Ollama needed)
uv run pytest -m ollama  # end-to-end tests against the local Ollama model
```

- `tests/unit`: contract-level tests. The agent loop is tested with a scripted fake client that returns real `ollama.ChatResponse` objects.
- `tests/integration`: a few end-to-end questions against `data/products.csv` (lookup, aggregate, condition). Skipped when the model is not available. Answers are checked by keywords, so results can vary with model output.

## Limitations

- Intended for small CSV files: all rows are held in memory and the BM25 index is built at startup.
- Retrieval is lexical (BM25). Synonyms and paraphrases that share no characters with the data are not matched.
- `aggregate` filters by exact equality only; use `filter_rows` for other conditions.
