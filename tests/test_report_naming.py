"""
What the Word report is called, and why the run's label is not trusted verbatim.

The report used to be a fixed `16_research_report.docx`, so two runs downloaded into one
folder said nothing about which was which. It now carries the run's topic handle -- the
`snake_case` label the LLM produces at VALIDATE_PROTOCOL and Telegram prints instead of a
ULID.

That label can also arrive from a client: `ResearchProtocol.label` is validated only for
length, and `_name_run` returns early when the protocol already carries one, so a
client-supplied label never passes through `slugify`. Since the name becomes part of the
object key `runs/{run_id}/{name}`, a label outside the key-safe shape is slugified before
it is used -- but one already in that shape is kept verbatim, because `slugify` drops
stopwords and would otherwise rename the run behind the user's back.
"""

from __future__ import annotations

from research_platform.exporter import WORD_REPORT_FALLBACK, word_report_name


def test_the_report_is_named_after_the_runs_topic():
    assert word_report_name("ai_in_lung_ct") == "16_ai_in_lung_ct_report.docx"


def test_an_existing_handle_survives_naming_unchanged():
    # slugify drops stopwords, so putting an already-slugged label back through it would
    # turn ai_in_lung_ct into ai_lung_ct and the file would stop matching the handle the
    # user sees next to the run.
    for handle in ("ai_in_lung_ct", "lung_cancer_ct_last_3m", "a", "x" * 64):
        assert word_report_name(handle) == f"16_{handle}_report.docx"


def test_a_run_without_a_label_keeps_the_original_name():
    # Naming can fail outright: the model may be unreachable and the question may slugify
    # to nothing, in which case `_name_run` leaves the protocol without a label.
    assert word_report_name(None) == WORD_REPORT_FALLBACK
    assert word_report_name("") == WORD_REPORT_FALLBACK
    assert word_report_name("   ") == WORD_REPORT_FALLBACK


def test_a_hostile_label_cannot_escape_the_runs_object_prefix():
    """A client can set `label` over the API, and the name lands in an object key."""
    for hostile in ("../../etc/passwd", "..\\..\\windows\\system32", "a/b", "..", "."):
        name = word_report_name(hostile)
        assert "/" not in name
        assert "\\" not in name
        assert ".." not in name
        assert name.startswith("16_")
        assert name.endswith(".docx")


def test_a_non_ascii_label_becomes_a_plain_file_name():
    name = word_report_name("sağlık_yapay_zekâ")
    assert name == "16_saglik_yapay_zeka_report.docx"
    assert name.isascii()


def test_the_numeric_prefix_keeps_the_report_in_reading_order():
    # Bundle members are written in sorted order, and digits sort before letters: without
    # the prefix the report would land after every numbered artifact instead of at 16.
    names = sorted(
        ["15_literature_inventory.md", "17a_source_figure_excerpt.png",
         word_report_name("ai_in_lung_ct")]
    )
    assert names[1] == "16_ai_in_lung_ct_report.docx"
