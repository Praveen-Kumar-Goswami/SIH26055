from __future__ import annotations

from pathlib import Path

import pytest

from smartscan.data.wise import validate_wise
from smartscan.types import SmartScanError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_synthetic_catalog_validates() -> None:
    result = validate_wise(FIXTURES / "wise_synthetic.csv")
    assert result.ok
    assert result.n_records == 2
    assert result.records[0].scan_type == "circular"
    assert result.records[1].pri_s is None


def test_rejects_ghz_as_hz() -> None:
    result = validate_wise(FIXTURES / "wise_bad.csv")
    assert not result.ok
    assert result.errors


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SmartScanError):
        validate_wise(tmp_path / "missing.csv")


def test_json_catalog(tmp_path: Path) -> None:
    path = tmp_path / "cat.json"
    path.write_text(
        """
        [{"source_record_id": "J1", "emitter_family": "synth",
          "frequency_min_hz": 2.5e9, "frequency_max_hz": 2.6e9}]
        """,
        encoding="utf-8",
    )
    result = validate_wise(path)
    assert result.ok
    assert result.records[0].source_record_id == "J1"
