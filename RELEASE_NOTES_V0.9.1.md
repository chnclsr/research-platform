# Research Platform v0.9.1

**Platform version:** `0.9.1`

**Document version:** `1.0`

**Release date:** `2026-07-30`

## A local research engine became a shared product

Version 0.9.1 is the point at which Research Platform should be understood as more than a
research-agent prototype. It is now a shared evidence service that office users can reach
from Codex, Claude, Telegram, or the operations console while one local workstation performs
the underlying collection and inference.

The validated deployment uses a single NVIDIA RTX 4060 with 8 GB VRAM. Language reasoning,
dense retrieval, and figure inspection remain local through Ollama. PostgreSQL, Redis, MinIO,
and a checkpointed worker turn that constrained model stack into a durable multi-user
research back end.

## Product capabilities in this release

- 27 connectors across nine web, academic, official, archival, code/data, and institutional
  source families.
- High-recall `literature_scan` mode with no mandatory source-count ceiling.
- Time budgets that stop new collection but still finish evidence processing and reporting.
- Query-branch and coverage-driven recovery rather than a single search pass.
- Structure-aware long-document passages with lexical and local dense retrieval.
- Claim-to-passage audit links, contradiction handling, and adversarial review.
- Theme-based synthesis designed around the limits of a local 4B model.
- Word reports with source catalogs, literature maps, evidence themes, and audit appendices.
- Local vision inspection of paper figures.
- Selected source-figure placement in the relevant report section, with source, page,
  caption, model interpretation, and distribution warning.
- Raw-only, result-only, and combined delivery bundles for downstream agents.
- MCP, Telegram, and office operations-console access to one shared run state.

## Showcase evidence

Three English end-to-end examples are checked into [`showcase/`](showcase/):

| Case | Retained sources | Extracted claims | Rounds |
|---|---:|---:|---:|
| Multimodal AI in radiology | 37 | 106 | 4 |
| Small modular reactors | 9 | 40 | 7 |
| Humanoid robots in production | 29 | 58 | 13 |

They include reader-facing Word documents, Markdown reports, source catalogs, search
protocols, literature inventories, and evidence visualizations. Raw source bodies and raw
passages remain in the local artifact store and are not republished in Git.

All three runs achieved full claim-audit coverage. They were nevertheless labeled
`completed_incomplete` because the platform’s strict family, branch, unresolved-claim, or
estimated-completeness gates still detected gaps. This distinction is a feature: useful
deliverables are preserved without hiding the limits of the search.

## Verification

- `155` automated tests passed.
- Ruff static checks passed.
- The showcase contains only curated result artifacts; raw corpora, secrets, logs, and local
  environment files are excluded from version control.

## Compatibility and upgrade

- Database migration: `0006_figure_observations`
- Main local language model: `qwen3:4b-instruct-2507-q4_K_M`
- Embedding model: `embeddinggemma:300m-qat-q4_0`
- Figure analyst: `qwen3.5:4b`

After updating the code:

```powershell
.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head
```

Existing v0.7 run history remains in PostgreSQL. The release does not require copying raw run
data into the Git repository.
