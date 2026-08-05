#!/usr/bin/env python3
"""Side-by-side review: the source PDF next to what the pipeline would produce today.

**The point is speed.** A full rebuild is ~26 minutes, which is far too slow to iterate a
`normalize` change against. But every body transform is a *pure function* of the converted
markdown — so for anything downstream of `convert` there is no need to touch the lake at all. This
runs the current transform sequence over already-converted bodies in **seconds**, writes a review
tree, and leaves the production lake untouched.

    python scripts/review.py                 # 10 varying documents (seeded, reproducible)
    python scripts/review.py --n 6 --seed 3   # a different batch
    python scripts/review.py --slug fm22_2dg --slug paid_um
    python scripts/review.py --clean

Each document lands as::

    ~/data/vdocs/_review/<slug>/source.pdf   # the VA original (downloaded once, cached)
    ~/data/vdocs/_review/<slug>/gold.md      # what the pipeline would produce today
    ~/data/vdocs/_review/assets -> ../assets # ONE symlink, so images render (scripts/preview.py)

Then in VS Code open `gold.md`, `Ctrl+Shift+V` for the preview, and drag `source.pdf` into a split
— PDF left, rendered markdown right. Edit a transform, re-run this, refresh.

⚠️ This mirrors the body-transform order in `stages/normalize/stage.py`. If that order changes and
this does not, the review lies — keep them together.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import shutil
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import yaml

from vdocs.config import Settings
from vdocs.kernel.profile import document_profile
from vdocs.stages.normalize import normalize_pure as nz
from vdocs.stages.normalize import revision_pure as rev
from vdocs.stages.normalize import tables_pure as tbl
from vdocs.stages.normalize import template_pure as tmpl


def _registries(cfg: Settings) -> tuple[frozenset[str], frozenset[str]]:
    conv = yaml.safe_load((cfg.registries / "structures/structures.yaml").read_text())[
        "conventions"
    ]
    toc = frozenset(
        t.lower() for c in conv if c.get("convention") == "toc" for t in (c.get("match") or [])
    )
    phrases = frozenset(
        yaml.safe_load((cfg.registries / "phrases/phrases.yaml").read_text())["phrases"] or []
    )
    return toc, phrases


def run_pipeline(body: str, toc_titles: frozenset[str], phrases: frozenset[str]) -> str:
    """The body transforms, in `stage.py`'s order — the one thing that must not drift."""
    body = tmpl.strip_title_image(body)
    body, _revisions, _flag = rev.extract_revision_history(body)
    body, _tables = tbl.extract_tables(body)
    body = tbl.text_boxes_to_code_fences(body)
    body = tbl.html_tables_to_gfm(body)
    body, _amap = nz.normalize_body(body, phrases, toc_titles=toc_titles)
    return body


# A bare content-addressed asset ref: `<sha256>.<ext>`, which resolves next to `body.md` where the
# image is not. Only these get repointed — rewriting every `](` would break the anchor links and the
# CSV sidecar links too (it did, on the first run: 269 broken anchors in one document).
_ASSET_REF_RE = re.compile(r"\]\((?=[0-9a-f]{16})([0-9a-f]+\.[A-Za-z0-9]{2,5})\)")


def _point_images_at_assets(body: str) -> str:
    """Repoint bare asset refs at the review tree's single `assets` symlink (scripts/preview.py)."""
    return _ASSET_REF_RE.sub(r"](../assets/\1)", body)


def pdf_url_by_slug(cfg: Settings) -> dict[str, str]:
    """Slug → the VA source PDF, for every document published in both formats."""
    records = json.loads(cfg.catalog_enriched.read_text(encoding="utf-8"))["records"]
    by_anchor: dict[str, dict[str, dict]] = {}
    for r in records:
        if r.get("noise_type") or not r.get("anchor_key"):
            continue
        by_anchor.setdefault(r["anchor_key"], {})[r.get("doc_format", "")] = r
    out: dict[str, str] = {}
    for formats in by_anchor.values():
        if "docx" in formats and "pdf" in formats:
            out[formats["docx"]["doc_slug"]] = formats["pdf"]["doc_url"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10, help="how many documents (default 10)")
    ap.add_argument("--seed", type=int, default=0, help="vary the batch")
    ap.add_argument("--slug", action="append", default=[], help="pick specific documents")
    ap.add_argument("--clean", action="store_true", help="remove the review tree")
    args = ap.parse_args()

    cfg = Settings()
    out_root = cfg.lake / "_review"
    if args.clean:
        shutil.rmtree(out_root, ignore_errors=True)
        print(f"removed {out_root}")
        return 0

    enriched = cfg.lake / "documents" / "silver" / "text" / "02-enriched"
    bodies = {p.parent.name: p for p in enriched.rglob("body.md")}
    pdfs = pdf_url_by_slug(cfg)
    candidates = sorted(set(bodies) & set(pdfs))
    if not candidates:
        print("no document has both a converted body and a source PDF", file=sys.stderr)
        return 1
    picked = args.slug or random.Random(args.seed).sample(candidates, min(args.n, len(candidates)))

    toc_titles, phrases = _registries(cfg)
    out_root.mkdir(parents=True, exist_ok=True)
    assets_link = out_root / "assets"
    if not assets_link.exists():
        assets_link.symlink_to(pathlib.Path("..") / "documents" / "assets")

    index = [
        "# Review batch",
        "",
        "| document | pages of source | words | headings | code refs |",
        "|---|---|---:|---:|---:|",
    ]
    for slug in picked:
        if slug not in bodies:
            print(f"  !! {slug}: no converted body — skipped", file=sys.stderr)
            continue
        d = out_root / slug
        d.mkdir(exist_ok=True)
        gold = run_pipeline(
            bodies[slug].read_text(encoding="utf-8", errors="replace"), toc_titles, phrases
        )
        (d / "gold.md").write_text(_point_images_at_assets(gold), encoding="utf-8")
        pdf = d / "source.pdf"
        if not pdf.exists():
            try:
                urllib.request.urlretrieve(pdfs[slug], pdf)  # noqa: S310 - VA VDL, the pipeline's own source
            except OSError as exc:
                print(f"  !! {slug}: PDF download failed ({exc})", file=sys.stderr)
        p = document_profile(gold)
        index.append(
            f"| [{slug}]({slug}/gold.md) | [pdf]({slug}/source.pdf) | {p.words:,} | "
            f"{p.headings:,} | {p.code_refs:,} |"
        )
        print(f"  {slug:<32} {p.words:>8,} words  {p.headings:>5} headings")

    (out_root / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"\n{len(picked)} documents → {out_root}")
    print(f"open:  code {out_root}/INDEX.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
