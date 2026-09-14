from __future__ import annotations

from research_platform.telegram_bot import (
    report_ready_keyboard,
    revision_draft_keyboard,
    revision_plan_keyboard,
)

RUN_ID = "01RUN".ljust(26, "0")
REVISION_ID = "01REVISION".ljust(26, "0")
PPTX_VERSION_ID = "01PPTX".ljust(26, "0")
DOCX_VERSION_ID = "01DOCX".ljust(26, "0")


def _accepted_revision() -> dict:
    return {
        "id": REVISION_ID,
        "revision_number": 1,
        "artifacts": [
            {"id": PPTX_VERSION_ID, "logical_name": "report.pptx"},
            {"id": DOCX_VERSION_ID, "logical_name": "report.docx"},
        ],
    }


def _callback_data(markup: dict) -> list[str]:
    return [
        button["callback_data"]
        for row in markup["inline_keyboard"]
        for button in row
    ]


def test_completed_report_exposes_both_files_revision_and_bundle_actions():
    callbacks = _callback_data(report_ready_keyboard(RUN_ID, _accepted_revision(), "tr"))

    assert callbacks == [
        f"rvfile:{PPTX_VERSION_ID}",
        f"rvfile:{DOCX_VERSION_ID}",
        f"revise:{RUN_ID}:{PPTX_VERSION_ID}",
        f"delivery:{RUN_ID}:result",
    ]
    assert all(len(item.encode()) <= 64 for item in callbacks)


def test_plan_and_draft_buttons_use_durable_revision_ids():
    plan_callbacks = _callback_data(revision_plan_keyboard(REVISION_ID, "en"))
    draft_callbacks = _callback_data(revision_draft_keyboard(_accepted_revision(), "en"))

    assert plan_callbacks == [
        f"rvplan:{REVISION_ID}:approve",
        f"rvplan:{REVISION_ID}:edit",
        f"rvplan:{REVISION_ID}:cancel",
    ]
    assert draft_callbacks == [
        f"rvfile:{PPTX_VERSION_ID}",
        f"rvfile:{DOCX_VERSION_ID}",
        f"rvaccept:{REVISION_ID}",
        f"rvnew:{REVISION_ID}",
        f"rvcancel:{REVISION_ID}",
    ]
    assert all(len(item.encode()) <= 64 for item in plan_callbacks + draft_callbacks)
