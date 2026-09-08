"""Opt-in Chromium acceptance test; API data is fixed, the panel JavaScript is real."""
import os
from urllib.parse import parse_qs, urlparse

import pytest

from research_platform.control_panel_ui import CONTROL_PANEL_HTML

pytestmark = pytest.mark.skipif(os.getenv("RUN_PANEL_BROWSER_TESTS") != "true",
                                reason="Explicit Chromium acceptance test")


def test_panel_visits_filters_paging_refresh_and_safe_text():
    from playwright.sync_api import expect, sync_playwright

    calls = []
    status = {"value": "running"}

    def route(request):
        url = urlparse(request.request.url)
        path, q = url.path, parse_qs(url.query)
        calls.append((path, q))
        if path == "/":
            request.fulfill(body=CONTROL_PANEL_HTML, content_type="text/html")
            return
        data = {}
        if path.endswith("/session"):
            data = {"is_admin": False, "display_name": "Panel test"}
        elif path.endswith("/status"):
            request.fulfill(status=503, body="isolated fixture")
            return
        elif path.endswith("/detail"):
            run_id = path.split("/")[3]
            data = {"run": {"id": run_id, "status": status["value"], "current_stage": "AUDIT",
                            "protocol": {"title": run_id}, "coverage": {}, "elapsed_seconds": 5},
                    "flow": {"nodes": [{"stage": "AUDIT", "label": "Audit", "state": "active",
                                        "visits": 205, "duration_seconds": 5}]},
                    "quality": {}, "funnel": {"steps": [], "admission": {}},
                    "llm": {}, "claim_summary": {}, "sources": [], "artifacts": []}
        elif path.endswith("/stages/AUDIT"):
            offset = int(q.get("offset", [0])[0])
            data = {"stage": "AUDIT", "label": "Audit", "visit_count": 205, "offset": offset,
                    "has_more": offset == 0, "total_seconds": 5,
                    "visits": [{"visit_id": i + 1, "stage": "AUDIT", "round": i,
                                "tools": [], "summary": {}} for i in range(offset, min(offset + 200, 205))]}
        elif "/visits/" in path or path.endswith("/events"):
            offset = int(q.get("offset", [0])[0])
            data = {"state": "completed", "history_available": True, "total": 60,
                    "has_more": offset == 0, "next_offset": offset + 50, "summaries": [],
                    "events": [{"id": 700 + offset, "label": "İddia denetimi", "type": "audit_claim",
                                "severity": "error", "payload": {"error": "<img src=x onerror=window.pwned=1>",
                                                                   "source_id": "s1",
                                                                   "scope_assessment": {"gaps": ["ct"]}}}]}
        elif path.endswith("/trace"):
            data = {"source": {"family": "academic"}, "passages": {}, "evidence": [],
                    "claims": [], "citation": None, "fate": {"label": "Kaynak izi testi"}}
        request.fulfill(json=data)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://panel.test/")
        page.evaluate("openRun('run-a')")
        node = page.locator(".flow-node.clickable")
        node.focus()
        node.press("Enter")
        expect(page.locator(".round-row")).to_have_count(200)
        page.get_by_role("button", name="Sonraki turları yükle").click()
        expect(page.locator(".round-row")).to_have_count(205)
        page.locator(".round-row").last.press("Enter")
        diagnostics = page.locator(".round-detail:not([hidden]) .visit-diagnostics")
        expect(diagnostics.locator("select")).to_have_count(1)
        diagnostics.locator("select").select_option("error")
        expect(diagnostics.get_by_text("60 olay", exact=False)).to_be_visible()
        diagnostics.get_by_role("button", name="Sonraki", exact=True).click()
        expect(diagnostics.locator('[data-event-id="750"]')).to_have_count(1)
        card = diagnostics.locator('[data-event-id="750"]')
        card.locator(":scope > summary").click()
        expect(card.get_by_text("<img src=x onerror=window.pwned=1>", exact=False).first).to_be_visible()
        assert page.evaluate("window.pwned") is None
        card.get_by_text("Facet kararları", exact=True).click()
        card.get_by_text("Teknik olay verisi", exact=True).click()
        card.get_by_role("button", name="Kaynak ve kanıt izini aç").click()
        expect(card.locator(".trace")).to_have_count(1)
        generic_section = page.locator("details.collapsible-section").first
        generic_section.locator(":scope > summary").click()
        expect(generic_section).to_have_attribute("open", "")
        page.locator(".drawer").evaluate("e=>e.scrollTop=500")
        page.evaluate(
            """() => {
                window.__roundSamples = [];
                window.__roundProbe = setInterval(
                    () => window.__roundSamples.push(
                        document.querySelectorAll('.round-row').length
                    ),
                    5,
                );
            }"""
        )
        page.evaluate("openRun('run-a',true)")
        samples = page.evaluate(
            """() => {
                clearInterval(window.__roundProbe);
                return window.__roundSamples;
            }"""
        )
        assert samples and min(samples) == 205
        expect(page.locator(".round-row")).to_have_count(205)
        expect(page.locator(".round-detail:not([hidden])")).to_have_count(1)
        expect(page.locator(".round-detail:not([hidden]) select")).to_have_value("error")
        expect(page.locator("details.collapsible-section").first).to_have_attribute("open", "")
        refreshed_card = page.locator('[data-event-id="750"]')
        expect(refreshed_card.get_by_text("Facet kararları", exact=True).locator("xpath=..")).to_have_attribute("open", "")
        expect(refreshed_card.get_by_text("Teknik olay verisi", exact=True).locator("xpath=..")).to_have_attribute("open", "")
        expect(refreshed_card.locator(".trace")).to_have_count(1)
        assert sum(path.endswith("/trace") for path, _ in calls) == 1
        assert page.locator(".drawer").evaluate("e=>e.scrollTop") == 500
        # Actual interval, not an explicit openRun, refreshes even with button focus.
        page.locator(".round-row").first.focus()
        before = sum(path.endswith("/detail") for path, _ in calls)
        page.wait_for_timeout(5600)
        assert sum(path.endswith("/detail") for path, _ in calls) > before
        status["value"] = "completed"
        page.evaluate("openRun('run-a',true)")
        before = sum(path.endswith("/detail") for path, _ in calls)
        page.wait_for_timeout(5600)
        assert sum(path.endswith("/detail") for path, _ in calls) == before
        page.evaluate("openRun('run-b')")
        expect(page.locator("#drawer-title")).to_have_text("run-b")
        expect(page.locator(".round-row")).to_have_count(0)
        assert not errors
        browser.close()
