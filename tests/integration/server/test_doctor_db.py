"""Integration: `diagnose` over a seeded index.db — the GREEN happy path and RED defect paths."""

from __future__ import annotations

from vdocs.kernel import db
from vdocs.server import doctor as doc
from vdocs.server.doctor import Health
from vdocs.stages.index.stage import _SCHEMA

_KEPT = frozenset({"UM", "TM"})
_POLICY = doc.DoctorPolicy(
    coverage={
        "app_user": doc.CoverageSpec(100),
        "doc_user": doc.CoverageSpec(100),
        "function_category": doc.CoverageSpec(90, "fallback-profile apps have no SPM line"),
        "doc_type": doc.CoverageSpec(100),
    },
    accepted_anchor_edge_cases=frozenset({"AR/WS:p13"}),
)

_DOC_COLS = (
    "doc_key, doc_id, app_code, doc_type, section, pkg_ns, version, patch_id, anchor_key, "
    "group_key, title, doc_label, app_user, doc_user, software_class, function_category, "
    "word_count, section_count, is_latest, template_id, source_sha256, source_url"
)


def _doc(conn, *, doc_key, doc_id, doc_type="UM", anchor_key="ADT:DG:UM:um", is_latest=1,
         app_user="clinical", doc_user="developer", software_class="vista",
         function_category="registration"):  # fmt: skip
    conn.execute(
        f"INSERT INTO documents ({_DOC_COLS}) VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_key, doc_id, "ADT", doc_type, "CLIN", "DG", "5.3", "DG*5.3*1", anchor_key,
         "ADT:DG:5.3", "T", "User Manual", app_user, doc_user, software_class, function_category,
         100, 4, is_latest, "", "abc", "https://va.gov/d/x.docx"),
    )  # fmt: skip


def _fts(conn, doc_key):
    conn.execute(
        "INSERT INTO chunks_fts (chunk_id, section_id, doc_key, title, doc_title, section_path, "
        "body) VALUES (?,?,?,?,?,?,?)",
        (f"{doc_key}/s", f"{doc_key}/s", doc_key, "Intro", "T", "T", "patient registration text"),
    )


def _healthy(conn):
    _doc(conn, doc_key="ADT/um1", doc_id="ADT:um1", anchor_key="ADT:DG:UM:um1")
    _doc(conn, doc_key="ADT/tm1", doc_id="ADT:tm1", doc_type="TM", anchor_key="ADT:DG:TM:tm1")
    for dk in ("ADT/um1", "ADT/tm1"):
        _fts(conn, dk)
    conn.execute("INSERT INTO entities VALUES ('routine:XL', 'routine', 'XL', 3)")
    conn.execute("INSERT INTO entity_mentions VALUES ('routine:XL', 'ADT/um1', 'ADT/um1/s')")
    conn.commit()


def _open(tmp_path):
    conn = db.connect(tmp_path / "index.db")
    conn.executescript(_SCHEMA)
    return conn


def test_diagnose_green_on_a_sound_corpus(tmp_path):
    conn = _open(tmp_path)
    _healthy(conn)
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY)
    conn.close()
    assert report.gold_count == 2
    assert report.verdict() == "GREEN" and not report.failures()


def test_diagnose_red_on_untyped_gold_doc(tmp_path):
    # an empty doc_type on a gold doc → doc_type coverage < 100% → FAIL → RED (F5 triage surface)
    conn = _open(tmp_path)
    _healthy(conn)
    _doc(conn, doc_key="ADT/x", doc_id="ADT:x", doc_type="", anchor_key="ADT:DG::x")
    _fts(conn, "ADT/x")
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY)
    conn.close()
    assert report.verdict() == "RED"
    fail = next(c for c in report.failures() if c.name == "coverage:doc_type")
    assert "ADT:x" in fail.detail  # the offending doc is named for triage


def test_diagnose_red_on_over_marked_anchor(tmp_path):
    # two is_latest docs sharing an anchor_key (version-collapse failure) → anchor integrity FAIL
    conn = _open(tmp_path)
    _healthy(conn)
    _doc(
        conn, doc_key="ADT/dup", doc_id="ADT:dup", anchor_key="ADT:DG:UM:um1"
    )  # dup of um1's anchor
    _fts(conn, "ADT/dup")
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY)
    conn.close()
    assert report.verdict() == "RED"
    assert any(c.name == "anchor integrity" and c.health is Health.FAIL for c in report.checks)


