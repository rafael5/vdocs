"""Property tests for kernel.bundle — the signed bundle manifest (§5.3, §12).

Invariants for any set of parts:
  * a manifest built from parts verifies clean against those same parts (build∘verify round-trip);
  * mutating any one part's bytes is always caught (no silent tamper);
  * dropping any one part is always caught.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from vdocs.kernel import bundle as b

_paths = st.sampled_from(["body.md", "history.yaml", "flags.yaml", "toc.yaml", "capture.yaml"])
_parts = st.dictionaries(_paths, st.binary(min_size=0, max_size=40), min_size=1, max_size=5)


def _build(parts):
    return b.build_manifest(
        parts, doc_id="d", anchor_key="A:B:C", tool_ver="0.1.0", source_sha256=["s"]
    )


@given(parts=_parts)
def test_build_then_verify_is_clean(parts):
    assert b.verify_manifest(_build(parts), parts) == []


@given(parts=_parts, extra=st.binary(min_size=1, max_size=8))
def test_any_content_change_is_caught(parts, extra):
    manifest = _build(parts)
    path = sorted(parts)[0]
    tampered = {**parts, path: parts[path] + extra}  # change one part's bytes
    assert b.verify_manifest(manifest, tampered) != []


@given(parts=_parts)
def test_dropping_a_part_is_caught(parts):
    if len(parts) < 2:
        return  # need at least one part left after dropping
    manifest = _build(parts)
    dropped = dict(sorted(parts.items())[1:])  # remove the first part
    finds = b.verify_manifest(manifest, dropped)
    assert any(f.kind == b.MISSING for f in finds)
