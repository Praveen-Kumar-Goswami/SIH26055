"""Disjoint synthetic TRAIN/VAL/DEV-TEST protocol.

The Stage 5/7 held-out seeds 1000–1029 are locked historical evidence.
They must never appear in training, validation, hyperparameter search,
or this research-cycle development test split.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartscan.config import TrainConfig, project_root
from smartscan.types import SmartScanError, content_fingerprint, sha256_file

HELD_OUT_SEED_MIN = 1000
HELD_OUT_SEED_MAX = 1029
HELD_OUT_SEEDS = frozenset(range(HELD_OUT_SEED_MIN, HELD_OUT_SEED_MAX + 1))

# Historical v2 train/val pairs. The improvement protocol uses different seeds.
V2_TRAIN_SEEDS = frozenset(range(0, 6))
V2_VAL_SEEDS = frozenset({200, 201})

RESEARCH_FAMILIES: tuple[str, ...] = ("sparse", "dense", "agile_threat", "random")

# Predeclared fresh final-test identities. Written to disk before any evaluation.
FRESH_TEST_FAMILIES: tuple[str, ...] = RESEARCH_FAMILIES
FRESH_TEST_SEEDS: tuple[int, ...] = tuple(range(8000, 8008))
# v4 accuracy pass. Never reuse 8000–8007 (already observed for v3).
FRESH_TEST_V4_SEEDS: tuple[int, ...] = tuple(range(9000, 9008))


def is_held_out_seed(seed: int) -> bool:
    return HELD_OUT_SEED_MIN <= int(seed) <= HELD_OUT_SEED_MAX


def iter_split_pairs(cfg: TrainConfig, split: str) -> list[tuple[str, int]]:
    if split == "val":
        specs = cfg.val_scenarios
    elif split in {"test", "dev-test", "dev_test"}:
        specs = cfg.test_scenarios
    else:
        specs = cfg.train_scenarios
    return [(item.scenario_id, int(seed)) for item in specs for seed in item.seeds]


def assert_no_held_out_seeds(pairs: list[tuple[str, int]], *, where: str) -> None:
    bad = [(fam, seed) for fam, seed in pairs if is_held_out_seed(seed)]
    if bad:
        raise SmartScanError(f"{where} contains frozen held-out pairs {bad}.")


def assert_disjoint_protocol(cfg: TrainConfig) -> dict[str, Any]:
    """Require train / val / dev-test disjoint by complete (scenario, seed)."""

    train = iter_split_pairs(cfg, "train")
    val = iter_split_pairs(cfg, "val")
    dev = iter_split_pairs(cfg, "test")
    for label, pairs in (("train", train), ("val", val), ("dev-test", dev)):
        assert_no_held_out_seeds(pairs, where=label)
    train_set, val_set, dev_set = set(train), set(val), set(dev)
    overlap_tv = sorted(train_set & val_set)
    overlap_td = sorted(train_set & dev_set)
    overlap_vd = sorted(val_set & dev_set)
    if overlap_tv or overlap_td or overlap_vd:
        raise SmartScanError(
            "Train/val/dev-test overlap: "
            f"train∩val={overlap_tv} train∩dev={overlap_td} val∩dev={overlap_vd}"
        )
    return {
        "n_train": len(train),
        "n_val": len(val),
        "n_dev_test": len(dev),
        "train_families": sorted({fam for fam, _seed in train}),
        "val_families": sorted({fam for fam, _seed in val}),
        "held_out_seeds_used": False,
    }


def fresh_test_pairs() -> list[dict[str, int | str]]:
    return [
        {"scenario_id": family, "seed": int(seed)}
        for family in FRESH_TEST_FAMILIES
        for seed in FRESH_TEST_SEEDS
    ]


def build_fresh_test_manifest() -> dict[str, Any]:
    pairs = fresh_test_pairs()
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "kind": "research_fresh_final_test",
        "n_paired_seeds": len(pairs),
        "notes": (
            "Generated and fingerprinted before evaluating SmartScanScheduler v3. "
            "Seeds 8000–8007 were never used in v2 training, the improvement "
            "train/val/dev-test splits, or the frozen Stage 5/7 held-out set 1000–1029. "
            "Do not tune on this manifest."
        ),
        "families": list(FRESH_TEST_FAMILIES),
        "seeds": list(FRESH_TEST_SEEDS),
        "pairs": pairs,
    }
    for item in pairs:
        if is_held_out_seed(int(item["seed"])):
            raise SmartScanError("Fresh-test manifest accidentally includes held-out seeds.")
    payload["content_fingerprint"] = content_fingerprint(
        {k: v for k, v in payload.items() if k != "content_fingerprint"}
    )
    return payload


def write_fresh_test_manifest(path: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
    dest = Path(path)
    payload = build_fresh_test_manifest()
    if dest.is_file() and not overwrite:
        existing_raw: Any = json.loads(dest.read_text(encoding="utf-8"))
        if not isinstance(existing_raw, dict):
            raise SmartScanError("Existing fresh-test manifest must be a JSON object.")
        existing: dict[str, Any] = existing_raw
        existing_fp = str(existing.get("content_fingerprint") or "")
        recomputed = content_fingerprint(
            {k: v for k, v in existing.items() if k != "content_fingerprint"}
        )
        if existing_fp and existing_fp != recomputed:
            raise SmartScanError("Existing fresh-test manifest fingerprint mismatch.")
        if existing.get("pairs") != payload["pairs"]:
            raise SmartScanError("Existing fresh-test manifest pairs must not be rewritten.")
        return existing
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def fresh_manifest_path() -> Path:
    return project_root() / "configs" / "fresh_test_manifest.json"


def fresh_v4_manifest_path() -> Path:
    return project_root() / "configs" / "fresh_test_v4_manifest.json"


def build_fresh_test_v4_manifest() -> dict[str, Any]:
    pairs = [
        {"scenario_id": family, "seed": int(seed)}
        for family in FRESH_TEST_FAMILIES
        for seed in FRESH_TEST_V4_SEEDS
    ]
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "kind": "research_fresh_final_test_v4",
        "n_paired_seeds": len(pairs),
        "notes": (
            "Generated and fingerprinted before evaluating SmartScanScheduler v4. "
            "Seeds 9000–9007 were never used in v2/v3 training, improvement splits, "
            "the v3 fresh test 8000–8007, or the frozen Stage 5/7 held-out set 1000–1029. "
            "Do not tune on this manifest."
        ),
        "families": list(FRESH_TEST_FAMILIES),
        "seeds": list(FRESH_TEST_V4_SEEDS),
        "pairs": pairs,
    }
    for item in pairs:
        seed_i = int(str(item["seed"]))
        if is_held_out_seed(seed_i):
            raise SmartScanError("v4 fresh-test manifest accidentally includes held-out seeds.")
        if seed_i in FRESH_TEST_SEEDS:
            raise SmartScanError("v4 fresh-test must not reuse v3 fresh-test seeds 8000–8007.")
    payload["content_fingerprint"] = content_fingerprint(
        {k: v for k, v in payload.items() if k != "content_fingerprint"}
    )
    return payload


def write_fresh_test_v4_manifest(path: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
    dest = Path(path)
    payload = build_fresh_test_v4_manifest()
    if dest.is_file() and not overwrite:
        existing_raw: Any = json.loads(dest.read_text(encoding="utf-8"))
        if not isinstance(existing_raw, dict):
            raise SmartScanError("Existing v4 fresh-test manifest must be a JSON object.")
        existing: dict[str, Any] = existing_raw
        existing_fp = str(existing.get("content_fingerprint") or "")
        recomputed = content_fingerprint(
            {k: v for k, v in existing.items() if k != "content_fingerprint"}
        )
        if existing_fp and existing_fp != recomputed:
            raise SmartScanError("Existing v4 fresh-test manifest fingerprint mismatch.")
        if existing.get("pairs") != payload["pairs"]:
            raise SmartScanError("Existing v4 fresh-test manifest pairs must not be rewritten.")
        return existing
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def file_sha256(path: str | Path) -> str:
    return sha256_file(Path(path))
