"""RC.3 — the golden harness GATES on unscoreable queries instead of only reporting them.

R‑19's real fix: a labelled question whose every judged section is outside the collection is
measuring label rot, not the engine. The harness has detected and excluded these since 2026-08-02
(`unscoreable_queries` in the rollup); these tests make their presence a *failure* — the harness
exits non-zero — while keeping the exclusion behaviour, so a red run still reports honest means.

Real objects, no mocks: a minimal but faithful index.db (documents / doc_sections / chunks /
chunks_fts / meta, the exact shape `server.search.lexical_search` and `evaluate()` read) plus
hand-written golden keys, one answerable and one hand-staled.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.baseline_golden import evaluate, gate_exit_code, main  # noqa: E402
from vdocs.server.search_pure import read_query  # noqa: E402

LIVE_SECTION = "XX/doc1/alpha"
GONE_SECTION = "ZZ/gone/never-fetched"


def _mk_lake(tmp_path: Path) -> Path:
    """A one-document, one-section lake whose index.db satisfies the harness end to end."""
    lake = tmp_path / "lake"
    lake.mkdir()
    conn = sqlite3.connect(lake / "index.db")
    conn.executescript(
        """
        CREATE TABLE documents (
          doc_key TEXT PRIMARY KEY, doc_id TEXT, title TEXT,
          app_code TEXT, doc_type TEXT, pkg_ns TEXT
        );
        CREATE TABLE doc_sections (
          section_id TEXT PRIMARY KEY, doc_key TEXT, is_latest INTEGER NOT NULL
        );
        CREATE TABLE chunks (chunk_id TEXT, section_id TEXT, part INTEGER, text TEXT);
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
          chunk_id UNINDEXED, section_id UNINDEXED, doc_key UNINDEXED,
          title, doc_title, section_path, body
        );
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    body = "The alpha install procedure loads the kernel distribution and installs it."
    conn.execute(
        "INSERT INTO documents VALUES ('XX/doc1', 'XX:doc1', 'Alpha Manual', 'XX', 'UG', 'XX')"
    )
    conn.execute("INSERT INTO doc_sections VALUES (?, 'XX/doc1', 1)", (LIVE_SECTION,))
    conn.execute("INSERT INTO chunks VALUES ('c1', ?, 0, ?)", (LIVE_SECTION, body))
    conn.execute(
        "INSERT INTO chunks_fts VALUES ('c1', ?, 'XX/doc1', 'Alpha', 'Alpha Manual', 'Alpha', ?)",
        (LIVE_SECTION, body),
    )
    conn.execute("INSERT INTO meta VALUES ('corpus_content_hash', 'fixturehash')")
    conn.commit()
    conn.close()
    return lake


def _mk_key(tmp_path: Path, name: str, staled: bool) -> Path:
    queries = [
        {
            "id": "alpha-install",
            "query": "How do I install the alpha kernel distribution?",
            "keywords": "install alpha kernel distribution",
            "intent": "answerable",
            "axis": "fixture",
            "relevant": [{"section_id": LIVE_SECTION, "grade": 3}],
        }
    ]
    if staled:
        queries.append(
            {
                "id": "gone-question",
                "query": "How does the departed application work?",
                "keywords": "departed application",
                "intent": "every judged section is outside the collection",
                "axis": "fixture",
                "relevant": [{"section_id": GONE_SECTION, "grade": 3}],
            }
        )
    path = tmp_path / name
    path.write_text(yaml.safe_dump({"version": 1, "k": 10, "queries": queries}), encoding="utf-8")
    return path


def test_gate_reds_on_a_hand_staled_key(tmp_path: Path) -> None:
    lake = _mk_lake(tmp_path)
    key = _mk_key(tmp_path, "staled.yaml", staled=True)
    result = evaluate(lake, key, None, expand=False)
    rollup = result["rollup"]
    assert rollup["unscoreable_queries"] == 1
    # The exclusion behaviour survives: the red run still reports honest means over the
    # answerable query, rather than refusing to produce a number.
    assert rollup["labeled_queries"] == 1
    assert rollup["mean_ndcg@k"] is not None
    assert gate_exit_code(rollup) == 1


