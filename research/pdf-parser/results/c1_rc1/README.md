# C1 RC1 Evidence

<!-- CODEX-2026-08-18: Compact, reviewable evidence for pdf-parser-v0.1.0-rc1. -->

This directory records the completed 180 Turkish + 50 English C1 run and the
C2 threshold sweeps. It intentionally excludes raw corpora, model caches, and
the 690 generated Markdown files.

Read in this order:

1. `calibration_report.md`
2. `summary.json`
3. `calibration_summary.json`
4. `route_errors.csv`

The complete per-document `predictions.jsonl` and generated Markdown are
reproducible work products. They are excluded from Git because they contain
local paths and add unnecessary repository weight.

The production thresholds were not changed: no route candidate met the agreed
precision, recall, and fast-path acceptance gates simultaneously.
