from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any

STRATEGY_LABELS = {
    "row_commit_each": "Satır başına commit",
    "row_add_one_transaction": "Satır ekle, tek transaction",
    "orm_add_all": "ORM add_all",
    "core_executemany": "Core executemany",
    "core_upsert_batched": "Batch upsert (ON CONFLICT)",
    "copy_records": "COPY",
    "repository_save_passages": "Repository save_passages",
    "vector_executemany": "pgvector executemany",
    "core_upsert_batched_reingest": "Batch upsert, re-ingest",
    "repository_save_passages_reingest": "Repository save_passages, re-ingest",
}
COLORS = [
    "#2563eb",
    "#059669",
    "#7c3aed",
    "#ea580c",
    "#0891b2",
    "#65a30d",
    "#dc2626",
    "#db2777",
]
VECTOR_STRATEGIES = frozenset({"vector_executemany"})
# Arms that write into a table already holding these chunks. They measure the UPDATE
# branch, so they do not belong in the same bar group or baseline as the insert arms.
REINGEST_PAIR = ("core_upsert_batched_reingest", "repository_save_passages_reingest")


def is_reingest(item: dict[str, Any]) -> bool:
    return bool(item.get("preseeded"))


def unstable_baseline_sizes(payload: dict[str, Any]) -> list[int]:
    """Sizes where the repository baseline splits into two clusters rather than scattering.

    A wide spread alone is not the problem; a wide spread is still summarised honestly by
    a median. The problem is two separated clusters, where the median lands wherever the
    split falls. So the test is whether one gap dominates the whole range, not how far
    the extremes are apart.
    """
    unstable = []
    for dataset in payload["datasets"]:
        low, high = baseline_clusters(payload, dataset["row_count"])
        if len(low) < 2 or len(high) < 2:
            continue
        spread = high[-1] - low[0]
        if spread and (high[0] - low[-1]) / spread >= 0.5:
            unstable.append(dataset["row_count"])
    return unstable


def baseline_clusters(payload: dict[str, Any], row_count: int) -> tuple[list[float], list[float]]:
    """Split the baseline's runs at its widest gap, which is where the two modes sit."""
    dataset = next(item for item in payload["datasets"] if item["row_count"] == row_count)
    baseline = next(
        item for item in dataset["configurations"] if item["strategy"] == "repository_save_passages"
    )
    values = sorted(run["wall_ms"] for run in baseline["runs"] if run["success"])
    gaps = [(values[index + 1] - values[index], index) for index in range(len(values) - 1)]
    split = max(gaps)[1] + 1
    return values[:split], values[split:]


def path_label(item: dict[str, Any]) -> str:
    return "Re-ingest" if is_reingest(item) else "Insert"


def variant_label(item: dict[str, Any]) -> str:
    return "pgvector" if item["strategy"] in VECTOR_STRATEGIES else "JSONB"


