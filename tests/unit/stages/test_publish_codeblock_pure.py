"""Unit tests for stages.publish.codeblock_pure — recover fenced code from the VDL's defect-D-4
patterns (FileMan docs-as-code pilot, L1.2; docs/fileman-docs-pilot-implementation-plan.md).

FileMan gold has 0 fenced code blocks: every M example is a bold-inline statement or escaped prose.
This transform fences the real patterns (standalone bold statements, escaped global listings, and
console sessions), un-escapes inside the fences, and — the main risk — leaves prose with inline
M-token emphasis untouched. Ambiguous bold code-ish lines go to a `manual-review` marker.
Pure: body markdown → (new body, report).
"""

from __future__ import annotations

from vdocs.stages.publish import codeblock_pure as cb


def _md(body: str) -> str:
    return cb.reconstruct(body)[0]


# --- standalone bold M statement → ```mumps ----------------------------------------------------
def test_standalone_bold_statement_becomes_a_mumps_fence():
    out, rep = cb.reconstruct('**S ^GLB(1)="First line."**\n')
    assert "```mumps" in out
    assert 'S ^GLB(1)="First line."' in out
    assert "**S ^GLB" not in out  # bold markers stripped inside the fence
    assert rep.blocks == 1


# --- escaped global listing under a caption → fenced + un-escaped + caption kept adjacent -------
def test_escaped_global_listing_is_fenced_unescaped_and_keeps_its_caption():
    body = (
        "##### Example 1\n\n"
        "Figure 6: EN^DDIOL—Example: Write Identifier Node\n\n"
        '^DD(filenumber,0,"ID","W1")=W " ",\\$P(^(0),U,2)\n\n'
        "An equivalent statement is shown below.\n"
    )
    out, rep = cb.reconstruct(body)
    assert "```mumps" in out
    assert '=W " ",$P(^(0),U,2)' in out  # \$P un-escaped to $P inside the fence
    assert "Figure 6: EN^DDIOL" in out  # caption preserved, directly above the fence
    assert out.index("Figure 6") < out.index("```mumps")
    assert "An equivalent statement is shown below." in out  # trailing prose untouched
    assert rep.lines_unescaped >= 1


# --- console session (direct-mode prompt) → ```console -----------------------------------------
def test_direct_mode_prompt_is_tagged_console():
    out, rep = cb.reconstruct('**\\>D EN^DDIOL("This is text.","","!!?12")**\n')
    assert "```console" in out
    assert '>D EN^DDIOL("This is text.","","!!?12")' in out  # \> un-escaped to >
    assert rep.console_blocks == 1


# --- THE critical negative: inline emphasis in prose is left alone -----------------------------
def test_prose_with_inline_m_token_emphasis_is_unchanged():
    body = "The **\\$ORDER** function is used at several points in VA FileMan's code.\n"
    out, rep = cb.reconstruct(body)
    assert out == body
    assert rep.blocks == 0


def test_new_person_prose_is_not_fenced():
    # "NEW" is an M command verb, but this is prose about the NEW PERSON file — must not fence.
    body = "Entries are stored in the **NEW PERSON** file (#200).\n"
    assert _md(body) == body


# --- blank-separated run of code lines merges into one block -----------------------------------
def test_blank_separated_global_lines_merge_into_one_block():
    body = '^TMP("DIHELP",\\$J,1)=""\n\n^TMP("DIHELP",\\$J,2)=" text"\n'
    out, rep = cb.reconstruct(body)
    assert rep.blocks == 1
    assert out.count("```mumps") == 1
    assert '^TMP("DIHELP",$J,1)=""' in out
    assert '^TMP("DIHELP",$J,2)=" text"' in out


# --- manual-review escape hatch (never silent) -------------------------------------------------
def test_ambiguous_bold_codeish_line_is_flagged_manual_review():
    out, rep = cb.reconstruct("**^TMP global node**\n")
    assert rep.manual_review == 1
    assert "manual-review" in out
    assert "```" not in out  # not confidently fenced


# --- existing fences are left alone ------------------------------------------------------------
def test_content_already_in_a_fence_is_not_reprocessed():
    body = "```mumps\nS X=1\n```\n"
    assert _md(body) == body


# --- determinism -------------------------------------------------------------------------------
def test_deterministic():
    body = '**S DIC="^DIZ(662001,",L=0**\n\nsome prose\n\n^GLB(1)="x"\n'
    assert cb.reconstruct(body) == cb.reconstruct(body)
