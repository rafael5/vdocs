"""Integration: every published SQL recipe executes against a contract-shaped index.db.

The recipes in ``ai-manifest.json`` are the Tier-1 self-sufficiency promise — an agent with
only the bundle and sqlite3 runs them verbatim. This test seeds a minimal index.db (the real
``_SCHEMA`` + the real contract ``view_ddl``) and executes each recipe with sample params, so
a schema or contract change that would break a published recipe breaks the build instead.
"""

from __future__ import annotations

from vdocs.kernel import db
from vdocs.kernel import read_contract as rc
from vdocs.stages.index.stage import _SCHEMA
from vdocs.stages.manifest.manifest_pure import SQL_RECIPES

_SAMPLE_PARAMS = {
    "match": '"kernel" OR "sign"',
    "k": 5,
    "section_id": "XU/krn_ug/signing-on",
    "app": "XU",
    "doc_type": "UM",
    "type": "routine",
    "name": "%SIGN%",
    "entity_id": "routine:XUS",
}


def test_every_published_recipe_executes_on_a_contract_db(tmp_path):
    conn = db.connect(tmp_path / "index.db")
    conn.executescript(_SCHEMA)
    spec = rc.load(rc.contract_path())
    conn.executescript(rc.view_ddl(spec))
    conn.execute("INSERT INTO meta VALUES ('read_schema_version', ?)", (rc.version(spec),))
    for name, recipe in SQL_RECIPES.items():
        if name.startswith("_"):
            continue
        sql = recipe["sql"]
        params = {k: v for k, v in _SAMPLE_PARAMS.items() if f":{k}" in sql}
        rows = conn.execute(sql, params).fetchall()  # must not raise
        assert isinstance(rows, list), name
    conn.close()


def test_the_synonym_recipe_states_its_real_scope(tmp_path):
    """SL.2: the card told assistants this recipe was *the* "query-vocabulary mismatch fix".
    Measured (SL.1), it covers the 21 FileMan files the DI pilot seeded, and search itself expands
    exactly one of them. A published capability the system does not have is the same defect as a
    stale coverage constant, so the purpose has to name the scope it actually has."""
    purpose = SQL_RECIPES["skl_synonyms"]["purpose"]
    assert "query-vocabulary mismatch fix" not in purpose
    assert "FileMan" in purpose and "pilot" in purpose
