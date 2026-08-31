# Local MLflow

MLflow is mandatory from Stage 4 onward. It is linked to the application database; it is not mixed into the same SQLite schema.

## Default layout

| Role | Default path |
| --- | --- |
| Domain records | `data/smartscan.db` |
| MLflow metadata | `data/mlflow.db` |
| MLflow artifacts | `artifacts/mlflow/` |
| UI/API | `127.0.0.1:5000` |

Configure via `.env.example`. Domain and MLflow files must not be the same path.

## Identity

`domain_run_id` is the project identity. MLflow runs are tagged with it. `mlflow_run_id` is stored back on the domain row. Writes are not one ACID transaction: `sync_status` is `pending | synced | error`.

```text
python -m smartscan.cli mlflow serve
python -m smartscan.cli mlflow reconcile --all
```

Reconcile finds one-sided records after an interrupted write and does not duplicate runs.

## What is logged

Config, hyperparameters, seeds, dataset and ground-truth fingerprints, git SHA when present, environment lock, metrics, curves, comparison tables, and the model bundle.

## Registry

Register `SmartScanScheduler` versions. Set **candidate** on every valid trained bundle. Move **champion** / production only after `performance_gate_passed=true` on the frozen held-out gate.

`python -m smartscan.cli models promote --require-gate` refuses champion when the gate is false.

## Offline

Tests use temporary SQLite files. Unit tests never require a reachable MLflow UI. `doctor` treats an unreachable UI as non-blocking.

## Stage 7

`python -m smartscan.cli benchmark ... --track` logs the held-out pack without retuning. `python -m smartscan.cli run ... --persist --track` links sequential and best-available demo runs the same way.
