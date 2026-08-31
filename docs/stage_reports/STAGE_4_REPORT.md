# Stage 4 report — queryable persistence and local MLflow

`implementation_complete`: **true**

`performance_gate_passed`: **not applicable** (Stage 4 has no scheduler performance gate)

## Files created or changed, grouped by purpose

### Domain store, artifacts, tracking
- `src/smartscan/storage/constants.py` — run/sync statuses, experiment names, indexed metric keys, CLI order aliases
- `src/smartscan/storage/models.py` — SQLAlchemy 2 mappings for the eleven required tables
- `src/smartscan/storage/db.py` — SQLite URL helpers, `PRAGMA foreign_keys=ON`, settings, Alembic upgrade
- `src/smartscan/storage/artifacts.py` — atomic put, SHA-256 of final bytes, Windows/POSIX traversal rejection
- `src/smartscan/storage/repositories.py` — required repository API, fail-closed `get_run`, reconcile
- `src/smartscan/storage/tracking.py` — `ExperimentTracker`, `MLflowTracker`, `NoOpTracker`, serve argv builder
- `src/smartscan/storage/pipeline.py` — `persist_baseline_run` / `build_repository`
- `src/smartscan/storage/alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial_domain_schema.py`
- `src/smartscan/storage/__init__.py` — public exports

### CLI, packaging, docs
- `src/smartscan/cli.py` — `db upgrade`, `run --persist --track`, `runs list/verify`, `mlflow serve/reconcile`
- `pyproject.toml` — SQLAlchemy / Alembic / MLflow as main deps; `smartscan.storage` included in coverage; Alembic package data
- `README.md`, `docs/BUILD_CONTRACT.md`, `.env.example`, `.gitignore`
- `artifacts/store/.gitkeep`
- `uv.lock` — regenerated so SQLAlchemy, Alembic, and MLflow are main-package pins (close-out)
- `docs/stage_reports/STAGE_4_REPORT.md` — this report

### Tests
- `tests/conftest.py` — tiny simulate fixture and `domain_repo`
- `tests/unit/test_storage_artifacts.py`, `test_storage_schema.py`, `test_storage_repositories.py`, `test_storage_tracking.py`, `test_storage_extra.py`
- `tests/integration/test_storage_cli.py`

## Commands executed and actual exit status

### Original Stage 4 implementation

