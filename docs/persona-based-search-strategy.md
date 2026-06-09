# Persona-Based Search & Filter Strategy

> **Status:** strategy proposal, 2026-06-09. Companion to
> [`doc-classification-filtering-summary.md`](doc-classification-filtering-summary.md). That doc
> says how documents are *classified*; this one says how a *person* should *find* them in the gold
> library. Grounded in the current gold composition (~1,091 kept docs) and `index.db` surface.

## Table of contents

1. [Who actually searches vdocs? (searcher ≠ content classification)](#1-who-actually-searches-vdocs)
2. [Is persona the first layer of filtering?](#2-is-persona-the-first-layer-of-filtering)
3. [The layered search model](#3-the-layered-search-model)
4. [Per-persona search profiles (master table)](#4-per-persona-search-profiles-master-table)
5. [Per-persona detail](#5-per-persona-detail)
6. [The coverage caveat — who the gold library serves vs starves](#6-the-coverage-caveat)
7. [Result presentation per persona](#7-result-presentation-per-persona)
8. [Implementation mapping & gaps](#8-implementation-mapping--gaps)

---

## 1. Who actually searches vdocs?

The first thing to untangle: **the searcher's persona is not the same thing as the document's
classification.** The classification doc defines two *content* axes — `app_user` (who operates the
app a doc is about) and `doc_user` (who reads a doc). The **searcher** is a real person sitting at
`vdocs ask`, and their role is what should drive the query.

The good news: the searcher's role draws from the **same 5-persona vocabulary**
(`clinical · clinical-admin · business-admin · developer · sysadmin`), and **`doc_user` is the
bridge** — a searcher with role *X* wants documents whose `doc_user` resolves to *X*. So the persona
model we already built is exactly the right pre-filter; we just point it at the *searcher* instead of
tagging the doc.

Who they are, concretely (and what they bring to the query):

| Searcher | Why they're here | They arrive knowing… |
|---|---|---|
| **developer** | build/maintain VistA M code, integrate | a **symbol** (routine `^XUS`, RPC, file #2, option, HL7 seg) or an API/interface |
| **clinical** | understand a clinical workflow / how to use an app | a **task** ("how do I cancel an order") or an app |
| **clinical-admin** | scheduling/registration/HIM procedures | a **task** or an app (Scheduling, ADT, ROI) |
| **business-admin** | billing/eligibility/fiscal workflows | a **task** or an app (IB, AR, IFCAP) |
| **sysadmin** | configure/secure/operate a package | a **package** + a config/security topic |

> vdocs' stated primary consumer is the **developer/analyst** (offline, zero-ML, code-adjacent). That
> persona is also the **best-served** by the gold corpus and the only one with rich symbol anchors —
> see §6.

---

## 2. Is persona the first layer of filtering?

**Mostly yes — persona is the highest-leverage *single* narrowing, and the right *default* first
lens — but it should be optional and composable, not a hard gate.**

Why it's the best default first move: the gold corpus is **heterogeneous** — a developer's Technical
Manual and a nurse's User Manual share almost no useful vocabulary. Faceted ("focused") retrieval
works by collapsing a heterogeneous corpus to a **homogeneous slice** *before* ranking, so BM25
competes apples-to-apples. Persona (→ `doc_user`) is the single facet that best achieves that
collapse: it cuts ~1,091 docs to the few-hundred a role actually reads.

Why it's not *strictly* first or mandatory:
- A developer who already has a **symbol** (`^XUS8`, RPC `ORWU NEWPERS`, file `#200`) should enter at
  the **entity layer** — that's a sharper narrowing than persona, and persona is implied by it.
- A searcher who knows the **app/package** ("everything in Scheduling") starts there.
- Persona should be a **soft pre-filter that expands gracefully** — if a persona slice returns too
  little, widen to "all" rather than hide a relevant doc whose `doc_user` differs. (A developer
  sometimes needs the *User* Manual to understand the workflow a routine implements.)

**Conclusion:** treat persona as **Layer 0** — an optional pre-filter offered *first by default*,
that any sharper signal (entity, known app) can supersede, and that always degrades to the full
corpus on demand.

---

## 3. The layered search model

```
Layer 0  PERSONA       → doc_user (and/or app_user) facet     soft pre-filter; default-first, optional
Layer 1  SCOPE         → app_code · pkg_ns · section · function_category · doc_type
Layer 2  ENTITY        → routine · rpc · fileman_file · option · global · hl7_segment · mail_group · build
Layer 3  CONTENT       → FTS5/BM25 over title + body (is_latest only)
```

- Each layer **narrows** the candidate set; Layer 3 **ranks** within it. This is exactly the existing
  `facets.faceted_search` pipeline (narrow → content-search), extended with the persona facets.
- **Entry point is flexible:** developers often enter at Layer 2 (symbol), operators at Layer 0→3
  (role → task). The layers compose in any order; only Layer 3 must be last.
- **`is_latest = 1` is always on** (gold = the version anchor; B1 fix makes that one-per-logical-doc).

---

## 4. Per-persona search profiles (master table)

For each searcher persona: the facets that pre-filter (Layers 0–1), the entity anchors (Layer 2), the
text fields to rank (Layer 3), and how well the gold corpus serves them.

| Persona | Pre-filter facets | Entity anchors | Rank over | Gold coverage |
|---|---|---|---|---|
| **developer** | `doc_user=developer` (TM/DG/API/INT/REF/TG) · `pkg_ns`/`app_code` | **routine · rpc · fileman_file · option · global · hl7_segment · mail_group · build** | body, title, **symbol names** | 🟢 **350 docs + all entities** — best served |
| **clinical** | `doc_user=clinical` · `function_category`∈{Clinical/Patient Care Services} · `app_user=clinical` | option · menu (via option) | body (procedures), `doc_title` | 🟢 large share of the **694 operator** docs |
| **clinical-admin** | `doc_user=clinical-admin` · `function_category`∈{Eligibility/Front Office/Telehealth&Scheduling} | option · menu | body (workflow), `doc_title` | 🟡 share of operator docs (Scheduling/ADT/ROI/HIM) |
| **business-admin** | `doc_user=business-admin` · `function_category`∈{VHA Finance/Financial Mgmt} · `app`∈{IB,AR,PRC} | option | body (billing/eligibility), `doc_title` | 🟡 smaller operator share (IB/AR/IFCAP) |
| **sysadmin** | `doc_user=sysadmin` (SG/AG/SM only) · `pkg_ns` | option · parameter (option) | body (config/security), `doc_title` | 🔴 **only ~47 docs** — install/ops omitted (§6) |

Cross-cutting fields every persona benefits from: `doc_title` + `body` (FTS), `app_code`/`pkg_ns`
(provenance), `doc_type` (kind), and — once materialized — `software_class`/`vasi_status` to favor
**national, Production** apps over Technical-Reference/Inactive ones.

---

## 5. Per-persona detail

### developer — symbol-first, the best-served persona
The developer is the only persona with a rich **anchor vocabulary**: the index carries 9 entity
types (routine, rpc, fileman_file, option, global, hl7_segment, mail_group, build,
package_namespace). The ideal flow is **entity → content**: pick the symbol, then BM25 within the few
docs that mention it. Persona pre-filter (`doc_user=developer` → TM/DG/API/INT) sharpens "concept"
queries ("how does the broker authenticate") but should expand to operator docs when the answer lives
in a User Manual. Surface: matched **symbol**, `doc_type`, `pkg_ns`, section path.

### clinical / clinical-admin / business-admin — task-first operators
These three are the **`operator` bucket** (694 UM/UG/QRG/TRG/FAQ docs), split by the doc's
`app_user`. They arrive with a *task*, not a symbol, so the flow is **persona/app → content**: narrow
to the role's apps via `doc_user`+`function_category`, then rank the task query over body+title. The
distinction among the three is *which apps* (clinical = CPRS/Pharmacy/Lab; clinical-admin =
Scheduling/ADT/ROI/HIM; business-admin = IB/AR/IFCAP) — `function_category` and `app_user` do that
cut. Surface: app **purpose** (one-liner), `doc_title`, snippet, menu/option matched.

### sysadmin — under-served by design
Wants install/config/security/ops. But **G4 omits Tiers B/C** (DIBR/IG/IG-IMP/POM/CFG), so gold keeps
only **SG/AG/SM (~47 docs)**. A sysadmin search should (a) be honest that install/back-out guides
were intentionally excluded, and (b) offer a one-click *"include install/ops docs"* that flips the
`doctype-policy` toggle conceptually (or points at the inventory/source). See §6.

---

## 6. The coverage caveat

The gold doc-type policy (G4: keep Tier-A reference core, omit B/C/D) **shapes who the library can
serve**. By `doc_user` bucket, the kept corpus is:

| doc_user bucket | docs | served? |
|---|---|---|
| **operator** (clinical / clinical-admin / business-admin) | **694** | 🟢 well (UM/UG/QRG/TRG/FAQ) |
| **developer** | **350** | 🟢 well (TM/DG/API/INT/REF) + 9 entity types |
| **sysadmin** | **47** | 🔴 thin — install/deploy/ops (DIBR/IG/POM/CFG) omitted |

**Implications for the strategy:**
- Lead with **developer** and **operator** experiences — that's where the content (and the symbols)
  live.
- For **sysadmin**, set expectations: surface the AG/SM/SG that *are* there, and treat the gap as a
  policy choice the user can reverse (`doctype-policy.yaml`), not a corpus failure.
- A persona pre-filter that returns near-zero (sysadmin, business-admin on a thin app) must **degrade
  to the broader corpus with a note**, never a bare empty result.

---

## 7. Result presentation per persona

What to *show* in a hit differs by persona — present the fields that persona uses to judge relevance:

| Persona | Show in each result |
|---|---|
| developer | matched **symbol** + type · `doc_type` · `pkg_ns`/`app_code` · section path · snippet |
| clinical / clinical-admin / business-admin | app **purpose** (one-liner) · `doc_title` · matched menu/option · snippet |
| sysadmin | `doc_type` (AG/SM/SG) · `pkg_ns` · snippet · *"install/ops docs excluded — toggle to include"* |
| any (browse) | `app_user`/`doc_user` chips · `software_class`·`vasi_status` (favor national/Production) · `doc_type` |

---

## 8. Implementation mapping & gaps

**Already in place** (maps directly to this strategy):
- `facets.faceted_search` — the narrow→content pipeline (Layers 1–3) + the **entity facet** (Layer 2).
- The **persona facets** `app_user` / `doc_user` (Layer 0) — `facets_pure.app_user_clause` /
  `doc_user_clause`, with `operator`→`app_user` delegation. Loaded from `app-profiles.yaml` +
  `doc-user.yaml`.
- `index.db` columns for Layer 1: `doc_type`, `app_code`, `pkg_ns`, `section`, `is_latest`; FTS over
  title+body for Layer 3.

**Gaps to close (in priority order):**
1. **Persona facets aren't computed in the index yet** — `doc_user`/`app_user` resolve at *query*
   time via the registry join (no `index.db` column). Fine for correctness; for facet-count speed and
   offline portability, consider stamping resolved `doc_user`/`app_user` as `documents` columns at
   `index` time (open item #1 in the classification doc).
2. **`function_category` / `software_class` / `vasi_status` not in `index.db`** — needed for the
   Layer-1 domain cut and the national/Production ranking boost. Join app-profiles at `index`.
3. **No CLI/API surface for the persona facets yet** — `vdocs ask` / faceted search need
   `--app-user` / `--doc-user` flags wired to the resolver.
4. **sysadmin honesty** — a "results thin because policy omitted install/ops docs" message + an
   include-toggle path.
5. **Soft-expand behavior** — when a persona slice underflows, auto-widen to the full corpus with a
   note rather than returning empty.

**Net:** the classification work already produced the right facets; the search strategy is mostly
*wiring and presentation* — expose the two persona axes as Layer-0 filters, lead with the
developer/operator experiences the corpus actually serves, and be explicit about the sysadmin gap the
doc-type policy creates.
