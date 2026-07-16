from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import benchmark_models


PROFILES = [
    {
        "profile": "qwen3-4b-rtx4060-full-gpu",
        "model": "qwen3:4b-instruct-2507-q4_K_M",
        "context_tokens": 24576,
        "temperature": 0.0,
        "top_p": None,
        "top_k": None,
        "presence_penalty": None,
        "max_output_tokens": 2048,
        "think": False,
        "reason_then_format": False,
        "reasoning_output_tokens": 20480,
    },
    {
        "profile": "qwen3.5-4b-rtx4060-full-gpu",
        "model": "qwen3.5:4b",
        "context_tokens": 24576,
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 1.5,
        "max_output_tokens": 2048,
        "think": True,
        "reason_then_format": True,
        "reasoning_output_tokens": 20480,
    },
    {
        "profile": "nanbeige4.1-3b-q8-rtx4060-max-thinking",
        "model": "tomng/nanbeige4.1:3b-q8_0",
        "context_tokens": 36864,
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 0,
        "min_p": 0.01,
        "repeat_penalty": 1.0,
        "presence_penalty": None,
        "max_output_tokens": 2048,
        "think": True,
        "reason_then_format": True,
        "reasoning_output_tokens": 32768,
    },
]


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    section_names = [section["name"] for section in runs[0]["sections"]]
    return {
        "quality_mean": round(statistics.mean(run["quality_score"] for run in runs), 2),
        "quality_min": min(run["quality_score"] for run in runs),
        "quality_max": max(run["quality_score"] for run in runs),
        "wall_seconds_mean": round(
            statistics.mean(run["performance"]["wall_seconds"] for run in runs), 3
        ),
        "tokens_per_second_mean": round(
            statistics.mean(
                run["performance"]["generation_tokens_per_second"] for run in runs
            ),
            3,
        ),
        "peak_vram_mib": max(run["gpu"]["peak_vram_mib"] for run in runs),
        "peak_gpu_utilization_percent": max(
            run["gpu"]["peak_gpu_utilization_percent"] for run in runs
        ),
        "error_count": sum(len(run["errors"]) for run in runs),
        "sections_mean": {
            name: round(
                statistics.mean(
                    next(section["score"] for section in run["sections"] if section["name"] == name)
                    * 100
                    for run in runs
                ),
                2,
            )
            for name in section_names
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="RTX 4060 optimized fair model benchmark")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--suite", choices=["development", "holdout"], default="holdout")
    parser.add_argument("--profiles", nargs="+", help="Run only named optimized profiles")
    parser.add_argument(
        "--sections",
        nargs="+",
        choices=["decomposition", "query_generation", "evidence_extraction", "entailment", "synthesis"],
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/model-optimized-benchmark.json")
    )
    args = parser.parse_args()
    if args.suite == "holdout":
        from benchmark_holdout_cases import apply

        apply()
    results = []
    selected_profiles = [
        profile for profile in PROFILES
        if not args.profiles or profile["profile"] in args.profiles
    ]
    if not selected_profiles:
        parser.error("No matching profile was selected")
    for profile in selected_profiles:
        runs = []
        for repeat in range(1, args.repeats + 1):
            print(f"RUN_START {profile['profile']} repeat={repeat}", flush=True)
            run = await benchmark_models.run_model(
                profile["model"],
                args.ollama_url,
                profile["context_tokens"],
                temperature=profile["temperature"],
                top_p=profile["top_p"],
                top_k=profile["top_k"],
                min_p=profile.get("min_p"),
                repeat_penalty=profile.get("repeat_penalty"),
                presence_penalty=profile["presence_penalty"],
                max_output_tokens=profile["max_output_tokens"],
                think=profile["think"],
                reason_then_format=profile["reason_then_format"],
                reasoning_output_tokens=profile["reasoning_output_tokens"],
                selected_sections=set(args.sections) if args.sections else None,
            )
            run["repeat"] = repeat
            runs.append(run)
            print(
                f"RUN_DONE {profile['profile']} repeat={repeat} "
                f"quality={run['quality_score']} seconds={run['performance']['wall_seconds']}",
                flush=True,
            )
        results.append({"profile": profile, "aggregate": aggregate(runs), "runs": runs})
    payload = {
        "benchmark_version": "1.2.0-hardware-optimized-holdout",
        "suite": args.suite,
        "generated_at": datetime.now(UTC).isoformat(),
        "hardware": "NVIDIA GeForce RTX 4060 8 GB; 32 GB system RAM",
        "selection_rule": "highest stable quality while retaining 100% GPU model placement",
        "repeats": args.repeats,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {args.output.resolve()}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
