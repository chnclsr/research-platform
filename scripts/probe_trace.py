#!/usr/bin/env python3
"""Probe trace for one run.

Shows what recovery tried each round, what the model proposed, which candidate the
deterministic scorer picked and whether it overruled the model, and what the probe
actually returned. Reads `run_events`; changes nothing.

    scripts/probe_trace.py <run_id>
"""
from __future__ import annotations

import json
import subprocess
import sys

EVENTS = (
    "recovery_plan",
    "probe_bundle_generated",
    "probe_candidate_selected",
    "probe_candidate_outcome",
)


def fetch(run_id: str) -> list[tuple[str, str, dict]]:
    query = (
        "SELECT to_char(created_at,'HH24:MI:SS'), event_type, payload::text "
        "FROM run_events WHERE run_id='" + run_id + "' AND event_type IN ("
        + ",".join(f"'{name}'" for name in EVENTS)
        + ") ORDER BY created_at;"
    )
    output = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "psql", "-U", "research", "-d", "research", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    for line in output.splitlines():
        if not line.strip():
            continue
        timestamp, event_type, payload = line.split("|", 2)
        rows.append((timestamp, event_type, json.loads(payload)))
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    rows = fetch(sys.argv[1])
    if not rows:
        print("No recovery or probe events yet for this run.")
        print("Probes only run once gap-driven recovery has nothing left to try.")
        return 0
    for timestamp, event_type, payload in rows:
        rnd = payload.get("round")
        head = f"{timestamp}  round {rnd}"
        if event_type == "recovery_plan":
            missions = payload.get("missions") or []
            probe = any(
                str(m.get("branch_id", "")).startswith("probe:") for m in missions
            )
            kind = "PROBE" if probe else "gap-driven"
            print(f"{head}  recovery_plan: {len(missions)} mission(s), {kind}")
            for mission in missions:
                branch = mission.get("branch_id", "")
                query = str(mission.get("query", ""))[:90]
                print(f"             {branch} :: {query}")
        elif event_type == "probe_bundle_generated":
            print(
                f"{head}  BUNDLE by {payload.get('generated_by')} "
                f"in {payload.get('latency_ms')}ms"
            )
            print(f"             tactics offered: {payload.get('tactics')}")
            if payload.get("rejected"):
                print(f"             rejected: {payload.get('rejected')}")
        elif event_type == "probe_candidate_selected":
            overruled = (
                "  <-- scorer overruled the model"
                if payload.get("disagreed_with_model")
                else ""
            )
            print(
                f"{head}  PICK  {payload.get('tactic') or '(fallback)'}  "
                f"score={payload.get('score')}  by={payload.get('selected_by')}  "
                f"model_rank={payload.get('suggested_rank')}{overruled}"
            )
            print(f"             connectors: {payload.get('connector_ids')}")
            signature = str(payload.get("mission_signature", ""))
            print(f"             query: {signature.split('||')[0][-90:]}")
        elif event_type == "probe_candidate_outcome":
            zero = payload.get("zero_yield_reason") or ""
            verdict = (
                f"ZERO YIELD ({zero})"
                if zero
                else f"{payload.get('new_source_versions')} new source version(s)"
            )
            print(f"{head}  RESULT {payload.get('tactic')}: {verdict}")
            print(
                f"             provider={payload.get('provider_candidates')} "
                f"novel={payload.get('novel_candidates')} "
                f"admitted={payload.get('admitted_candidates')} "
                f"acquired={payload.get('acquisition_successful')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
