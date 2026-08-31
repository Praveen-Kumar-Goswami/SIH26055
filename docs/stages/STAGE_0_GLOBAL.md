BEGIN GLOBAL EXECUTION CONTRACT
Read the entire repository and this specification before editing. Preserve working prior-stage code and user changes.
Build only the requested stage. Use prior-stage public interfaces; do not duplicate or fork GroundTruth, logs, metrics, repositories or configuration models.
Use public, synthetic, or properly licensed user-supplied data only. Do not invent, scrape, or redistribute J.C. Wise or other restricted data without explicit rights, and never include classified emitter parameters.
Stay offline by default. External datasets are optional runtime inputs; unit tests use tiny generated fixtures and must pass without credentials or downloads.
Use pathlib and project-root-relative paths. Never write outside the repository or require administrator privileges.
Use fixed, explicitly recorded seeds for Python, NumPy, PyTorch, Gymnasium and policies. Same inputs and seed must reproduce the same artifacts and metrics within documented tolerance.
Canonical content fingerprints hash schema-versioned semantic inputs using sorted keys and normalized numeric forms while excluding volatile timestamps and absolute paths. Artifact SHA-256 hashes serialized bytes. Semantically identical content may retain its fingerprint even when compression changes artifact bytes.
Keep policy-visible observations, prediction features and rewards free of Stage-1 oracle truth, true emitter IDs/parameters and future data. Ground truth is allowed only inside the physical simulator and post-run evaluator.
Write type hints and docstrings for public APIs. Add tests before or with implementation. Run Ruff, mypy and relevant pytest suites before declaring completion.
Do not fabricate benchmark results or quietly relax thresholds. If an acceptance gate fails, report the failure and continue improving only within the current stage.
Keep large arrays and model files out of SQLite; store relative artifact paths plus SHA-256 checksums. Never load pickle, joblib, or Stable-Baselines3 bundles from untrusted paths. Load only locally generated, checksum-verified bundles from configured model roots, and use weights-only formats where supported.
Update docs/BUILD_CONTRACT.md only for compatible clarifications. Record any unavoidable interface change and migrate all callers/tests in the same stage.
At the end, write docs/stage_reports/STAGE_N_REPORT.md, state implementation_complete and any performance_gate_passed as separate booleans, and stop. Do not begin the next stage without a new user instruction.
END GLOBAL EXECUTION CONTRACT