def configurations(payload: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    return [
        (dataset["row_count"], configuration)
        for dataset in payload["datasets"]
        for configuration in dataset["configurations"]
    ]


def grouped_bar_svg(
    payload: dict[str, Any],
    *,
    metric: str,
    title: str,
    y_label: str,
    value_scale: float = 1.0,
) -> str:
    width, height = 1180, 620
    left, right, top, bottom = 105, 35, 75, 145
    plot_width = width - left - right
    plot_height = height - top - bottom
    datasets = [
        {
            **dataset,
            "configurations": [item for item in dataset["configurations"] if not is_reingest(item)],
        }
        for dataset in payload["datasets"]
    ]
    strategies = [item["strategy"] for item in datasets[0]["configurations"]]
    values = [
        float(item[metric]) / value_scale
        for dataset in datasets
        for item in dataset["configurations"]
    ]
    maximum = max(values) * 1.12 if values else 1.0
    group_width = plot_width / len(datasets)
    bar_width = group_width * 0.78 / len(strategies)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        (
            "<style>text{font-family:DejaVu Sans,Arial,sans-serif;fill:#172033}"
            ".title{font-size:24px;font-weight:700}.axis{font-size:13px}"
            ".value{font-size:11px}.legend{font-size:12px}</style>"
        ),
        (
            f'<text x="{width / 2}" y="38" text-anchor="middle" class="title">'
            f"{html.escape(title)}</text>"
        ),
    ]
    for tick in range(6):
        value = maximum * tick / 5
        y = top + plot_height - plot_height * tick / 5
        parts.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" '
            'stroke="#d7dde8" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" class="axis">'
            f"{value:,.1f}</text>"
        )
    for group_index, dataset in enumerate(datasets):
        group_x = left + group_index * group_width + group_width * 0.11
        for strategy_index, item in enumerate(dataset["configurations"]):
            value = float(item[metric]) / value_scale
            bar_height = plot_height * value / maximum
            x = group_x + strategy_index * bar_width
            y = top + plot_height - bar_height
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width - 3:.2f}" '
                f'height="{bar_height:.2f}" fill="{COLORS[strategy_index % len(COLORS)]}" rx="2"/>'
            )
            parts.append(
                f'<text x="{x + (bar_width - 3) / 2:.2f}" y="{max(top + 12, y - 5):.2f}" '
                f'text-anchor="middle" class="value">{value:,.1f}</text>'
            )
        parts.append(
            f'<text x="{left + (group_index + 0.5) * group_width:.2f}" '
            f'y="{top + plot_height + 28}" text-anchor="middle" class="axis">'
            f"{dataset['row_count']:,} kayıt</text>"
        )
    parts.append(
        f'<text transform="translate(24 {top + plot_height / 2}) rotate(-90)" '
        f'text-anchor="middle" class="axis">{html.escape(y_label)}</text>'
    )
    per_row = 4
    legend_width = plot_width / per_row
    for index, strategy in enumerate(strategies):
        x = left + (index % per_row) * legend_width
        legend_y = height - 92 + (index // per_row) * 24
        parts.append(
            f'<rect x="{x:.2f}" y="{legend_y}" width="13" height="13" '
            f'fill="{COLORS[index % len(COLORS)]}" rx="2"/>'
        )
        parts.append(
            f'<text x="{x + 18:.2f}" y="{legend_y + 11}" class="legend">'
            f"{html.escape(STRATEGY_LABELS[strategy])}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def speedup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    transformed = {**payload, "datasets": []}
    for dataset in payload["datasets"]:
        baselines = {
            is_reingest(item): item
            for item in dataset["configurations"]
            if item["strategy"] in {"repository_save_passages", "repository_save_passages_reingest"}
        }
        transformed["datasets"].append(
            {
                **dataset,
                "configurations": [
                    {
                        **item,
                        "toast_and_auxiliary_bytes_median": (
                            item["total_relation_bytes_median"]
                            - item["heap_bytes_median"]
                            - item["index_bytes_median"]
                        )
                        if "total_relation_bytes_median" in item
                        else None,
                        "speedup_vs_repository": round(
                            baselines[is_reingest(item)]["wall_ms_median"] / item["wall_ms_median"],
                            3,
                        ),
                    }
                    for item in dataset["configurations"]
                ],
            }
        )
    return transformed


def write_summary_csv(payload: dict[str, Any], output: Path) -> None:
    fieldnames = [
        "row_count",
        "strategy",
        "table",
        "wall_ms_mean",
        "wall_ms_median",
        "wall_ms_min",
        "wall_ms_max",
        "wall_ms_stdev",
        "rows_per_second_median",
        "speedup_vs_row_commit_each",
        "speedup_vs_repository",
        "wal_bytes_median",
        "heap_bytes_median",
        "index_bytes_median",
        "toast_and_auxiliary_bytes_median",
        "total_relation_bytes_median",
        "io_writes_median",
        "io_write_ms_median",
        "io_extends_median",
        "io_extend_ms_median",
        "io_fsyncs_median",
        "io_fsync_ms_median",
        "sql_statement_count_median",
        "executemany_call_count_median",
        "commit_count_median",
        "all_valid",
    ]
    enriched = speedup_payload(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row_count, item in configurations(enriched):
            writer.writerow({"row_count": row_count, **{key: item[key] for key in fieldnames[1:]}})


def by_strategy(dataset: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in dataset["configurations"] if item["strategy"] == name)


def partial_conflict_lines(payload: dict[str, Any]) -> list[str]:
    methodology = payload["methodology"]
    lines = [
        "## Kısmi çakışma: karışık INSERT ve UPDATE yolu",
        "",
        (
            "Her veri setindeki çift indeksli chunk'lar farklı içerikle önceden yazıldı. Ölçülen "
            "çağrı aynı transaction içinde satırların yüzde 50'sini güncelledi ve yüzde 50'sini "
            "ekledi. Ön dolum ve doğrulama süre dışında bırakıldı; iki yöntemin sırası her "
            "tekrarda ters çevrildi."
        ),
        "",
        (
            "| Toplam kayıt | Önceden var | Yeni | Mevcut repository medyan ms | "
            "Aday bulk medyan ms | Hızlanma | Mevcut SQL | Bulk SQL | Geçerli koşu |"
        ),
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset in payload["datasets"]:
        bulk = dataset["strategies"]["bulk_upsert"]
        legacy = dataset["strategies"]["legacy_repository"]
        valid = sum(run["success"] for run in bulk["runs"]) + sum(
            run["success"] for run in legacy["runs"]
        )
        total = len(bulk["runs"]) + len(legacy["runs"])
        lines.append(
            f"| {dataset['row_count']:,} | {dataset['preseeded_rows']:,} | "
            f"{dataset['new_rows']:,} | {legacy['wall_ms_median']:,.3f} | "
            f"{bulk['wall_ms_median']:,.3f} | {bulk['speedup_vs_legacy']:.3f}x | "
            f"{legacy['sql_statement_count_median']:,.0f} | "
            f"{bulk['sql_statement_count_median']:,.0f} | {valid}/{total} |"
        )
    lines += [
        "",
        (
            f"Her hücre {methodology['repeats']} kez ölçüldü ve "
            f"{methodology['warmups']} warm-up yapıldı. Sonuç, farkın yalnız tamamen boş veya "
            "tamamen dolu tabloya özgü olup olmadığını sınar."
        ),
        "",
        "Ham sonuç: `results/postgres_bulk_insert_partial.json`",
        "",
    ]
    return lines


def markdown_report(
    payload: dict[str, Any],
    result_path: Path,
    partial_payload: dict[str, Any] | None = None,
) -> str:
    environment = payload["environment"]
    methodology = payload["methodology"]
    enriched = speedup_payload(payload)
    core_repository_gains = [
        by_strategy(dataset, "core_upsert_batched")["speedup_vs_repository"]
        for dataset in enriched["datasets"]
    ]
    gain_text = ", ".join(f"{gain:.3f}x" for gain in core_repository_gains)
    unstable = unstable_baseline_sizes(payload)
    stable_sizes = [
        dataset["row_count"]
        for dataset in payload["datasets"]
        if dataset["row_count"] not in unstable
    ]
    stable_gain_text = ", ".join(
        f"{by_strategy(dataset, 'core_upsert_batched')['speedup_vs_repository']:.3f}x"
        f" ({dataset['row_count']:,} kayıt)"
        for dataset in enriched["datasets"]
        if dataset["row_count"] in stable_sizes
    )
    stable_partial_text = (
        ", ".join(
            f"{dataset['strategies']['bulk_upsert']['speedup_vs_legacy']:.3f}x"
            for dataset in partial_payload["datasets"]
            if dataset["row_count"] in stable_sizes
        )
        if partial_payload is not None
        else "ayrı deney çalıştırılmadı"
    )
    unstable_note = ""
    unstable_limit_lines: list[str] = []
    if unstable:
        described = []
        for size in unstable:
            low, high = baseline_clusters(payload, size)
            described.append(
                f"{size:,} kayıtta {low[0]:,.0f}-{low[-1]:,.0f} ms ve "
                f"{high[0]:,.0f}-{high[-1]:,.0f} ms"
            )
        unstable_note = (
            "Karşılaştırma tabanı olan mevcut repository yolu "
            f"{', '.join(described)} olmak üzere çift tepeli ölçüldüğü için bu boyut"
            f"{'lar' if len(unstable) > 1 else ''} manşet oranına alınmamıştır. "
        )
        for size in unstable:
            low_cluster, high_cluster = baseline_clusters(payload, size)
            unstable_limit_lines.append(
                f"- {size:,} kayıtta `repository_save_passages` dağılımı çift tepelidir: "
                f"{len(low_cluster)} koşu {min(low_cluster):,.0f}-{max(low_cluster):,.0f} ms, "
                f"{len(high_cluster)} koşu {min(high_cluster):,.0f}-{max(high_cluster):,.0f} ms. "
                "Medyan, bölünmenin nereye denk geldiğine göre kayar; bu boyuttaki hızlanma "
                "oranı bu nedenle nokta tahmini olarak kullanılamaz. Kümelenme koşu sırasıyla "
                "ilişkilendirilemedi ve nedeni belirlenemedi. Daha büyük veri boyutlarında "
                "dağılım tek tepelidir."
            )
    lines = [
        "# PostgreSQL Veritabanı Toplu Yazma Testi",
        "",
        "## Amaç",
        "",
        (
            "Bu deney, passage kayıtlarının satır başına commit edilmesi, tek transaction içinde "
            "yazılması ve toplu yazılması arasındaki süre, throughput, WAL, I/O ve SQL çağrısı "
            "farklarını aynı veri üzerinde ölçer. Ayrıca embedding'in JSONB yerine native pgvector "
            "sütununda tutulmasının yazma maliyetine etkisini karşılaştırır."
        ),
        "",
        "## Kısa sonuç",
        "",
        (
            f"Aday batch upsert, mevcut repository yoluna göre {stable_gain_text} hızlandı. "
            f"Yüzde 50 çakışmalı ek deneyde aynı boyutlarda hızlanma {stable_partial_text} oldu. "
            f"{unstable_note}Ana matriste 300/300, ek matriste 60/60 koşu veri bütünlüğü "
            "doğrulamasını geçti. Ölçümlerin tamamı üretim kodu değiştirilmeden alınmıştır; "
            "ölçülen aday yöntemin `Repository.save_passages` içine uygulanması ayrı bir "
            "değişikliktir ve kendi testleriyle birlikte sunulmaktadır."
        ),
        "",
        "## Test edilen mimari",
        "",
        (
            f"Üretimdeki `PassageRow.embedding` alanı PostgreSQL `JSONB` olarak tutulmaktadır ve "
            f"kolların çoğu bu şema üzerinde çalışır. Karşılaştırma için aynı sütunları taşıyan, "
            f"yalnızca embedding tipi `vector({methodology['embedding_dimensions']})` olan "
            f"`{methodology['vector_storage'].split()[-1]}` tablosu oluşturulmuş ve tek bir kol bu "
            f"tabloya yazmıştır. İki tablo aynı birincil anahtar, aynı tekillik kısıtı ve aynı "
            f"yardımcı indeksleri taşır, böylece aradaki tek değişken embedding tipidir."
        ),
        "",
        "## Deney ortamı",
        "",
        "| Alan | Değer |",
        "|---|---|",
        f"| Test tarihi (UTC) | {payload['generated_at']} |",
        f"| İşletim sistemi | {environment['operating_system']} |",
        f"| CPU | {environment['cpu_model']} |",
        (
            f"| Çekirdek | {environment['physical_cpu_count']} fiziksel, "
            f"{environment['logical_cpu_count']} mantıksal |"
        ),
        f"| RAM | {environment['ram_bytes'] / 1024**3:.1f} GiB |",
        f"| Python | {environment['python']} |",
        f"| PostgreSQL | {environment['postgresql'].split(' on ')[0]} |",
        f"| SQLAlchemy | {environment['sqlalchemy']} |",
        f"| asyncpg | {environment['asyncpg']} |",
        f"| Docker | {environment['docker']} |",
        f"| Docker Compose | {environment['docker_compose']} |",
        f"| Container image | `{environment['container_image']}` |",
        f"| Benchmark taban commit'i | `{environment['benchmark_commit']}` |",
        (
            f"| Ölçüm sırasında çalışma ağacı | "
            f"{'Değişiklik içeriyordu' if environment['benchmark_git_dirty'] else 'Temizdi'} |"
        ),
        f"| İzole hedef | `127.0.0.1:{environment['host_port']}/{environment['database']}` |",
        "",
        "Sonuçlar bu makinenin CPU, disk, kernel, Docker ve PostgreSQL koşullarına özeldir.",
        "",
        "## Karşılaştırılan yöntemler",
        "",
        "1. `row_commit_each`: Her satır için INSERT ve commit.",
        "2. `row_add_one_transaction`: ORM satır eklemeleri, tek transaction ve commit.",
        "3. `orm_add_all`: SQLAlchemy `add_all`, tek transaction ve commit.",
        "4. `core_executemany`: SQLAlchemy Core executemany, tek transaction ve commit.",
        (
            f"5. `core_upsert_batched`: `INSERT ... ON CONFLICT DO UPDATE`, "
            f"{methodology['upsert_batch']:,} satırlık batch'ler, tek transaction ve commit. "
            f"Repository ile aynı idempotent semantiği taşıyan tek bulk yöntem."
        ),
        "6. `copy_records`: asyncpg `copy_records_to_table` ile PostgreSQL COPY protokolü.",
        (
            "7. `repository_save_passages`: Mevcut repository yöntemi; her passage için varlık "
            "sorgusu, ORM yazımı ve sonda tek commit."
        ),
        (
            "8. `vector_executemany`: 4. yöntemle aynı statement şekli, ama native pgvector "
            "sütununa yazar. Şema karşılaştırması içindir, yöntem karşılaştırması değil."
        ),
        (
            "9. `core_upsert_batched_reingest`: 5. yöntemle aynı kod, ama tablo bu chunk'ları "
            "zaten tutarken çalışır. Upsert'in UPDATE dalını ölçer."
        ),
        (
            "10. `repository_save_passages_reingest`: 7. yöntemle aynı kod, aynı dolu tablo "
            "üzerinde. 9. yöntemin karşılaştırma tabanı budur."
        ),
        "",
        "## Veri seti ve ölçüm yöntemi",
        "",
        (
            f"Kayıt sayıları {', '.join(f'{size:,}' for size in methodology['sizes'])}; her kayıt "
            f"{methodology['text_chars']} metin karakteri ve "
            f"{methodology['embedding_dimensions']} elemanlı embedding içerir. Her veri boyutu ve "
            f"yöntem için {methodology['warmups']} warm-up ile {methodology['repeats']} ölçüm "
            "tekrarı yapılmıştır. Süre yalnızca yazma yöntemini ve commit işlemini kapsar; "
            "TRUNCATE, checkpoint, istatistik sorguları ve doğrulama ölçüm dışındadır."
        ),
        "",
        "## Adil karşılaştırma önlemleri",
        "",
        "- Her yöntem ve boyutta aynı deterministik passage ve embedding verisi kullanıldı.",
        (
            "- Her koşudan önce her iki tablo da TRUNCATE ile aynı başlangıç durumuna getirildi, "
            "böylece JSONB kolları ile pgvector kolu aynı veritabanı durumundan başladı."
        ),
        "- Aynı engine, bağlantı havuzu ve session factory kullanıldı.",
        (
            f"- {methodology['repeats']} tekrarda yöntem sırası deterministik Latin "
            "rotasyonuyla tam konum dengesi sağlayacak biçimde döndürüldü."
        ),
        "- Her veri boyutu kendi tam veri setiyle ayrıca warm-up edildi.",
        (
            "- Payload serileştirmesi her kolda ölçüm penceresinin içinde bırakıldı. ORM kolları "
            "parametre bağlarken serileştirir; COPY ve pgvector kolları da kendi payload'ını "
            "ölçülen bölümde üretir."
        ),
        (
            "- Başarılı sayılmak için kayıt, embedding boyutu, içerik hash'i, kimlik, chunk ve NULL "
            "kontrollerinin tamamının geçmesi istendi."
        ),
        (
            "- WAL doğrudan başlangıç ve bitiş LSN farkından; I/O ise ölçüm dışı checkpoint sonrası "
            "`pg_stat_io` farkından hesaplandı."
        ),
        (
            "- Her `pg_stat_io` okumasından önce `pg_stat_force_next_flush()` çağrıldı ve bağlantı "
            "havuzu tek bağlantıya sabitlendi. Gerekçesi aşağıdaki ölçüm notunda açıklanmıştır."
        ),
        "",
        "## Ölçüm notu: pg_stat_io tahsisi",
        "",
        (
            "PostgreSQL backend'e özel I/O sayaçlarını paylaşılan belleğe saniyede en fazla bir kez "
            "yazar. `pg_stat_clear_snapshot()` yalnızca okuyucunun görünümünü tazeler, backend'in "
            "bekleyen sayaçlarını yayımlamaz. Bu nedenle bir saniyeden kısa süren ölçüm pencereleri "
            "kendi I/O'sunu sıfır olarak raporlar ve yükü bir sonraki pencereye taşır. Bu deneyin "
            "ilk sürümünde tam olarak bu olmuştu: bir saniyenin altında biten koşuların büyük "
            "bölümü sıfır `extends` bildirmişti, ki boş tabloya yazarken bu fiziksel olarak "
            "imkansızdır. Ölçüm penceresinin ardından aynı backend'de `pg_stat_force_next_flush()` "
            "çağrılarak ve tüm yazma işi tek bağlantıya sabitlenerek düzeltildi. Aşağıdaki I/O "
            "tablosu bu düzeltmeden sonra üretilmiştir."
        ),
        "",
        "## Başlangıç, bitiş ve veri bütünlüğü",
        "",
        "| Kayıt hedefi | Ham koşu | Başlangıç aralığı | Bitiş aralığı | Geçerli koşu |",
        "|---:|---:|---:|---:|---:|",
    ]
    for dataset in payload["datasets"]:
        runs = [run for item in dataset["configurations"] for run in item["runs"]]
        start_values = [run["start_row_count"] for run in runs]
        end_values = [run["end_row_count"] for run in runs]
        valid_runs = sum(run["success"] and run["validation"]["valid"] for run in runs)
        lines.append(
            f"| {dataset['row_count']:,} | {len(runs)} | {min(start_values)} - "
            f"{max(start_values)} | {min(end_values):,} - {max(end_values):,} | "
            f"{valid_runs}/{len(runs)} |"
        )
    lines += [
        "",
        "## Süre ve throughput sonuçları",
        "",
        (
            "| Kayıt | Yöntem | Şema | Yol | Ortalama ms | Medyan ms | Min ms | Maks ms | "
            "Std sapma ms | Medyan kayıt/sn | Satır commit'e göre | Repository'ye göre |"
        ),
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row_count, item in configurations(enriched):
        lines.append(
            f"| {row_count:,} | `{item['strategy']}` | {variant_label(item)} | "
            f"{path_label(item)} | {item['wall_ms_mean']:,.3f} | "
            f"{item['wall_ms_median']:,.3f} | {item['wall_ms_min']:,.3f} | "
            f"{item['wall_ms_max']:,.3f} | {item['wall_ms_stdev']:,.3f} | "
            f"{item['rows_per_second_median']:,.3f} | "
            + ("- | " if is_reingest(item) else f"{item['speedup_vs_row_commit_each']:.3f}x | ")
            + f"{item['speedup_vs_repository']:.3f}x |"
        )
    lines += [
        "",
        (
            "`repository_save_passages` idempotent upsert semantiği çalıştırır, ama 1-4. ve 6. "
            "yöntemler düz insert yapar. Bu kollara göre hesaplanan hızlanma bu nedenle yöntem "
            "farkının yanında semantik farkı da içerir. Semantiği eşit olan tek karşılaştırma "
            "`core_upsert_batched` ile `repository_save_passages` arasındakidir."
        ),
        "",
        "![Medyan süre](assets/wall_time.svg)",
        "",
        "![Medyan throughput](assets/throughput.svg)",
        "",
        "![Repository yöntemine göre hızlanma](assets/speedup_vs_repository.svg)",
        "",
        "## İstemci tarafı serileştirme tavanı",
        "",
        (
            "Her yöntem, PostgreSQL tek bayt görmeden önce embedding'i aktarım biçimine çevirmek "
            "zorundadır. Bu maliyet veritabanından bağımsızdır ve hiçbir yazma yöntemi bunu "
            "ortadan kaldıramaz, dolayısıyla ulaşılabilir en iyi süreyi sınırlar."
        ),
        "",
        (
            "| Kayıt | JSON serileştirme ms | pgvector literal ms | En hızlı JSONB kolu ms | "
            "Serileştirmenin payı |"
        ),
        "|---:|---:|---:|---:|---:|",
    ]
    for dataset in enriched["datasets"]:
        serialization = dataset["client_serialization"]
        jsonb_items = [
            item
            for item in dataset["configurations"]
            if item["strategy"] not in VECTOR_STRATEGIES and "wall_ms_median" in item
        ]
        fastest = min(jsonb_items, key=lambda item: item["wall_ms_median"])
        share = 100 * serialization["embedding_json_dumps_ms"] / fastest["wall_ms_median"]
        lines.append(
            f"| {dataset['row_count']:,} | {serialization['embedding_json_dumps_ms']:,.3f} | "
            f"{serialization['embedding_vector_literal_ms']:,.3f} | "
            f"{fastest['wall_ms_median']:,.3f} (`{fastest['strategy']}`) | {share:.1f}% |"
        )
    lines += [
        "",
        "## Re-ingest: upsert'in UPDATE dalı",
        "",
        (
            "Yukarıdaki kolların tamamı boş tabloya yazar. Üretimde bir belge yeniden "
            "işlendiğinde aynı `(source_version_id, chunk_index)` çiftleri tabloda zaten "
            "vardır ve `ON CONFLICT DO UPDATE` INSERT dalını değil UPDATE dalını çalıştırır. "
            "Bu bölümdeki iki kol, tablo bu chunk'ları farklı içerikle tutarken çalışır; "
            "önceden doldurma ölçüm dışındadır. Her koşuda satırların gerçekten "
            "üzerine yazıldığı doğrulanır."
        ),
        "",
        (
            "| Kayıt | Medyan ms, mevcut yöntem | Medyan ms, batch upsert | Hızlanma | "
            "Insert yoluna göre upsert maliyeti | WAL MiB, mevcut | WAL MiB, upsert |"
        ),
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset in enriched["datasets"]:
        upsert = by_strategy(dataset, "core_upsert_batched_reingest")
        repository = by_strategy(dataset, "repository_save_passages_reingest")
        insert_upsert = by_strategy(dataset, "core_upsert_batched")
        overhead = 100 * (upsert["wall_ms_median"] / insert_upsert["wall_ms_median"] - 1)
        lines.append(
            f"| {dataset['row_count']:,} | {repository['wall_ms_median']:,.3f} | "
            f"{upsert['wall_ms_median']:,.3f} | "
            f"{repository['wall_ms_median'] / upsert['wall_ms_median']:.3f}x | "
            f"{overhead:+.1f}% | {repository['wal_bytes_median'] / 1024**2:.3f} | "
            f"{upsert['wal_bytes_median'] / 1024**2:.3f} |"
        )
    lines += [
        "",
        "## WAL, boyut ve I/O sonuçları",
        "",
        (
            "| Kayıt | Yöntem | Şema | Yol | Medyan WAL MiB | Heap artışı MiB | "
            "İndeks artışı MiB | TOAST ve yardımcı MiB | Toplam artış MiB | I/O yazma | "
            "I/O yazma ms | Extend | Extend ms | Fsync | Fsync ms |"
        ),
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row_count, item in configurations(enriched):
        lines.append(
            f"| {row_count:,} | `{item['strategy']}` | {variant_label(item)} | "
            f"{path_label(item)} | {item['wal_bytes_median'] / 1024**2:.3f} | "
            f"{item['heap_bytes_median'] / 1024**2:.3f} | "
            f"{item['index_bytes_median'] / 1024**2:.3f} | "
            f"{item['toast_and_auxiliary_bytes_median'] / 1024**2:.3f} | "
            f"{item['total_relation_bytes_median'] / 1024**2:.3f} | "
            f"{item['io_writes_median']:,.0f} | {item['io_write_ms_median']:,.3f} | "
            f"{item['io_extends_median']:,.0f} | {item['io_extend_ms_median']:,.3f} | "
            f"{item['io_fsyncs_median']:,.0f} | {item['io_fsync_ms_median']:,.3f} |"
        )
    lines += [
        "",
        "![Medyan WAL](assets/wal_bytes.svg)",
        "",
        (
            "Aynı tabloya yazan kollarda kayıt içeriği aynı olduğu için heap, indeks ve toplam "
            "relation artışı da aynıdır; yöntemlerden hiçbiri daha az kalıcı veri yazmaz. "
            "Boyut ve I/O sütunları her kolun kendi hedef tablosundan okunur, bu yüzden pgvector "
            "kolunun değerleri JSONB kollarıyla doğrudan değil şema karşılaştırması olarak "
            "okunmalıdır. TOAST ve yardımcı alan, toplam relation artışından ana heap ve ana "
            "indeks artışının çıkarılmasıyla hesaplanmıştır; büyük JSONB embedding değerlerinin "
            "önemli bölümü bu alandadır."
        ),
        "",
        "## SQL statement ve commit sayıları",
        "",
        "| Kayıt | Yöntem | Medyan SQL statement | Executemany | Commit |",
        "|---:|---|---:|---:|---:|",
    ]
    for row_count, item in configurations(enriched):
        lines.append(
            f"| {row_count:,} | `{item['strategy']}` | "
            f"{item['sql_statement_count_median']:,.0f} | "
            f"{item['executemany_call_count_median']:,.0f} | "
            f"{item['commit_count_median']:,.0f} |"
        )
    lines += [
        "",
        (
            "`copy_records` SQLAlchemy cursor katmanını atladığı için statement sayısı ayrıca "
            "sayılmıştır; tek COPY protokol gidiş dönüşü bir statement olarak raporlanır."
        ),
        "",
        "## Bulgular",
        "",
    ]
    for dataset in enriched["datasets"]:
        row_count = dataset["row_count"]
        jsonb_items = [
            item for item in dataset["configurations"] if item["strategy"] not in VECTOR_STRATEGIES
        ]
        fastest = min(jsonb_items, key=lambda item: item["wall_ms_median"])
        upsert = by_strategy(dataset, "core_upsert_batched")
        row_commit = by_strategy(dataset, "row_commit_each")
        wal_reduction = (
            100
            * (row_commit["wal_bytes_median"] - fastest["wal_bytes_median"])
            / row_commit["wal_bytes_median"]
        )
        lines.append(
            f"- {row_count:,} kayıtta en düşük medyan süre `{fastest['strategy']}` ile "
            f"{fastest['wall_ms_median']:,.3f} ms ölçüldü. Semantiği repository ile eşleşen "
            f"`core_upsert_batched` {upsert['wall_ms_median']:,.3f} ms ile mevcut repository "
            f"yöntemine göre {upsert['speedup_vs_repository']:.3f}x, satır başına commit'e göre "
            f"{upsert['speedup_vs_row_commit_each']:.3f}x hızlandı. En hızlı kolun satır başına "
            f"commit'e göre medyan WAL azalması yüzde {wal_reduction:.2f} oldu."
        )
    reingest_gain_text = ", ".join(
        f"{by_strategy(dataset, 'repository_save_passages_reingest')['wall_ms_median'] / by_strategy(dataset, 'core_upsert_batched_reingest')['wall_ms_median']:.2f}x"
        for dataset in enriched["datasets"]
    )
    reingest_overhead_text = ", ".join(
        f"{100 * (by_strategy(dataset, 'core_upsert_batched_reingest')['wall_ms_median'] / by_strategy(dataset, 'core_upsert_batched')['wall_ms_median'] - 1):+.1f}%"
        for dataset in enriched["datasets"]
    )
    upsert_penalty_text = ", ".join(
        f"{100 * (by_strategy(dataset, 'core_upsert_batched')['wall_ms_median'] / by_strategy(dataset, 'core_executemany')['wall_ms_median'] - 1):+.1f}%"
        for dataset in enriched["datasets"]
    )
    copy_gain_text = ", ".join(
        f"{100 * (1 - by_strategy(dataset, 'copy_records')['wall_ms_median'] / by_strategy(dataset, 'core_executemany')['wall_ms_median']):.1f}%"
        for dataset in enriched["datasets"]
    )
    vector_gain_text = ", ".join(
        f"{by_strategy(dataset, 'core_executemany')['wall_ms_median'] / by_strategy(dataset, 'vector_executemany')['wall_ms_median']:.2f}x"
        for dataset in enriched["datasets"]
    )
    vector_size_text = ", ".join(
        f"{100 * (by_strategy(dataset, 'vector_executemany')['total_relation_bytes_median'] / by_strategy(dataset, 'core_executemany')['total_relation_bytes_median'] - 1):.0f}%"
        for dataset in enriched["datasets"]
    )
    lines += [
        (
            "- `row_add_one_transaction` ile `orm_add_all`, SQLAlchemy'nin PostgreSQL "
            "insertmanyvalues/executemany yolunda tek statement ve tek commit üretmesi nedeniyle "
            "birbirine yakın sonuç verdi."
        ),
        (
            f"- Idempotent olmanın bedeli küçüktür: `core_upsert_batched`, çakışma çözümü "
            f"yapmayan `core_executemany` ile üç boyutta da {upsert_penalty_text} fark verdi. "
            "Bulk yazıma geçerken repository semantiğinden vazgeçmek için ölçülmüş bir gerekçe "
            "yoktur."
        ),
        (
            f"- COPY protokolü beklendiği kadar ayrışmadı: `copy_records`, "
            f"`core_executemany` ile arasında {copy_gain_text} fark bıraktı. Sebebi, aşağıdaki "
            "serileştirme tavanıdır; iki yöntem de aynı istemci tarafı JSON maliyetini öder ve "
            "COPY yalnızca sunucu tarafındaki farkı kazanır."
        ),
        (
            f"- Re-ingest yolunda kazanç korunuyor: dolu tabloya yazarken batch upsert, "
            f"mevcut yönteme göre {reingest_gain_text} hızlıydı. UPDATE dalı INSERT dalından "
            f"pahalı ({reingest_overhead_text}), ama bu maliyet iki yöntemde de ortaya çıkar ve "
            "aradaki farkı kapatmıyor."
        ),
        (
            f"- Ölçülen en büyük tekil kazanç yöntem değil şema değişikliğinden geldi: "
            f"native `vector` sütununa yazan `vector_executemany`, aynı statement şekliyle "
            f"JSONB'ye yazan `core_executemany` yöntemine göre {vector_gain_text} hızlıydı. "
            f"Karşılığında tablo {vector_size_text} daha fazla yer kapladı, çünkü pgvector "
            "değerleri JSONB gibi TOAST sıkıştırmasından yararlanmaz."
        ),
        (
            "- Satır başına commit WAL'ı yaklaşık yüzde 1 artırdı; asıl fark süre, statement ve "
            "commit sayısında oluştu. Bulk yazımın gerekçesi depolama tasarrufu değildir."
        ),
        (
            "- Mevcut repository yöntemi kayıt başına bir SELECT ve autoflush kaynaklı bir INSERT "
            "üretti. Bu nedenle statement sayısı `2N`, commit sayısı 1 oldu."
        ),
        (
            "- Repository sürelerinin standart sapması diğer yöntemlerden yüksektir. Bu yöntem için "
            "ortalama yerine medyan karar metriği olarak daha dayanıklıdır."
        ),
        "",
        "## Mevcut repository yönteminin darboğazı",
        "",
        (
            "`save_passages`, her passage için `(source_version_id, chunk_index)` varlık sorgusu "
            "çalıştırır. Session autoflush davranışı önceki bekleyen INSERT'i sonraki SELECT "
            "öncesinde gönderir. Sonuçta N kayıt için 2N ağ gidiş dönüşü oluşur. Tek commit "
            "kullanılması WAL ve commit maliyetini sınırlar, fakat sorgu sayısını sınırlamaz. "
            "`INSERT ... ON CONFLICT DO UPDATE` aynı idempotent sonucu batch başına tek statement "
            "ile üretir."
        ),
        "",
        "## Güvenilirlik sınırları",
        "",
        "- Sonuçlar tek bir makine ve tek container üzerinde alınmıştır.",
        (
            "- Re-ingest kollarında tablo, ölçüm dışında kalan bir dolum adımıyla "
            "hazırlanır. Bu satırlar taze yazıldığı için üretimdeki bir tablonun "
            "parçalanma ve autovacuum durumunu birebir temsil etmez."
        ),
        (
            f"- Her hücrede {methodology['repeats']} ölçüm vardır; özellikle repository yönteminde "
            "yüksek varyans gözlendi."
        ),
        *unstable_limit_lines,
        (
            "- `pg_stat_io` checkpoint ile fiziksel yazmaya zorlanmış ve her okumadan önce flush "
            "edilmiştir, ancak kernel ve depolama katmanı zamanlaması tamamen ayrıştırılamaz."
        ),
        (
            "- Ana re-ingest kolları tüm satırların çakıştığı durumu ölçer; yüzde 50 çakışmalı "
            "karışık yol ayrı ek deneyde ölçülmüştür."
        ),
        (
            "- Eşzamanlı yazarlar, lock contention, bağlantı kaybı ve transaction retry davranışı "
            "bu matriste yoktur."
        ),
        (
            "- pgvector kolu yalnızca yazma maliyetini ölçer. HNSW veya IVFFlat vektör indeksi "
            "oluşturulmamıştır; indeksli bir tabloda yazma maliyeti belirgin biçimde artar."
        ),
        (
            "- pgvector'e COPY protokolüyle yazmak asyncpg için binary codec gerektirdiğinden bu "
            "matriste yoktur."
        ),
        "",
        "## Üretim için aday ve karar noktaları",
        "",
        (
            "Ölçümler bulk yazımın değerlendirilmesini gerekçelendirir. Teknik aday yöntem "
            f"`core_upsert_batched`, yani {methodology['upsert_batch']:,} satırlık batch'lerle "
            "`INSERT ... ON CONFLICT DO UPDATE`. Bu yöntem repository'nin idempotent güncelleme "
            "semantiğini korur ve ölçülen tek eşdeğer semantikli bulk yoldur. `copy_records` daha "
            "hızlı olabilir fakat çakışma çözümü sunmaz; upsert gerektiren bir yolda ancak geçici "
            "tabloya COPY ve ardından tek MERGE ile kullanılabilir, bu da bu deneyin dışındadır."
        ),
        "",
        (
            "Uygulama öncesinde gerekli görülen regresyon ve güvenlik kontrolleri ve bunların "
            "hangi testle karşılandığı:"
        ),
        "",
        (
            "- Yeni ve mevcut passage karışımında alanların doğru insert/update edilmesi: "
            "`test_mixed_batch_inserts_new_chunks_and_updates_existing_ones`."
        ),
        (
            "- Tekrarlanan `(source_version_id, chunk_index)` davranışı: "
            "`test_duplicate_chunks_in_one_call_keep_first_id_and_last_content`."
        ),
        (
            "- Batch ortasında hata olduğunda tam rollback: "
            "`test_a_failing_batch_leaves_no_earlier_batch_behind`, ki test önce ilk batch'in "
            "gerçekten gönderildiğini doğrular."
        ),
        (
            "- Batch sınırının uygulanması: "
            "`test_save_passages_sends_one_statement_per_batch_and_commits_once`, "
            "2N+1 kayıtta üç statement ve tek commit."
        ),
        (
            "- Eşzamanlı writer ve deadlock: "
            "`tests/test_passage_persistence_postgres.py`, gerçek PostgreSQL üzerinde. "
            "Kilit sırası kaldırıldığında testin `DeadlockDetectedError` ürettiği "
            "doğrulanmıştır, yani sıralama önlemi varsayım değil ölçülmüş bir gerekliliktir."
        ),
        (
            "- SQLite ile PostgreSQL farkı: ana suite SQLite üzerinde, eşzamanlılık dosyası "
            "PostgreSQL üzerinde koşar; iki dialect de aynı `on_conflict_do_update` yolunu "
            "kullanır."
        ),
        (
            "- Yetkilendirme beklentilerinin korunması: `save_passages` `run_id` almadığı için "
            "`_OwnershipEnforced` sarmalamasının dışındadır ve imzası değişmemiştir."
        ),
        (
            "- Kapsanmayan tek başlık, bağlantı kaybı ve üst katman retry politikasıdır; "
            "entegrasyon PR'ının ayrı risk başlığıdır."
        ),
        "",
        "## Yeniden çalıştırma",
        "",
        "```bash",
        "docker compose -f research/bulk-insert/compose.yml up -d --wait postgres",
        "PYTHONPATH=src .venv311/bin/python scripts/benchmark_bulk_insert.py \\",
        (
            f"  --sizes {' '.join(str(size) for size in methodology['sizes'])} "
            f"--repeats {methodology['repeats']} --warmups {methodology['warmups']} \\"
        ),
        (
            f"  --dimensions {methodology['embedding_dimensions']} "
            f"--text-chars {methodology['text_chars']} "
            f"--upsert-batch {methodology['upsert_batch']} \\"
        ),
        "  --output research/bulk-insert/results/postgres_bulk_insert.json",
        "PYTHONPATH=src .venv311/bin/python scripts/benchmark_partial_conflict.py \\",
        (
            f"  --sizes {' '.join(str(size) for size in methodology['sizes'])} "
            f"--repeats {methodology['repeats']} --warmups {methodology['warmups']} \\"
        ),
        (
            f"  --dimensions {methodology['embedding_dimensions']} "
            f"--text-chars {methodology['text_chars']} "
            f"--upsert-batch {methodology['upsert_batch']} \\"
        ),
        "  --output research/bulk-insert/results/postgres_bulk_insert_partial.json",
        "PYTHONPATH=src .venv311/bin/python scripts/report_bulk_insert.py",
        "```",
        "",
        "Ham sonuç: `results/postgres_bulk_insert.json`",
        "",
        "Özet CSV: `results/postgres_bulk_insert_summary.csv`",
        "",
        "## Teknik sonuç",
        "",
        (
            "Bu makinede embedding içeren yazma yükü için tek transaction toplu yazım açık biçimde "
            "daha hızlıdır. Repository ile aynı idempotent semantiği taşıyan `core_upsert_batched`, "
            f"mevcut repository yöntemine göre medyan sürede {gain_text} hızlanma sağlamıştır. "
            "WAL ve nihai tablo boyutu kazancı küçük olduğundan üretim gerekçesi depolama azalması "
            "değil, ağ gidiş dönüşü ve transaction maliyetinin azaltılmasıdır. Kazancın bir tavanı "
            "vardır: en hızlı kolun süresinin kayda değer bir bölümü istemci tarafı embedding "
            "serileştirmesidir ve bunu hiçbir yazma yöntemi düşürmez. Native pgvector sütunu bu "
            "tavanı sunucu tarafında düşürür, karşılığında disk kullanımını artırır; bu ayrı bir "
            "şema kararıdır ve bu deneyin kapsamı dışındadır. Verilerin işaret ettiği teknik aday, "
            "idempotent upsert "
            "semantiği ve batch sınırları korunarak bulk repository yoludur. Üretim kodu bu "
            "rapor kapsamında değiştirilmemiştir; entegrasyon kararı aşağıdaki kontrollerle "
            "birlikte verilmelidir."
        ),
        "",
        f"Bu rapor `{result_path.name}` dosyasındaki ölçümlerden yeniden üretilebilir.",
        "",
    ]
    if partial_payload is not None:
        marker = lines.index("## Güvenilirlik sınırları")
        lines[marker:marker] = partial_conflict_lines(partial_payload)
    report = "\n".join(lines)
    if "\u2014" in report:
        raise ValueError("Report must not contain an em dash")
    return report


def generate(result_path: Path, report_path: Path, partial_result_path: Path | None = None) -> None:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assets = report_path.parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    charts = {
        "wall_time.svg": grouped_bar_svg(
            payload,
            metric="wall_ms_median",
            title="Medyan yazma süresi",
            y_label="Milisaniye",
        ),
        "throughput.svg": grouped_bar_svg(
            payload,
            metric="rows_per_second_median",
            title="Medyan throughput",
            y_label="Kayıt / saniye",
        ),
        "speedup_vs_repository.svg": grouped_bar_svg(
            speedup_payload(payload),
            metric="speedup_vs_repository",
            title="Repository yöntemine göre hızlanma",
            y_label="Hızlanma katsayısı",
        ),
        "wal_bytes.svg": grouped_bar_svg(
            payload,
            metric="wal_bytes_median",
            title="Medyan WAL üretimi",
            y_label="MiB",
            value_scale=1024**2,
        ),
    }
    for name, content in charts.items():
        (assets / name).write_text(content, encoding="utf-8")
    write_summary_csv(payload, result_path.with_name("postgres_bulk_insert_summary.csv"))
    partial_payload = (
        json.loads(partial_result_path.read_text(encoding="utf-8"))
        if partial_result_path is not None and partial_result_path.exists()
        else None
    )
    report_path.write_text(markdown_report(payload, result_path, partial_payload), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate PostgreSQL bulk insert report assets")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("research/bulk-insert/results/postgres_bulk_insert.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("research/bulk-insert/REPORT.md"),
    )
    parser.add_argument(
        "--partial-input",
        type=Path,
        default=Path("research/bulk-insert/results/postgres_bulk_insert_partial.json"),
    )
    args = parser.parse_args()
    generate(args.input, args.report, args.partial_input)
    print(f"REPORT {args.report.resolve()}")


if __name__ == "__main__":
    main()
