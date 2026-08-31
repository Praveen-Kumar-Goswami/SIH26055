"""Local, explicit RNGs. Never seed or read global numpy/python RNG state."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np


def spawn_generator(seed: int | np.random.Generator) -> np.random.Generator:
    """Return a local Generator. Integer seeds are mixed with a domain string."""

    if isinstance(seed, np.random.Generator):
        return seed
    if seed < 0:
        raise ValueError(f"seed must be nonnegative, got {seed}.")
    return np.random.default_rng(int(seed))


def derive_seed(parent: int, *labels: Any) -> int:
    """Derive a stable child seed from a parent seed and labels."""

    payload = json_like(parent, *labels)
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "little") % (2**31 - 1)


def json_like(*parts: Any) -> bytes:
    text = "|".join(repr(part) for part in parts)
    return text.encode("utf-8")
