from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import Counter
from typing import Any

import yaml

from .llm import LLMProvider
from .evidence_quality import evidence_quality_gate
from .repository import Repository
from .schemas import CoverageMetrics, ResearchProtocol
from .storage import ObjectStore


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
    for claim, link, source in evidence:
        evidence_by_claim.setdefault(claim.id, []).append((link, source))

    reportable = [claim for claim in claims if _is_reportable(claim)]
    excluded = [claim for claim in claims if not _is_reportable(claim)]
    context_lines = []
    ordered_reportable = sorted(
        reportable,
        key=lambda claim: (
            claim.status == "supported",
            claim.importance == "major",
            float((claim.audit or {}).get("question_relevance", 0.0)),
        ),
        reverse=True,
    )
    context_char_budget = max(
        8000,
        min(
            50000,
            int(
                getattr(
                    getattr(llm, "settings", None),
                    "llm_context_tokens",
                    8192,
                )
                * 2.5
            ),
        ),
    )
    for claim in ordered_reportable[:60]:
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
        refs = ", ".join(f"{source.title} ({source.url})" for _, source in links)
        quotes = " | ".join(link.quote[:600] for link, _ in links)
        candidate_context = (
            f"CLAIM: {claim.text}\nSTATUS: {claim.status}\n"
            f"QUESTION_RELEVANCE: {claim.audit.get('question_relevance', 0)}\n"
            f"SOURCES: {refs}\nVERIFIED_QUOTES: {quotes}"
        )
        if len("\n\n".join([*context_lines, candidate_context])) > context_char_budget:
            break
        context_lines.append(candidate_context)
    language_is_turkish = protocol.report_language.lower().startswith("tr")
    deterministic_synthesis = {
        "executive_summary": (
            f"Kanıt denetimini geçen {len(reportable)} iddia vardır; bunların "
            f"{sum(claim.status == 'supported' for claim in reportable)} tanesi bağımsız "
            "kaynaklarla desteklenmiştir. Ayrıntılı ve kaynaklı bulgular raporun ilgili "
            "bölümlerindedir."
            if language_is_turkish
            else f"{len(reportable)} claims passed evidence audit; "
            f"{sum(claim.status == 'supported' for claim in reportable)} have independent support. "
            "See the sourced findings for details."
        ),
        "report": (
            "Model sentezi doğrulanabilirlik kapısını geçemediği için yeni yorum eklenmedi; "
            "yalnız denetlenmiş bulgular raporlandı."
            if language_is_turkish
            else "No additional interpretation was added because model synthesis did not pass the "
            "grounding gate; only audited findings are reported."
        ),
        "uncertainty": (
            "Bağımsız destek, karşı kanıt ve kapsam eksikleri belirsizlik raporunda gösterilmiştir."
            if language_is_turkish
            else "Independent support, counterevidence, and coverage gaps are listed in the uncertainty report."
        ),
    }
    if protocol.output_mode == "raw":
        synthesis = {
            "executive_summary": "Ham veri modu seçildi; model sentezi çalıştırılmadı.",
            "report": "Ham kaynaklar ve pasajlar teslim paketinde sunulmuştur.",
            "uncertainty": (
                "İddia çıkarımı, denetim ve sentez ham veri modunda bilinçli olarak atlandı."
            ),
        }
    elif not context_lines:
        synthesis = {
            "executive_summary": (
                "Denetim kapısından geçen raporlanabilir iddia bulunamadı. "
                "Sistem, doğrulanmamış sonuç üretmek yerine araştırmayı eksik olarak teslim etti."
                if language_is_turkish
                else "No reportable claim passed the evidence audit. The system returned an incomplete "
                "research result instead of generating an unverified conclusion."
            ),
            "report": (
                "Doğrulanmış kanıt bulunmadığından model sentezi çalıştırılmadı."
                if language_is_turkish
                else "Model synthesis was skipped because no verified evidence was available."
            ),
            "uncertainty": (
                "Kaynak ve kapsam eksikleri coverage ve belirsizlik raporlarında listelenmiştir."
                if language_is_turkish
                else "Source and coverage gaps are listed in the coverage and uncertainty reports."
            ),
        }
    else:
        try:
            synthesis = await llm.complete_json(
                "Create concise JSON with executive_summary, report, and uncertainty. Use only the supplied "
                "claims and VERIFIED_QUOTES, distinguish supported from qualified findings, retain source URLs, "
                f"write every value in report language '{protocol.report_language}', and never add facts. "
                "Follow the user's outline guidance when it does not conflict with evidence safety.",
                f"QUESTION: {protocol.primary_question}\n"
                f"OUTLINE_GUIDANCE: {outline_guidance or 'Use the default audited structure.'}\n\n"
                + "\n\n".join(context_lines),
            )
            if not isinstance(synthesis, dict):
                synthesis = {"report": synthesis}
            synthesis_blob = json.dumps(synthesis, ensure_ascii=False)
            allowed_urls = {
                source.url
                for claim in ordered_reportable
                for _, source in evidence_by_claim.get(claim.id, [])
            }
            output_urls = set(re.findall(r"https?://[^\s)\]>]+", synthesis_blob))
            english_markers = len(
                re.findall(
                    r"\b(?:the|and|with|from|this|study|claim|source|evidence)\b",
                    synthesis_blob,
                    flags=re.IGNORECASE,
                )
            )
            turkish_markers = len(
                re.findall(
                    r"\b(?:ve|ile|bu|bir|çalışma|iddia|kaynak|kanıt|ancak)\b",
                    synthesis_blob,
                    flags=re.IGNORECASE,
                )
            )
            if output_urls - allowed_urls or (
                language_is_turkish and english_markers > max(2, turkish_markers)
            ):
                synthesis = deterministic_synthesis
        except Exception as exc:
            synthesis = dict(deterministic_synthesis)
            synthesis["uncertainty"] += f" LLM synthesis unavailable: {type(exc).__name__}."

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
    report_md = (
        f"# {protocol.title}\n\n"
        f"## Araştırma sorusu\n\n{protocol.primary_question}\n\n"
        f"## Bağımsız kaynaklarla desteklenen bulgular\n\n{findings_md}\n\n"
        f"## Tek kaynaklı / doğrulama gerektiren bulgular\n\n{qualified_md}\n\n"
        f"## Model sentezi\n\n{_markdown(synthesis.get('report'))}\n"
    )
    executive_md = (
        "# Yönetici Özeti\n\n"
        f"Raporlanabilir iddia: {len(reportable)} · Dışlanan/zayıf iddia: {len(excluded)}\n\n"
        f"{_markdown(synthesis.get('executive_summary'))}\n"
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
            ["source_id", "family", "connector", "title", "url", "persistent_id", "relevance"],
            [
                [
                    s.id,
                    s.family,
                    s.connector_id,
                    s.title,
                    s.url,
                    s.persistent_id,
                    (s.metadata_json or {}).get("relevance_score", 0),
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