| Command | Exit status |
| --- | --- |
| `ruff check src tests` | 0 |
| `mypy src` | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov=smartscan.storage --cov-fail-under=90` | 0 |
| `python -m smartscan.cli db upgrade` | 0 |
| `python -m smartscan.cli run --config configs/demo.yaml --strategy sequential --persist --track --seed 42 --schedule-seed 0` | 0 |
| `python -m smartscan.cli runs list --strategy sequential --order-by avg_intercept_rate` | 0 |
| `python -m smartscan.cli runs verify 9ce634b8-9e6c-456f-820b-40ed39cc029f` | 0 |
| `python -m smartscan.cli mlflow reconcile --all` | 0 |

### Reproducibility close-out (this pass)

| Command | Exit status |
| --- | --- |
| `uv lock --check` (before regeneration) | 1 (stale, as expected) |
| `uv lock` | 0 |
| `uv lock --check` (after regeneration) | 0 |
| `uv sync --frozen --extra dev --python 3.11` into a clean venv | 0 |
| clean-venv import of `sqlalchemy`, `alembic`, `mlflow`, `smartscan` | 0 |
| `ruff check src tests` (clean 3.11 venv) | 0 |
| `mypy src` (clean 3.11 venv) | 0 |
| `pytest tests --cov=smartscan.rf --cov=smartscan.data --cov=smartscan.receiver --cov=smartscan.metrics --cov=smartscan.storage --cov-fail-under=90` (clean 3.11 venv) | 0 |
| `python -m smartscan.cli mlflow serve --host 127.0.0.1 --port 5000` | process started; UI `/` and `/health` HTTP 200 |
| MLflow HTTP client `get_run` + `list_artifacts` + artifact download | 0 |
| REST `GET /ajax-api/2.0/mlflow/runs/get?run_id=8ffa759c…` | HTTP 200, includes `domain_run_id` |

No unrun check is claimed as passed.

## Tests, coverage, acceptance-gate evidence

Close-out suite (clean Python 3.11.9 venv installed from the updated lock):

- **196 passed**, 0 failed
- Combined line coverage **rf + data + receiver + metrics + storage: 96.36%** (threshold 90%)

Original implementation suite (working `.venv`, before lock close-out): combined **96.41%**; dedicated `smartscan.storage` **92.55%**.

Acceptance evidence (unchanged from the official persist):

- Alembic upgrade from an empty temporary directory creates all eleven domain tables plus `alembic_version`; SQLite `PRAGMA foreign_keys=ON`; orphan `runs` insert raises `IntegrityError`
- PostgreSQL URLs parse as backend `postgresql` without requiring a live server or extra DBAPI in tests
- Stage 1–3 round-trip: identical GroundTruth `content_fingerprint`, receiver `config_hash`, log checksums, indexed metric scalars, and full EvaluationResult fingerprint
- Semantically identical GroundTruth reuses one `content_fingerprint` row; NPZ vs HDF5 bytes differ in `artifact_sha256`
- Path traversal and absolute forms rejected: `C:\…`, `C:/…`, `/etc/passwd`, UNC, `..`, mixed `foo\..\bar`
- Temporary MLflow SQLite backend receives params, finite metrics, `domain_run_id` tags, and artifacts; IDs link both ways
- One-sided write (domain pending + pre-created MLflow run with the same tag) reconciles to **exactly one** MLflow run
- MLflow unavailable (`FailingTracker`) leaves the domain run `completed` / `sync_status=error`; later reconcile succeeds
- `list_runs` sorts/filters all seven frozen metrics plus `event_interception_ratio`; CLI `--order-by avg_intercept_rate` maps to `average_intercept_rate`
- Champion/production aliases refused unless `validation_status=validated`
- `verify_checksums=True` fails closed on missing or corrupt files and does not return partial trusted data

Official sequential persist (`configs/demo.yaml`, detector seed 42, schedule seed 0):

| Field | Value |
| --- | --- |
| `domain_run_id` | `9ce634b8-9e6c-456f-820b-40ed39cc029f` |
| `mlflow_run_id` | `8ffa759c2e0148c48c7b4754a07429ca` |
| status / sync | `completed` / `synced` |
| Pd | 0 (0/16) |
| Pfa | 0 (0/206) |
| Sensitivity | 4.02077 dB |
| Average intercept rate | 0 /s (0/2) |
| Average reward | unavailable (`no_observable_reward_in_decision_log`) |
| Correct predictions | unavailable (`pre_action_forecasts_absent`) |
| Average intercept-time error | unavailable (`pre_action_forecasts_absent`) |
| event_interception_ratio | 0 (0/5) |

`runs verify` recomputed the same metrics fingerprint as Stage 3 (`0985cbe6…`). These Pd/Pfa zeros are the real Stage 1 demo vs normalized noise, not fabricated ML results.

### Lockfile close-out

`pyproject.toml` lists `sqlalchemy>=2.0`, `alembic>=1.13`, and `mlflow>=2.14` as **main** dependencies. Before this pass, `uv.lock` still treated them as `extra == 'storage'` only.

- `uv.lock` SHA-256 before: `5c19c2c7efafa0ac41cd6273a176ab626a91424ffe6068de1beb422aed471756`
- `uv lock --check` failed: lockfile needed an update
- `uv lock` (no `--upgrade`; existing project workflow) resolved 154 packages, exit 0
- `uv.lock` SHA-256 after: `49307593860d84050ae593628674845eefc81a8a39ffc99503aa87f97ee5d00d`
- `uv lock --check` then passed
- Main `smartscan` dependencies in the lock now include `alembic`, `mlflow`, and `sqlalchemy`. Constraint specifiers in `pyproject.toml` were not changed.

Clean install: `UV_PROJECT_ENVIRONMENT=C:\Users\Prabh\AppData\Local\Temp\smartscan-py311-lockcheck uv sync --frozen --extra dev --python 3.11` (exit 0, 108 packages). Imports: Python 3.11.9, SQLAlchemy 2.0.52, Alembic 1.19.1, MLflow 3.15.2, smartscan 0.1.0.

### Local MLflow UI smoke test

`python -m smartscan.cli mlflow serve --host 127.0.0.1 --port 5000` served `http://127.0.0.1:5000` (`/` and `/health` HTTP 200). Tracking client against that server loaded the official persist run:

