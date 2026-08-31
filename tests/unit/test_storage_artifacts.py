from __future__ import annotations

from pathlib import Path

import pytest

from smartscan.storage.artifacts import ArtifactStore, looks_absolute, sanitize_relative_path
from smartscan.types import SmartScanError, sha256_bytes


def test_put_bytes_checksum_matches_final_bytes(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "art")
    data = b"hello-smartscan"
    ref = store.put_bytes("logs/sample.bin", data)
    assert ref.relative_path == "logs/sample.bin"
    assert ref.sha256 == sha256_bytes(data)
    assert store.resolve("logs/sample.bin").read_bytes() == data
    reused = store.put_bytes("logs/sample.bin", data, overwrite=False)
    assert reused.reused is True
    assert reused.sha256 == ref.sha256


def test_mixed_separators_stay_under_root(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "art")
    ref = store.put_bytes("foo\\bar/baz.bin", b"x")
    assert ref.relative_path == "foo/bar/baz.bin"
    assert store.verify("foo/bar/baz.bin", ref.sha256).is_file()


@pytest.mark.parametrize(
    "bad",
    [
        r"C:\Windows\temp",
        r"C:/abs/path",
        "/etc/passwd",
        r"\\server\share\x",
        r"..\secret",
        "../secret",
        r"foo\..\bar",
        "foo/../../outside",
        "foo/./../../etc",
        "",
        ".",
        "foo:bar",
    ],
)
def test_rejects_absolute_and_traversal(tmp_path: Path, bad: str) -> None:
    store = ArtifactStore(tmp_path / "art")
    with pytest.raises(SmartScanError):
        store.put_bytes(bad, b"x")
    with pytest.raises(SmartScanError):
        sanitize_relative_path(bad, root=tmp_path / "art")


def test_looks_absolute_windows_and_posix() -> None:
    assert looks_absolute(r"C:\data\x")
    assert looks_absolute("C:/data/x")
    assert looks_absolute("/var/tmp")
    assert looks_absolute(r"\\host\share")
    assert not looks_absolute("runs/abc/metrics.json")


def test_verify_missing_and_corrupt(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "art")
    ref = store.put_bytes("a.bin", b"payload")
    with pytest.raises(SmartScanError, match="missing"):
        store.verify("missing.bin", ref.sha256)
    dest = store.resolve("a.bin")
    dest.write_bytes(b"tampered")
    with pytest.raises(SmartScanError, match="checksum"):
        store.verify("a.bin", ref.sha256)


def test_writing_temp_is_replaced(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "art")
    dest_dir = store.root / "k"
    dest_dir.mkdir()
    stale = dest_dir / "file.bin.writing"
    stale.write_bytes(b"stale")
    ref = store.put_bytes("k/file.bin", b"fresh")
    assert not stale.exists()
    assert store.resolve("k/file.bin").read_bytes() == b"fresh"
    assert ref.sha256 == sha256_bytes(b"fresh")
