# Research Platform Showcase

**Platform version:** `0.9.1`
**Document version:** `1.0`
**Date:** `2026-07-30`

This directory contains three curated English runs produced end to end by the local office
deployment. The examples are checked-in product evidence, not hand-written mock reports.

## Included cases

| Directory | Research question | Rounds | Sources | Claims | Relative recall |
|---|---|---:|---:|---:|---:|
| [`radiology`](radiology/) | Clinical evidence on multimodal vision-language and foundation models in radiology, 2024–2026 | 4 | 37 | 106 | 0.9730 |
| [`small-modular-reactors`](small-modular-reactors/) | Evidence on SMR cost, schedule, regulation, and deployment claims | 7 | 9 | 40 | 0.8889 |
| [`humanoid-robots`](humanoid-robots/) | Production evidence versus expectations for humanoid robots | 13 | 29 | 58 | 1.0000 |

Relative recall is an internal discovery-quality signal based on accepted and observed
candidates. It is not a claim that the system found every source that exists.

## Files retained per case

- `01_executive_summary.md`
- `02_full_research_report.md`
- `05_source_catalog.csv`
- `09_search_protocol.yaml`
- `15_literature_inventory.md`
- `16_research_report.docx`
- `16a_research_contribution_landscape.png`
- `16b_theme_evidence_map.png`
- one source-figure excerpt when a suitable figure was found

Raw source bodies, raw passages, and ZIP bundles are intentionally omitted from Git to keep
the repository compact and to avoid republishing a large third-party corpus. They remain
available from the originating local artifact store.

## How to read the status

All three runs ended as `completed_incomplete`, not `completed`. This is deliberate and
important:

- all three achieved `1.00` claim-audit coverage;
- each produced a usable report and the selected artifacts;
- one or more strict exit gates—such as source-family coverage, query-branch coverage,
  unresolved major claims, or estimated completeness—remained below target.

The platform therefore delivered the work while preserving the gaps instead of silently
promoting it to a fully complete research result.

## Recommended review order

1. Open the Word report to inspect the reader-facing result.
2. Read the full Markdown report to inspect source references.
3. Review the literature inventory to see what each retained source contributed.
4. Inspect the source catalog and search protocol for provenance and reproducibility.
5. Compare the theme map with the report structure.
