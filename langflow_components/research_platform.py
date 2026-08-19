"""Fixed control-plane components for the Research Platform API."""

from __future__ import annotations

import os
import time

import httpx
from langflow.custom import Component
from langflow.io import DataInput, DropdownInput, MultilineInput, Output, StrInput
from langflow.schema import Data


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class BuildResearchProtocol(Component):
    display_name = "Build Research Protocol"
    description = "Creates a validated Research Platform protocol payload."
    icon = "FileCheck"
    name = "BuildResearchProtocol"
    inputs = [
        StrInput(name="title", display_name="Title", required=True),
        MultilineInput(name="primary_question", display_name="Primary Question", required=True),
        MultilineInput(name="sub_questions", display_name="Sub-questions (one per line)"),
        DropdownInput(name="profile", display_name="Connector Profile", options=["core", "all"], value="core"),
        StrInput(name="report_language", display_name="Report Language", value="tr"),
        # Required: the platform refuses a protocol that does not state how long the run
        # may collect, so the flow has to ask rather than inherit a hidden default.
        StrInput(name="max_wall_minutes", display_name="Max Wall Minutes", required=True),
    ]
    outputs = [Output(name="protocol", display_name="Protocol", method="build_protocol")]

    def build_protocol(self) -> Data:
        families = (
            ["web", "academic", "official_legal", "code_data"]
            if self.profile == "core"
            else [
                "web", "academic", "books_theses", "patents_standards", "official_legal",
                "news_archives", "code_data", "company", "grey_literature",
            ]
        )
        return Data(data={
            "title": self.title,
            "primary_question": self.primary_question,
            "sub_questions": [q.strip() for q in self.sub_questions.splitlines() if q.strip()],
            "scope": {"geography": [], "domains": []},
            "languages": [self.report_language, "en"] if self.report_language != "en" else ["en"],
            "report_language": self.report_language,
            "connectors": {"profile": self.profile, "included_families": families},
            "budget": {"max_wall_minutes": int(self.max_wall_minutes)},
        })


class StartResearchRun(Component):
    display_name = "Start Research Run"
    description = "Submits a protocol without exposing graph or security internals."
    icon = "Play"
    name = "StartResearchRun"
    inputs = [
        DataInput(name="protocol", display_name="Protocol", required=True),
        StrInput(name="api_url", display_name="API URL", value=os.getenv("RESEARCH_API_URL", "http://api:8000")),
        StrInput(name="api_token", display_name="API Token", value=os.getenv("RESEARCH_API_TOKEN", ""), advanced=True),
    ]
    outputs = [Output(name="run", display_name="Research Run", method="start")]

    def start(self) -> Data:
        payload = self.protocol.data if hasattr(self.protocol, "data") else self.protocol
        response = httpx.post(
            f"{self.api_url.rstrip('/')}/v1/research-runs",
            headers=_headers(self.api_token), json={"protocol": payload}, timeout=30,
        )
        response.raise_for_status()
        return Data(data=response.json())


class WatchResearchRun(Component):
    display_name = "Watch Research Run"
    description = "Polls run status until completion or timeout."
    icon = "Activity"
    name = "WatchResearchRun"
    inputs = [
        DataInput(name="run", display_name="Research Run", required=True),
        StrInput(name="api_url", display_name="API URL", value=os.getenv("RESEARCH_API_URL", "http://api:8000")),
        StrInput(name="api_token", display_name="API Token", value=os.getenv("RESEARCH_API_TOKEN", ""), advanced=True),
        StrInput(name="timeout_seconds", display_name="Timeout Seconds", value="2700"),
    ]
    outputs = [Output(name="status", display_name="Final Status", method="watch")]

    def watch(self) -> Data:
        run = self.run.data if hasattr(self.run, "data") else self.run
        run_id = run["id"]
        deadline = time.monotonic() + int(self.timeout_seconds)
        while time.monotonic() < deadline:
            response = httpx.get(
                f"{self.api_url.rstrip('/')}/v1/research-runs/{run_id}",
                headers=_headers(self.api_token), timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            if data["status"] in {"completed", "completed_incomplete", "failed", "cancelled"}:
                return Data(data=data)
            time.sleep(2)
        return Data(data={"id": run_id, "status": "watch_timeout"})


class DownloadResearchBundle(Component):
    display_name = "Download Research Bundle"
    description = "Downloads the final reproducibility ZIP and returns its bytes as data."
    icon = "Download"
    name = "DownloadResearchBundle"
    inputs = [
        DataInput(name="run", display_name="Research Run", required=True),
        StrInput(name="api_url", display_name="API URL", value=os.getenv("RESEARCH_API_URL", "http://api:8000")),
        StrInput(name="api_token", display_name="API Token", value=os.getenv("RESEARCH_API_TOKEN", ""), advanced=True),
    ]
    outputs = [Output(name="bundle", display_name="Bundle", method="download")]

    def download(self) -> Data:
        run = self.run.data if hasattr(self.run, "data") else self.run
        run_id = run["id"]
        response = httpx.get(
            f"{self.api_url.rstrip('/')}/v1/research-runs/{run_id}/artifacts/research_bundle.zip",
            headers=_headers(self.api_token), timeout=120,
        )
        response.raise_for_status()
        return Data(data={"run_id": run_id, "filename": "research_bundle.zip", "content_hex": response.content.hex()})
