---
name: evaluate-before-pr
description: Record an accuracy evaluation for the current code and check it against the per-model baselines. Use before creating a pull request, or when asked to evaluate, record an evaluation, or reset evaluation baselines.
---

# Evaluate before PR

The `eval-check` PR workflow cannot run Ollama. It only reads runs committed under `evals/records/` and matches them
to the code by a fingerprint of `src/`, `data/`, `evals/` (except `evals/records/`) and `uv.lock`.

## Steps

1. Skip evaluation if no file in the fingerprint scope changed since the last recorded run:
   `uv run csv-agent-eval-check` says "matches this code state". Go to step 7.
2. Commit all code changes first. Any later edit inside the fingerprint scope invalidates the run.
3. Confirm Ollama is running and the models exist: `ollama list`.
4. Run the evaluation for every model in `evals/records/baseline.json` (each case runs 3 times; this takes minutes):

   ```bash
   uv run csv-agent-eval data/products.csv evals/products.json --models qwen3.5:9b qwen3.5:4b --record
   ```

   Reset baselines instead (append `--reset-baseline "<reason>"`) only when the evaluation rules changed
   (`evals/products.json`, `is_correct`, the repeat count) or the user asks. Never reset to hide a regression.
5. Check the report: `uv run csv-agent-eval-check`.
6. Commit `evals/records/` separately, e.g. `eval: record run for <change>`.
7. Tell the user the per-model accuracy, any regression warning, and any `Baseline registered` / `Baseline RESET`
   line. A regression does not block the PR, but must be mentioned in the PR description.

If a model fails every run, nothing is recorded: Ollama is likely down or the model is missing. Report it and stop.
