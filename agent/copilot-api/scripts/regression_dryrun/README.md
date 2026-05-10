# Regression Dry-Run Artifacts

This directory contains artifacts from the Wk2 Team C regression dry-run
(Plan §15.5.6). The dry-run proves that the eval gate CI catches regressions
as intended:

1. A deliberate bug is planted in supervisor.py (route_from_start always
   routes to intake_extractor regardless of documents).
2. The eval runner is run — it fails on extraction and RAG cases that
   expect evidence_retriever to be reached without documents.
3. The bug is reverted.
4. The eval runner is run again — it passes.

## Files

- `ci_fail.json` — eval_results.json captured after planting the bug
- `ci_pass.json` — eval_results.json captured after reverting the bug
- `bug_patch.diff` — the deliberate bug introduced (for audit)

## How to reproduce

```bash
# Plant the bug
cd agent/copilot-api
python -c "
import pathlib
p = pathlib.Path('app/graph/supervisor.py')
t = p.read_text()
# Force route_from_start to always return intake_extractor (breaks cases without docs)
t = t.replace(
    'if docs and intake_status == \"pending\"',
    'if True  # REGRESSION BUG: always route to intake_extractor'
)
p.write_text(t)
"

# Run and capture failure
python -m evals.runner --mode extraction > /dev/null 2>&1
cp eval_results.json scripts/regression_dryrun/ci_fail.json

# Revert
git checkout app/graph/supervisor.py

# Run and capture pass
python -m evals.runner --mode extraction > /dev/null 2>&1
cp eval_results.json scripts/regression_dryrun/ci_pass.json
```