def test_gate_passes_on_an_all_answerable_key(tmp_path: Path) -> None:
    lake = _mk_lake(tmp_path)
    key = _mk_key(tmp_path, "clean.yaml", staled=False)
    rollup = evaluate(lake, key, None, expand=False)["rollup"]
    assert rollup["unscoreable_queries"] == 0
    assert gate_exit_code(rollup) == 0


def test_main_exits_nonzero_on_staled_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lake = _mk_lake(tmp_path)
    key = _mk_key(tmp_path, "staled.yaml", staled=True)
    out = tmp_path / "report.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "baseline_golden.py",
            "--data-dir",
            str(lake),
            "--queries",
            str(key),
            "--out",
            str(out),
            "--no-expand",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    # The report was still written before the gate fired — evidence survives a red run.
    assert out.is_file()
    assert json.loads(out.with_suffix(".json").read_text())["rollup"]["unscoreable_queries"] == 1


def test_main_completes_on_clean_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lake = _mk_lake(tmp_path)
    key = _mk_key(tmp_path, "clean.yaml", staled=False)
    out = tmp_path / "report.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "baseline_golden.py",
            "--data-dir",
            str(lake),
            "--queries",
            str(key),
            "--out",
            str(out),
            "--no-expand",
        ],
    )
    main()  # no SystemExit — a clean key completes normally
    assert out.is_file()


# ── Fix 4 of the keyword-search proposal: the harness grades the keyword form ──────────────────


def _write_key(tmp_path: Path, queries: list[dict]) -> Path:
    path = tmp_path / "key.yaml"
    path.write_text(yaml.safe_dump({"version": 1, "k": 10, "queries": queries}), encoding="utf-8")
    return path


def test_harness_searches_the_keyword_form_not_the_sentence(tmp_path: Path) -> None:
    lake = _mk_lake(tmp_path)
    # No word of the sentence is in the corpus, so searching it would find nothing at all.
    key = _write_key(
        tmp_path,
        [
            {
                "id": "alpha-install",
                "query": "What happens here?",
                "keywords": "alpha install",
                "axis": "fixture",
                "relevant": [{"section_id": LIVE_SECTION, "grade": 3}],
            }
        ],
    )
    result = evaluate(lake, key, None, expand=False)
    assert result["queries"][0]["top5"][0]["section_id"] == LIVE_SECTION
    assert result["rollup"]["mean_ndcg@k"] == 1.0


def test_a_query_without_a_keyword_form_is_refused(tmp_path: Path) -> None:
    lake = _mk_lake(tmp_path)
    key = _write_key(
        tmp_path,
        [
            {
                "id": "sentence-only",
                "query": "How do I install the alpha kernel distribution?",
                "axis": "fixture",
                "relevant": [{"section_id": LIVE_SECTION, "grade": 3}],
            }
        ],
    )
    with pytest.raises(SystemExit, match="sentence-only"):
        evaluate(lake, key, None, expand=False)


def test_every_golden_query_has_a_searchable_keyword_form() -> None:
    spec = yaml.safe_load(Path("registries/golden-queries.yaml").read_text(encoding="utf-8"))
    for q in spec["queries"]:
        assert read_query(q.get("keywords") or "").all, q["id"]


def test_the_six_plain_english_searches_are_in_the_golden_key() -> None:
    spec = yaml.safe_load(Path("registries/golden-queries.yaml").read_text(encoding="utf-8"))
    plain = {q["keywords"]: q for q in spec["queries"] if q.get("axis") == "plain-english"}
    assert set(plain) == {
        "change password",
        "create user account",
        "background jobs",
        "set up printer",
        "enter patient allergies",
        "send email",
    }
    assert all(q["relevant"] for q in plain.values())
