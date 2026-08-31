# Third-party notices

This prototype bundles no vendor binaries. Runtime and development dependencies are declared in `pyproject.toml` / `uv.lock` and retain their own licenses (BSD, MIT, Apache-2.0, PSF, and others). Inspect installed package metadata before redistribution.

## Scientific and ML stack

NumPy, SciPy, pandas, h5py, PyYAML, Pydantic, PyTorch, Gymnasium, Stable-Baselines3.

## Persistence and tracking

SQLAlchemy, Alembic, SQLite, MLflow.

## Dashboard

Streamlit, Plotly.

## Data adapters (optional runtime inputs)

- **Turing Synthetic Radar Dataset (TSRD)** — Hugging Face gated corpus; this repository ships only tiny synthetic PulseTrain fixtures. See `docs/DATA_SOURCES.md`. Do not commit the 70 GB corpus.
- **J.C. Wise-compatible catalogs** — not redistributed. Supply a local CSV/JSON. `tests/fixtures/wise_synthetic.csv` is a synthetic schema example, not Wise content.

## Notice

Do not copy classified emitter parameters, scraped restricted catalogs, or tokens into this tree. `.env` is gitignored.
