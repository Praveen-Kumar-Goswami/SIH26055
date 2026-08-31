from __future__ import annotations

import pytest
from pydantic import ValidationError

from smartscan.types import ReceiverConfig, ScanCommand, SmartScanError


def test_receiver_config_ratio_gate() -> None:
    ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9)
    with pytest.raises((SmartScanError, ValidationError), match=">= 10"):
        ReceiverConfig(receiver_ibw_hz=2e9, scan_span_hz=16e9)


def test_ibw_wider_than_band() -> None:
    cfg = ReceiverConfig(receiver_ibw_hz=1e8, scan_span_hz=16e9)
    cfg.validate_ibw_for_band(1e9)
    with pytest.raises(SmartScanError, match="wider"):
        cfg.validate_ibw_for_band(5e7)


def test_scan_command_dwell() -> None:
    ScanCommand(decision_id="d0", target_band=0, dwell_steps=4)
    with pytest.raises((SmartScanError, ValidationError)):
        ScanCommand(decision_id="d0", target_band=0, dwell_steps=0)
