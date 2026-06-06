# Test coverage

Coverage is measured over `topobank/*` (configured in `.coveragerc`) and
reported in CI (`.github/workflows/test.yml`) with a `--cov-fail-under=75`
regression floor.

Run locally:

```bash
pytest --cov=topobank --cov-config=.coveragerc --cov-report=term-missing
```

## What is omitted from coverage, and why

Coverage is scoped to **core application logic** (see `.coveragerc`):

| Pattern | Why excluded |
|---|---|
| `*/migrations/*` | Auto-generated database migrations. |
| `*/static/*` | Static assets (no executable code). |
| `*/testing/*` | Test fixtures, factories and helpers. |
| `*.html` | Django templates. |
| `*.txt` | Test data files. |
| `*/admin.py` | Django admin display/registration glue — exercised via the admin UI; low value to unit-test. |

## Current status

- **Core coverage: ~79%** — the gate is a **75%** regression floor.
- Targets: **80%** near-term, **90%** longer-term. The gate is intentionally a
  floor *below* current coverage (it fails CI only on a regression); raise it
  toward 80→90% as the gaps below are filled.

## Path to 90%

Reaching 90% means covering roughly the following (largest first). The bulk is
Celery/analysis orchestration and the data pipeline, which need integration-
style tests (eager Celery is already enabled; some need real topography data):

| Module | Coverage | Untested area |
|---|---|---|
| `analysis/tasks.py` | 46% | Celery workflow orchestration — `schedule_workflow`, `execute_workflow`, dependency/chord handling |
| `analysis/models.py` | 70% | `WorkflowResult`/`Workflow` methods (subject dispatch, eval, `submit_again`, `resolve_workflow`) |
| `manager/models.py` | 80% | data-pipeline branches (deepzoom/squeezed/refresh-cache edge cases) |
| `analysis/legacy/workflows.py` | 65% | `WorkflowImplementation.eval` / result handling |
| `manager/utils.py` | 65% | reader / subject-dict helpers |
| `files/models.py` | 76% | manifest file save/download edge cases |
| `analysis/controller.py` | 79% | `AnalysisController` query branches |
| `manager/zip_model.py` | 58% | container export/import paths |
| `manager/management/commands/*` | 54–78% | per-object processing loops (need real topographies with data files) |

The single biggest lever is `analysis/tasks.py` (the workflow execution
engine, ~117 uncovered lines); it and `analysis/models.py` together account
for most of the gap to 90%.
