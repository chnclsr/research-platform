# Product Overview: Research Platform

**Platform version:** `0.9.1`
**Document version:** `1.0`
**Date:** `2026-07-30`

## Executive statement

Research Platform is a local-first evidence service built for an office in which people
already work with capable general-purpose agents. Its purpose is not to replace Codex or
Claude. It gives them a common research substrate that can search broadly, preserve raw
material, identify relevant passages, expose uncertainty, and hand back reproducible
evidence packages.

The product milestone is the integration, not merely the pipeline:

- one workstation hosts the service;
- one consumer RTX 4060 performs local inference;
- multiple office users can submit work through their own agents or Telegram;
- the operations console exposes queue, stage, connector, coverage, and artifact state;
- every client receives the same durable run identity and output contract.

This turns research from an isolated chat behavior into shared infrastructure.

## Why the constrained hardware matters

The validated machine has an NVIDIA RTX 4060 with 8 GB VRAM, 32 GB system memory, and an
Intel Core i7-14700K. The deployment therefore cannot solve quality by placing a very large
model behind every step. The architecture makes a different trade:

1. deterministic code handles identity, hashes, dates, deduplication, state, budgets, and
   coverage arithmetic;
2. retrieval limits each model call to the most relevant, position-preserving passages;
3. small local models receive narrow, typed tasks;
4. evidence is accumulated in PostgreSQL rather than model context;
5. synthesis works from themed evidence packets with source allow-lists;
6. the final result remains inspectable through the source catalog, claim ledger, and raw
   corpus.

The result is not “a 4B model pretending to know everything.” It is a 4B model operating
inside a system that supplies memory, tools, provenance, and quality controls.

## The five accountable layers

| Layer | Responsibility | Auditable record |
|---|---|---|
| 1. Intent and planning | Protocol validation, decomposition, query branches, budgets | Search protocol, query branches, run events |
| 2. Discovery and acquisition | Federated search, URL policy, fallback reading, snapshots | Search attempts, acquisition strategy, source versions, hashes |
| 3. Corpus and retrieval | Normalization, structure-aware passages, lexical+dense ranking | Passage locations, retrieval scores, deduplication decisions |
| 4. Evidence and quality | Claim extraction, entailment, contradictions, coverage recovery | Evidence links, claim ledger, coverage snapshots, audit records |
| 5. Delivery and collaboration | Synthesis, Word export, raw/result bundles, MCP/Telegram | Reports, manifests, artifact catalog, client/run attribution |

These are logical accountability layers. The runtime contains more individual nodes because
each layer is split into idempotent operations that can be retried and checkpointed.

## Information collection

The connector registry currently exposes 27 connectors in nine families:

- **Web:** AgentSearch/SearXNG.
- **Academic:** OpenAlex, Semantic Scholar, Crossref, arXiv, Europe PMC, Zotero Local,
  Zotero Web.
- **Books and theses:** Open Library, OpenAlex dissertations.
- **Patents and standards:** EPO OPS, IETF Datatracker, trusted standards-domain search.
- **Official and legal:** Federal Register, EUR-Lex, configurable official registries.
- **News and archives:** GDELT, Internet Archive CDX, AgentSearch News.
- **Code and data:** GitHub, Hugging Face, Zenodo, DataCite.
- **Company:** SEC EDGAR, verified company-domain search.
- **Grey literature:** Zenodo Grey, institutional repositories.

Search is connector-aware. Query compilation preserves the central subject while adapting
syntax and filters for academic APIs, code search, news, and official sources. Candidate
records are deduplicated by persistent identifier first, then canonical URL, content hash,
and bibliographic similarity.

Acquisition follows a legal and observable resolver chain:

1. depth-one snapshots for GitHub repository URLs, rendered from tracked README,
   manifest, and source files;
2. open API or directly downloadable content;
3. AgentSearch reading;
4. Crawl4AI for structural or dynamic pages;
5. Jina Reader's browser engine for pages still blocked or empty;
6. a controlled Scrapling fallback where configured.

Failed strategies and access restrictions are recorded. Restricted content triggers a search
for lawful open-access alternatives; it does not trigger paywall circumvention.

## Recall rather than one-source answering

The default research mode is `literature_scan`. Its purpose is to build a relevant corpus,
not to select one convenient citation.

