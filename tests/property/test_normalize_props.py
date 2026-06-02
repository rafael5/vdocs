"""Property tests for the normalize anchor substrate (§6.7, §13 ~line 1374).

The structural invariant the whole Phase-4 retrieval layer depends on: **no anchor points
nowhere.** For any generated heading tree with bookmarked cross-references, every link target
that ``normalize`` rewrites resolves into the anchor map — zero dead anchors."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from vdocs.stages.normalize import anchors_pure as ac
from vdocs.stages.normalize import normalize_pure as nz

# heading text that yields a non-empty GitHub slug (letters/digits + single spaces)
_words = (
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 ", min_size=1, max_size=20)
    .map(lambda s: re.sub(r"\s+", " ", s).strip())
    .filter(lambda s: ac.github_slug(s, {}) != "")
)

_LINK_TARGET = re.compile(r"\]\(#([^)]+)\)")


@given(headings=st.lists(st.tuples(st.integers(min_value=2, max_value=4), _words), max_size=8))
def test_no_anchor_points_nowhere(headings: list[tuple[int, str]]):
    # build a body: an H1 title, then each heading carrying a _Toc bookmark, plus a cross-ref to it
    parts = ["# Manual", ""]
    for i, (level, text) in enumerate(headings):
        bm = f"_Toc{i}"
        parts += [f"See [{text}](#{bm}).", "", f'{"#" * level} <span id="{bm}"></span>{text}', ""]
    body = "\n".join(parts) + "\n"

    out_body, amap = nz.normalize_body(body, frozenset(), doc_id="app/m")
    slugs = {r.github_slug for r in amap.rows}

    # every rewritten link target resolves: into the anchor map, the TOC anchor, or (only for a
    # target we never had a heading for) an UNRESOLVED bookmark left untouched — never a slug
    # that points at nothing.
    for m in _LINK_TARGET.finditer(out_body):
        target = m.group(1)
        if target == "contents":  # the TOC anchor (back-links + the `## Contents` heading)
            continue
        if target.startswith("_Toc"):  # an unmapped bookmark, deliberately left as-is
            assert amap.outbound.get(target) == ac.UNRESOLVED
            continue
        assert target in slugs  # resolved slugs always land in the anchor map


@given(texts=st.lists(_words, min_size=1, max_size=10))
def test_github_slug_is_deterministic_and_unique(texts: list[str]):
    seen: dict[str, int] = {}
    slugs = [ac.github_slug(t, seen) for t in texts]
    assert len(set(slugs)) == len(slugs)  # every minted slug is unique within a document
    # determinism: the same input sequence (fresh `seen`) yields the identical slugs
    seen2: dict[str, int] = {}
    assert [ac.github_slug(t, seen2) for t in texts] == slugs


@given(text=_words, n=st.integers(min_value=1, max_value=6))
def test_github_slug_suffix_is_monotonic(text: str, n: int):
    seen: dict[str, int] = {}
    slugs = [ac.github_slug(text, seen) for _ in range(n)]
    base = slugs[0]
    # the k-th repeat of a heading gets the GitHub `-1`, `-2`, … document-order suffix
    assert slugs == [base] + [f"{base}-{i}" for i in range(1, n)]


@given(headings=st.lists(st.tuples(st.integers(min_value=1, max_value=4), _words), max_size=8))
def test_normalize_body_is_idempotent(headings: list[tuple[int, str]]):
    # §12's literal invariant: normalize_body(normalize_body(x)) == normalize_body(x)
    parts: list[str] = []
    for level, text in headings:
        parts += ["#" * level + " " + text, "", "Some body prose.", ""]
    body = "\n".join(parts) + "\n"
    once, _ = nz.normalize_body(body, frozenset(), doc_id="app/d")
    twice, _ = nz.normalize_body(once, frozenset(), doc_id="app/d")
    assert twice == once
