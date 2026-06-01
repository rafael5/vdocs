"""Unit tests for kernel.fingerprint — file/tree/sqlite signatures (§7, §9.2)."""

import hashlib
import os
import sqlite3

from vdocs.kernel import fingerprint as fp


def _touch(path, content: bytes, mtime: float):
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))


def test_file_fingerprint_cheap_is_stable_for_same_size_and_mtime(tmp_path):
    f = tmp_path / "a.txt"
    _touch(f, b"hello", 1_000_000.0)
    assert fp.file_fingerprint(f) == fp.file_fingerprint(f)


def test_file_fingerprint_cheap_changes_when_mtime_changes(tmp_path):
    f = tmp_path / "a.txt"
    _touch(f, b"hello", 1_000_000.0)
    first = fp.file_fingerprint(f)
    _touch(f, b"hello", 2_000_000.0)
    assert fp.file_fingerprint(f) != first


def test_file_fingerprint_verify_is_content_hash(tmp_path):
    f = tmp_path / "a.txt"
    _touch(f, b"hello", 5.0)
    expected = hashlib.sha256(b"hello").hexdigest()
    assert fp.file_fingerprint(f, verify=True) == expected
    # mtime change does not affect the strong content hash
    _touch(f, b"hello", 999.0)
    assert fp.file_fingerprint(f, verify=True) == expected


def test_tree_fingerprint_is_deterministic_and_order_independent(tmp_path):
    (tmp_path / "sub").mkdir()
    _touch(tmp_path / "b.txt", b"two", 10.0)
    _touch(tmp_path / "sub" / "a.txt", b"one", 10.0)
    assert fp.tree_fingerprint(tmp_path) == fp.tree_fingerprint(tmp_path)


def test_tree_fingerprint_changes_when_a_member_changes(tmp_path):
    _touch(tmp_path / "a.txt", b"one", 10.0)
    before = fp.tree_fingerprint(tmp_path, verify=True)
    _touch(tmp_path / "a.txt", b"CHANGED", 10.0)
    assert fp.tree_fingerprint(tmp_path, verify=True) != before


def test_tree_fingerprint_differs_for_different_trees(tmp_path):
    t1 = tmp_path / "t1"
    t2 = tmp_path / "t2"
    t1.mkdir()
    t2.mkdir()
    _touch(t1 / "a.txt", b"x", 10.0)
    _touch(t2 / "a.txt", b"y", 10.0)
    assert fp.tree_fingerprint(t1, verify=True) != fp.tree_fingerprint(t2, verify=True)


def test_iter_files_is_sorted_and_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "sub" / "a.txt").write_text("a")
    (tmp_path / "c.txt").write_text("c")
    rels = [p.relative_to(tmp_path).as_posix() for p in fp.iter_files(tmp_path)]
    assert rels == sorted(rels)
    assert rels == ["b.txt", "c.txt", "sub/a.txt"]


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (id, v) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_sqlite_fingerprint_cheap_counts_rows(tmp_path):
    db = tmp_path / "x.db"
    _make_db(db, [(1, "a"), (2, "b")])
    assert fp.sqlite_fingerprint(db, "t") == fp.sqlite_fingerprint(db, "t")


def test_sqlite_fingerprint_verify_changes_with_content(tmp_path):
    db = tmp_path / "x.db"
    _make_db(db, [(1, "a")])
    before = fp.sqlite_fingerprint(db, "t", verify=True)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE t SET v = 'CHANGED' WHERE id = 1")
    conn.commit()
    conn.close()
    assert fp.sqlite_fingerprint(db, "t", verify=True) != before
