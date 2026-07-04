"""The D2.5 floor-verification gate — measured entity join rates vs declared floors.

Each ``floor-verified`` type in ``registries/entity-quality.yaml`` declares the
vista-meta ``data-v1`` vocabulary it joins (``"<relpath>.tsv:<column>"``) and a
numeric floor. This module measures the live rates against an unpacked vista-meta
bundle at gate time (F1: never stale numbers) and renders PASS/FAIL:

- floor-verified: rate >= floor required;
- no-authoritative-vocabulary / excluded: reported, never blocking
  (excluded residue is `doctor`'s job);
- a type shipping without a declaration is UNDECLARED → FAIL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vdocs.kernel.entity_quality import EntityQuality


@dataclass(frozen=True)
class TypeMeasurement:
    type: str
    status: str
    count: int
    joined: int
    rate: float
    floor: float
    ok: bool


def load_vocab(vista_meta_dir: Path, spec: str) -> set[str]:
    """Read the vocabulary column named by a registry ``vocabulary`` spec
    (``"code-model/routines.tsv:routine_name"``) from an unpacked vista-meta
    data-v1 tree. Values are normalized to upper-case for the join."""
    relpath, column = spec.split(":")
    path = vista_meta_dir / relpath
    lines = path.read_text(encoding="utf-8").split("\n")
    header = lines[0].split("\t")
    i = header.index(column)
    return {row[i].upper() for row in (line.split("\t") for line in lines[1:] if line) if row[i]}


def measure(
    entities_by_type: dict[str, list[str]],
    vocabs: dict[str, set[str]],
    quality: EntityQuality,
) -> list[TypeMeasurement]:
    """One measurement row per declared or shipping type (pure)."""
    rows: list[TypeMeasurement] = []
    for name in sorted(set(quality.types) | set(entities_by_type)):
        canonicals = entities_by_type.get(name, [])
        policy = quality.types.get(name)
        if policy is None:
            rows.append(TypeMeasurement(name, "UNDECLARED", len(canonicals), 0, 0.0, 0.0, ok=False))
            continue
        if policy.status != "floor-verified":
            rows.append(TypeMeasurement(name, policy.status, len(canonicals), 0, 0.0, 0.0, ok=True))
            continue
        vocab = vocabs.get(name, set())
        joined = sum(1 for c in canonicals if c.upper() in vocab)
        rate = round(joined / len(canonicals), 4) if canonicals else 1.0
        rows.append(
            TypeMeasurement(
                name,
                policy.status,
                len(canonicals),
                joined,
                rate,
                policy.floor,
                ok=rate >= policy.floor,
            )  # fmt: skip
        )
    return rows


def verdict(rows: list[TypeMeasurement]) -> str:
    return "PASS" if all(r.ok for r in rows) else "FAIL"


def render(rows: list[TypeMeasurement], echo) -> None:  # type: ignore[no-untyped-def]
    echo("=== entity quality — measured join rates vs declared floors ===")
    for r in rows:
        if r.status == "floor-verified":
            mark = "✅" if r.ok else "❌"
            echo(f"  {mark} {r.type:<18} {r.joined}/{r.count} = {r.rate:.1%} (floor {r.floor:.0%})")
        else:
            mark = "✅" if r.ok else "❌"
            echo(f"  {mark} {r.type:<18} {r.count} entities — {r.status}")
