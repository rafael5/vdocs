"""Unit tests for kernel.cas — content-addressed store + atomic write (§5.1, §9.2)."""

import hashlib

import pytest

from vdocs.kernel import cas


def test_atomic_write_creates_file_with_content(tmp_path):
    target = tmp_path / "nested" / "out.txt"
    cas.atomic_write(target, b"payload")
    assert target.read_bytes() == b"payload"


def test_atomic_write_leaves_no_tmp_files(tmp_path):
    target = tmp_path / "out.txt"
    cas.atomic_write(target, b"payload")
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


def test_put_returns_sha256_and_stores_by_hash(tmp_path):
    store = cas.Cas(tmp_path)
    digest = store.put(b"hello world", ext="txt")
    assert digest == hashlib.sha256(b"hello world").hexdigest()
    assert store.path_for(digest, ext="txt").read_bytes() == b"hello world"


def test_put_is_idempotent_write_once(tmp_path):
    store = cas.Cas(tmp_path)
    d1 = store.put(b"same", ext="bin")
    path = store.path_for(d1, ext="bin")
    mtime_before = path.stat().st_mtime_ns
    d2 = store.put(b"same", ext="bin")  # second put must not rewrite
    assert d1 == d2
    assert path.stat().st_mtime_ns == mtime_before


def test_atomic_write_skips_rewrite_when_content_unchanged(tmp_path):
    # R2: a no-op re-write must not touch the file, so the cheap size:mtime_ns fingerprint stays
    # stable and SKIP_IF_UNCHANGED actually skips on a re-run.
    target = tmp_path / "out.md"
    cas.atomic_write(target, b"same bytes")
    mtime_before = target.stat().st_mtime_ns
    cas.atomic_write(target, b"same bytes")  # identical → must not rewrite
    assert target.stat().st_mtime_ns == mtime_before
    assert target.read_bytes() == b"same bytes"


def test_atomic_write_rewrites_when_content_changes(tmp_path):
    target = tmp_path / "out.md"
    cas.atomic_write(target, b"first")
    mtime_before = target.stat().st_mtime_ns
    cas.atomic_write(target, b"second")  # changed → must rewrite
    assert target.read_bytes() == b"second"
    assert target.stat().st_mtime_ns != mtime_before


def test_get_round_trips(tmp_path):
    store = cas.Cas(tmp_path)
    digest = store.put(b"data", ext="dat")
    assert store.get(digest, ext="dat") == b"data"


def test_get_missing_raises(tmp_path):
    store = cas.Cas(tmp_path)
    with pytest.raises(FileNotFoundError):
        store.get("0" * 64, ext="dat")


def test_atomic_write_cleans_up_tmp_on_failure(tmp_path):
    # Replacing onto an existing *directory* fails, exercising the cleanup branch.
    target = tmp_path / "adir"
    target.mkdir()
    with pytest.raises(OSError):
        cas.atomic_write(target, b"payload")
    assert [p.name for p in tmp_path.iterdir()] == ["adir"]  # no stray .tmp left


def test_has_reports_membership(tmp_path):
    store = cas.Cas(tmp_path)
    digest = store.put(b"x", ext="dat")
    assert store.has(digest, ext="dat")
    assert not store.has("f" * 64, ext="dat")
