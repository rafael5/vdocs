"""RR.2 — the BM25 field weights are a pinned constant, and the engine can be swept against them.

Two things are tested here, both for the same reason: a tuning knob nobody pins is a knob that
drifts. The shipped weights are pinned to exact values, so changing them is a deliberate committed
decision with a measurement behind it; and `lexical_search` accepts an explicit override, so the
sweep measures the **real engine** rather than a re-implementation of its query.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vdocs.server import search
from vdocs.server import search_pure as sp


def test_shipped_weights_are_pinned() -> None:
    # Fitted on the 451-document DEV collection (L1.2) and re-swept on production in RR.2.
    # A change here is only legitimate with a per-question win recorded in the tracker.
    assert sp.FTS_WEIGHTS == {
        "doc_title": 2.5,
        "title": 2.0,
        "section_path": 1.5,
        "body": 1.0,
    }


def test_weights_map_to_columns_in_schema_order() -> None:
    # A misordered weight vector silently mis-weights columns — the failure this ordering prevents.
    assert sp.bm25_weights() == [1.0, 1.0, 1.0, 2.0, 2.5, 1.5, 1.0]


def _lake(tmp_path: Path) -> Path:
    """Two sections: one carries the query token in its DOC TITLE, the other only in its body."""
    db = tmp_path / "index.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE documents (
          doc_key TEXT PRIMARY KEY, doc_id TEXT, title TEXT,
          app_code TEXT, doc_type TEXT, pkg_ns TEXT
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
          chunk_id UNINDEXED, section_id UNINDEXED, doc_key UNINDEXED,
          title, doc_title, section_path, body
        );
        """
    )
    conn.executemany(
        "INSERT INTO documents VALUES (?, ?, ?, 'XX', 'UM', 'XX')",
        [
            ("XX/titled", "XX:titled", "Taskman Manual"),
            ("XX/bodied", "XX:bodied", "General Manual"),
        ],
    )
    conn.executemany(
        "INSERT INTO chunks_fts "
        "(chunk_id, section_id, doc_key, title, doc_title, section_path, body) "
        "VALUES (?, ?, ?, ?, ?, 'XX', ?)",
        [
            ("c1", "XX/titled/s", "XX/titled", "Overview", "Taskman Manual", "an overview"),
            ("c2", "XX/bodied/s", "XX/bodied", "Overview", "General Manual",
             "taskman taskman taskman scheduling detail"),
        ],
    )  # fmt: skip
    conn.commit()
    conn.close()
    return db


def test_search_honours_an_explicit_weight_override(tmp_path: Path) -> None:
    db = _lake(tmp_path)
    # doc_title weighted far above body promotes the document whose TITLE carries the token…
    heavy_title = search.lexical_search(
        db, "taskman", k=2, expansions={}, weights={"doc_title": 50.0, "body": 1.0}
    )
    assert heavy_title[0]["section_id"] == "XX/titled/s"
    # …and the reverse ordering promotes the section whose BODY does. The override reaches the
    # ranking, which is what makes a sweep meaningful.
    heavy_body = search.lexical_search(
        db, "taskman", k=2, expansions={}, weights={"doc_title": 0.1, "body": 50.0}
    )
    assert heavy_body[0]["section_id"] == "XX/bodied/s"


def test_search_defaults_to_the_shipped_weights(tmp_path: Path) -> None:
    db = _lake(tmp_path)
    default = search.lexical_search(db, "taskman", k=2, expansions={})
    explicit = search.lexical_search(db, "taskman", k=2, expansions={}, weights=sp.FTS_WEIGHTS)
    assert [h["section_id"] for h in default] == [h["section_id"] for h in explicit]
