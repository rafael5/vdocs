"""Unit: the D3 release assembler — vdocs-data-v1 bundle + split manifests.

The V7-parity rules under test: bundle_sha256 lives OUTSIDE the bundle (in-bundle
vs standalone manifest variants); doc_meta_staged is stripped from the shipped
index.db (ADR-0001); rich assets are excluded and DECLARED; assembly is
deterministic (two builds → identical bytes).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tarfile

from vdocs.server import release as rel

_CONTRACT = {
    "artifact": "vdocs-data",
    "read_schema_version": "1.5",
    "corpus_content_hash": "e" * 64,
    "corpus_doc_count": 3,
    "entity_types": {"option": {"status": "excluded", "count": 0}},
    "peer_vocabulary": {"artifact": "vista-meta-data", "content_hash": "23d0"},
    "tool_ver": "0.1.0",
    "generated_at": "t",
}


def _payload(tmp_path):
    gold = tmp_path / "gold"
    (gold / "consolidated" / "CPRS" / "or_um").mkdir(parents=True)
    (gold / "consolidated" / "CPRS" / "or_um" / "body.md").write_text("# OR UM\n")
    (gold / "glossary.md").write_text("# Glossary\n")
    (gold / "_shared" / "boilerplate").mkdir(parents=True)
    (gold / "_shared" / "boilerplate" / "b1.md").write_text("boiler\n")
    (gold / "_shared" / "history").mkdir()
    (gold / "_shared" / "history" / "cas1").write_bytes(b"OLD-VERSION-BYTES")
    (gold / "knowledge.db").write_bytes(b"build-intermediate")
    db = tmp_path / "index.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta VALUES ('read_schema_version', '1.5');
        CREATE TABLE doc_meta_staged (doc_id TEXT PRIMARY KEY, payload TEXT);
        INSERT INTO doc_meta_staged VALUES ('x', 'secret-staging');
        """
    )
    conn.commit()
    conn.close()
    return gold, db


def test_strip_staged_removes_the_table_and_keeps_meta(tmp_path):
    _, db = _payload(tmp_path)
    out = tmp_path / "shipped.db"
    rel.strip_staged(db, out)
    conn = sqlite3.connect(out)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "doc_meta_staged" not in tables
    assert conn.execute("SELECT value FROM meta WHERE key='read_schema_version'").fetchone() == (
        "1.5",
    )
    conn.close()
    # the source is untouched (strip works on the shipped COPY)
    src = sqlite3.connect(db)
    assert src.execute("SELECT count(*) FROM doc_meta_staged").fetchone() == (1,)
    src.close()


def test_release_manifest_shape():
    doc = rel.release_manifest(
        _CONTRACT,
        source_commit="5" * 40,
        files={"index.db": {"sha256": "a" * 64, "bytes": 10}},
        consolidated={"files": 1, "tree_sha256": "b" * 64},
    )
    assert doc["tag"] == "data-v1"
    assert doc["corpus_content_hash"] == "e" * 64  # the D1 axes carry through
    assert doc["source_commit"] == "5" * 40
    assert doc["rich_assets"] == "excluded"  # decided + declared, not open (F15)
    assert doc["history_cas"] == "excluded"  # 292MB version-history CAS — v1.x follow-up
    assert doc["knowledge_db"] == "excluded"  # build intermediate, never a consumer surface
    assert doc["consolidated"]["tree_sha256"] == "b" * 64
    assert "bundle_sha256" not in doc  # in-bundle variant (F5)


def test_standalone_adds_bundle_hash():
    inb = rel.release_manifest(_CONTRACT, source_commit="5" * 40, files={}, consolidated={})
    st = rel.standalone_manifest(inb, "b" * 64)
    assert st["bundle_sha256"] == "b" * 64 and "bundle_sha256" not in inb


def test_tree_hash_is_order_independent_and_name_sensitive():
    one = rel.tree_hash({"a/x.md": b"1", "b/y.md": b"2"})
    two = rel.tree_hash({"b/y.md": b"2", "a/x.md": b"1"})
    assert one == two
    assert rel.tree_hash({"a/RENAMED.md": b"1", "b/y.md": b"2"}) != one


def test_bundle_is_deterministic_and_manifest_inside(tmp_path):
    gold, db = _payload(tmp_path)
    inb = rel.release_manifest(_CONTRACT, source_commit="5" * 40, files={}, consolidated={})
    out = tmp_path / rel.BUNDLE_NAME
    sha1 = rel.write_bundle(out, index_db=db, gold_dir=gold, manifest=inb)
    first = out.read_bytes()
    sha2 = rel.write_bundle(out, index_db=db, gold_dir=gold, manifest=inb)
    assert first == out.read_bytes() and sha1 == sha2
    assert hashlib.sha256(first).hexdigest() == sha1
    with tarfile.open(out) as tf:
        names = tf.getnames()
        raw = tf.extractfile(f"{rel.BUNDLE_ROOT}/manifest.json").read()
    assert f"{rel.BUNDLE_ROOT}/index.db" in names
    assert f"{rel.BUNDLE_ROOT}/gold/consolidated/CPRS/or_um/body.md" in names
    assert f"{rel.BUNDLE_ROOT}/gold/_shared/boilerplate/b1.md" in names
    assert f"{rel.BUNDLE_ROOT}/gold/glossary.md" in names
    # excluded-and-declared payload never leaks into the bundle
    assert not [n for n in names if "history" in n or "knowledge.db" in n]
    assert "bundle_sha256" not in json.loads(raw)


def test_release_notes_carries_both_fingerprints():
    notes = rel.release_notes(_CONTRACT, bundle_sha="b" * 64)
    assert "e" * 64 in notes  # corpus_content_hash
    assert "b" * 64 in notes  # bundle_sha256
    assert "23d0" in notes  # peer pin prefix
    assert rel.STANDALONE_NAME in notes  # points at the in-repo record


def test_publish_commands_create_when_tag_absent(tmp_path):
    cmds = rel.publish_commands(tag_exists=False, dist=tmp_path, notes="N")
    assert len(cmds) == 1
    assert cmds[0][:3] == ["gh", "release", "create"]
    assert str(tmp_path / rel.BUNDLE_NAME) in cmds[0]
    assert "--notes" in cmds[0] and "N" in cmds[0]
    assert "--clobber" not in cmds[0]


def test_publish_commands_clobber_and_edit_when_tag_exists(tmp_path):
    # `gh release create` fails on an existing tag — the 2026-07-05 stranded
    # re-cut. Existing tag → replace assets + refresh notes, never create.
    cmds = rel.publish_commands(tag_exists=True, dist=tmp_path, notes="N")
    assert [c[:3] for c in cmds] == [
        ["gh", "release", "upload"],
        ["gh", "release", "edit"],
    ]
    upload, edit = cmds
    assert upload[3] == rel.TAG and "--clobber" in upload
    for name in (rel.BUNDLE_NAME, rel.STANDALONE_NAME, rel.SUMS_NAME):
        assert str(tmp_path / name) in upload
    assert edit[3] == rel.TAG and "--notes" in edit and "N" in edit
