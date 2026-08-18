#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
critic.py - 14 Boyutlu Enterprise PDF Critic & Quality Evaluator
================================================================
Açık kaynak standartları (Docling, Marker, MinerU, Nougat, DocLayNet)
referans alınarak geliştirilmiş, sıfır etiketli (zero-shot) okuma kalitesi
ve anomali tespit motoru.

14 TEMEL BOYUT:
  [A. METİN KAYIP & ATLAMALAR]
    1. Char/Word Density Gap (Ham PDF vs Çıktı Karakter Kaybı)
    2. Scanned / OCR Proxy (Görsel ağırlıklı / Taranmış Sayfa)
    3. Vector/Drawing Drop (Tablo ve Vektör Çizimlerinin Yutulması)

  [B. FONT & KODLAMA BOZULMALARI]
    4. CID Font & Glif Bozulması (Gibberish Ratio)
    5. Unicode & Control Noise (Marker: \ufffd, \u200b, görünmez ve kontrol karakterleri)

  [C. DİLBİLGİSİ & OKUMA SIRASI]
    6. Two-Column Dangling Cuts (İki Sütun Çaprazlama Atlama)
    7. Broken Lines (Paragraf Kırık Satır Bütünlüğü)
    8. Hyphenation Artifacts (Asılı Kalan Satır Sonu Tireleri)
    9. Orphan Footnotes & Numbers (Dipnot ve Sayfa No Sızıntısı)
    10. Running Header / Footer Leakage (Docling: Tekrarlayan Üst/Alt Başlık Sızıntısı)
    11. Repetition Loops & Degeneration (Nougat: N-gram Tekrar Döngüleri / Halüsinasyon)

  [D. FORMÜL & TABLO & YAPI BÜTÜNLÜĞÜ]
    12. LaTeX & Math Delimiter Balance (MinerU: Açık Kalan $, $$, parantez ve ortamlar)
    13. Markdown Table Structural Integrity (Docling-eval: Bozuk Tablo Sütun Dağılımı)
    14. Heading Hierarchy Coherence (DocLayNet: Başlık Ağacı Düzensizliği ve Derinlik Atlama)
