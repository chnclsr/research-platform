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

from .llm import LLMProvider
from .evidence_quality import evidence_quality_gate
from .figure_analysis import FigurePipelineResult, analyze_run_figures
from .repository import Repository
from .report_synthesis import build_synthesis_package
from .schemas import CoverageMetrics, ResearchProtocol
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


def _is_reportable(claim: Any) -> bool:
    relevance = float((claim.audit or {}).get("question_relevance", 0.0))
    supporting = int((claim.audit or {}).get("supporting_evidence", 0))
    return claim.status in {"supported", "qualified"} and relevance >= 0.20 and supporting > 0


async def build_exports(
    run_id: str,
    protocol: ResearchProtocol,
    coverage: CoverageMetrics,
    repo: Repository,
    store: ObjectStore,
    llm: LLMProvider,
    *,
    outline_guidance: str = "",
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
    synthesis_package = await build_synthesis_package(
        llm=llm,
        # The model reasons over English claims, so it gets the English question; the
        # "write in report language" instruction inside the synthesis handles the output.
        question=protocol.primary_question,
        language=protocol.report_language,
        sources=sources,
        reportable_claims=[] if protocol.output_mode == "raw" else ordered_reportable,
        evidence_by_claim=evidence_by_claim,
        # Sub-questions become section headings in the report, so these are printed text.
        sub_questions=protocol.sub_questions_for_report(),
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
                f"### {index}. {claim.text}\n\n"
                f"Durum: `{claim.status}` · Soru ilgisi: "
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
                f"- `{claim.status}` — {claim.text}  \n"
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
            f"- Literatür rolü: `{tier}` · Yayın tarihi: `{published}` · Tür: `{publication_type}`\n"
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
    report_md = (
        f"# {protocol.title}\n\n"
        f"## Araştırma sorusu\n\n{protocol.question_for_report()}\n\n"
        f"## Yönetici sentezi\n\n{_markdown(synthesis.get('executive_summary'))}\n\n"
        f"## Tematik kanıt sentezi\n\n{_markdown(synthesis.get('report'))}\n\n"
        f"## Belirsizlikler ve araştırma boşlukları\n\n"
        f"{_markdown(synthesis.get('uncertainty'))}\n\n"
        f"## Ek A — Bağımsız kaynaklarla desteklenen atomik bulgular\n\n{findings_md}\n\n"
        f"## Ek B — Tek kaynaklı / doğrulama gerektiren atomik bulgular\n\n{qualified_md}\n\n"
        f"## Ek C — Kaynak bazlı literatür dökümü\n\n"
        f"Araştırmada korunan **{len(sources)}** kaynağın tamamı, her kaynağın rolü ve "
        "çıkarılan bulgularıyla `15_literature_inventory.md` dosyasında listelenmiştir.\n"
    )
    executive_md = (
        "# Yönetici Özeti\n\n"
        f"{_markdown(synthesis.get('executive_summary'))}\n\n"
        "Kaynak kataloğu, atomik claim kayıtları ve retrieval/coverage ölçümleri teslim "
        "paketinin denetim eklerinde ayrıca korunmuştur.\n"
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
                "literature_role", "published_at", "discovery_relevance",
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
    manifest = {
        "run_id": run_id,
        "protocol": protocol.model_dump(mode="json"),
        "source_count": len(sources),
        "claim_count": len(claims),
        "reportable_claim_count": len(reportable),
        "excluded_claim_count": len(excluded),
        "source_ids": [s.id for s in sources],
        "coverage": coverage.model_dump(),
    }
    files["10_reproducibility_manifest.json"] = (
        "application/json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    unaudited = [claim for claim in claims if not claim.audit]
    irrelevant = [claim for claim in claims if claim.status == "irrelevant"]
    audit_md = (
        "# Denetim Raporu\n\n"
        f"- Toplam iddia: {len(claims)}\n"
        f"- Raporlanabilir: {len(reportable)}\n"
        f"- Tek kaynaklı/qualified: {len(qualified)}\n"
        f"- Sentezden dışlanan: {len(excluded)}\n"
        f"- İlgisiz: {len(irrelevant)}\n"
        f"- Denetlenmemiş: {len(unaudited)}\n"
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
        "\n".join(f"- {claim.text}" for claim in qualified) or "- Tek kaynaklı iddia yok."
    )
    uncertainty_md = (
        "# Belirsizlik Raporu\n\n"
        f"{_markdown(synthesis.get('uncertainty'))}\n\n"
        f"## Bağımsız doğrulama gereken iddialar\n\n{qualified_uncertainty}\n\n"
        f"## Sentez dışında bırakılan iddialar\n\n{excluded_md}\n"
    )
    files["12_uncertainty_report.md"] = ("text/markdown", uncertainty_md.encode("utf-8"))

    versions = await repo.list_source_versions(run_id)
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
    # Tables and code the parsers recovered as structure. They are already rendered inline
    # in the passage text; this artifact exists so a consumer that wants the grid rather
    # than the markdown does not have to re-parse the prose.
    structured_extracts = [
        {
            "source_id": source.id,
            "source_version_id": version.id,
            "url": source.url,
            "title": source.title,
            "parser_id": (version.provenance or {}).get("parser_id", ""),
            "tables": (version.provenance or {}).get("tables", []),
            "code_blocks": (version.provenance or {}).get("code_blocks", []),
        }
        for source, version in versions
        if (version.provenance or {}).get("tables")
        or (version.provenance or {}).get("code_blocks")
    ]
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
    files["16_research_report.docx"] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        word_report.document,
    )
    for figure_name, figure_bytes in word_report.figures.items():
        files[figure_name] = ("image/png", figure_bytes)
    for research_figure in figure_result.generated_figures:
        files[research_figure.name] = ("image/png", research_figure.data)

    existing_artifacts = await repo.list_artifacts(run_id)
    current_figure_names = {
        name
        for name in files
        if re.fullmatch(r"17[a-z]_source_figure_.*\.png", name)
    }
    stale_figures = [
        artifact
        for artifact in existing_artifacts
        if re.fullmatch(r"17[a-z]_source_figure_.*\.png", artifact.name)
        and artifact.name not in current_figure_names
    ]
    for artifact in stale_figures:
        await store.delete(artifact.object_key)
    await repo.delete_artifacts(run_id, {artifact.name for artifact in stale_figures})

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
