"""Typed configuration — one Settings object, all paths derived from the lake (§9.1).

ADR-005: Pydantic Settings, validated at startup, env-overridable via ``DATA_DIR``.
There are **no** module-level path constants and no hardcoded absolute paths anywhere
else in the codebase — stages receive resolved paths from this object via ``ctx``.
The layer→directory map is §5.3.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from vdocs import __version__


def _default_data_dir() -> Path:
    return Path.home() / "data" / "vdocs"


class Settings(BaseSettings):
    """Resolved configuration for one pipeline run."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(
        default_factory=_default_data_dir,
        validation_alias=AliasChoices("DATA_DIR", "VDOCS_DATA_DIR", "data_dir"),
    )
    vdl_base_url: str = Field(
        default="https://www.va.gov/vdl/",
        validation_alias=AliasChoices("VDL_BASE_URL", "VDOCS_VDL_BASE_URL", "vdl_base_url"),
    )

    @property
    def tool_ver(self) -> str:
        return __version__

    # --- the lake root (§5.3) ---
    @property
    def lake(self) -> Path:
        return self.data_dir

    # --- bronze (immutable evidence) ---
    @property
    def bronze(self) -> Path:
        return self.lake / "bronze"

    @property
    def bronze_catalog(self) -> Path:
        return self.bronze / "catalog"

    @property
    def bronze_raw(self) -> Path:
        return self.bronze / "raw"

    @property
    def catalog_raw(self) -> Path:
        return self.bronze_catalog / "raw.json"

    @property
    def catalog_enriched(self) -> Path:
        return self.bronze_catalog / "enriched.json"

    @property
    def raw_index(self) -> Path:
        return self.bronze_raw / "index.json"

    @property
    def assets(self) -> Path:
        return self.lake / "assets"

    # --- silver (conformed, versioned text) ---
    @property
    def silver(self) -> Path:
        return self.lake / "silver"

    @property
    def silver_text(self) -> Path:
        return self.silver / "text"

    # --- gold (curated, derived, computable) ---
    @property
    def gold(self) -> Path:
        return self.lake / "gold"

    @property
    def gold_consolidated(self) -> Path:
        return self.gold / "consolidated"

    @property
    def gold_shared(self) -> Path:
        return self.gold / "_shared"

    @property
    def publish(self) -> Path:
        return self.gold / "publish"

    @property
    def corpus_manifest(self) -> Path:
        return self.gold / "corpus-manifest.json"

    @property
    def discovery_json(self) -> Path:
        return self.gold / "discovery.json"

    @property
    def glossary(self) -> Path:
        return self.gold / "glossary.md"

    # --- derived stores (§5.5) ---
    @property
    def state_db(self) -> Path:
        return self.lake / "state.db"

    @property
    def index_db(self) -> Path:
        return self.lake / "index.db"

    @property
    def vectors_db(self) -> Path:
        return self.lake / "vectors.db"

    @property
    def reports(self) -> Path:
        return self.lake / "reports"