The collector:

- branches the main question into coverage dimensions;
- searches several connector families;
- expands from references and outgoing links;
- records discovery observations and connector health;
- retains direct and useful contextual sources;
- checks missing families, unanswered branches, unresolved claims, novelty, and saturation;
- creates targeted recovery missions when gaps remain;
- continues until quality gates, saturation, or the collection budget ends.

The source catalog and literature inventory remain first-class deliverables. A downstream
agent can therefore ask for the filtered raw research without accepting the local model’s
final synthesis.

## Long-document processing

Early versions passed only a leading slice of long documents to extraction. The current
pipeline instead:

- recognizes headings and structural boundaries;
- creates overlapping, position-preserving passages;
- records page, section, paragraph, and character locations where available;
- indexes passages lexically and with local embeddings;
- retrieves per sub-question;
- reranks relevant passages and includes neighboring context;
- sends separate evidence tasks to the local model.

This avoids both naive document concatenation and first-12,000-character bias.

## Evidence, contradiction, and audit

Claims are not stored as unsupported prose. An evidence link records:

- source and source version;
- passage location;
- a short verbatim quotation;
- support, contradiction, or uncertainty direction;
- confidence and entailment status.

Major claims target multiple independent sources. Independence checks consider author,
institution, dataset, and citation-chain overlap. Deterministic coverage calculations decide
whether another collection round is required.

An adversarial-review stage attempts to expose weak generalizations, missing comparison
groups, authority problems, and contradictory evidence before synthesis.

## Synthesis and Word reports

The report pipeline was redesigned when simple compilation proved insufficient. It now:

1. groups accepted evidence into report themes;
2. builds bounded evidence packets with source allow-lists;
3. asks the model to synthesize across studies, not enumerate isolated claims;
4. validates source references and repairs unsupported output;
5. creates a structured Word document with tables, contribution maps, and appendices;
6. keeps atomic evidence and retrieval measurements available for audit.

Figure intelligence adds a second path. The system locates figures in acquired papers,
captures the figure and caption, asks a local vision model for a structured interpretation,
rejects invented approximate values, and can place a source excerpt into the report where it
helps explain the text. The original source, page, caption, and interpretation remain linked.

## Office integration

### Codex and Claude

The authenticated MCP gateway exposes research lifecycle and retrieval tools. An agent can
start a run, monitor it, answer human checkpoints, inspect evidence, and download:

- `raw`: relevant retained sources, versions, provenance, and passages;
- `result`: synthesized report and audit artifacts;
- `both`: the combined reproducible bundle.

### Telegram

Telegram makes the same service accessible from a phone without exposing database or model
ports. The bot supports duration selection, raw/result/both modes, status, cancellation, and
optional HITL checkpoints.

### Operations console

The console shows who submitted a request, queue and worker state, current pipeline stage,
coverage signals, connector behavior, accepted sources, logs, and downloadable artifacts.
It also provides controlled start/stop operations during development.

## What the showcase proves

The repository includes three English end-to-end examples:

| Domain | Retained sources | Extracted claims | Claim-audit coverage |
|---|---:|---:|---:|
| Multimodal radiology AI | 37 | 106 | 1.00 |
| Small modular reactors | 9 | 40 | 1.00 |
| Humanoid robots in production | 29 | 58 | 1.00 |

Across the three runs, the system retained 75 source records and extracted 204 claims on the
local workstation.

The runs also demonstrate an important product behavior: a useful report is not relabeled as
fully complete merely because generation ended. All three were delivered as
`completed_incomplete` because at least one strict coverage gate remained unmet. Missing
families, branches, or unresolved claims remain explicit in the coverage and uncertainty
artifacts.

## Current limitations

- Local 4B synthesis quality depends on retrieval and decomposition quality.
- Some connectors are rate-limited or credential-dependent.
- Web acquisition cannot guarantee access to every dynamic or restricted page.
- Coverage metrics are operational estimates, not a proof that every publication on the
  internet was found.
- `completed_incomplete` is common under intentionally strict thresholds.
- The current release is single-tenant; office access is protected by tokens and network
  allow-lists rather than full enterprise RBAC.

These limitations are visible by design. The platform’s central promise is not omniscience;
it is broad collection with honest, reproducible evidence handling.
