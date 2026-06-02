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
    crawl_delay: float = Field(
        default=1.5,
        validation_alias=AliasChoices("CRAWL_DELAY", "VDOCS_CRAWL_DELAY", "crawl_delay"),
    )

    @property
    def tool_ver(self) -> str:
        return __version__

    @property
    def user_agent(self) -> str:
        """Descriptive crawl/fetch User-Agent — VA infra 403s the default client UA (§3.1)."""
        return f"vdocs/{__version__} (+github.com/rafael5/vdocs)"

    registries_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("REGISTRIES_DIR", "VDOCS_REGISTRIES_DIR", "registries_dir"),
    )

    @property
    def registries(self) -> Path:
        """The curated, version-controlled vocabularies — in the **repo**, not the lake (§9.7)."""
        if self.registries_dir is not None:
            return self.registries_dir
        # repo root = src/vdocs/config.py → parents[2]
        return Path(__file__).resolve().parents[2] / "registries"

    # --- the lake root (§5.3) ---
    @property
    def lake(self) -> Path:
        return self.data_dir

    # --- inventory medallion (control plane; metadata only — §4, §5.3) ---
    @property
    def inventory(self) -> Path:
        return self.lake / "inventory"

    @property
    def inventory_bronze(self) -> Path:
        return self.inventory / "bronze"

    @property
    def inventory_silver(self) -> Path:
        return self.inventory / "silver"

    @property
    def inventory_gold(self) -> Path:
        return self.inventory / "gold"

    @property
    def gold_inventory_json(self) -> Path:
        """inv-gold: the GOLD INVENTORY as a browsable/portable JSON selection surface."""
        return self.inventory_gold / "inventory.json"

    @property
    def gold_inventory_db(self) -> Path:
        """inv-gold: the GOLD INVENTORY as a queryable SQLite store (table ``inventory``)."""
        return self.inventory_gold / "inventory.db"

    @property
    def gold_inventory_csv(self) -> Path:
        """inv-gold: the GOLD INVENTORY published as a flat CSV table (doc_id + the §5 columns)."""
        return self.inventory_gold / "inventory.csv"

    @property
    def catalog_raw(self) -> Path:
        """inv-bronze: the raw scraped catalog (immutable crawl evidence)."""
        return self.inventory_bronze / "catalog.raw.json"

    @property
    def catalog_enriched(self) -> Path:
        """inv-silver: the conformed/enriched per-record inventory."""
        return self.inventory_silver / "catalog.enriched.json"

    # --- document medallion bronze (data plane; the fetched subset — §5.3) ---
    @property
    def bronze(self) -> Path:
        return self.lake / "bronze"

    @property
    def bronze_raw(self) -> Path:
        return self.bronze / "raw"

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

    @property
    def silver_converted(self) -> Path:
        """document-silver 01: raw markdown bundles from ``convert`` (pre-identity-FM)."""
        return self.silver_text / "01-converted"

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
