"""Property tests for kernel.fingerprint.tree_fingerprint (§7.4, §12).

The strong (content) tree fingerprint must be a pure function of the tree's *content*: independent
of the order files were created, and sensitive to any single-byte change."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from vdocs.kernel import fingerprint as fp

_name = st.text(alphabet="abcdefgh", min_size=1, max_size=8)


@given(files=st.dictionaries(_name, st.binary(max_size=20), min_size=1, max_size=6))
def test_tree_fingerprint_is_order_independent_and_byte_sensitive(files: dict[str, bytes]):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        ra, rb = Path(a), Path(b)
        for name, content in files.items():
            (ra / name).write_bytes(content)
        for name, content in reversed(list(files.items())):  # opposite creation order
            (rb / name).write_bytes(content)

        # order-independent: same content set → same strong fingerprint regardless of write order
        before = fp.tree_fingerprint(ra, verify=True)
        assert before == fp.tree_fingerprint(rb, verify=True)

        # byte-sensitive: changing any one file's bytes changes the fingerprint
        victim = sorted(files)[0]
        (ra / victim).write_bytes(files[victim] + b"\x01")
        assert fp.tree_fingerprint(ra, verify=True) != before