| Field | Value from MLflow server |
| --- | --- |
| `run_id` | `8ffa759c2e0148c48c7b4754a07429ca` |
| experiment | `smartscan-baselines` (id 1); also present: `smartscan-predictor`, `smartscan-scheduler` |
| status | `FINISHED` |
| tag `domain_run_id` | `9ce634b8-9e6c-456f-820b-40ed39cc029f` |
| tag `content_fingerprint` | `0a1189f223baa22d3d9823764518a402ef0f0a3832ea5c48fdfca5b118b20c05` |
| tag `metrics_content_fingerprint` | `0985cbe6b7f9f22e58cafd13a17e07fd3a856bb8fefca66347b1e7a716ef7a79` |
| params | `strategy=sequential`, `seed_receiver=42`, `seed_schedule=0`, `n_steps=2000`, `n_bands=16`, `dt_s=0.001`, `scenario_name=sparse` |
| metrics | `pd=0`, `pfa=0`, `sensitivity=4.020765690505802`, `average_intercept_rate=0`, `event_interception_ratio=0` |
| artifacts | `metrics.json` (18194 B), `receiver_run.npz` (26226 B), `0a1189f223baa22d.npz` (2036 B) |

`download_artifacts(…, "metrics.json")` returned 18194 bytes containing Pd and the Stage 3 metrics fingerprint. REST `GET /ajax-api/2.0/mlflow/runs/get?run_id=8ffa759c…` was HTTP 200 and included `domain_run_id`. Unavailable reward/forecast metrics are omitted from MLflow scalars (typed-unavailable in the domain store, never faked as zero).

Uvicorn multiprocess logged `WinError 10022` on some Windows worker sockets; the parent still answered HTTP 200. That is a Windows MLflow/uvicorn quirk, not a missing run.

### Deduplication policy

- **Semantic identity:** `content_fingerprint` of canonical JSON (volatile timestamps and absolute paths stripped). Identical GroundTruth realizations share `ground_truth/{fingerprint[:16]}.npz`.
- **Byte identity:** SHA-256 of **final** on-disk bytes after atomic replace (`name + ".writing"` then rename). Identical bytes share `artifact_sha256`.
- Compression-only changes (NPZ vs HDF5) keep the content fingerprint and change `artifact_sha256`.

## Reproducibility

- Scenario: `configs/demo.yaml` (`sparse`, seed 42, `dt_s=0.001`, `duration_s=2.0`, `demo_2_18`)
- Receiver: `configs/receiver.yaml`, sequential dwell 8, detector seed 42, schedule seed 0
- GroundTruth `content_fingerprint`: `0a1189f223baa22d3d9823764518a402ef0f0a3832ea5c48fdfca5b118b20c05`
- Receiver config hash: `410388f9a0fe40192e29f6c3718a6edbe5db20ce7a83f9e79fe48284d2de67aa`
- Metrics content fingerprint (excludes `created_at`): `0985cbe6b7f9f22e58cafd13a17e07fd3a856bb8fefca66347b1e7a716ef7a79`
- Domain DB: `data/smartscan.db`; MLflow: `data/mlflow.db`; artifacts: `artifacts/store/`
- git SHA: **none** (this workspace is not a git repository)
- `uv.lock` SHA-256: `49307593860d84050ae593628674845eefc81a8a39ffc99503aa87f97ee5d00d` (`uv lock --check` passes)

## Known limitations or blockers

- No live PostgreSQL is configured; URL acceptance is parse/engine-construction only.
- No trained model bundle is registered. Helpers exist for Stage 5; champion alias is refused for unvalidated placeholders.
- On Windows, `mlflow serve` may log uvicorn worker `WinError 10022` while still serving the UI and REST API.
- None of these is a Stage 4 blocker.

Stage 5 (predictor / PPO / scheduler) was not started.
