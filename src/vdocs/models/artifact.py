"""Artifact contracts — the boundary type for a declared pipeline input/output (§7.1).

An ``ArtifactContract`` is the data half of the stage contract: it declares *what* an
artifact is (kind, storage class, producer) and knows how to ``locate`` / ``validate`` /
``fingerprint`` itself **from typed config** — never from a hardcoded path (§9.1). The
behaviour dispatches on ``kind``; ``EXTERNAL`` artifacts (e.g. the VDL website) cannot be
cheaply inspected, so they always validate and carry a constant fingerprint.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from vdocs.kernel import db
from vdocs.kernel import fingerprint as fp

if TYPE_CHECKING:
    from vdocs.config import Settings


class Kind(StrEnum):
    """The physical shape of an artifact (§7.1)."""

    FILE = "file"
    TREE_TEXT = "tree_text"
    TREE_ASSET_CAS = "tree_asset_cas"
    SQLITE_TABLE = "sqlite_table"
    SQLITE_VIEW = "sqlite_view"
    GIT_REMOTE = "git_remote"
    EXTERNAL = "external"  # a non-lake source such as the VDL website (the `vdl` artifact)


class StorageClass(StrEnum):
    """The lifecycle/ownership class an artifact belongs to (§5.1, §7.1)."""

    ASSET_WRITE_ONCE = "asset_write_once"
    TEXT_VERSIONED = "text_versioned"
    STATE = "state"
    EXTERNAL = "external"


class Root(StrEnum):
    """Which configured base a file/tree artifact resolves against (§9.1).

    Almost everything lives in the data lake; the curated pattern registries are the one
    exception — version-controlled repo config, not lake data (§9.7) — yet they are a real,
    fingerprintable input, so they resolve against ``cfg.registries`` instead of ``cfg.lake``.
    """

    LAKE = "lake"
    REGISTRIES = "registries"


class Resolved(BaseModel):
    """A located artifact: a filesystem path and, for SQLite kinds, a table name."""

    model_config = {"frozen": True}

    path: Path | None = None
    table: str | None = None


class CheckResult(BaseModel):
    """Outcome of an artifact validity check: usable + a human-readable detail."""

    model_config = {"frozen": True}

    ok: bool
    detail: str = ""


_TREE_KINDS = {Kind.TREE_TEXT, Kind.TREE_ASSET_CAS}
_SQLITE_KINDS = {Kind.SQLITE_TABLE, Kind.SQLITE_VIEW}
_NON_LOCAL_KINDS = {Kind.EXTERNAL, Kind.GIT_REMOTE}


class ArtifactContract(BaseModel):
    """A declared input/output of a stage, identified by a stable ``key`` (§7.1)."""

    model_config = {"frozen": True}

    key: str
    kind: Kind
    storage_class: StorageClass
    produced_by: str | None = None
    optional: bool = False
    # Which configured base a file/tree resolves against (lake by default; §9.1).
    root: Root = Root.LAKE
    # Locators: relpath for files/trees (None ⇒ the root dir itself); db+table for SQLite.
    relpath: str | None = None
    db: str | None = None
    table: str | None = None

    def locate(self, cfg: Settings) -> Resolved:
        """Resolve this artifact to a concrete path/(db, table) from config."""
        if self.kind in _NON_LOCAL_KINDS:
            return Resolved()
        if self.kind in _SQLITE_KINDS:
            assert self.db is not None, f"{self.key}: SQLite artifact needs a db"
            return Resolved(path=cfg.lake / self.db, table=self.table)
        base = cfg.registries if self.root is Root.REGISTRIES else cfg.lake
        if self.relpath is not None:
            return Resolved(path=base / self.relpath)
        assert self.root is Root.REGISTRIES, f"{self.key}: file/tree artifact needs a relpath"
        return Resolved(path=base)

    def validate(self, cfg: Settings) -> CheckResult:  # type: ignore[override]
        """Check the artifact exists, is structurally usable, and meets min cardinality.

        (Shadows Pydantic's deprecated ``BaseModel.validate`` classmethod alias, which we
        never use — the contract API in §7.1 specifies this name.)
        """
        if self.kind in _NON_LOCAL_KINDS:
            return CheckResult(ok=True, detail=f"{self.kind} source assumed present")
        resolved = self.locate(cfg)
        path = resolved.path
        assert path is not None
        if self.kind == Kind.FILE:
            ok = path.is_file()
            return CheckResult(ok=ok, detail="" if ok else f"missing file {path}")
        if self.kind in _TREE_KINDS:
            if not path.is_dir():
                return CheckResult(ok=False, detail=f"missing tree {path}")
            empty = next(fp.iter_files(path), None) is None
            return CheckResult(ok=not empty, detail="empty tree" if empty else "")
        # SQLite table/view
        if not path.exists():
            return CheckResult(ok=False, detail=f"missing db {path}")
        return self._validate_sqlite(path)

    def _validate_sqlite(self, path: Path) -> CheckResult:
        kind_filter = "view" if self.kind == Kind.SQLITE_VIEW else "table"
        conn = db.connect(path, read_only=True)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = ? AND name = ?",
                (kind_filter, self.table),
            ).fetchone()
        finally:
            conn.close()
        ok = row is not None
        return CheckResult(ok=ok, detail="" if ok else f"missing {kind_filter} {self.table}")

    def fingerprint(self, cfg: Settings, *, verify: bool = False) -> str:
        """Cheap-by-default content signature (strong on ``verify``); §7.3."""
        if self.kind in _NON_LOCAL_KINDS:
            return f"external:{self.key}"
        resolved = self.locate(cfg)
        path = resolved.path
        assert path is not None
        if self.kind == Kind.FILE:
            return fp.file_fingerprint(path, verify=verify)
        if self.kind in _TREE_KINDS:
            return fp.tree_fingerprint(path, verify=verify)
        assert self.table is not None
        return fp.sqlite_fingerprint(path, self.table, verify=verify)
