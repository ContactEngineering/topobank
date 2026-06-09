# Test coverage

Coverage is measured over `topobank/*` (configured in `.coveragerc`) and
reported in CI (`.github/workflows/test.yml`) with a `--cov-fail-under=80`
gate.

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

- **Core coverage: ~81%** — the gate is set at **80%**.
- Target: **90%** longer-term. The margin above 80% is small; the gaps below
  are where to add tests when raising it further.

## Path to 90%

Reaching 90% means covering roughly the following (largest first). The bulk is
analysis/data-pipeline code that needs integration-style tests (eager Celery is
already enabled; some need real topography data):

| Module | Coverage | Untested area |
|---|---|---|
| `analysis/models.py` | 70% | `WorkflowResult`/`Workflow` methods (subject dispatch, eval, `submit_again`, `resolve_workflow`) |
| `analysis/tasks.py` | 76% | remaining: dependency-failure propagation, the progress-callback path, chord edge cases |
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
