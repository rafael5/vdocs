"""Code-block reconstruction for ``export-fileman`` (FileMan docs-as-code pilot, L1.2; see
``docs/fileman-docs-pilot-implementation-plan.md`` and
``docs/fileman-integrated-master-poc-proposal.md`` §5a).

The FileMan gold has **zero** fenced code blocks (defect D-4): every M example is rendered as a
bold-inline statement (``**S ^GLB(1)="x"**``) or an escaped-prose global listing
(``^DD(...)=W " ",\\$P(^(0),U,2)``). This pure transform fences those, un-escapes markdown artifacts
*inside* the fences, and tags console sessions — while leaving prose that merely *emphasizes* M
tokens (``the **$ORDER** function``) untouched, which is the dominant false-positive risk.

Detection is deliberately high-precision (bias to leaving prose alone):

* A line is **code** if, after stripping a full bold wrap, it starts (anchored) with an *uppercase*
  M command verb or a ``^`` global ref **and** carries an M operator (``= ^ $ (``) after it. The
  uppercase + anchored + operator triple rejects "If the call…" and "NEW PERSON file".
* Consecutive code lines (interior single blank lines allowed) merge into one fenced block.
* A block is **console** when it carries a direct-mode prompt (``>``); else ``mumps``.
* A fully-bold, code-ish-but-unconfirmable line (operator present, doesn't cleanly parse) is wrapped
  in a ``manual-review`` marker and **counted** — never silently dropped (the gate forbids that).

Pure + deterministic: ``reconstruct(body) -> (new_body, report)``; no clock, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# M command verbs (uppercase, case-sensitive on purpose — real code uses uppercase; prose words like
# "If"/"Set"/"New" are mixed-case and must not match).
_VERBS = (
    "SET|S|DO|D|WRITE|W|KILL|K|NEW|N|IF|I|FOR|F|QUIT|Q|XECUTE|X|GOTO|G|HANG|H|"
    "MERGE|M|READ|R|ZWRITE|ZWR|ZW"
)
# An optional escaped/plain direct-mode prompt, then a verb token or a global ref.
_LEAD = r"\\?>?\s*"
_VERB_RE = re.compile(rf"^{_LEAD}(?:{_VERBS})\b")
_GLOBAL_RE = re.compile(rf"^{_LEAD}\^")
_OP_RE = re.compile(r"[=^$(]")
_PROMPT_RE = re.compile(rf"^{_LEAD}".replace(r"\\?>?", r"\\?>"))  # requires the > prompt
_BOLD_RE = re.compile(r"^\*\*(.+)\*\*$")
# markdown-escape artifacts to undo inside code (e.g. \$ -> $, \_ -> _)
_UNESCAPE_RE = re.compile(r"\\([$_*<>\[\]#`])")


@dataclass(frozen=True)
class CodeblockReport:
    """What the reconstruction did — surfaced by the L1.4 driver / the gate."""

    blocks: int = 0
    console_blocks: int = 0
    lines_unescaped: int = 0
    manual_review: int = 0


def _strip_bold(s: str) -> tuple[str, bool]:
    """Return (inner, was_fully_bold) — strips a single full ``**…**`` wrap if present."""
    m = _BOLD_RE.match(s)
    return (m.group(1).strip(), True) if m else (s, False)


def _is_code(core: str) -> bool:
    """True if ``core`` (bold already stripped) is an M statement, not prose."""
    if _GLOBAL_RE.match(core):
        return "=" in core or "(" in core  # a global *statement*, not a bare ref
    m = _VERB_RE.match(core)
    return bool(m and _OP_RE.search(core[m.end() :]))  # operator after the verb


def _is_console(core: str) -> bool:
    return bool(_PROMPT_RE.match(core))


def _is_manual(line: str) -> bool:
    """A fully-bold, code-ish line that carries an M operator but doesn't cleanly parse as code."""
    core, bold = _strip_bold(line.strip())
    if not bold or _is_code(core):
        return False
    starts = _VERB_RE.match(core) or _GLOBAL_RE.match(core)
    return bool(starts and _OP_RE.search(core))


def _classify(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    core, _ = _strip_bold(s)
    if _is_code(core):
        return "code"
    if _is_manual(line):
        return "manual"
    return "prose"


def reconstruct(body: str) -> tuple[str, CodeblockReport]:
    """Fence the VDL's bold/escaped code patterns. Returns the rewritten body + a report."""
    lines = body.split("\n")
    out: list[str] = []
    blocks = console_blocks = unescaped = manual = 0
    in_fence = False
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue

        kind = _classify(line)
        if kind == "code":
            run, j = _collect_run(lines, i)
            cooked, was_console, n_unesc = _render_block(run)
            if out and out[-1].strip() != "":
                out.append("")
            out.extend(cooked)
            blocks += 1
            console_blocks += 1 if was_console else 0
            unescaped += n_unesc
            i = j
            continue
        if kind == "manual":
            out.append("<!-- vdocs-codeblock: manual-review — bold code-ish line -->")
            out.append(line)
            manual += 1
            i += 1
            continue
        out.append(line)
        i += 1

    rebuilt = "\n".join(out)
    return rebuilt, CodeblockReport(blocks, console_blocks, unescaped, manual)


def _collect_run(lines: list[str], start: int) -> tuple[list[str], int]:
    """Gather a maximal run of code lines from ``start`` (interior single blank lines allowed)."""
    run: list[str] = []
    j = start
    n = len(lines)
    while j < n:
        if _classify(lines[j]) == "code":
            run.append(lines[j])
            j += 1
            continue
        if lines[j].strip() == "":  # look past blanks for another code line
            k = j
            while k < n and lines[k].strip() == "":
                k += 1
            if k < n and _classify(lines[k]) == "code":
                j = k
                continue
        break
    return run, j


def _render_block(run: list[str]) -> tuple[list[str], bool, int]:
    """Turn a run of raw code lines into fenced, un-escaped output lines."""
    console = False
    cooked: list[str] = []
    unescaped = 0
    for raw in run:
        core, _ = _strip_bold(raw.strip())
        if _is_console(core):
            console = True
        new = _UNESCAPE_RE.sub(r"\1", core)
        if new != core:
            unescaped += 1
        cooked.append(new)
    lang = "console" if console else "mumps"
    return [f"```{lang}", *cooked, "```", ""], console, unescaped
