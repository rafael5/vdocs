"""Six plain-English keyword searches for the golden key (keyword-search proposal, fix 4, App. C).

REVIEWER DRAFTS for the operator to approve; nothing here is in registries/golden-queries.yaml yet.
Each search uses a word the manuals avoid ("password" where they say verify code). Every judged
section was checked present, latest and searchable in index.db, and graded by reading its passage
text (3 ideal · 2 highly relevant · 1 related), as the golden key requires.

Measured today, before fixes 2 and 3:
- the web console as built by fix 1 (all words, relevance order, any-word fallback), document level:
  rank of the first document holding a judged section;
- the MCP as it is today, section level: rank of the first judged section.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from vdocs.server import search as S

sys.path.insert(0, str(Path(__file__).parent))
from _common import DB, provenance  # noqa: E402

DRAFTS = {
    "plain-change-password": {
        "keywords": "change password",
        "intent": "How a user changes their VistA password; the manuals call it the verify code.",
        "relevant": {
            "XU/krn_8_0_sm_signon_security_ug/defining-a-strong-verify-code": 3,
            "XWB/xwb_1_1_sm_r/change-vista-verify-code-component": 2,
            "PRC/ifcp5_1ldqt_user_manual/changing-your-verify-code": 2,
            "XU/krn_8_0_sm_signon_security_ug/lifetime-of-verify-code": 1,
            "EDIS/edp_um/changing-your-verify-code": 1,
        },
        "notes": "The 'Changing User ID and Password' sections (VSE GUI, lab, SEOC manuals) say "
        "only 'Not applicable' or 'contact your supervisor': not relevant, and exactly what a "
        "plain 'password' search finds first.",
    },
    "plain-create-user-account": {
        "keywords": "create user account",
        "intent": "How a system administrator adds a new VistA user (Kernel, NEW PERSON file).",
        "relevant": {
            "XU/krn_8_0_sm_signon_security_ug/adding-new-users": 3,
            "XU/krn_8_0_sm_signon_security_ug/add-a-new-user-to-the-system-option": 3,
            "XU/krn_8_0_sm_signon_security_ug/edit-an-existing-user-option": 1,
        },
        "notes": "The manuals say 'new user' and the NEW PERSON (#200) file; 'user account' "
        "appears in two of the judged passages.",
    },
    "plain-background-jobs": {
        "keywords": "background jobs",
        "intent": "What runs work in the background in VistA: TaskMan, which the manuals call "
        "background tasks.",
        "relevant": {
            "XU/krn_8_0_sm_taskman_ug/introduction": 3,
            "XU/krn_8_0_sm_taskman_ug/taskman-user-interface": 3,
            "XU/krn_8_0_sm_taskman_ug/summary": 2,
            "XU/krn_8_0_dg_taskman_ug/overview": 2,
        },
        "notes": "The manuals say 'tasks' and 'background processing', rarely 'jobs'.",
    },
    "plain-set-up-printer": {
        "keywords": "set up printer",
        "intent": "How a printer is defined for VistA: an entry in Kernel's DEVICE (#3.5) file "
        "with a terminal type.",
        "relevant": {
            "XU/krn_8_0_sm_device_handler_ug/device-35-file": 3,
            "XU/krn_8_0_sm_device_handler_ug/terminal-type-32-file": 2,
            "XU/krn_8_0_sm_device_handler_ug/printing-to-devices": 1,
        },
        "notes": "Kernel's general device setup. Application-specific printer sections (VBECS "
        "printers, ScripTalk printers) answer a narrower question and are not judged.",
    },
    "plain-enter-patient-allergies": {
        "keywords": "enter patient allergies",
        "intent": "How a clinician records a patient's allergy: Adverse Reaction Tracking (GMRA), "
        "or CPRS's Allergies pane.",
        "relevant": {
            "GMRA/gmra_4_0_um/enteredit-patient-reaction-data": 3,
            "GMRA/gmra_4_0_um/enteredit-patient-reaction-data-1": 3,
            "CPRS/cprsguium/entering-allergies": 3,
            "CPRS/cprsguium/entering-new-allergies": 2,
            "GMRA/gmra_4_0_um/entering-allergies-from-the-cover-sheet": 2,
        },
        "notes": "The roll-and-scroll option is 'Enter/Edit Patient Reaction Data'; twin titles "
        "graded by content (both describe the option in full).",
    },
    "plain-send-email": {
        "keywords": "send email",
        "intent": "How a user sends a message in VistA: MailMan's Send a Message option.",
        "relevant": {
            "XM/xm_8_0_userguide/smlsend-a-message-option": 3,
            "XM/xm_8_0_getstartguide/sending-mail": 3,
            "XM/xm_8_0_userguide/sending-mail": 2,
            "XM/xm_8_0_netrefguide/sending-network-messages": 1,
        },
        "notes": "The manuals say 'mail' and 'message', rarely 'email'.",
    },
}

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
LATEST = {r[0] for r in con.execute("SELECT doc_key FROM documents WHERE is_latest = 1")}
TITLE = dict(con.execute("SELECT doc_key, title FROM documents"))


def quoted(q: str, op: str) -> str:
    return f" {op} ".join('"' + f.replace('"', '""') + '"' for f in q.split()).replace("  ", " ")


def web_docs(q: str) -> tuple[list[str], bool]:
    """vdocs-web after fix 1: all words ranked by three passages (1, ½, ¼), else any word, best."""

    def run(m: str, n: int) -> list[str]:
        per: dict[str, list[float]] = defaultdict(list)
        sql = "SELECT doc_key, bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ?"
        for dk, sc in con.execute(sql, (m,)):
            if dk in LATEST:
                per[dk].append(sc)
        order = sorted(per, key=lambda d: TITLE.get(d) or "")
        return sorted(order, key=lambda d: sum(x / 2**i for i, x in enumerate(sorted(per[d])[:n])))

    hits = run(quoted(q, ""), 3)
    return (hits, False) if hits else (run(quoted(q, "OR"), 1), True)


def main() -> None:
    out: dict = {"provenance": provenance(), "status": "reviewer drafts, not yet approved"}
    present = {r[0] for r in con.execute("SELECT DISTINCT section_id FROM chunks_fts")}
    sec_doc = dict(con.execute("SELECT section_id, doc_key FROM doc_sections"))
    for qid, d in DRAFTS.items():
        rel = set(d["relevant"])
        missing = sorted(s for s in rel if s not in present or sec_doc.get(s) not in LATEST)
        reld = {sec_doc[s] for s in rel if s in sec_doc}
        docs, fell = web_docs(d["keywords"])
        mcp = [h["section_id"] for h in S.lexical_search(DB, d["keywords"], k=15)]
        out[qid] = {
            "keywords": d["keywords"],
            "judged_sections": len(rel),
            "not_present_latest_searchable": missing,
            "web_first_relevant_document_rank": next(
                (i + 1 for i, x in enumerate(docs) if x in reld), None
            ),
            "web_documents_matched": len(docs),
            "web_fallback": fell,
            "mcp_first_relevant_section_rank_top15": next(
                (i + 1 for i, x in enumerate(mcp) if x in rel), None
            ),
        }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
