"""Unit tests for kernel.bundle — the signed bundle manifest (§5.3, §6.6).

`bundle.yaml` makes a gold anchor bundle a verifiable unit: every part + sha256 + a bundle_digest.
verify_manifest recomputes from disk so any tamper / missing / extra part is caught.
"""

from __future__ import annotations

import hashlib

import yaml

from vdocs.kernel import bundle as b


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_PARTS = {
    "body.md": b"# Doc\n",
    "history.yaml": b"anchor_key: X\n",
    "capture.yaml": b"captures: {}\n",
}


def _manifest(parts=None):
    return b.build_manifest(
        parts if parts is not None else _PARTS,
        doc_id="CPRS/or_ig",
        anchor_key="CPRS:OR:IG",
        tool_ver="0.1.0",
        source_sha256=["abc", "def"],
        captures={"revisions": {"outcome": "captured"}},
    )


# --- build_manifest ----------------------------------------------------------------------------
def test_build_manifest_lists_every_part_with_hash_and_size():
    m = _manifest()
    parts = {e["path"]: e for e in m["parts"]}
    assert set(parts) == set(_PARTS)
    for path, data in _PARTS.items():
        assert parts[path]["sha256"] == _sha(data)
        assert parts[path]["bytes"] == len(data)
    assert m["anchor_key"] == "CPRS:OR:IG" and m["generated_by"] == "0.1.0"
    assert m["source_sha256"] == ["abc", "def"]
    assert m["captures"] == {"revisions": {"outcome": "captured"}}


def test_build_manifest_never_lists_itself():
    m = _manifest({**_PARTS, "extra.yaml": b"x"})
    assert b.MANIFEST_NAME not in {e["path"] for e in m["parts"]}


def test_bundle_digest_is_order_independent_and_content_sensitive():
    h = {"a": "1", "b": "2"}
    assert b.bundle_digest(h) == b.bundle_digest({"b": "2", "a": "1"})  # order-independent
    assert b.bundle_digest(h) != b.bundle_digest({"a": "1", "b": "3"})  # content-sensitive
    assert b.bundle_digest(h) != b.bundle_digest({"a": "1"})  # part-set-sensitive


def test_manifest_round_trips_through_yaml():
    m = _manifest()
    assert yaml.safe_load(yaml.safe_dump(m)) == m


# --- verify_manifest ---------------------------------------------------------------------------
def test_verify_clean_bundle_has_no_findings():
    assert b.verify_manifest(_manifest(), dict(_PARTS)) == []


def test_verify_detects_hash_mismatch():
    tampered = {**_PARTS, "body.md": b"# Tampered\n"}
    kinds = [f.kind for f in b.verify_manifest(_manifest(), tampered)]
    assert b.HASH_MISMATCH in kinds


def test_verify_detects_missing_part():
    on_disk = {k: v for k, v in _PARTS.items() if k != "capture.yaml"}
    finds = b.verify_manifest(_manifest(), on_disk)
    assert any(f.kind == b.MISSING and f.path == "capture.yaml" for f in finds)


def test_verify_detects_extra_part():
    on_disk = {**_PARTS, "stowaway.txt": b"surprise"}
    finds = b.verify_manifest(_manifest(), on_disk)
    assert any(f.kind == b.EXTRA and f.path == "stowaway.txt" for f in finds)


def test_verify_detects_tampered_digest_when_parts_match():
    m = _manifest()
    m["bundle_digest"] = "0" * 64  # forge the digest while parts are untouched
    kinds = [f.kind for f in b.verify_manifest(m, dict(_PARTS))]
    assert kinds == [b.DIGEST_MISMATCH]
