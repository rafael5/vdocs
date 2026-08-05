# VO.5 — what `archive` means in the VDL, measured

**Measured 2026-08-04**, out of the effort's step order, against the production inventory snapshot
(`inventory/silver/catalog.enriched.json`, 8,907 records, crawl of 2026-08-03) and the built corpus
(`index.db`, 1,040 documents / 615 version groups). Prompted by an operator hypothesis:

> *The documents marked "archive" are just older duplicate copies. They don't use version control,
> so that is what I assume the reason is.*

**Verdict: substantially confirmed for the documentation, with two corrections that change what
follows from it.** VA's *stated* intent remains unestablished — this establishes what the archive
population **is**, not what VA means by the word. The effort's standing rule holds: do not infer
intent from a label.

## The 3,404 archive records are two unrelated populations

| | records | share of archive |
|---|---:|---:|
| **not VistA documentation** — VBA benefits forms, VA reference links | **1,234** | **36.3%** |
| genuine VistA documentation | 2,170 | 63.7% |

The first population has nothing to do with versioning. It is 1,096 VBA benefits PDFs — *Application
for Education Benefits*, *Direct Deposit Sign-Up SF 1199A*, *Statement in Support of Claim* — plus
137 VA reference links. The same handful of forms is listed on many application pages, and **92.6%
of every VBA form record in the library (1,096 of 1,184) carries `archive`**, against 1.5% of active
records. The pipeline already classifies these as noise and excludes them. More than a third of the
38.2% headline figure is this, and no explanation involving VistA versioning applies to it.

## For the genuine documentation, the hypothesis holds

| genuine archive documents | 2,170 | |
|---|---:|---:|
| an older or duplicate copy of a document that also exists live | **1,511** | **69.6%** |
| no live counterpart at all | 659 | 30.4% |

And the direction is right. Of the 1,347 duplicate pairs where a version is comparable:

| the archive copy is… | | |
|---|---:|---:|
| **older** than the live one | **973** | **72.2%** |
| the same version (a straight duplicate listing) | 346 | 25.7% |
| newer | 28 | 2.1% |

133 of the same-version pairs carry an **identical filename** — the same file listed twice, once
under each label. So: 97.9% of the pairs are older-or-equal, which is the mechanism described.

**The 659 without a live counterpart are the same phenomenon in a different shape.** They are
release-pinned or patch-pinned documents — *VSE GUI 1.6 Release Notes*, *ROR\*1.5\*34 Installation
Guide*, *MAG\*3\*197 User Guide*, *SR\*3\*174 User Manual Change Pages*. They have no current
version because the concept does not apply: rather than revising one document, VA publishes a new
one per release and moves the previous one to archive. Not "duplicate copies" literally, but the
same absence of version control producing the same accumulation.

## The correction that matters: archive is *not* redundant in our corpus

The obvious consequence — *if archive is older duplicates, we can ignore it* — is **false here**, and
by a wide margin.

| archive documents in the built corpus | |
|---|---:|
| archive-labelled document rows | 255 |
| folded as prior versions inside a group whose current version is **active** | **106** |
| folded as prior versions inside an archive-only group | 94 |
| **surviving as the current version of their group** | **55** |
| …of those 55, how many have an active twin in the corpus | **0** |

`consolidate` already does the deduplication the hypothesis implies: the archive copies that *were*
older duplicates are folded into their live document's version lineage. What survives carrying the
`archive` label is the **residue** — 55 documents that are the only copy we hold, with no active
replacement anywhere in the library. Among them: the DSS *User's Guide* and *Technical Manual*,
IFCAP *Technical Manual* and *Logistics Data Query Tool User Manual*, VIST *User Manual*, Consults
*User Guide*, the CPRS *List Manager Clinician's Getting Started Guide*, FB *User Manual (1995)*.

Excluding `archive` from the collection would therefore not remove duplicates. It would remove the
sole surviving documentation for those packages — which is exactly the case the master-set rule was
written for: *VA deprecating a package does not remove its code from VistA.*

## What this settles, and what it does not

**Settled:** the composition of the archive population, and the mechanism behind it. The 38.2%
figure should never be quoted unqualified again — 36% of it is benefits forms, and the documentation
remainder is superseded copies plus release-pinned documents.

**Not settled:** whether VA uses the label deliberately and consistently, or whether it is editorial
habit. One snapshot cannot distinguish a policy from a convention.

## VO.5 is CLOSED — the intent question is declared unestablished (2026-08-05)

The paragraph above originally deferred intent to "what VO.2–VO.4 exist to build". **That deferral
was wrong, and closing it is the honest result rather than a gap left open.**

The timeline VO.2 starts records the VDL from 2026-08-05 forward. The labels whose meaning is in
question were applied over **2005–2022** — the 115 populated `decommission_date` values span exactly
that range, all of them before our first snapshot. A record that begins after every event it would
need to explain cannot explain them. Waiting for VO.3/VO.4 to answer this would be waiting for
evidence that, by construction, will never arrive.

What *would* settle it is outside this pipeline's reach: a statement from VA about its own editorial
policy. Nothing in the crawl, the corpus, or the measured VistA model substitutes for that.

**Therefore:** the composition of the archive population is established and recorded above; **VA's
intent behind the label is unestablished and no further work is scheduled to establish it.** Per the
effort's standing rule, that is recorded as a known unknown — not as a finding, and not as an open
task pretending to be actionable. Future timeline deltas may still show a *new* label being applied,
which is evidence about VA's behaviour going forward; it is not evidence about the 2005–2022 back
catalogue, and must not be presented as such.

**Method note.** Two measurement traps were hit and corrected while doing this, both worth carrying:

- A fuzzy title match that strips version numbers scores *DG\*5.3\*850 Release Notes* and
  *DG\*5.3\*1064 Release Notes* as identical. Patch identifiers are **document identity**, not
  version markers — strip them and every patch document collapses into one. Corrected by comparing
  `patch_id_full` before matching titles; the duplicate estimate fell from 82.6% to 69.6%.
- Joining catalog records by `<app>:<slug>` returned 2,164 matches for 1,044 admitted documents —
  one document is several catalog rows. Per-document questions must be asked of `index.db`'s
  `documents` table, never of the inventory record list.

## Reproducing

Inventory: `$DATA_DIR/inventory/silver/catalog.enriched.json`, fields `app_status`, `noise_type`,
`anchor_key`, `patch_id_full`, `patch_ver`, `doc_code`. Corpus: `$DATA_DIR/index.db`, table
`documents` (`app_status`, `anchor_key`, `is_latest`). Duplicate test = an archive record whose
`anchor_key` matches a live record's, plus a same-patch title match at ≥0.85 for the anchor_key
misses.
