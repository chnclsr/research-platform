#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark.py
============
14 Boyutlu Enterprise PDF Critic ve Smart Router için 12 Dokümanlık Kapsamlı Benchmark Runner.
"""

import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from router import PDFRouter

# UTF-8 console output setup
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

def run_benchmark():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    corpus_dir = os.path.join(os.path.dirname(base_dir), "corpus")
    
    docs = [
        {"file": "attention_tablo.pdf", "category": "Mimari / Tablo"},
        {"file": "bert_2sutun_dipnot.pdf", "category": "2-Sütun / Dipnot"},
        {"file": "gpt3_uzun_75sayfa.pdf", "category": "Uzun Belge (75+)"},
        {"file": "gpt4_uzun_gorsel.pdf", "category": "Karmaşık / Görsel"},
        {"file": "resnet_2sutun_gorsel.pdf", "category": "2-Sütun / Vektör Çizim"},
        {"file": "vgg_tablo_agirlikli.pdf", "category": "Tek Sütun / Yoğun Tablo"},
        {"file": "sybil_lung_cancer.pdf", "category": "Medikal / Klinik Rapor"},
        {"file": "math_heavy_transformer.pdf", "category": "Yoğun Matematik"},
        {"file": "ieee_style_vit.pdf", "category": "Konferans / IEEE Düzeni"},
        {"file": "tabular_financial_rag.pdf", "category": "Finans / Büyük Tablolar"},
        {"file": "multimodal_llava.pdf", "category": "Multimodal / Kod & Diyalog"},
        {"file": "turkish_nlp_bert.pdf", "category": "Türkçe & Özel Glifler"}
    ]
    
    router = PDFRouter()
    results = []
    
    print("=" * 115)
    print("14 BOYUTLU ENTERPRISE PDF CRITIC & ROUTER BENCHMARK (12 DOKÜMAN)")
    print("=" * 115)
    print(f"{'Dosya Adı':<26} | {'Kategori':<24} | {'YapıSkor':<8} | {'14M-Kalite':<10} | {'Karar / Parser':<22} | {'Süre'}")
    print("-" * 115)
    
    for item in docs:
        pdf_path = os.path.join(corpus_dir, item["file"])
        if not os.path.exists(pdf_path):
            print(f"HATA: {item['file']} bulunamadı!")
            continue
            
        t0 = time.perf_counter()
        decision = router.route_document(pdf_path)
        total_time = (time.perf_counter() - t0) * 1000
        
        target = decision["target_parser"]
        fb = "[FALLBACK]" if decision["fallback_triggered"] else "[DEFAULT]"
        q_score = decision["quality_score"]
        struct_score = decision.get("structural_score", 0.0)
        crit_issue = decision.get("critical_issue", "NONE")
        
        decision_str = f"{target} {fb}"
        
        print(f"{item['file']:<26} | {item['category']:<24} | {struct_score:<8.1f} | {q_score:<10.1f} | {decision_str:<22} | {total_time:.1f}ms")
        
        results.append({
            "file": item["file"],
            "category": item["category"],
            "structural_score": struct_score,
            "quality_score": q_score,
            "target_parser": target,
            "fallback_triggered": decision["fallback_triggered"],
            "critical_issue": crit_issue,
            "reason": decision["reason"],
            "detailed_metrics": decision.get("detailed_metrics", {}),
            "elapsed_ms": total_time
        })
        
    print("=" * 115)
    
    # Save results to docs
    out_json = os.path.join(base_dir, "docs", "benchmark_14metrics_results.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print(f"\n[+] 14 Metrik Benchmark Sonuçları Kaydedildi: {out_json}")
    return results

if __name__ == "__main__":
    run_benchmark()
