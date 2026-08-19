from __future__ import annotations

# CODEX-2026-08-18: C1 corpus contract and metric regression tests.

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from c1_metrik import metrikler
from c1_orneklem import sec
from c2_kalibrasyon import _aday, _dil_kirilimi, _kabul_edilen_aday, _sinif
from korpus_kaynak import (
    METIN_REFERANSI, PDF_PARSE, SAYFA_ETIKETI, SAYFA_GORSELI, YALNIZCA_DUZEN,
    DocLayNetKaynak, OcrTurkKaynak, OmniDocBenchKaynak, OpenDataLoaderBenchKaynak,
)


def test_metrics_are_one_for_identical_markdown():
    text = "# Baslik\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
    result = metrikler(text, text)
    assert result["char_similarity"] == 1.0
    assert result["token_f1"] == 1.0
    assert result["structure_similarity"] == 1.0
    assert result["utility"] == 1.0


def test_metrics_ignore_production_page_heading():
    result = metrikler("Merhaba dunya", "# Page 1\n\nMerhaba dunya")
    assert result["char_similarity"] == 1.0


def test_ocrturk_adapter_reads_bom_and_pairs_by_id(tmp_path: Path):
    folder = tmp_path / "data_1"
    folder.mkdir()
    (folder / "data_1.pdf").write_bytes(b"%PDF-fixture")
    (folder / "data_1.md").write_text("| A |\n| --- |\n| 1 |", encoding="utf-8")
    (folder / "count_info.json").write_text(
        json.dumps({"tables": 1, "figures": 0, "equations": 0}), encoding="utf-8"
    )
    (folder / "source.json").write_text(
        json.dumps({"difficulty": "hard", "type": "thesis"}), encoding="utf-8-sig"
    )
    with patch("korpus_kaynak.sayfa_sayisi", return_value=1):
        record = list(OcrTurkKaynak(str(tmp_path)).kayitlar())[0]
    assert {PDF_PARSE, METIN_REFERANSI, SAYFA_ETIKETI} <= set(record.yetenekler)
    assert record.ustveri["zorluk"] == "hard"
    assert record.referans["tablo_izi"] == 1


def test_doclaynet_only_claims_layout_when_annotations_exist(tmp_path: Path):
    for subset, annotations in (("public", []), ("truth", [
        {"image_id": 1, "category_id": 7},
    ])):
        root = tmp_path / subset
        (root / "PNG").mkdir(parents=True)
        (root / "PNG" / "p.png").write_bytes(b"png")
        payload = {
            "categories": [{"id": 7, "name": "Table"}],
            "images": [{"id": 1, "file_name": "p.png"}],
            "annotations": annotations,
        }
        (root / "coco.json").write_text(json.dumps(payload), encoding="utf-8")
    records = list(DocLayNetKaynak(str(tmp_path)).kayitlar())
    public, truth = records
    assert SAYFA_GORSELI in public.yetenekler
    assert YALNIZCA_DUZEN not in public.yetenekler
    assert {SAYFA_GORSELI, YALNIZCA_DUZEN, SAYFA_ETIKETI} <= set(truth.yetenekler)


def test_omnidocbench_reports_missing_image(tmp_path: Path):
    payload = [{
        "page_info": {"image_path": "missing.png", "page_attribute": {}},
        "layout_dets": [{"category_type": "table", "text": "x"}],
    }]
    (tmp_path / "OmniDocBench.json").write_text(json.dumps(payload), encoding="utf-8")
    record = list(OmniDocBenchKaynak(str(tmp_path)).kayitlar())[0]
    assert SAYFA_GORSELI not in record.yetenekler
    assert record.sorunlar == ["gorsel_yok"]


def test_opendataloader_adapter_exposes_english_pdf_reference_and_labels(tmp_path: Path):
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "ground-truth" / "markdown").mkdir(parents=True)
    (tmp_path / "pdfs" / "001.pdf").write_bytes(b"%PDF-fixture")
    (tmp_path / "ground-truth" / "markdown" / "001.md").write_text(
        "# Heading\n\n| A |\n| --- |\n| 1 |", encoding="utf-8"
    )
    annotation = {"001.pdf": {"elements": [
        {"category": "Table"}, {"category": "Chart"}, {"category": "Equation"},
    ]}}
    (tmp_path / "ground-truth" / "reference.json").write_text(
        json.dumps(annotation), encoding="utf-8"
    )
    with patch("korpus_kaynak.sayfa_sayisi", return_value=1):
        record = list(OpenDataLoaderBenchKaynak(str(tmp_path)).kayitlar())[0]
    assert record.yol_koku == "opendataloader_bench"
    assert {PDF_PARSE, METIN_REFERANSI, SAYFA_ETIKETI} <= set(record.yetenekler)
    assert record.etiketler == {"tablo": 1, "sekil": 1, "denklem": 1}
    assert record.ustveri["dil"] == "en"


def test_calibration_classification_counts():
    result = _sinif([True, True, False, False], [True, False, True, False])
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 1, 1, 1)
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


def test_calibration_does_not_invent_candidate_without_positive_examples():
    assert _aday([{"actual_positives": 0}]) is None


def test_calibration_rejects_tradeoff_that_misses_quality_target():
    row = {"recall": 0.8, "precision": 0.7, "fast_rate": 0.5, "f2": 0.81}
    assert _kabul_edilen_aday([row]) is None


def test_cache_and_validation_share_balanced_sample_selection():
    # CODEX-2026-08-18: Cache/dogrulama ilk-N uyusmazliginin regresyon testi.
    records = [
        {"kimlik": "plain-1", "veri_seti": "x", "yetenekler": [PDF_PARSE, METIN_REFERANSI],
         "ustveri": {"tur": "plain"}, "etiketler": {"tablo": 0}},
        {"kimlik": "plain-2", "veri_seti": "x", "yetenekler": [PDF_PARSE, METIN_REFERANSI],
         "ustveri": {"tur": "plain"}, "etiketler": {"tablo": 0}},
        {"kimlik": "table-1", "veri_seti": "x", "yetenekler": [PDF_PARSE, METIN_REFERANSI],
         "ustveri": {"tur": "table"}, "etiketler": {"tablo": 1}},
    ]
    assert [row["kimlik"] for row in sec(records, None, 2, ["x"])] == ["plain-1", "table-1"]


def test_language_breakdown_does_not_hide_transfer_result():
    def row(language: str, gain: float, routed: bool, utility: float) -> dict:
        return {
            "input": {"metadata": {"dil": language}},
            "delta": {"heavy_minus_fast": gain},
            "route": {"routed_heavy": routed},
            "scores": {name: {"utility": utility} for name in ("fast", "heavy", "routed")},
        }
    result = _dil_kirilimi([row("tr", 0.03, True, 0.9), row("en", 0.0, False, 0.8)], 0.02)
    assert result["tr"]["current_baseline"]["recall"] == 1.0
    assert result["en"]["heavy_benefit_positives"] == 0
