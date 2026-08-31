# Data sources

## Turing Synthetic Radar Dataset (TSRD)

- Dataset: https://huggingface.co/datasets/alan-turing-institute/turing-synthetic-radar-dataset
- Loader: https://github.com/alan-turing-institute/turing-deinterleaving-challenge
- Paper: Gunn et al., arXiv:2602.03856

The corpus is gated and on the order of 70 GB. This project remains fully testable without downloading it. Unit tests use a few synthetic PDWs. No test requires `HF_TOKEN`, a Hugging Face login, or network access.

Prefer `turing_deinterleaving_challenge.PulseTrain.load`. When that package is absent, the adapter reads the **published PulseTrain.save layout**:

- `/data` — float32 array `(N, 5)`
- `/labels` — optional integer labels, local to this pulse train
- `/metadata/feature_names` and metadata attributes such as `collection_time_s`
- `/metadata/receiver` optional group with `mode`

Default column order when names are missing: Time of Arrival (µs), Centre Frequency (MHz), Pulse Width (µs), Angle of Arrival (deg), Amplitude (dB).

### Units

- ToA µs → seconds via `* 1e-6`, then step `floor(t / dt)`
- Centre Frequency MHz → Hz via `* 1e6`, then BandPlan mapping
- Pulse Width µs used for bin overlap. Energy in a step is `linear_power * overlap_s / dt_s`. Zero pulse width deposits into the ToA bin as a one-step impulse.
- Amplitude is published as dB. Default conversion is `10 log10(power_W / 1 W)` because the dataset description treats received amplitude as decreasing quadratically with range (power-like). `20 log10` voltage convention is supported explicitly. Non-finite amplitudes are quarantined and counted.

### Stare vs scan

Default GroundTruth conversion is **stare** (EME truth as observed by a wideband oracle receiver in the dataset). **Scan** mode is stored as observations: `occupancy_is_observation_not_truth=true`. Scan-mode non-detections must not be treated as non-transmissions. TSRD is still not this project's narrowband scanning receiver; Stage 2 must apply the project detector to converted truth.

### Band plans

Both `demo_2_18` and `turing_0_18` are supported. For `demo_2_18`, pulses below 2 GHz are dropped and reported as `clipped_low_ghz`. The 0–18 GHz source is never silently reinterpreted.

### Label namespacing

TSRD emitter labels are local to each pulse train. This adapter namespaces them as `{file_sha256}:{label}` so label `1` in two files is never the same emitter.

## J.C. Wise-compatible catalog (optional)

Legacy reference: http://www.radars.org.uk/ — availability and redistribution rights vary. **Do not scrape. Do not fabricate a catalog. Do not commit real database content.**

Supply a local CSV or JSON with this schema:

| Field | Required | Notes |
| --- | --- | --- |
| source_record_id | yes | Stable id in the user file |
| emitter_family | yes | Public family/name as supplied |
| frequency_min_hz | yes | Hertz; values below 1e6 Hz are rejected as unit errors |
| frequency_max_hz | yes | Must exceed min |
| pri_s | no | Seconds |
| prf_hz | no | Must agree with PRI within 5% if both set |
| pulse_width_s | no | Seconds |
| scan_type | no | As supplied; unknown stays unknown |
| scan_period_s | no | Seconds |
| public_threat_priority | no | Public/assessed only |
| source_reference | no | |
| license_note | no | |

`tests/fixtures/wise_synthetic.csv` is a clearly synthetic schema example, not Wise content.

## Provenance recorded on GroundTruth

Source URI (basename only in semantic fingerprint), original file SHA-256, loader name, receiver mode, transformation config, dropped/out-of-range/ambiguous counts, output content fingerprint, and a digest of AoA/PDW side columns.
