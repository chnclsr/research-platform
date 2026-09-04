from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from collections import Counter
from typing import Any

import yaml

from .claim_localization import localize_claim_texts
from .evidence_quality import evidence_quality_gate
from .figure_analysis import FigurePipelineResult, analyze_run_figures
from .language_guard import foreign_sentences, language_matches
from .llm import LLMProvider
from .report_synthesis import SynthesisPackage, build_synthesis_package
from .repository import Repository
from .schemas import CoverageMetrics, ResearchProtocol
from .scoping import LABEL_MAX_LENGTH, slugify
from .storage import ObjectStore
from .word_report import build_word_report


def _csv_bytes(headers: list[str], rows: list[list[Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8-sig")


def _markdown(value: Any, level: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(f"- {_markdown(item, level + 1).replace(chr(10), ' ')}" for item in value)
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            label = str(key).replace("_", " ").strip().title()
            rendered = _markdown(item, level + 1)
            if isinstance(item, (dict, list)):
                lines.append(f"{'#' * min(6, level + 3)} {label}\n\n{rendered}")
            else:
                lines.append(f"**{label}:** {rendered}")
        return "\n\n".join(lines)
    return str(value)


def _summary_heading(language: str) -> str:
    return "Özet" if language.lower().startswith("tr") else "Summary"


# The report's own furniture, which used to be Turkish whatever `report_language` said -- so
# an English report arrived with Turkish headings while a Turkish one leaked English claims.
# Both directions are the same bug seen from opposite ends.
_REPORT_LABELS = {
    "tr": {
        "question": "Araştırma sorusu",
        "thematic": "Tematik kanıt sentezi",
        "uncertainty": "Belirsizlikler ve araştırma boşlukları",
        "appendix_a": "Ek A — Bağımsız kaynaklarla desteklenen atomik bulgular",
        "appendix_b": "Ek B — Tek kaynaklı / doğrulama gerektiren atomik bulgular",
        "appendix_c": "Ek C — Kaynak bazlı literatür dökümü",
        "appendix_c_body": (
            "Araştırmada korunan **{count}** kaynağın tamamı, her kaynağın rolü ve "
            "çıkarılan bulgularıyla `15_literature_inventory.md` dosyasında listelenmiştir."
        ),
        "summary_note": (
            "Kaynak kataloğu, atomik claim kayıtları ve retrieval/coverage ölçümleri teslim "
            "paketinin denetim eklerinde ayrıca korunmuştur."
        ),
        "empty_corpus_note": (
            "**Bu koşuda kaynaklar toplandı ancak kanıt çıkarılamadı.** Aşağıdaki bölümler "
            "bu nedenle boştur. Toplanan kaynaklar ve ham veriler teslim paketinde korunuyor; "
            "koşu olay kaydındaki `empty_synthesis_with_corpus` girdisi zincirin nerede "
            "koptuğunu söylüyor."
        ),
    },
    "en": {
        "question": "Research question",
        "thematic": "Thematic evidence synthesis",
        "uncertainty": "Uncertainties and research gaps",
        "appendix_a": "Appendix A — Atomic findings supported by independent sources",
        "appendix_b": "Appendix B — Single-source / verification-pending atomic findings",
        "appendix_c": "Appendix C — Source-by-source literature inventory",
        "appendix_c_body": (
            "All **{count}** sources retained in this research, with each source's role and "
            "the findings extracted from it, are listed in `15_literature_inventory.md`."
        ),
        "summary_note": (
            "The source catalogue, atomic claim records and retrieval/coverage measurements "
            "are preserved separately in the bundle's audit appendices."
        ),
        "empty_corpus_note": (
            "**This run collected sources but extracted no evidence.** The sections below are "
            "empty for that reason. The sources and raw data are preserved in the bundle; the "
            "`empty_synthesis_with_corpus` entry in the run's event log says where the chain "
            "broke."
        ),
    },
}


def _report_labels(language: str) -> dict[str, str]:
    return _REPORT_LABELS["tr" if language.lower().startswith("tr") else "en"]


def structured_extract_rows(versions: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    """Tables and code the parsers recovered as structure, one record per source.

    Already rendered inline in the passage text; this exists so a consumer that wants the
    grid rather than the markdown does not have to re-parse the prose. Each record also
    names the connector that found the source and the parser that read it -- the two halves
    of how the grid came to exist, and the first thing to check when a table looks wrong.

    Sources whose parse recovered no structure are left out entirely rather than carried as
    empty records.
    """
    rows = []
    for source, version in versions:
        provenance = version.provenance or {}
        tables = provenance.get("tables", [])
        code_blocks = provenance.get("code_blocks", [])
        if not tables and not code_blocks:
            continue
        rows.append(
            {
                "source_id": source.id,
                "source_version_id": version.id,
                "url": source.url,
                "title": source.title,
                "connector_id": source.connector_id,
                "parser_id": provenance.get("parser_id", ""),
                "tables": tables,
                "code_blocks": code_blocks,
            }
        )
    return rows


WORD_REPORT_FALLBACK = "16_research_report.docx"
# What a topic handle may contain once it is part of an object key. `_name_run` already
# produces this shape; anything else has to earn it.
_SAFE_LABEL = re.compile(r"[A-Za-z0-9_]{1,64}")


def word_report_name(label: str | None) -> str:
    """The Word report's file name, derived from the run's topic handle.

    A client can set `ResearchProtocol.label` over the API -- it is validated for length
    only, and `_name_run` returns early when the protocol already carries one, so such a
    label never passes through `slugify`. The name becomes part of the object key
    `runs/{run_id}/{name}`, where `../` would write outside the run's prefix.

    Rather than slugify unconditionally, a label that is already key-safe is kept verbatim:
    `slugify` drops stopwords, so re-running it would turn `ai_in_lung_ct` into
    `ai_lung_ct` and the file would no longer match the handle Telegram prints beside the
    run. Only a label outside the safe shape is forced through it.

    The `16_` prefix stays because bundle members are written in sorted order, and a name
    starting with a letter would sort after every numbered artifact instead of keeping the
    report's place in the reading sequence.
    """
    handle = (label or "").strip()
    if not _SAFE_LABEL.fullmatch(handle):
        handle = slugify(handle, max_length=LABEL_MAX_LENGTH)
    return f"16_{handle}_report.docx" if handle else WORD_REPORT_FALLBACK


def _is_reportable(claim: Any) -> bool:
    """The single reportability gate.

    ADVERSARIAL_REVIEW's evidence grade is deliberately NOT consulted here. A grade that
    silently removed claims would be invisible when it misfired: a report that dropped a
    claim reads exactly like one that never had it. The grade steers the prose instead.
    """
    relevance = float((claim.audit or {}).get("question_relevance", 0.0))
    supporting = int((claim.audit or {}).get("supporting_evidence", 0))
    return claim.status in {"supported", "qualified"} and relevance >= 0.20 and supporting > 0


def appraisal_grade(claim: Any) -> str:
    """The evidence grade, or `değerlendirilmedi` for a run made before appraisal existed."""
    appraisal = (getattr(claim, "audit", None) or {}).get("appraisal") or {}
    return str(appraisal.get("grade") or "değerlendirilmedi")


def _parsing_manifest(versions: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    """How each source was ACTUALLY parsed, for the reproducibility manifest.

    `protocol.parsers` already sits in the manifest, but it records the caller's
    overrides -- a request, not an outcome. It said `{"overrides": {}}` for a run whose
    PDF went through smart_pdf and had 15 of its 43 pages re-extracted by Docling on a
    CUDA device, and nothing in the manifest said so.

    That gap matters more than it looks. `content_hash` is the sha256 of the parsed
    text, and the same PDF does not produce the same text on CPU and on CUDA -- measured
    on a 261-page corpus, 7 pages differ and one loses a whole markdown table. A manifest
    that names the protocol but not the engine and the accelerator cannot be used to
    reproduce the run it describes.

    Only the keys that decide the output are copied. The per-page breakdown stays in
    `13_raw_sources.jsonl`: a manifest answers "what produced this", the raw dump carries
    the audit trail. Keys a parser did not set are dropped rather than written as null,
    so a single-extractor source stays a three-line record.
    """
    kept = (
        "parser_profile", "engine_counts", "engine_devices", "engine_build",
        "engine_version", "router_version", "esik_version", "degraded",
        "duration_ms", "gate_duration_ms", "engine_durations_ms",
    )
    records: list[dict[str, Any]] = []
    for source, version in versions:
        provenance = version.provenance or {}
        parse = provenance.get("parse_provenance") or {}
        record: dict[str, Any] = {
            "source_id": source.id,
            "content_hash": version.content_hash,
            "document_type": provenance.get("document_type"),
            "parser_id": provenance.get("parser_id"),
        }
        record.update({key: parse[key] for key in kept if parse.get(key) is not None})
        records.append(record)
    return records


_SWEPT_SECTION_FIELDS = ("synthesis", "consensus", "disagreements", "implications")


async def sweep_synthesis_package(
    llm: LLMProvider, package: SynthesisPackage, language: str
) -> tuple[SynthesisPackage, dict[str, Any]]:
    """Diagnose language drift without replacing any reader-facing model output."""
    prose = {
        "executive_summary": package.executive_summary,
        "cross_study_assessment": package.cross_study_assessment,
        "conclusion": package.conclusion,
        "uncertainty": package.uncertainty,
    }
    for index, section in enumerate(package.sections):
        for name in _SWEPT_SECTION_FIELDS:
            prose[f"section_{index}_{name}"] = getattr(section, name)
    mismatches = [
        key
        for key, value in prose.items()
        if value and (
            not language_matches(value, language)
            or bool(foreign_sentences(value, language))
        )
    ]
    return package, {
        "mode": "diagnostic_only",
        "checked": len(prose),
        "mismatches": mismatches,
        "rewritten": 0,
        "preserved": len(prose),
    }


async def build_exports(
    run_id: str,
    protocol: ResearchProtocol,
    coverage: CoverageMetrics,
    repo: Repository,
    store: ObjectStore,
    llm: LLMProvider,
) -> list[str]:
    sources = await repo.list_sources(run_id)
    claims = await repo.list_claims(run_id)
    evidence = await repo.list_evidence(run_id)
    evidence_by_claim: dict[str, list[tuple]] = {}
    evidence_by_source: dict[str, list[tuple]] = {}
    for claim, link, source in evidence:
        evidence_by_claim.setdefault(claim.id, []).append((link, source))
        evidence_by_source.setdefault(source.id, []).append((claim, link))

    reportable = [claim for claim in claims if _is_reportable(claim)]
    excluded = [claim for claim in claims if not _is_reportable(claim)]
    ordered_reportable = sorted(
        reportable,
        key=lambda claim: (
            claim.status == "supported",
            claim.importance == "major",
            float((claim.audit or {}).get("question_relevance", 0.0)),
        ),
        reverse=True,
    )
    language_is_turkish = protocol.report_language.lower().startswith("tr")
    # Once per run, for every surface. The claims are English whatever language the run was
    # asked in, and three separate renderers used to reach for `claim.text` directly -- the
    # synthesis fallback, the atomic-findings appendices and the executive summary -- which
    # is how English sentences reached a Turkish report from three different directions.
    claim_texts, claim_language_diagnostics = await localize_claim_texts(
        llm, ordered_reportable, protocol.report_language
    )
    await repo.event(
        run_id, "claim_localization", claim_language_diagnostics
    )
    def claim_display(claim: Any) -> str:
        """The statement as the reader should see it.

        Only for prose a person reads. Evidence matching and the audit records keep
        `claim.text`: the quote was matched against the English statement, and a ledger that
        stored a translation could not be checked against the source it came from.
        """
        return claim_texts.get(str(claim.id), str(getattr(claim, "text", "")))

    synthesis_package = await build_synthesis_package(
        llm=llm,
        # The model reasons over English claims, so it gets the English question; the
        # "write in report language" instruction inside the synthesis handles the output.
        question=protocol.primary_question,
        language=protocol.report_language,
        sources=sources,
        reportable_claims=[] if protocol.output_mode == "raw" else ordered_reportable,
        evidence_by_claim=evidence_by_claim,
        # Matching stays in research-language English; the paired titles are display-only.
        sub_questions=protocol.sub_questions,
        sub_question_titles=protocol.sub_questions_for_report(),
        claim_texts=claim_texts,
        display_question=protocol.question_for_report(),
        coverage=coverage.model_dump(),
    )
    await repo.event(
        run_id,
        "synthesis_generation",
        {
            "generated_by_llm": synthesis_package.generated_by_llm,
            "generation_status": synthesis_package.generation_status,
            "validation_warnings": synthesis_package.validation_warnings,
            "layers": synthesis_package.generation_diagnostics,
            "report_mode": synthesis_package.report_mode,
            "answerability_status": synthesis_package.answerability_status,
            "quality": synthesis_package.quality_diagnostics,
        },
    )
    figure_result = FigurePipelineResult()
    if protocol.output_mode != "raw":
        figure_result = await analyze_run_figures(
            run_id=run_id,
            question=protocol.primary_question,
            language=protocol.report_language,
            section_titles=[section.title for section in synthesis_package.sections],
            sources=sources,
            repo=repo,
            store=store,
            settings=getattr(llm, "settings", None),
        )
    if protocol.output_mode == "raw":
        synthesis = {
            "executive_summary": (
                "Ham veri modu seçildi; model sentezi çalıştırılmadı."
                if language_is_turkish
                else "Raw mode was selected; model synthesis was not run."
            ),
            "report": (
                "Ham kaynaklar ve pasajlar teslim paketinde sunulmuştur."
                if language_is_turkish
                else "Raw sources and passages are provided in the delivery bundle."
            ),
            "uncertainty": (
                "İddia çıkarımı, denetim ve sentez ham veri modunda bilinçli olarak atlandı."
                if language_is_turkish
                else "Claim extraction, audit, and synthesis were intentionally skipped in raw mode."
            ),
        }
    else:
        # v0.23.0 keeps this hook as a diagnostic surface only. It must return the exact
        # package it received even when the prose is in the wrong language.
        synthesis_package, sweep_diagnostics = await sweep_synthesis_package(
            llm, synthesis_package, protocol.report_language
        )
        await repo.event(run_id, "report_language_sweep", sweep_diagnostics)
        # Derived after the sweep so the markdown and the .docx render the same prose.
        synthesis = {
            "executive_summary": synthesis_package.executive_summary,
            "report": synthesis_package.narrative,
            "uncertainty": synthesis_package.uncertainty,
        }

    def render_findings(selected_claims: list[Any]) -> str:
        findings = []
        for index, claim in enumerate(selected_claims, 1):
            links = [
                (link, source)
                for link, source in evidence_by_claim.get(claim.id, [])
                if evidence_quality_gate(
                    claim.text,
                    link.quote,
                    section_path=(link.location or {}).get("section_path"),
                    source_title=source.title,
                    entailment_score=link.entailment_score,
                )[0]
            ]
            citations = (
                "\n".join(
                    f"- [{source.title}]({source.url}) — {link.location.get('section_path') or 'Document'}, "
                    f"chars {link.location.get('start_char')}–{link.location.get('end_char')} — "
                    f"“{link.quote[:400]}” (entailment={link.entailment_score:.2f})"
                    for link, source in links
                )
                or "- Kaynak pasajı bulunamadı."
            )
            findings.append(
                f"### {index}. {claim_display(claim)}\n\n"
                f"Durum: `{claim.status}` · Kanıt notu: `{appraisal_grade(claim)}` · "
                f"Soru ilgisi: "
                f"`{claim.audit.get('question_relevance', 0):.2f}`\n\n{citations}"
            )
        return "\n\n".join(findings) or "Bu kategoride iddia bulunamadı."

    supported = [claim for claim in reportable if claim.status == "supported"]
    qualified = [claim for claim in reportable if claim.status == "qualified"]
    findings_md = render_findings(supported)
    qualified_md = render_findings(qualified)

    def source_inventory_card(index: int, source: Any) -> str:
        metadata = source.metadata_json or {}
        linked = evidence_by_source.get(source.id, [])
        tier = metadata.get("literature_relevance_tier", "direct")
        scope_role = metadata.get("research_scope_role", "primary_in_scope")
        published = (
            metadata.get("published_at")
            or metadata.get("publication_year")
            or metadata.get("year")
            or "unknown"
        )
        publication_type = (
            metadata.get("subtype")
            or metadata.get("type")
            or metadata.get("publication_type")
            or "unknown"
        )
        abstract = metadata.get("abstract") or metadata.get("snippet") or ""
        if isinstance(abstract, list):
            abstract = " ".join(str(item) for item in abstract)
        abstract = html.unescape(re.sub(r"<[^>]+>", " ", str(abstract)))
        abstract = " ".join(abstract.split())[:700]
        unique_findings: list[str] = []
        seen_claims: set[str] = set()
        for claim, link in linked:
            if claim.id in seen_claims:
                continue
            if not evidence_quality_gate(
                claim.text,
                link.quote,
                section_path=(link.location or {}).get("section_path"),
                source_title=source.title,
                entailment_score=link.entailment_score,
            )[0]:
                continue
            seen_claims.add(claim.id)
            unique_findings.append(
                f"- `{claim.status}` — {claim_display(claim)}  \n"
                f"  Kanıt: “{link.quote[:350]}”"
            )
        finding_text = "\n".join(unique_findings)
        if not finding_text:
            finding_text = (
                f"- Metadata özeti: {abstract}"
                if abstract
                else "- Bu kaynaktan doğrulanmış claim çıkarılmadı; kaynak katalog ve ham veri paketinde korundu."
            )
        return (
            f"### {index}. [{source.title}]({source.url})\n\n"
            f"- Kaynak ailesi: `{source.family}` · Connector: `{source.connector_id}`\n"
            f"- Literatür rolü: `{tier}` · Kapsam rolü: `{scope_role}` · "
            f"Yayın tarihi: `{published}` · Tür: `{publication_type}`\n"
            f"- Kalıcı kimlik: `{source.persistent_id or 'yok'}`\n"
            f"- Discovery relevance: `{float(metadata.get('relevance_score', 0.0)):.2f}` · "
            f"İçerik relevance: `{float(metadata.get('content_relevance_score', 0.0)):.2f}`\n\n"
            f"**Bu kaynak ne söylüyor?**\n\n{finding_text}"
        )

    literature_inventory_md = (
        "# Kaynak Bazlı Literatür Envanteri\n\n"
        f"Toplam korunan kaynak: **{len(sources)}**. Bu dosya yalnız nihai sentezde seçilen "
        "kaynakları değil, araştırma kapsamında kabul edilen bütün kaynakları listeler. "
        "`contextual` kaynaklar kesin kanıt sayılmadan literatür haritasında korunur.\n\n"
        + (
            "\n\n".join(
                source_inventory_card(index, source)
                for index, source in enumerate(sources, 1)
            )
            or "Kabul edilen kaynak bulunamadı."
        )
        + "\n"
    )
    summary_heading = _summary_heading(protocol.report_language)
    labels = _report_labels(protocol.report_language)
    # Sources but no claims is a contradiction, and the report used to present it as an
    # ordinary short document. The reader is told instead of left to wonder.
    empty_corpus = bool(sources) and not reportable
    corpus_note = f"> {labels['empty_corpus_note']}\n\n" if empty_corpus else ""
    answerability_appendix_note = (
        (
            "> Bu iddialar izlenebilirlik için korunmuştur; düşük soru ilgileri nedeniyle "
            "ana yanıta dahil edilmemiştir.\n\n"
            if language_is_turkish
            else "> These claims are retained for traceability; their low question relevance "
            "kept them out of the main answer.\n\n"
        )
        if synthesis_package.answerability_status == "insufficient"
        else ""
    )
    thematic_block = (
        f"## {labels['thematic']}\n\n{_markdown(synthesis.get('report'))}\n\n"
        if synthesis.get("report")
        else ""
    )
    warning_codes = sorted(
        {
            warning
            for warnings in synthesis_package.validation_warnings.values()
            for warning in warnings
        }
    )
    validation_note = (
        (
            "> ⚠ LLM metni doğrulama uyarılarıyla birlikte özgün biçimde korunmuştur: "
            if language_is_turkish
            else "> ⚠ The original LLM text is preserved with validation warnings: "
        )
        + ", ".join(warning_codes)
        + "\n\n"
        if warning_codes
        else ""
    )
    near_scope_sources = [
        source
        for source in sources
        if (source.metadata_json or {}).get("research_scope_role")
        in {"near_scope", "excluded"}
    ]
    near_scope_block = ""
    if near_scope_sources:
        heading = (
            "## Yakın ama kapsam dışı çalışmalar"
            if language_is_turkish
            else "## Near-scope but excluded studies"
        )
        rows = "\n".join(
            f"- [{source.title}]({source.url}) — "
            f"`{(source.metadata_json or {}).get('research_scope_role')}`"
            for source in near_scope_sources
        )
        near_scope_block = f"{heading}\n\n{rows}\n\n"
    report_md = (
        f"# {protocol.title}\n\n"
        f"{corpus_note}"
        f"## {labels['question']}\n\n{protocol.question_for_report()}\n\n"
        f"{near_scope_block}"
        f"## {summary_heading}\n\n{validation_note}{_markdown(synthesis.get('executive_summary'))}\n\n"
        f"{thematic_block}"
        f"## {labels['uncertainty']}\n\n"
        f"{_markdown(synthesis.get('uncertainty'))}\n\n"
        f"## {labels['appendix_a']}\n\n{answerability_appendix_note}{findings_md}\n\n"
        f"## {labels['appendix_b']}\n\n{answerability_appendix_note}{qualified_md}\n\n"
        f"## {labels['appendix_c']}\n\n"
        f"{labels['appendix_c_body'].format(count=len(sources))}\n"
    )
    executive_md = (
        f"# {summary_heading}\n\n"
        f"{corpus_note}"
        f"{validation_note}{_markdown(synthesis.get('executive_summary'))}\n\n"
        f"{labels['summary_note']}\n"
    )

    files: dict[str, tuple[str, bytes]] = {}
    files["01_executive_summary.md"] = ("text/markdown", executive_md.encode("utf-8"))
    files["02_full_research_report.md"] = ("text/markdown", report_md.encode("utf-8"))
    files["03_evidence_matrix.csv"] = (
        "text/csv",
        _csv_bytes(
            [
                "claim_id",
                "claim",
                "status",
                "question_relevance",
                "direction",
                "quote",
                "source_title",
                "source_url",
                "section_path",
                "page_number",
                "start_char",
                "end_char",
                "passage_id",
                "retrieval_score",
                "entailment",
            ],
            [
                [
                    c.id,
                    c.text,
                    c.status,
                    c.audit.get("question_relevance", 0),
                    e.direction,
                    e.quote,
                    s.title,
                    s.url,
                    e.location.get("section_path"),
                    e.location.get("page_number"),
                    e.location.get("start_char"),
                    e.location.get("end_char"),
                    e.location.get("passage_id"),
                    e.location.get("retrieval_score"),
                    e.entailment_score,
                ]
                for c, e, s in evidence
            ],
        ),
    )
    ledger = []
    for claim in claims:
        links = evidence_by_claim.get(claim.id, [])
        ledger.append(
            json.dumps(
                {
                    "claim_id": claim.id,
                    "claim": claim.text,
                    "status": claim.status,
                    "reportable": _is_reportable(claim),
                    "confidence": claim.confidence,
                    "evidence": [
                        {
                            "source_id": s.id,
                            "url": s.url,
                            "direction": e.direction,
                            "quote": e.quote,
                        }
                        for e, s in links
                    ],
                    "audit": claim.audit,
                },
                ensure_ascii=False,
            )
        )
    files["04_claim_ledger.jsonl"] = (
        "application/x-ndjson",
        ("\n".join(ledger) + "\n").encode("utf-8"),
    )
    files["05_source_catalog.csv"] = (
        "text/csv",
        _csv_bytes(
            [
                "source_id", "family", "connector", "title", "url", "persistent_id",
                "literature_role", "scope_role", "published_at", "discovery_relevance",
                "content_relevance", "evidence_claims", "reportable_claims",
            ],
            [
                [
                    s.id,
                    s.family,
                    s.connector_id,
                    s.title,
                    s.url,
                    s.persistent_id,
                    (s.metadata_json or {}).get("literature_relevance_tier", "direct"),
                    (s.metadata_json or {}).get("research_scope_role", "primary_in_scope"),
                    (s.metadata_json or {}).get("published_at"),
                    (s.metadata_json or {}).get("relevance_score", 0),
                    (s.metadata_json or {}).get("content_relevance_score", 0),
                    len({claim.id for claim, _ in evidence_by_source.get(s.id, [])}),
                    len({
                        claim.id
                        for claim, _ in evidence_by_source.get(s.id, [])
                        if _is_reportable(claim)
                    }),
                ]
                for s in sources
            ],
        ),
    )
    contradictions = [
        c for c, e, _ in evidence if e.direction == "contradicts" and _is_reportable(c)
    ]
    files["06_contradiction_map.md"] = (
        "text/markdown",
        (
            "# Çelişki Haritası\n\n"
            + ("\n".join(f"- {c.text}" for c in contradictions) or "Çelişki adayı bulunamadı.")
            + "\n"
        ).encode("utf-8"),
    )
    family_counts = Counter(s.family for s in sources)
    coverage_md = "# Kapsam Raporu\n\n" + yaml.safe_dump(
        {
            "metrics": coverage.model_dump(),
            "source_families": dict(family_counts),
            "reportable_claims": len(reportable),
            "excluded_claims": len(excluded),
        },
        allow_unicode=True,
        sort_keys=False,
    )
    files["07_coverage_report.md"] = ("text/markdown", coverage_md.encode("utf-8"))
    bib = [
        f"@misc{{SRC{i:04d},\n  title = {{{source.title}}},\n  url = {{{source.url}}}\n}}"
        for i, source in enumerate(sources, 1)
    ]
    files["08_bibliography.bib"] = (
        "application/x-bibtex",
        ("\n\n".join(bib) + "\n").encode("utf-8"),
    )
    files["09_search_protocol.yaml"] = (
        "application/yaml",
        yaml.safe_dump(
            protocol.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8"),
    )
    versions = await repo.list_source_versions(run_id)
    manifest = {
        "run_id": run_id,
        "protocol": protocol.model_dump(mode="json"),
        "source_count": len(sources),
        "claim_count": len(claims),
        "reportable_claim_count": len(reportable),
        "excluded_claim_count": len(excluded),
        "source_ids": [s.id for s in sources],
        "parsing": _parsing_manifest(versions),
        "coverage": coverage.model_dump(),
        "synthesis": {
            "generated_by_llm": synthesis_package.generated_by_llm,
            "generation_status": synthesis_package.generation_status,
            "validation_warnings": synthesis_package.validation_warnings,
            "layers": synthesis_package.generation_diagnostics,
            "report_mode": synthesis_package.report_mode,
            "answerability_status": synthesis_package.answerability_status,
            "quality": synthesis_package.quality_diagnostics,
        },
    }
    files["10_reproducibility_manifest.json"] = (
        "application/json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    unaudited = [claim for claim in claims if not claim.audit]
    irrelevant = [claim for claim in claims if claim.status == "irrelevant"]
    appraisals = [
        (claim.audit or {}).get("appraisal") for claim in claims if (claim.audit or {}).get("appraisal")
    ]
    grade_counts = Counter(str(item.get("grade", "")) for item in appraisals)
    tiers = {str(item.get("tier", "")) for item in appraisals} - {""}
    reason_counts = Counter(
        reason for item in appraisals for reason in (item.get("reasons") or [])
    )
    appraisal_md = ""
    if appraisals:
        grades = "".join(
            f"- {grade}: {count}\n"
            for grade, count in sorted(grade_counts.items(), key=lambda row: -row[1])
        )
        reasons = "".join(
            f"- {reason}: {count}\n" for reason, count in reason_counts.most_common(10)
        ) or "- Not düşüren gerekçe yok.\n"
        appraisal_md = (
            "\n## Kanıt değerlendirmesi\n\n"
            f"Katman: `{', '.join(sorted(tiers)) or 'bilinmiyor'}`\n\n"
            f"{grades}\n### Not düşüren gerekçeler\n\n{reasons}"
        )
    audit_md = (
        "# Denetim Raporu\n\n"
        f"- Toplam iddia: {len(claims)}\n"
        f"- Raporlanabilir: {len(reportable)}\n"
        f"- Tek kaynaklı/qualified: {len(qualified)}\n"
        f"- Sentezden dışlanan: {len(excluded)}\n"
        f"- İlgisiz: {len(irrelevant)}\n"
        f"- Denetlenmemiş: {len(unaudited)}\n"
        f"{appraisal_md}"
    )
    files["11_audit_report.md"] = ("text/markdown", audit_md.encode("utf-8"))
    excluded_md = (
        "\n".join(
            f"- `{claim.status}` · relevance={claim.audit.get('question_relevance', 0):.2f} — {claim.text}"
            for claim in excluded
        )
        or "- Dışlanan iddia yok."
    )
    qualified_uncertainty = (
        "\n".join(f"- {claim_display(claim)}" for claim in qualified) or "- Tek kaynaklı iddia yok."
    )
    uncertainty_md = (
        "# Belirsizlik Raporu\n\n"
        f"{_markdown(synthesis.get('uncertainty'))}\n\n"
        f"## Bağımsız doğrulama gereken iddialar\n\n{qualified_uncertainty}\n\n"
        f"## Sentez dışında bırakılan iddialar\n\n{excluded_md}\n"
    )
    files["12_uncertainty_report.md"] = ("text/markdown", uncertainty_md.encode("utf-8"))

    raw_source_lines = []
    for source, version in versions:
        raw_source_lines.append(
            json.dumps(
                {
                    "source": {
                        "id": source.id,
                        "family": source.family,
                        "connector_id": source.connector_id,
                        "title": source.title,
                        "url": source.url,
                        "persistent_id": source.persistent_id,
                        "metadata": source.metadata_json,
                    },
                    "version": {
                        "id": version.id,
                        "content_hash": version.content_hash,
                        "acquisition_method": version.acquisition_method,
                        "access_status": version.access_status,
                        "retrieved_at": version.retrieved_at.isoformat(),
                        "provenance": version.provenance,
                        "content": version.content,
                        "raw_content": version.raw_content,
                    },
                },
                ensure_ascii=False,
            )
        )
    files["13_raw_sources.jsonl"] = (
        "application/x-ndjson",
        ("\n".join(raw_source_lines) + ("\n" if raw_source_lines else "")).encode("utf-8"),
    )

    passages = await repo.list_passages(run_id)
    raw_passage_lines = [
        json.dumps(passage.model_dump(mode="json"), ensure_ascii=False) for passage in passages
    ]
    files["14_raw_passages.jsonl"] = (
        "application/x-ndjson",
        ("\n".join(raw_passage_lines) + ("\n" if raw_passage_lines else "")).encode("utf-8"),
    )
    files["15_literature_inventory.md"] = (
        "text/markdown",
        literature_inventory_md.encode("utf-8"),
    )
    structured_extracts = structured_extract_rows(versions)
    if structured_extracts:
        files["18_structured_extracts.json"] = (
            "application/json",
            json.dumps(structured_extracts, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    if figure_result.observations:
        files["17_figure_observations.json"] = (
            "application/json",
            json.dumps(
                figure_result.manifest(),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )
    # The DOCX is rendered from audited run state and bounded synthesis
    # sections. A model-selected source figure may enter as a tightly cropped,
    # attributed internal-review excerpt; deterministic reconstruction remains
    # the fallback when a safe crop is unavailable.
    word_report = build_word_report(
        run_id=run_id,
        title=protocol.title,
        # Printed in the document, so it follows the report language rather than the
        # English wording the research side used.
        question=protocol.question_for_report(),
        language=protocol.report_language,
        coverage=coverage.model_dump(),
        sources=sources,
        claims=claims,
        reportable_claims=ordered_reportable,
        evidence_by_claim=evidence_by_claim,
        executive_summary=str(synthesis.get("executive_summary", "")),
        narrative=_markdown(synthesis.get("report")),
        uncertainty=_markdown(synthesis.get("uncertainty")),
        scope=protocol.scope.model_dump(mode="json"),
        sub_questions=protocol.sub_questions_for_report(),
        connector_ids=protocol.connectors.included_connectors,
        research_mode=protocol.research_mode,
        synthesis_package=synthesis_package,
        figure_observations=figure_result.observations,
        research_figures=figure_result.generated_figures,
    )
    files[word_report_name(protocol.label)] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        word_report.document,
    )
    # Written before the artifacts, so an export that fails while uploading leaves no
    # citation record describing a document nobody received.
    await repo.replace_report_citations(run_id, word_report.citations)
    dropped = Counter(
        str(citation.drop_reason)
        for citation in word_report.citations
        if not citation.cited
    )
    await repo.event(
        run_id,
        "report_citations",
        {
            "sources": len(word_report.citations),
            "cited": sum(citation.cited for citation in word_report.citations),
            "dropped": dict(dropped),
        },
    )
    for figure_name, figure_bytes in word_report.figures.items():
        files[figure_name] = ("image/png", figure_bytes)
    for research_figure in figure_result.generated_figures:
        files[research_figure.name] = ("image/png", research_figure.data)

    existing_artifacts = await repo.list_artifacts(run_id)
    # Artifacts whose name depends on the run itself: a source figure is numbered by how
    # many were selected, and the Word report now carries the topic handle. Exporting a run
    # twice would otherwise leave the previous export's copy behind, and both would land in
    # the bundles.
    run_named = re.compile(r"17[a-z]_source_figure_.*\.png|16_.*\.docx")
    stale = [
        artifact
        for artifact in existing_artifacts
        if run_named.fullmatch(artifact.name) and artifact.name not in files
    ]
    for artifact in stale:
        await store.delete(artifact.object_key)
    await repo.delete_artifacts(run_id, {artifact.name for artifact in stale})

    saved = []
    for name, (media_type, data) in files.items():
        key = f"runs/{run_id}/{name}"
        await store.put(key, data, media_type)
        await repo.save_artifact(run_id, name, media_type, key, len(data))
        saved.append(name)

    raw_names = {
        "05_source_catalog.csv",
        "08_bibliography.bib",
        "09_search_protocol.yaml",
        "10_reproducibility_manifest.json",
        "13_raw_sources.jsonl",
        "14_raw_passages.jsonl",
        "15_literature_inventory.md",
    }
    result_names = set(files) - {"13_raw_sources.jsonl", "14_raw_passages.jsonl"}
    bundle_specs = {
        "raw_bundle.zip": raw_names,
        "result_bundle.zip": result_names,
        "research_bundle.zip": set(files),
    }
    bundle_names = []
    for bundle_name, selected_names in bundle_specs.items():
        archive_stream = io.BytesIO()
        with zipfile.ZipFile(archive_stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(selected_names):
                _, data = files[name]
                archive.writestr(name, data)
        bundle = archive_stream.getvalue()
        bundle_key = f"runs/{run_id}/{bundle_name}"
        await store.put(bundle_key, bundle, "application/zip")
        await repo.save_artifact(run_id, bundle_name, "application/zip", bundle_key, len(bundle))
        bundle_names.append(bundle_name)
    return [*saved, *bundle_names]
