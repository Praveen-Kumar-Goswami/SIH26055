"""Write the predeclared v3 fresh-test manifest if missing. Never overwrites pairs."""

from __future__ import annotations

from smartscan.ml.protocol import fresh_manifest_path, write_fresh_test_manifest


def main() -> int:
    payload = write_fresh_test_manifest(fresh_manifest_path(), overwrite=False)
    print(f"wrote {fresh_manifest_path()}")
    print(f"n_pairs={payload['n_paired_seeds']}")
    print(f"content_fingerprint={payload['content_fingerprint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
