BEGIN STAGE 1 PROMPT - COPY FROM HERE
You are the senior scientific Python engineer responsible for Stage 1 of SIH26055. Build a deterministic RF environment with perfect evaluation truth, frozen shared contracts and safe adapters for the referenced public radar data.
Scope: Create the repository foundation, band/time mathematics, four emitter classes, scenario I/O, event extraction, reproducible ground-truth artifacts, Turing TSRD ingestion and a J.C. Wise-compatible local catalog importer.
Do not build: Do not build the scanning receiver, detector, metrics engine, database, MLflow server, predictor, RL policy or dashboard.
Required work order
Inspect the repository. If it is empty, create the locked src layout, pyproject.toml, a reproducible Python 3.11 uv.lock, core/dev dependency groups, README skeleton, .gitignore and configs directory. Update the lock only with intentional dependency changes.
Materialize this specification as authoritative Markdown at docs/SIH26055_BUILD_SPEC.md, keep one executable prompt per file under docs/stages/, and write docs/BUILD_CONTRACT.md from the frozen architecture, data contracts and metric names. These files become the machine-readable handoff for later stages.
Implement and test time/band primitives before emitters. Implement emitters before scenarios. Implement deterministic save/reload before external-data adapters.
Run the unit and integration gates, create docs/stage_reports/STAGE_1_REPORT.md, then stop.
Mathematical and simulation contract
Time is integer indexed. Require T/dt to be an integer within a strict tolerance; otherwise reject the config. Set N = round(T/dt), t[n] = n*dt for reporting only, and use n % period_steps for all periodic behavior.
A band occupies [edge[k], edge[k+1]). Validate finite strictly increasing edges and use searchsorted with an explicit high-edge exclusion rule.
Ship two named profiles: demo_2_18 with sixteen 1 GHz bands from 2 to 18 GHz, and turing_0_18 with eighteen 1 GHz bands from 0 to 18 GHz. Every model/run stores its profile ID and exact edges.
Implement exactly four public emitter classes: ContinuousEmitter, CircularScanEmitter, SectorScanEmitter and FrequencyAgileEmitter. A reusable on/off gate may be composed into any class, but it is not a fifth public emitter type.
CircularScanEmitter: phase_step[n] = (phase0_steps + n) mod period_steps after mapping the receiver direction and beamwidth to integer phase bins. Its one-period sampled duty fraction must match the exact illuminated-step count within one sample.
SectorScanEmitter: implement a deterministic triangular sweep over [theta_min, theta_max], including endpoint behavior. Test both directions and wrap-free angular distance.
FrequencyAgileEmitter: active hop = hop_bands[(phase_offset + n // dwell_steps) mod L]. Validate positive dwell_steps, nonempty sequence and legal bands.
Overlapping emitters combine with logical OR for occupancy and linear addition for power. Never sum dB values. Keep emitter-level truth in an event table rather than Python objects inside an N x K array.
Extract maximal emitter-band illumination intervals as half-open [start_step, end_step). A hop or inactive gap closes an event; adjacent active samples from the same emitter and band remain one event.
Required GroundTruth artifact
occupied: bool array [N,K].
signal_power_w: float32 array [N,K] with finite nonnegative linear power.
events: tabular records with stable event_id, emitter_id, band, start_step, end_step, source and optional evaluator-only synthetic threat_weight/hidden metadata; these fields are never policy-visible.
scenario_config, BandPlan, dt_s, seed, generator version, source provenance, canonical content_fingerprint and artifact_sha256. The content fingerprint hashes semantic inputs; artifact SHA-256 hashes stored bytes.
Use compressed NPZ or HDF5 with an explicit schema_version. Reload must reproduce arrays bit-for-bit and the canonical event table exactly.
Reject NaN/Inf, negative power, invalid band references, zero/negative step counts, and conflicting emitter IDs with actionable validation messages.
Built-in scenarios
sparse: continuous plus circular-scan activity with low overlap.
dense: all four emitter types with simultaneous overlap and mixed SNR-relevant power.
agile_threat: periodic scanning, multi-band hopping, a late-arriving previously unseen emitter and differentiated evaluator-only synthetic threat weights for post-run analysis. Missing weights default to neutral 1.0 and no evaluator-only weight is policy-visible.
edge_zero: no emitters; used throughout receiver and metric tests.
A seeded random generator with bounded, validated distributions and no global RNG state.
Turing Synthetic Radar Dataset adapter
Implement smartscan.data.turing as an optional, streaming adapter. The dataset is large and gated; the project must remain fully testable without downloading it.
Accept a user-provided TSRD .h5 pulse-train path. Prefer the official turing_deinterleaving_challenge.PulseTrain.load API; do not guess or hard-code undocumented HDF5 internals.
Map PDW Time of Arrival (microseconds) to step indices and Centre Frequency (MHz) to BandPlan bins. Convert Amplitude dB according to verified dataset metadata, documenting whether it is 20log10 amplitude or 10log10 power. When filling signal_power_w, accumulate pulse energy as linear_power times pulse/bin overlap and divide by dt_s; use Pulse Width across bin boundaries. Quarantine and report ambiguous-unit records; preserve AoA and metadata in provenance/side tables.
TSRD emitter labels are local to each pulse train; namespace them with the pulse-train fingerprint so label 1 in two files is never treated as the same emitter.
Record source URI, receiver mode, original file SHA-256, dataset/repository version when known, transformation config, dropped/out-of-range/ambiguous counts and output content fingerprint. Default to stare mode for GroundTruth. Treat scan mode as receiver observations or an external baseline unless paired with corresponding stare truth; never interpret scan-mode non-detections as non-transmissions.
Support both BandPlan profiles. For demo_2_18, explicitly filter 0-2 GHz pulses and report coverage loss; never silently reinterpret the 0-18 GHz source.
Provide an integration command that operates on one local file and a unit-test fixture containing a few synthetic PDWs. No unit test may require HF_TOKEN, a Hugging Face login, network access or the 70 GB corpus.
Document that TSRD models emitted electromagnetic-environment truth rather than this project's narrowband receiver. Stage 2 must still apply the project receiver/detector to the converted truth.
J.C. Wise-compatible catalog adapter
Treat the legacy Radar Emitter Database reference as an optional user-supplied local CSV/JSON source because availability and redistribution rights may vary. Do not scrape a website and do not fabricate a catalog.
Define and document a stable input schema: source_record_id, emitter_family, frequency_min_hz, frequency_max_hz, optional PRI/PRF, pulse_width, scan_type, scan_period_s, optional public threat_priority, source_reference and license_note.
Validate units/ranges, preserve each raw record's provenance and map only legally supplied records into scenario templates or observable catalog features. Unknown fields remain unknown; do not fill with invented values.
Ship only a tiny clearly synthetic schema example under tests/fixtures, not real database content.
CLI and documentation deliverables
python -m smartscan.cli simulate --config configs/demo.yaml --output artifacts/runs/stage1_demo.npzpython -m smartscan.cli inspect-ground-truth artifacts/runs/stage1_demo.npzpython -m smartscan.cli import-turing --input /path/train.h5 --band-plan demo_2_18 --output data/processed/sample.npzpython -m smartscan.cli validate-wise --input /path/catalog.csv
README Stage 1 section with equations, units, schemas, commands, public-data limitations and exact replay instructions.
docs/DATA_SOURCES.md with TSRD access/provenance notes and the optional J.C. Wise-compatible schema.
No generated large data in git. Keep only tiny deterministic fixtures and their expected checksums.
Tests and acceptance gate
T/dt validation and half-open band-edge behavior, including exactly 18 GHz being out of range.
Continuous duty cycle, circular sampled duty count, sector endpoints/direction, agile hop at every boundary and on/off gating.
Overlapping occupancy/power and separate emitter events.
Same semantic seed/config produces an identical content_fingerprint even if compression bytes differ; save/reload preserves arrays and canonical events bit-for-bit; artifact_sha256 verifies exact stored bytes; a different seed changes semantic truth and its content fingerprint.
All four built-in scenarios validate, including zero emitters and a late new emitter.
Tiny TSRD fixture converts with correct units, pulse-width energy aggregation, namespaced labels and reported clipping/ambiguity; stare-truth and scan-observation handling are tested; Wise schema validates and rejects bad units/ranges.
Ruff, mypy and Stage 1 pytest suite pass with at least 90% line coverage for smartscan.rf and smartscan.data.
The demo command exits 0, prints per-band activity/event counts and creates a reloadable artifact with a checksum.
Stage 1 is complete only when: The deterministic simulator, four emitter classes, frozen contracts, both band profiles, replayable artifacts and both safe data-adapter paths exist and every listed test passes.
Required completion report
Create docs/stage_reports/STAGE_1_REPORT.md and finish your response with the same facts:
Files created or changed, grouped by purpose.
Commands executed and their actual exit status; never claim an unrun check passed.
Test count, coverage result when available, and acceptance-gate evidence.
Reproducibility details: seed, config, data fingerprint, git SHA if the repository has one.
Known limitations or blockers. A blocker means the stage is not complete.
Stop condition: Stop after Stage 1. Do not begin the next stage. Return the completion report and wait for the user to approve the next prompt.
END STAGE 1 PROMPT - STOP COPYING
