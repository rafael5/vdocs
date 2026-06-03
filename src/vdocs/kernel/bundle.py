"""Pure bundle-manifest primitives — the signed bundle manifest ``bundle.yaml`` (§5.3, §6.6).

A gold anchor bundle (``consolidate``, §6.6) is a directory of typed parts (``body.md`` +
``history.yaml`` + optional ``flags.yaml``/``toc.yaml``/``capture.yaml``). ``bundle.yaml`` makes the
bundle a **verifiable unit**: it lists every *other* part with its ``sha256`` + byte length, folds
the ``capture.yaml`` outcome summary, records the member ``source_sha256`` provenance roots + the
producing ``tool_ver``, and carries a ``bundle_digest`` = ``sha256`` over the sorted ``path:sha256``
lines. The ``validate`` gate recomputes the hashes from disk and the digest — any drift is tamper or
incompleteness, and blocks (the §6/§11 "reproducibility is auditability" principle applied to bundle
completeness).

**"Signed" = a verifiable content digest** (recompute to verify — key-free, tamper-*evident*); a
*keyed* signature over ``bundle_digest`` (GPG/cosign) is a future increment once key management
exists, and changes nothing about the manifest's shape.

Pure: bytes in, plain dicts/findings out; ``consolidate`` writes the file, ``validate`` re-verifies.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

MANIFEST_NAME = "bundle.yaml"

# Integrity finding kinds (verify_manifest).
MISSING = "missing-part"  # listed in the manifest, absent on disk
EXTRA = "extra-part"  # present on disk, not in the manifest
HASH_MISMATCH = "hash-mismatch"  # a listed part's bytes changed
DIGEST_MISMATCH = "digest-mismatch"  # parts match but the recorded bundle_digest does not
UNMANIFESTED = "unmanifested"  # a bundle with no bundle.yaml at all (cannot be verified)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bundle_digest(part_hashes: dict[str, str]) -> str:
    """The bundle's single verifiable digest: ``sha256`` over the sorted ``path:sha256`` lines.

    Deterministic and order-independent (sorted), so any change to any part — or a part added or
    removed — changes the digest. This is the key-free 'signature' a verifier recomputes (§6.6)."""
    payload = "\n".join(f"{path}:{h}" for path, h in sorted(part_hashes.items()))
    return _sha256(payload.encode("utf-8"))


def build_manifest(
    parts: dict[str, bytes],
    *,
    doc_id: str,
    anchor_key: str,
    tool_ver: str,
    source_sha256: list[str],
    captures: dict | None = None,
) -> dict:
    """Build the ``bundle.yaml`` mapping from the bundle's parts.

    ``parts`` maps each part's bundle-relative path → its bytes; it must **exclude** the manifest
    itself (``bundle.yaml`` is the manifest *of* the other parts, never of itself). Any
    ``bundle.yaml`` key is dropped defensively so a caller can't make the manifest self-referential.
    """
    clean = {p: d for p, d in parts.items() if p != MANIFEST_NAME}
    hashes: dict[str, str] = {path: _sha256(data) for path, data in sorted(clean.items())}
    entries = [
        {"path": path, "sha256": hashes[path], "bytes": len(clean[path])} for path in sorted(clean)
    ]
    digest = bundle_digest(hashes)
    return {
        "doc_id": doc_id,
        "anchor_key": anchor_key,
        "generated_by": tool_ver,
        "source_sha256": list(source_sha256),
        "captures": captures or {},
        "parts": entries,
        "bundle_digest": digest,
    }


@dataclass(frozen=True)
class IntegrityFinding:
    """One bundle-integrity finding (empty list ⇒ the bundle is complete and untampered)."""

    kind: str
    path: str  # the offending part path ("" for a digest mismatch)
    detail: str


def verify_manifest(manifest: dict, parts_on_disk: dict[str, bytes]) -> list[IntegrityFinding]:
    """Recompute hashes from ``parts_on_disk`` against ``manifest`` (§6.6 bundle-integrity gate).

    ``parts_on_disk`` maps each on-disk part's bundle-relative path → its bytes, **excluding** the
    manifest file. Returns the integrity findings: a part listed-but-missing or disk-but-unlisted,
    a content hash mismatch, or — when every part matches — a recorded ``bundle_digest`` that
    disagrees with the recomputed one (a tampered digest field). Empty ⇒ verified."""
    listed = {e["path"]: e for e in (manifest.get("parts") or [])}
    findings: list[IntegrityFinding] = []
    for path in sorted(set(listed) | set(parts_on_disk)):
        if path not in parts_on_disk:
            findings.append(IntegrityFinding(MISSING, path, f"{path} listed but absent on disk"))
        elif path not in listed:
            findings.append(IntegrityFinding(EXTRA, path, f"{path} on disk but not in manifest"))
        elif _sha256(parts_on_disk[path]) != listed[path].get("sha256"):
            findings.append(IntegrityFinding(HASH_MISMATCH, path, f"{path} content changed"))
    # Only when the part set + per-part hashes all agree do we separately verify the recorded digest
    # (a part-level finding localises disk tamper; the digest check catches a forged digest field).
    if not findings:
        recomputed = bundle_digest({p: _sha256(d) for p, d in parts_on_disk.items()})
        if recomputed != manifest.get("bundle_digest"):
            findings.append(
                IntegrityFinding(DIGEST_MISMATCH, "", "bundle_digest does not match recomputed")
            )
    return findings
