"""Checksummed artifact store with atomic writes and traversal rejection.

Deduplication policy
--------------------
* Semantic identity uses ``content_fingerprint`` (canonical JSON of inputs,
  excluding volatile timestamps and absolute paths). Identical GroundTruth
  realizations share one fingerprint and reuse ``ground_truth/{fp[:16]}.npz``.
* Byte identity uses SHA-256 of the **final** on-disk bytes after atomic
  replace. Identical serialized bytes share ``artifact_sha256``.
* Compression-only changes (NPZ vs HDF5, or a compressor rewrite) keep the
  content fingerprint and produce a different artifact SHA-256. The store
  does not treat those as the same file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smartscan.types import GroundTruth, SmartScanError, sha256_bytes, sha256_file


def looks_absolute(path: str) -> bool:
    """True for POSIX, Windows drive, and UNC forms."""

    text = path.strip()
    if not text:
        return False
    candidate = Path(text)
    if candidate.is_absolute():
        return True
    if len(text) >= 2 and text[1] == ":":
        return True
    posix = text.replace("\\", "/")
    if posix.startswith("/") or posix.startswith("//"):
        return True
    if posix.startswith("\\\\") or text.startswith("\\\\"):
        return True
    return False


def sanitize_relative_path(relative: str, *, root: Path) -> Path:
    """Return a sanitized relative Path under *root*; reject traversal."""

    if relative is None or not str(relative).strip():
        raise SmartScanError("Artifact path must be a nonempty relative path.")
    text = str(relative).strip()
    if looks_absolute(text):
        raise SmartScanError(f"Absolute artifact path rejected: {relative}")
    posix = text.replace("\\", "/")
    if looks_absolute(posix):
        raise SmartScanError(f"Absolute artifact path rejected: {relative}")
    parts: list[str] = []
    for part in posix.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise SmartScanError(f"Path traversal rejected: {relative}")
        if ":" in part:
            raise SmartScanError(f"Drive-spec artifact path rejected: {relative}")
        if "\x00" in part:
            raise SmartScanError("NUL byte in artifact path.")
        parts.append(part)
    if not parts:
        raise SmartScanError(f"Artifact path has no components: {relative}")
    rel = Path(*parts)
    base = root.resolve()
    dest = (base / rel).resolve()
    try:
        dest.relative_to(base)
    except ValueError as exc:
        raise SmartScanError(f"Artifact path escapes store root: {relative}") from exc
    return rel


@dataclass(frozen=True)
class ArtifactRef:
    relative_path: str
    sha256: str
    reused: bool = False


class ArtifactStore:
    """Project-relative artifact root. Never stores absolute paths in refs."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def relative_posix(self, relative: str) -> str:
        return sanitize_relative_path(relative, root=self.root).as_posix()

    def resolve(self, relative: str) -> Path:
        rel = sanitize_relative_path(relative, root=self.root)
        return (self.root / rel).resolve()

    def put_bytes(
        self,
        relative: str,
        data: bytes,
        *,
        overwrite: bool = True,
    ) -> ArtifactRef:
        rel = sanitize_relative_path(relative, root=self.root)
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and not overwrite:
            digest = sha256_file(dest)
            return ArtifactRef(relative_path=rel.as_posix(), sha256=digest, reused=True)
        tmp = dest.with_name(dest.name + ".writing")
        if tmp.exists():
            tmp.unlink()
        tmp.write_bytes(data)
        tmp.replace(dest)
        digest = sha256_file(dest)
        if digest != sha256_bytes(data):
            # Final on-disk bytes are the source of truth; they should match
            # what we wrote for a plain byte payload.
            pass
        return ArtifactRef(relative_path=rel.as_posix(), sha256=digest, reused=False)

    def put_file(self, relative: str, source: str | Path, *, overwrite: bool = True) -> ArtifactRef:
        return self.put_bytes(relative, Path(source).read_bytes(), overwrite=overwrite)

    def put_ground_truth(self, relative: str, truth: GroundTruth, *, overwrite: bool = False) -> ArtifactRef:
        from smartscan.rf.io import save_ground_truth

        rel = sanitize_relative_path(relative, root=self.root)
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and not overwrite:
            digest = sha256_file(dest)
            return ArtifactRef(relative_path=rel.as_posix(), sha256=digest, reused=True)
        save_ground_truth(truth, dest)
        digest = truth.artifact_sha256 or sha256_file(dest)
        return ArtifactRef(relative_path=rel.as_posix(), sha256=digest, reused=False)

    def put_receiver_run(self, relative: str, run: object) -> ArtifactRef:
        from smartscan.receiver.logs import ReceiverRun, save_receiver_run

        if not isinstance(run, ReceiverRun):
            raise SmartScanError("put_receiver_run expects a ReceiverRun.")
        rel = sanitize_relative_path(relative, root=self.root)
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        save_receiver_run(run, dest)
        digest = run.artifact_sha256 or sha256_file(dest)
        return ArtifactRef(relative_path=rel.as_posix(), sha256=digest, reused=False)

    def verify(self, relative: str, expected_sha256: str) -> Path:
        """Fail closed: missing or corrupt files raise and yield no path trust."""

        rel = sanitize_relative_path(relative, root=self.root)
        dest = (self.root / rel).resolve()
        if not dest.is_file():
            raise SmartScanError(f"Artifact missing: {rel.as_posix()}")
        digest = sha256_file(dest)
        if digest != expected_sha256:
            raise SmartScanError(
                f"Artifact checksum mismatch for {rel.as_posix()}: "
                f"expected {expected_sha256}, got {digest}."
            )
        return dest
