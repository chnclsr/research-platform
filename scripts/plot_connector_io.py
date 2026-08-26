"""Konnektör I/O eşzamanlılık deneyinin SVG grafiklerini ham JSON'lardan üretir.

Grafikler elle yazılmaz: tek kaynak `research/connector-concurrency/results/`
altındaki benchmark JSON dosyalarıdır. Böylece benchmark yeniden koşulduğunda
grafik de yeniden üretilir ve rapordaki sayılarla ayrışamaz.

Kullanım (repo kökünde):
    python scripts/plot_connector_io.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

RESULTS = Path("research/connector-concurrency/results")
ASSETS = Path("research/connector-concurrency/assets")

WIDTH = 1000
MARGIN = 40
BAR_H = 20
BAR_PITCH = 24
GROUP_GAP = 22

SERIES_COLORS = ("#2563eb", "#f97316", "#0f9d58")

CATEGORY_FONT = 15
VALUE_FONT = 12


def _text_width(text: str, size: int, *, bold: bool = False) -> float:
    """Arial'de yaklaşık metin genişliği.

    Tam ölçüm için font metriği gerekir; burada amaç yerleşimin çakışmaması, o
    yüzden karakter başına ortalama genişlikle üstten tahmin yeterli.
    """
    return len(text) * size * (0.60 if bold else 0.56)


@dataclass(frozen=True)
class Series:
    label: str
    color: str
    values: list[float | None]


def _nice_ticks(vmax: float) -> tuple[float, list[float]]:
    """Ekseni bitiren üst sınırı ve etiketlenecek tick değerlerini seçer."""
    for step in (25, 50, 100, 250, 500, 1000, 2500, 5000):
        if vmax / step <= 6:
            top = step * (int(vmax // step) + 1)
            return float(top), [float(step * i) for i in range(int(top // step) + 1)]
    step = 10000
    top = step * (int(vmax // step) + 1)
    return float(top), [float(step * i) for i in range(int(top // step) + 1)]


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_chart(
    *,
    title: str,
    subtitle: str,
    alt_title: str,
    alt_desc: str,
    categories: list[str],
    series: list[Series],
    footnote: str = "",
) -> str:
    rows = len(categories)
    bars = len(series)
    values = [v for s in series for v in s.values if v is not None]
    top_value, ticks = _nice_ticks(max(values))

    # Sol kenar en uzun satır etiketine, sağ kenar en uzun değer etiketine göre
    # belirlenir; sabit kenarlar uzun etiketlerde taşmaya yol açıyordu.
    left = MARGIN + max(_text_width(c, CATEGORY_FONT) for c in categories) + 20
    widest_value = max(_text_width(f"{v:.0f} ms", VALUE_FONT, bold=True) for v in values)
    right = WIDTH - MARGIN - widest_value - 8

    # Gösterge kendi satırında durur; başlığın yanına konunca uzun başlıkla
    # çakışıyordu.
    legend_y = 92
    top = legend_y + 38

    group_h = bars * BAR_PITCH + GROUP_GAP
    bars_h = (bars - 1) * BAR_PITCH + BAR_H
    axis_y = top + rows * group_h - GROUP_GAP + 20
    height = axis_y + (70 if footnote else 45)

    span = right - left

    def x_of(value: float) -> float:
        return left + span * (value / top_value)

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">'
    )
    out.append(f'  <title id="title">{_esc(alt_title)}</title>')
    out.append(f'  <desc id="desc">{_esc(alt_desc)}</desc>')
    out.append(f'  <rect width="{WIDTH}" height="{height}" fill="#ffffff"/>')
    out.append(
        f'  <text x="40" y="42" font-family="Arial, sans-serif" font-size="24" '
        f'font-weight="700" fill="#172033">{_esc(title)}</text>'
    )
    out.append(
        f'  <text x="40" y="68" font-family="Arial, sans-serif" font-size="14" '
        f'fill="#556070">{_esc(subtitle)}</text>'
    )

    legend_x = float(MARGIN)
    for s in series:
        out.append(
            f'  <rect x="{round(legend_x, 1)}" y="{legend_y}" width="16" height="16" '
            f'rx="3" fill="{s.color}"/>'
        )
        out.append(
            f'  <text x="{round(legend_x + 24, 1)}" y="{legend_y + 13}" '
            f'font-family="Arial, sans-serif" font-size="14" fill="#172033">'
            f"{_esc(s.label)}</text>"
        )
        legend_x += 24 + _text_width(s.label, 14) + 28

    out.append('  <g stroke="#d7dde7" stroke-width="1">')
    for tick in ticks:
        x = round(x_of(tick), 1)
        out.append(f'    <line x1="{x}" y1="{top - 10}" x2="{x}" y2="{axis_y - 10}"/>')
    out.append("  </g>")

    out.append(
        '  <g font-family="Arial, sans-serif" font-size="12" fill="#667085" text-anchor="middle">'
    )
    for index, tick in enumerate(ticks):
        label = "0 ms" if index == 0 else f"{tick:g}"
        out.append(f'    <text x="{round(x_of(tick), 1)}" y="{axis_y + 13}">{label}</text>')
    out.append("  </g>")

    out.append(
        f'  <g font-family="Arial, sans-serif" font-size="{CATEGORY_FONT}" fill="#172033" '
        f'text-anchor="end">'
    )
    for row, category in enumerate(categories):
        centre = top + row * group_h + bars_h / 2 + 5
        out.append(
            f'    <text x="{round(left - 20, 1)}" y="{round(centre, 1)}">{_esc(category)}</text>'
        )
    out.append("  </g>")

    labels: list[str] = []
    for series_index, s in enumerate(series):
        out.append(f'  <g fill="{s.color}">')
        for row, value in enumerate(s.values):
            if value is None:
                continue
            y = top + row * group_h + series_index * BAR_PITCH
            width = max(round(x_of(value) - left, 1), 1.0)
            out.append(
                f'    <rect x="{round(left, 1)}" y="{y}" width="{width}" '
                f'height="{BAR_H}" rx="4"/>'
            )
            labels.append(
                f'    <text x="{round(left + width + 8, 1)}" y="{y + 15}">{value:.0f} ms</text>'
            )
        out.append("  </g>")

    out.append(
        f'  <g font-family="Arial, sans-serif" font-size="{VALUE_FONT}" font-weight="700" '
        f'fill="#172033">'
    )
    out.extend(labels)
    out.append("  </g>")

    if footnote:
        out.append(
            f'  <text x="40" y="{height - 18}" font-family="Arial, sans-serif" '
            f'font-size="12" fill="#667085">{_esc(footnote)}</text>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _config_key(config: dict) -> str:
    if config["mode"] in {"serial", "blocking_serial"}:
        return "serial"
    return f"c{config['concurrency']}"


def _medians(payload: dict, stage_name: str) -> dict[str, float]:
    for stage in payload["stages"]:
        if stage["stage"] == stage_name:
            return {_config_key(c): c["wall_ms_median"] for c in stage["configurations"]}
    raise KeyError(stage_name)


def build_local(payload: dict) -> str:
    search = _medians(payload, "search")
    acquisition = _medians(payload, "acquisition")
    keys = ["serial", "c1", "c2", "c4", "c8"]
    categories = ["Sıralı", "asyncio c=1", "asyncio c=2", "asyncio c=4", "asyncio c=8"]
    return render_chart(
        title="Kontrollü yerel deney: medyan duvar süresi",
        subtitle="8 işlem, 5 tekrar · düşük değer daha iyi",
        alt_title="Kontrollü yerel deney medyan duvar süreleri",
        alt_desc=(
            "Sekiz işlem için arama ve indirme medyan sürelerinin concurrency "
            "seviyelerine göre karşılaştırması. Düşük süre daha iyidir."
        ),
        categories=categories,
        series=[
            Series("Arama", SERIES_COLORS[0], [search.get(k) for k in keys]),
            Series("İndirme", SERIES_COLORS[1], [acquisition.get(k) for k in keys]),
        ],
    )


def build_live(payload: dict) -> str:
    search = _medians(payload, "search")
    acquisition = _medians(payload, "acquisition")
    keys = ["serial", "c1", "c2", "c4"]
    categories = ["Sıralı", "asyncio c=1", "asyncio c=2", "asyncio c=4"]
    return render_chart(
        title="Canlı ağ deneyi: medyan duvar süresi",
        subtitle="4 gerçek kaynak, 5 tekrar · düşük değer daha iyi",
        alt_title="Canlı ağ deneyi medyan duvar süreleri",
        alt_desc=(
            "Dört gerçek kaynak için arama ve indirme medyan sürelerinin concurrency "
            "seviyelerine göre karşılaştırması. Düşük süre daha iyidir."
        ),
        categories=categories,
        series=[
            Series("Arama", SERIES_COLORS[0], [search.get(k) for k in keys]),
            Series("İndirme", SERIES_COLORS[1], [acquisition.get(k) for k in keys]),
        ],
        footnote=(
            "Not: Canlı ağda tekil koşular sağlayıcı gecikmesi nedeniyle değişebilir; "
            "sütunlar 5 koşunun medyanıdır."
        ),
    )


def build_pipeline(payload: dict) -> str:
    search = _medians(payload, "pipeline_search")
    acquisition = _medians(payload, "pipeline_acquisition")
    threadpool = {
        _config_key(c): c["wall_ms_median"]
        for c in payload["threadpool_reference"]["configurations"]
    }
    keys = ["c1", "c2", "c4"]
    threadpool_keys = ["serial", "c2", "c4"]
    categories = [
        "c=1 (referans: serial)",
        "c=2 (referans: worker=2)",
        "c=4 (referans: worker=4)",
    ]
    return render_chart(
        title="Gerçek pipeline düğümleri ve ThreadPool referansı",
        subtitle="8 kontrollü I/O işi, 5 tekrar · düşük değer daha iyi",
        alt_title="Pipeline düğümleri ve ThreadPool referansı medyan duvar süreleri",
        alt_desc=(
            "_search_node ve _acquire_node düğümlerinin c=1, c=2 ve c=4 medyan süreleri ile "
            "aynı iş yükünün bloklayan senkron ThreadPool referansı. Düşük süre daha iyidir."
        ),
        categories=categories,
        series=[
            Series("Arama düğümü", SERIES_COLORS[0], [search.get(k) for k in keys]),
            Series("İndirme düğümü", SERIES_COLORS[1], [acquisition.get(k) for k in keys]),
            Series(
                "ThreadPool referansı",
                SERIES_COLORS[2],
                [threadpool.get(k) for k in threadpool_keys],
            ),
        ],
        footnote=(
            "ThreadPool referansı bloklayan senkron I/O içindir; üretim bağlayıcıları "
            "async'tir ve ThreadPoolExecutor içinde çalıştırılmaz."
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--assets", type=Path, default=ASSETS)
    args = parser.parse_args()
    args.assets.mkdir(parents=True, exist_ok=True)

    jobs = [
        ("local_benchmark.json", "local_wall_time.svg", build_local),
        ("live_benchmark.json", "live_wall_time.svg", build_live),
        ("pipeline_benchmark.json", "pipeline_wall_time.svg", build_pipeline),
    ]
    for source, target, builder in jobs:
        payload = json.loads((args.results / source).read_text(encoding="utf-8"))
        (args.assets / target).write_text(builder(payload), encoding="utf-8")
        print(f"RESULT {(args.assets / target).resolve()}")


if __name__ == "__main__":
    main()