def test_diagnose_flags_empty_fts_and_missing_entities(tmp_path):
    # a gold doc with no FTS rows and no entities → search surface FAIL + entity graph WARN.
    conn = _open(tmp_path)
    _doc(conn, doc_key="ADT/u", doc_id="ADT:u", anchor_key="ADT:DG:UM:u")
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY)
    conn.close()
    search = next(c for c in report.checks if c.name == "search surface")
    entity = next(c for c in report.checks if c.name == "entity graph")
    assert search.health is Health.FAIL and "empty" in search.detail
    assert entity.health is Health.WARN  # missing entities is a WARN, not RED
    assert report.verdict() == "RED"  # the empty FTS is the failure


def test_diagnose_function_category_gap_is_by_design_not_red(tmp_path):
    conn = _open(tmp_path)
    _doc(conn, doc_key="ADT/a", doc_id="ADT:a", anchor_key="ADT:DG:UM:a")
    # a second gold doc with no function_category → 50% < 100 but >= the 90? no, 50 < 90 → FAIL.
    # use 10 docs so one gap = 90% == the floor → BY-DESIGN, not RED.
    for i in range(9):
        _doc(conn, doc_key=f"ADT/b{i}", doc_id=f"ADT:b{i}", anchor_key=f"ADT:DG:UM:b{i}")
    _doc(
        conn, doc_key="ADT/gap", doc_id="ADT:gap", anchor_key="ADT:DG:UM:gap", function_category=""
    )
    for dk in ("ADT/a", "ADT/gap", *[f"ADT/b{i}" for i in range(9)]):
        _fts(conn, dk)
    conn.execute("INSERT INTO entities VALUES ('routine:XL','routine','XL',1)")
    conn.execute("INSERT INTO entity_mentions VALUES ('routine:XL','ADT/a','ADT/a/s')")
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY)
    conn.close()
    fc = next(c for c in report.checks if c.name == "coverage:function_category")
    assert fc.health is Health.BY_DESIGN  # 90% meets the floor → expected gap, not a defect
    assert report.verdict() == "GREEN"


# --- P1: read-contract validation (emitted DB == spec) ------------------------------------------


def _with_contract(tmp_path):
    """A DB carrying the generated v_* views + a stamped meta version — the consumer surface."""
    from vdocs.kernel import read_contract as rc

    spec = rc.load(rc.contract_path())
    conn = _open(tmp_path)
    conn.executescript(rc.view_ddl(spec))
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('read_schema_version', ?)", (rc.version(spec),)
    )
    _doc(conn, doc_key="ADT/a", doc_id="ADT:a", anchor_key="ADT:DG:UM:a")
    _fts(conn, "ADT/a")
    conn.commit()
    return conn, spec


def test_diagnose_contract_check_passes_when_db_matches_spec(tmp_path):
    conn, spec = _with_contract(tmp_path)
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY, read_spec=spec)
    conn.close()
    rc_check = next(c for c in report.checks if c.name == "read contract")
    assert rc_check.health is Health.PASS and "views match" in rc_check.detail


def test_diagnose_contract_check_fails_red_when_a_view_is_missing(tmp_path):
    conn, spec = _with_contract(tmp_path)
    conn.execute("DROP VIEW v_entities")  # the published interface no longer matches the spec
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY, read_spec=spec)
    conn.close()
    rc_check = next(c for c in report.checks if c.name == "read contract")
    assert rc_check.health is Health.FAIL and "v_entities missing" in rc_check.detail
    assert report.verdict() == "RED"


# --- P2: enum-coverage gate (undefined facet value fails the producer) --------------------------


def _define(conn, *rows):
    conn.executemany("INSERT INTO vocab (kind, code, label, description) VALUES (?,?,?,'')", rows)


def test_enum_gate_fails_red_on_an_undefined_function_category(tmp_path):
    # the seeded doc uses function_category='registration'; vocab defines only 'Laboratory' → the
    # value is undefined → FAIL ⇒ RED (exactly the "grew the library with a new domain" case).
    conn, spec = _with_contract(tmp_path)
    _define(conn, ("function_category", "Laboratory", "Laboratory"))
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY, read_spec=spec)
    conn.close()
    fc = next(c for c in report.checks if c.name == "vocab:function_category")
    assert fc.health is Health.FAIL and "registration" in fc.detail
    assert report.verdict() == "RED"


def test_enum_gate_passes_when_every_value_is_defined(tmp_path):
    conn, spec = _with_contract(tmp_path)
    _define(
        conn,
        ("function_category", "registration", "Registration"),
        ("doc_type", "UM", "User Manual"),
        ("section", "CLIN", "Clinical"),
        ("persona", "clinical", "Clinical"),
        ("persona", "developer", "Developer"),
    )
    conn.commit()
    report = doc.diagnose(conn, kept_doctypes=_KEPT, policy=_POLICY, read_spec=spec)
    conn.close()
    for field in ("function_category", "doc_type", "section", "app_user", "doc_user"):
        assert next(c for c in report.checks if c.name == f"vocab:{field}").health is Health.PASS