"""

import os
import re
import time
from typing import Dict, Any, List
from collections import Counter

class PDFCritic:
    """14 Boyutlu Açık Kaynak Standartlarında Kalite ve Yönlendirme Denetleyicisi."""
    
    SENTENCE_END_PUNCT = ('.', '!', '?', ':', ';"', '."', "!'", "?'", '”', '’')
    HEADER_PREFIXES = ('#', '##', '###', '####', '#####', '######', '---', '***')
    
    def __init__(self, fallback_threshold: float = 75.0):
        self.fallback_threshold = fallback_threshold

    def evaluate(self, router_json: Dict[str, Any], inspector_text: str) -> Dict[str, Any]:
        start_time = time.perf_counter()
        
        # -------------------------------------------------------------
        # 0. Girdilerin Hazırlanması
        # -------------------------------------------------------------
        features = router_json.get("features", {})
        is_scanned = router_json.get("is_scanned", False)
        struct_score = router_json.get("structural_score", 0.0)
        pdf_path = router_json.get("pdf_path", "unknown.pdf")
        
        raw_pdf_chars = features.get("raw_pdf_chars", 0)
        raw_pdf_words = features.get("raw_pdf_words", 0)
        total_pages = max(int(features.get("total_pages", 1)), 1)
        vector_drawings_per_page = features.get("orthogonal_lines_per_page", 0.0) + features.get("bezier_curves_per_page", 0.0)
        
        insp_chars = len(inspector_text.strip()) if inspector_text else 0
        insp_words = len(inspector_text.split()) if inspector_text else 0
        
        # Hızlı Hata (Boş dönme durumu)
        if insp_chars < 30:
            target = "miner-VL" if is_scanned else "docling"
            reason = "Taranmış belge (OCR/miner-VL gerekli)" if is_scanned else "Metin tamamen atlandı / okunamadı"
            return {
                "pdf_path": pdf_path,
                "target_parser": target,
                "fallback_triggered": True,
                "quality_score": 0.0,
                "reason": reason,
                "critical_issue": "TOTAL_TEXT_DROPPED",
                "detailed_metrics": {"char_drop_ratio": 1.0, "is_scanned": is_scanned},
                "elapsed_ms": round((time.perf_counter() - start_time) * 1000, 2)
            }

        # -------------------------------------------------------------
        # [A. METİN KAYIP & ATLAMALAR]
        # -------------------------------------------------------------
        # 1. Char Drop Gap
        char_drop_ratio = 0.0
        if raw_pdf_chars > 0:
            char_drop_ratio = max(0.0, 1.0 - (insp_chars / raw_pdf_chars))

        # 2. Scanned / OCR Proxy
        # is_scanned zaten router'dan belirlendi.

        # 3. Vector/Drawing Drop
        vector_table_drop = (vector_drawings_per_page > 80.0) and (insp_words < (60 * total_pages))

        # -------------------------------------------------------------
        # [B. FONT & KODLAMA BOZULMALARI]
        # -------------------------------------------------------------
        # 4. Gibberish Ratio (Non-ASCII ve bozuk glifler)
        non_ascii_chars = sum(1 for c in inspector_text if ord(c) > 127 and not c.isalnum() and c not in 'çğıöşüÇĞİÖŞÜ’“”«»—–\n\r\t ')
        gibberish_ratio = non_ascii_chars / max(insp_chars, 1)

        # 5. Unicode & Control Noise (Marker: \ufffd, \u200b, \x00-\x1f vb.)
        control_and_replacement_chars = sum(
            1 for c in inspector_text 
            if c in ('\ufffd', '\u200b', '\u200c', '\u200d', '\ufeff') or (ord(c) < 32 and c not in '\n\r\t')
        )
        unicode_noise_ratio = control_and_replacement_chars / max(insp_chars, 1)

        # -------------------------------------------------------------
        # [C. DİLBİLGİSİ & OKUMA SIRASI]
        # -------------------------------------------------------------
        lines = [line.strip() for line in inspector_text.splitlines() if line.strip()]
        total_transitions = max(len(lines) - 1, 1)
        dangling_cuts = 0
        broken_lines = 0

        for i in range(len(lines) - 1):
            curr_l, next_l = lines[i], lines[i + 1]
            if curr_l.startswith(self.HEADER_PREFIXES) or next_l.startswith(self.HEADER_PREFIXES):
                continue
            if curr_l.startswith('|') or next_l.startswith('|') or curr_l.startswith(('$$', '```')):
                continue

            if not curr_l.endswith(self.SENTENCE_END_PUNCT):
                first_char = next_l[0] if next_l else ''
                if first_char.isupper():
                    dangling_cuts += 1
                elif first_char.islower():
                    broken_lines += 1

        # 6. Two-Column Dangling Ratio
        dangling_ratio = dangling_cuts / total_transitions

        # 7. Broken Line Ratio
        broken_line_ratio = broken_lines / total_transitions

        # 8. Hyphenation Artifacts
        hyphen_matches = re.findall(r'\b[a-zA-ZçğıöşüÇĞİÖŞÜ]{2,}-\s+[a-zA-ZçğıöşüÇĞİÖŞÜ]{2,}\b', inspector_text)
        hyphen_density = (len(hyphen_matches) / max(insp_words, 1)) * 1000

        # 9. Orphan Footnotes & Numbers
        orphan_num_matches = re.findall(r'(?:^|\n)\s*(\d{1,3}|<u>\d{1,3}</u>)\s*(?:\n|$)', inspector_text)
        orphan_count = len(orphan_num_matches)

        # 10. Running Header / Footer Leakage (Docling: Tekrarlayan Başlık/Altlık Sızıntısı)
        line_counts = Counter(lines)
        repeated_headers = sum(count for line, count in line_counts.items() if count >= 3 and len(line) > 8 and not line.startswith('|'))
        running_header_leak_ratio = repeated_headers / max(len(lines), 1)

        # 11. Repetition Loops & Degeneration (Nougat: 4-gram döngüleri)
        words_list = inspector_text.split()
        if len(words_list) >= 8:
            four_grams = [" ".join(words_list[j:j+4]) for j in range(len(words_list)-3)]
            four_gram_counts = Counter(four_grams)
            repetition_loops = sum(c - 1 for c in four_gram_counts.values() if c >= 3)
            repetition_loop_ratio = repetition_loops / max(len(four_grams), 1)
        else:
            repetition_loop_ratio = 0.0

        # -------------------------------------------------------------
        # [D. FORMÜL & TABLO & YAPI BÜTÜNLÜĞÜ]
        # -------------------------------------------------------------
        # 12. LaTeX & Math Delimiter Balance (MinerU)
        single_dollar_count = len(re.findall(r'(?<!\$)\$(?!\$)', inspector_text))
        double_dollar_count = len(re.findall(r'\$\$', inspector_text))
        latex_open_env = len(re.findall(r'\\begin\{[a-zA-Z*]+\}', inspector_text))
        latex_close_env = len(re.findall(r'\\end\{[a-zA-Z*]+\}', inspector_text))
        
        latex_imbalance = (single_dollar_count % 2) + (double_dollar_count % 2) + abs(latex_open_env - latex_close_env)

        # 13. Markdown Table Structural Integrity (Docling-eval)
        table_lines = [l for l in lines if l.startswith('|') and l.endswith('|')]
        table_irregular_rows = 0
        if len(table_lines) >= 2:
            col_counts = [l.count('|') for l in table_lines]
            mode_cols = Counter(col_counts).most_common(1)[0][0]
            table_irregular_rows = sum(1 for c in col_counts if c != mode_cols)
        table_irregularity_ratio = table_irregular_rows / max(len(table_lines), 1) if table_lines else 0.0

        # 14. Heading Hierarchy Coherence (DocLayNet)
        heading_levels = [len(m.group(1)) for l in lines if (m := re.match(r'^(#{1,6})\s+', l))]
        heading_jumps = 0
        for k in range(len(heading_levels) - 1):
            diff = heading_levels[k+1] - heading_levels[k]
            if diff > 1:  # Örneğin H1'den direkt H3 veya H4'e atlama
                heading_jumps += (diff - 1)
        heading_incoherence_ratio = heading_jumps / max(len(heading_levels), 1) if heading_levels else 0.0

        # -------------------------------------------------------------
        # GENEL KALİTE SKORU HESAPLAMA (0 - 100) (Kalibre Edilmiş Açık Kaynak Ağırlıkları)
        # -------------------------------------------------------------
        score = 100.0

        # [A. METİN KAYIP & ATLAMALAR]
        if char_drop_ratio > 0.10:
            score -= min((char_drop_ratio - 0.10) * 120.0, 45.0)
        if is_scanned:
            score -= 60.0
        if vector_table_drop:
            score -= 30.0

        # [B. FONT & UNICODE BOZULMALARI]
        if gibberish_ratio > 0.02:
            score -= min(gibberish_ratio * 300.0, 25.0)
        if unicode_noise_ratio > 0.005:
            score -= min(unicode_noise_ratio * 400.0, 20.0)

        # [C. DİLBİLGİSİ & AKIŞ (Eşik Değerli)]
        # İki sütun çaprazlama (0.08 üstü tehlikeli)
        if dangling_ratio > 0.08:
            score -= min((dangling_ratio - 0.08) * 160.0, 35.0)
            
        # Kırık satır (PDF doğal satır kayması 0.30'a kadar normaldir)
        if broken_line_ratio > 0.35:
            score -= min((broken_line_ratio - 0.35) * 50.0, 15.0)
            
        # Asılı tireleme
        if hyphen_density > 3.0:
            score -= min((hyphen_density - 3.0) * 1.5, 15.0)
            
        # Dipnot ve sayfa no sızıntısı (1000 kelime başına yoğunluk)
        orphan_density = (orphan_count / max(insp_words, 1)) * 1000
        if orphan_density > 5.0:
            score -= min((orphan_density - 5.0) * 1.0, 10.0)
            
        # Running Header sızıntısı
        if running_header_leak_ratio > 0.04:
            score -= min((running_header_leak_ratio - 0.04) * 150.0, 15.0)
            
        # Repetition Loops
        if repetition_loop_ratio > 0.03:
            score -= min((repetition_loop_ratio - 0.03) * 250.0, 20.0)

        # [D. FORMÜL, TABLO VE HİYERARŞİ]
        if latex_imbalance > 0:
            score -= min(latex_imbalance * 5.0, 20.0)
        if table_irregularity_ratio > 0.15:
            score -= min(table_irregularity_ratio * 40.0, 15.0)
        if heading_incoherence_ratio > 0.20:
            score -= min(heading_incoherence_ratio * 30.0, 10.0)

        quality_score = max(0.0, min(100.0, round(score, 1)))

        # -------------------------------------------------------------
        # Kritik Teşhis ve Yönlendirme
        # -------------------------------------------------------------
        critical_issue = "NONE"
        if is_scanned:
            critical_issue = "SCANNED_NEEDS_OCR"
        elif char_drop_ratio > 0.35:
            critical_issue = f"TEXT_DROPPED_GAP_{char_drop_ratio*100:.0f}%"
        elif gibberish_ratio > 0.08 or unicode_noise_ratio > 0.02:
            critical_issue = "CID_FONT_UNICODE_CORRUPTION"
        elif latex_imbalance >= 4 or struct_score >= 180.0:
            critical_issue = "MATH_FORMULA_HEAVY"
        elif dangling_ratio > 0.16:
            critical_issue = "TWO_COLUMN_CROSS_JUMP"
        elif running_header_leak_ratio > 0.08:
            critical_issue = "HEADER_FOOTER_BLEED"

        fallback_triggered = False
        target_parser = "pdf-inspector"
        reason = f"pdf-inspector akışı başarılı (14 Metrik Kalite: {quality_score}/100)"

        if quality_score < self.fallback_threshold or critical_issue != "NONE":
            fallback_triggered = True
            if critical_issue in ("SCANNED_NEEDS_OCR", "CID_FONT_UNICODE_CORRUPTION", "MATH_FORMULA_HEAVY") or struct_score >= 150.0:
                target_parser = "miner-VL"
            else:
                target_parser = "docling"
            reason = f"Kalite yetersiz / Bozulma [{critical_issue}] (Kalite: {quality_score}/100) -> Fallback: {target_parser}"

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "pdf_path": pdf_path,
            "target_parser": target_parser,
            "fallback_triggered": fallback_triggered,
            "quality_score": quality_score,
            "structural_score": struct_score,
            "reason": reason,
            "critical_issue": critical_issue,
            "detailed_metrics": {
                # A. Metin Kayıp
                "char_drop_ratio": round(char_drop_ratio, 4),
                "is_scanned": is_scanned,
                "vector_table_drop": vector_table_drop,
                # B. Font & Unicode
                "gibberish_ratio": round(gibberish_ratio, 4),
                "unicode_noise_ratio": round(unicode_noise_ratio, 4),
                # C. Dilbilgisi & Okuma Sırası
                "dangling_sentence_ratio": round(dangling_ratio, 4),
                "broken_line_ratio": round(broken_line_ratio, 4),
                "hyphen_density_per_1k_words": round(hyphen_density, 2),
                "orphan_artifacts": orphan_count,
                "orphan_density_per_1k_words": round(orphan_density, 2),
                "running_header_leak_ratio": round(running_header_leak_ratio, 4),
                "repetition_loop_ratio": round(repetition_loop_ratio, 4),
                # D. Formül & Tablo & Başlık
                "latex_imbalance": latex_imbalance,
                "table_irregularity_ratio": round(table_irregularity_ratio, 4),
                "heading_incoherence_ratio": round(heading_incoherence_ratio, 4)
            },
            "elapsed_ms": elapsed_ms
        }
