"""Shared probe data + corpus provenance for the MCP-interface review measurements.

Every report carries `provenance` (index_db, documents, chunks, corpus_content_hash) — the
reports/README.md rule: a measurement that cannot name the corpus it read is not evidence.
"""

import sqlite3
from pathlib import Path

DB = Path.home() / "data/vdocs/index.db"


def provenance() -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
    return {
        "index_db": str(DB),
        "documents": con.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "chunks": con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "corpus_content_hash": meta.get("corpus_content_hash"),
        "read_schema_version": meta.get("read_schema_version"),
    }


FILES = {
    "2": "PATIENT", "200": "NEW PERSON", "19": "OPTION", "50": "DRUG", "44": "HOSPITAL LOCATION",
    "4": "INSTITUTION", "100": "ORDER", "101": "PROTOCOL", "52": "PRESCRIPTION", "60":
    "LABORATORY TEST", "63": "LAB DATA", "8925": "TIU DOCUMENT", "8994": "REMOTE PROCEDURE",
    "50.7": "PHARMACY ORDERABLE ITEM", "3.5": "DEVICE", "9.4": "PACKAGE", "9.6": "BUILD",
    "9.7": "INSTALL", "3.8": "MAIL GROUP", "4.2": "DOMAIN", "120.8": "PATIENT ALLERGIES",
    "409.68": "OUTPATIENT ENCOUNTER", "8989.3": "KERNEL SYSTEM PARAMETERS", "811.9":
    "REMINDER DEFINITION", "870": "HL LOGICAL LINK", "9.8": "ROUTINE", "3.7": "MAILBOX",
    "71": "RAD/NUC MED PROCEDURES", "405": "PATIENT MOVEMENT", "1": "FILE",
}  # fmt: skip

PARA = {
    "kids-install-build": "steps to put a patch distribution onto a VistA system",
    "radiology-cancel-exam": "how to call off an imaging procedure that was ordered",
    "tiu-unsigned-notes": "list the clinical documents I still have to sign",
    "lab-file60-audit": "track who edited lab test definitions",
    "cprs-enter-immunization": "record a vaccine given to a patient in the clinical GUI",
    "hl7-security-keys": "which access keys does the messaging package require",
    "fileman-file-200-new-person": "where are VistA user accounts stored",
    "fileman-input-transform-definition": "code that validates a field value as it is entered",
    "fileman-finder-api": "programmatic lookup of entries matching a value in a file",
    "taskman-monitor": "check whether the background job scheduler is running",
    "hl7-start-tcpip-link": "bring up a network connection for message exchange",
    "vista-signon-credentials": "how users log in and what they must type",
}  # fmt: skip
