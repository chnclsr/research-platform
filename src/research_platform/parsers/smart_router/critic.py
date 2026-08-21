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
import statistics
import time
import unicodedata
from typing import Dict, Any, List, Optional
from collections import Counter

from .ayarlar import AYAR

class PDFCritic:
    """14 Boyutlu Açık Kaynak Standartlarında Kalite ve Yönlendirme Denetleyicisi."""
    
    SENTENCE_END_PUNCT = ('.', '!', '?', ':', ';"', '."', "!'", "?'", '”', '’')
    HEADER_PREFIXES = ('#', '##', '###', '####', '#####', '######', '---', '***')
    # kod/formul blogu baslangici -- satir gecisi sayilmaz
    BLOK_ONEK = ('$$', '```')
    
    def __init__(self, fallback_threshold: float = AYAR.kalite_esik,
                 ceza: Optional[Dict[str, float]] = None):
        """`ceza`: sayfa skorunun ceza katsayilari (`SAYFA_CEZA` bicimi).

        Varsayilani modul sonundaki `SAYFA_CEZA` -- orasi da etkin profilden
        gelir. Burada `None` birakilip cagri aninda cozuluyor, cunku `SAYFA_CEZA`
        bu siniftan SONRA tanimli; varsayilan deger olarak yazilsa NameError olur.
        """
        self.fallback_threshold = fallback_threshold
        self.ceza = dict(ceza) if ceza else SAYFA_CEZA

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

    # ==================================================================
    # SAYFA BAZLI YOL  (plan E1 + D3)  —  evaluate() yukarida degismedi
    # ==================================================================

    def sayfa_metrikleri(self, markdown: str, *,
                         ham_karakter: int | None = None) -> Dict[str, Any]:
        """Tek sayfanin 12 metrigi.

        D7 geregi `running_header_leak_ratio` ve `repetition_loop_ratio`
        BURADA YOK — tekrar sorusu tek sayfada tanim geregi olculemez.
        D5 geregi `vector_table_drop` YOK — yerine giris kapisinin has_table'i.

        `ham_karakter` verilmezse `char_drop_ratio` **None** doner, 0 DEGIL:
        olculemeyen metrik olculmus gibi gosterilmez.
        """
        metin = markdown or ""
        karakter = len(metin.strip())
        kelime = len(metin.split())

        # --- D4: taban sayfanin kendi duz metni, markdown isaretleri dusulmus
        if ham_karakter is None:
            char_drop = None
        elif ham_karakter > 0:
            temiz = len(markdown_isaretsiz(metin))
            char_drop = max(0.0, 1.0 - temiz / ham_karakter)
        else:
            char_drop = 1.0 if karakter == 0 else 0.0

        # --- gibberish. evaluate()'in kuralindan FARKLI (orasi kasitli
        # degismedi, bkz. asagidaki not) -- burada Unicode kategorisi 'Sm'
        # (matematik sembolu: x . E . +-, ->, vb.) ve dogrulanmis birkac 'Po'
        # imi (dipnot/asal isareti) de mesru sayiliyor. Olculdu (2026-08-20,
        # entegrasyon_plani.md Bolum 17 madde #1): karantinada hala reddedilen
        # 20 sayfanin en az 19'unda "gibberish" denen karakterlerin tamami ya
        # da buyuk cogunlugu bu iki kategoriden -- Docling'in DOGRU cikardigi
        # sembolleri (x, elemani, bos kume, +-, ok, vb.) fast'in bozup ASCII'ye
        # indirgedigi (orn. "Context ->" -> "Context*!*") yerlerde heavy
        # cezalandiriliyordu. `Sk` (tek basina aksan/diaresiz isareti, orn.
        # Docling'in "d¨urfen" gibi ayirdigi umlaut) BILEREK disarida birakildi
        # -- bu gercek, kucuk bir cikarim kusuru, mesru sayilmiyor.
        MESRU_PO = '†‡′″‰·'
        bozuk_ascii = sum(1 for c in metin
                          if ord(c) > 127 and not c.isalnum()
                          and c not in 'çğıöşüÇĞİÖŞÜ’“”«»—–\n\r\t '
                          and unicodedata.category(c) != "Sm"
                          and c not in MESRU_PO)
        gibberish = bozuk_ascii / max(karakter, 1)

        # --- D6: orandan ikili varlik sinyaline
        unicode_bozuk = any(
            c == '\ufffd' or unicodedata.category(c) in ("Co", "Cs", "Cn")
            for c in metin
        )

        satir = [s.strip() for s in metin.splitlines() if s.strip()]
        gecis = max(len(satir) - 1, 1)
        dangling = kirik = 0
        for i in range(len(satir) - 1):
            simdi, sonra = satir[i], satir[i + 1]
            if simdi.startswith(self.HEADER_PREFIXES) or sonra.startswith(self.HEADER_PREFIXES):
                continue
            if simdi.startswith('|') or sonra.startswith('|') or simdi.startswith(self.BLOK_ONEK):
                continue
            if not simdi.endswith(self.SENTENCE_END_PUNCT):
                ilk = sonra[0] if sonra else ''
                if ilk.isupper():
                    dangling += 1
                elif ilk.islower():
                    kirik += 1

        tire = re.findall(r'\b[a-zA-ZçğıöşüÇĞİÖŞÜ]{2,}-\s+[a-zA-ZçğıöşüÇĞİÖŞÜ]{2,}\b', metin)
        tire_yogunluk = (len(tire) / max(kelime, 1)) * 1000

        oksuz = re.findall(r'(?:^|\n)\s*(\d{1,3}|<u>\d{1,3}</u>)\s*(?:\n|$)', metin)
        oksuz_yogunluk = (len(oksuz) / max(kelime, 1)) * 1000

        tek_dolar = len(re.findall(r'(?<!\$)\$(?!\$)', metin))
        cift_dolar = len(re.findall(r'\$\$', metin))
        env_ac = len(re.findall(r'\\begin\{[a-zA-Z*]+\}', metin))
        env_kap = len(re.findall(r'\\end\{[a-zA-Z*]+\}', metin))
        latex = (tek_dolar % 2) + (cift_dolar % 2) + abs(env_ac - env_kap)

        tablo_satir = [s for s in satir if s.startswith('|') and s.endswith('|')]
        tablo_duzensiz = 0.0
        if len(tablo_satir) >= 2:
            sutun = [s.count('|') for s in tablo_satir]
            mod = Counter(sutun).most_common(1)[0][0]
            tablo_duzensiz = sum(1 for c in sutun if c != mod) / len(tablo_satir)

        seviye = [len(m.group(1)) for s in satir if (m := re.match(r'^(#{1,6})\s+', s))]
        atlama = 0
        for k in range(len(seviye) - 1):
            fark = seviye[k + 1] - seviye[k]
            if fark > 1:
                atlama += fark - 1
        baslik_tutarsiz = atlama / max(len(seviye), 1) if seviye else 0.0

        return {
            "karakter": karakter,
            "kelime": kelime,
            "char_drop_ratio": None if char_drop is None else round(char_drop, 4),
            "gibberish_ratio": round(gibberish, 4),
            "unicode_bozuk": unicode_bozuk,
            "dangling_sentence_ratio": round(dangling / gecis, 4),
            "broken_line_ratio": round(kirik / gecis, 4),
            "hyphen_density_per_1k_words": round(tire_yogunluk, 2),
            "orphan_density_per_1k_words": round(oksuz_yogunluk, 2),
            "latex_imbalance": latex,
            "table_irregularity_ratio": round(tablo_duzensiz, 4),
            "heading_incoherence_ratio": round(baslik_tutarsiz, 4),
        }

    def sayfa_skoru(self, m: Dict[str, Any], *, needs_ocr: bool = False,
                    bos: bool = False) -> Dict[str, Any]:
        """Sayfa kalite skoru (0-100) ve kritik teshis.

        BOS sayfada skor **None** doner, 0 DEGIL: bos sayfanin olculecek bir
        kalitesi yoktur. Sifir vermek onu "en kotu sayfa" yapip agir motora
        gonderirdi. (Plan bunu ongormuyordu; bos sayfa ayrimi eklendi.)
        """
        if bos:
            return {"quality_score": None, "critical_issue": "BOS_SAYFA",
                    "olculemedi": True, "cezalar": {}}

        C = self.ceza
        skor = 100.0
        cd = m.get("char_drop_ratio")

        # Her ceza `ceza()` uzerinden gecer: skoru dusurur VE dokume yazilir.
        # Dokum teshis icindir -- 2026-08-21'e kadar yalniz toplam skor
        # gorunuyordu, bu yuzden "sayfa neden low_quality" sorusu ancak kod
        # okunarak cevaplanabiliyordu. Olculdu: yalniz low_quality yuzunden agir
        # motora giden 26 sayfanin 25'inde TEK ceza dangling'di (rapor O.8.2).
        cezalar: Dict[str, float] = {}

        def ceza(ad: str, miktar: float) -> None:
            nonlocal skor
            if miktar > 0:
                cezalar[ad] = round(cezalar.get(ad, 0.0) + miktar, 2)
                skor -= miktar

        if cd is not None and cd > C["char_drop_esik"]:
            ceza("char_drop", min((cd - C["char_drop_esik"]) * C["char_drop_kat"],
                                  C["char_drop_tavan"]))
        if needs_ocr:
            ceza("scanned", C["scanned"])
        if m["gibberish_ratio"] > C["gibberish_esik"]:
            ceza("gibberish", min(m["gibberish_ratio"] * C["gibberish_kat"],
                                  C["gibberish_tavan"]))
        if m["unicode_bozuk"]:
            ceza("unicode_bozuk", C["unicode_bozuk"])
        if m["dangling_sentence_ratio"] > C["dangling_esik"]:
            ceza("dangling",
                 min((m["dangling_sentence_ratio"] - C["dangling_esik"]) * C["dangling_kat"],
                     C["dangling_tavan"]))
        if m["broken_line_ratio"] > C["broken_esik"]:
            ceza("broken",
                 min((m["broken_line_ratio"] - C["broken_esik"]) * C["broken_kat"],
                     C["broken_tavan"]))
        if m["hyphen_density_per_1k_words"] > C["hyphen_esik"]:
            ceza("hyphen",
                 min((m["hyphen_density_per_1k_words"] - C["hyphen_esik"]) * C["hyphen_kat"],
                     C["hyphen_tavan"]))
        if m["orphan_density_per_1k_words"] > C["orphan_esik"]:
            ceza("orphan",
                 min((m["orphan_density_per_1k_words"] - C["orphan_esik"]) * C["orphan_kat"],
                     C["orphan_tavan"]))
        if m["latex_imbalance"] > 0:
            ceza("latex", min(m["latex_imbalance"] * C["latex_kat"], C["latex_tavan"]))
        if m["table_irregularity_ratio"] > C["tablo_duzensiz_esik"]:
            ceza("tablo_duzensiz",
                 min(m["table_irregularity_ratio"] * C["tablo_duzensiz_kat"],
                     C["tablo_duzensiz_tavan"]))
        if m["heading_incoherence_ratio"] > C["baslik_tutarsiz_esik"]:
            ceza("baslik_tutarsiz",
                 min(m["heading_incoherence_ratio"] * C["baslik_tutarsiz_kat"],
                     C["baslik_tutarsiz_tavan"]))

        # Sayfada hic metin yok ama bos da degil (gorsel/cizim var) -> metin dusmus
        if m["karakter"] < 30:
            return {"quality_score": 0.0, "critical_issue": "TOTAL_TEXT_DROPPED",
                    "olculemedi": False, "cezalar": cezalar}

        kritik = "NONE"
        if needs_ocr:
            kritik = "SCANNED_NEEDS_OCR"
        elif cd is not None and cd > 0.35:
            kritik = "TEXT_DROPPED_GAP_%d%%" % round(cd * 100)
        elif m["gibberish_ratio"] > 0.08 or m["unicode_bozuk"]:
            kritik = "CID_FONT_UNICODE_CORRUPTION"
        elif m["latex_imbalance"] >= 4:
            kritik = "MATH_FORMULA_HEAVY"
        elif m["dangling_sentence_ratio"] > 0.16:
            kritik = "TWO_COLUMN_CROSS_JUMP"

        return {"quality_score": max(0.0, min(100.0, round(skor, 1))),
                "critical_issue": kritik, "olculemedi": False,
                # Hangi cezanin ne kadar dusurdugu. Skoru DEGISTIRMEZ; yalniz
                # "bu sayfa neden dusuk puan aldi" sorusunu cevaplar.
                "cezalar": cezalar}

    def belge_metrikleri(self, tam_metin: str) -> Dict[str, Any]:
        """D7: yalniz BELGE duzeyinde olculebilen iki metrik."""
        satir = [s.strip() for s in tam_metin.splitlines() if s.strip()]
        sayim = Counter(satir)
        tekrar = sum(c for s, c in sayim.items()
                     if c >= 3 and len(s) > 8 and not s.startswith('|'))
        header_leak = tekrar / max(len(satir), 1)

        kelime = tam_metin.split()
        if len(kelime) >= 8:
            dortlu = [" ".join(kelime[j:j + 4]) for j in range(len(kelime) - 3)]
            sayim4 = Counter(dortlu)
            dongu = sum(c - 1 for c in sayim4.values() if c >= 3)
            tekrar_orani = dongu / max(len(dortlu), 1)
        else:
            tekrar_orani = 0.0

        return {"running_header_leak_ratio": round(header_leak, 4),
                "repetition_loop_ratio": round(tekrar_orani, 4)}

    def evaluate_pages(self, router_json: Dict[str, Any],
                       pages: List[tuple], *,
                       ham_karakter: Dict[int, int] | None = None,
                       bayraklar: Dict[int, Dict[str, Any]] | None = None
                       ) -> Dict[str, Any]:
        """Sayfa bazli degerlendirme (plan E1 + D3).

        pages        : [(sayfa_no, markdown)] — sayfa_no 1-TABANLI (plan E5)
        ham_karakter : {sayfa_no: PyMuPDF duz metin karakter sayisi} — D4 icin.
                       Verilmezse char_drop_ratio "olculemedi" (None) olur.
        bayraklar    : {sayfa_no: {needs_ocr, has_table, has_figure, bos}} —
                       giris kapisindan (plan E2). Verilmezse hepsi False.

        Belge skoru SAYFA skorlarindan turetilir, tersi degil (plan D3).
        Toplama bicimi (medyan) KALIBRE EDILMEDI — D12'nin isi.
        """
        t0 = time.perf_counter()
        ham_karakter = ham_karakter or {}
        bayraklar = bayraklar or {}

        sayfa_sonuc: List[Dict[str, Any]] = []
        for no, md in pages:
            b = bayraklar.get(no, {})
            m = self.sayfa_metrikleri(md, ham_karakter=ham_karakter.get(no))
            s = self.sayfa_skoru(m, needs_ocr=bool(b.get("needs_ocr")),
                                 bos=bool(b.get("bos")))
            sayfa_sonuc.append({
                "sayfa_no": no,
                "quality_score": s["quality_score"],
                # Teshis: skoru hangi ceza ne kadar dusurdu. Karara girmez.
                "cezalar": s.get("cezalar") or {},
                "critical_issue": s["critical_issue"],
                "olculemedi": s["olculemedi"],
                "needs_ocr": bool(b.get("needs_ocr")),
                "has_table": bool(b.get("has_table")),
                "has_figure": bool(b.get("has_figure")),
                "metrikler": m,
            })

        tam_metin = "\n\n".join(md for _, md in pages)
        belge_m = self.belge_metrikleri(tam_metin)

        olculen = [s["quality_score"] for s in sayfa_sonuc
                   if s["quality_score"] is not None]
        if olculen:
            belge_skor = statistics.median(olculen)
            if belge_m["running_header_leak_ratio"] > 0.04:
                belge_skor -= min(
                    (belge_m["running_header_leak_ratio"] - 0.04) * 150.0, 15.0)
            if belge_m["repetition_loop_ratio"] > 0.03:
                belge_skor -= min(
                    (belge_m["repetition_loop_ratio"] - 0.03) * 250.0, 20.0)
            belge_skor = max(0.0, min(100.0, round(belge_skor, 1)))
        else:
            belge_skor = None  # her sayfa olculemedi

        return {
            "pdf_path": router_json.get("pdf_path", "unknown.pdf"),
            "sayfalar": sayfa_sonuc,
            "belge": {
                "quality_score": belge_skor,
                "toplama": "sayfa skorlarinin medyani (KALIBRE EDILMEDI, plan D12)",
                "sayfa_sayisi": len(sayfa_sonuc),
                "olculemeyen_sayfa": sum(1 for s in sayfa_sonuc if s["olculemedi"]),
                "esik_alti_sayfa": sum(1 for s in sayfa_sonuc
                                       if s["quality_score"] is not None
                                       and s["quality_score"] < self.fallback_threshold),
                "belge_metrikleri": belge_m,
            },
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        }

# ==========================================================================
# SAYFA BAZLI DEGERLENDIRME  —  plan E1 + D3, metrik onarimlari D4·D5·D6·D7
# ==========================================================================
#
# `evaluate()` YUKARIDA DEGISMEDI. Plan E1: "evaluate() korunur, yanina sayfa
# listesi alan bir metot eklenir." Karsilastirilabilirlik icin eski yol aynen
# duruyor; asagidaki her sey ek.
#
# Neler degisti (hepsinin gerekcesi olculdu):
#
#   D4  char_drop_ratio  — eski taban router'in raw_pdf_chars'iydi, iki taraf da
#       PyMuPDF'ten geliyordu, 8/8 belgede 0,0 cikiyordu. Yeni taban SAYFANIN
#       kendi get_text("text") uzunlugu, markdown isaretleri dusulerek.
#       Olculdu: 261 sayfanin 14'unu isaretledi (src/critic_onarim_denemesi.py).
#
#   D5  vector_table_drop  — CIKARILDI. "Cok cizim ve az kelime" kurali; iki
#       kosul ters korele, kesisim 261 sayfada SIFIR. Esik gevsetmeyle de
#       kurtarilamadi (en iyi deneme duyarlilik 0,13). Yerine giris kapisinin
#       has_table bayragi geliyor (duyarlilik 0,93 / 0,98).
#
#   D6  unicode_noise_ratio  — orandan IKILI VARLIK sinyaline dondu. Eski esik
#       0,005; depodaki tum parser ciktilarinda en kotu gozlem 0,00444, yani
#       esik hicbir zaman tetiklenmiyordu. inspector 461 sayfada tek bozuk
#       karakter uretmedi -> ikili sinyal onda sifir yanlis alarm verir.
#
#   D7  running_header_leak_ratio ve repetition_loop_ratio SAYFA DUZEYINDE
#       OLCULEMEZ — "ayni satir kac kez tekrarliyor" sorusu birden fazla sayfa
#       gerektirir. Bu ikisi BELGE duzeyinde kalir, kalan 12 metrik sayfada.
#
# ESIKLER KALIBRE EDILMEDI. Asagidaki CEZA/ESIK degerleri `evaluate()`'in
# duz metne gore ayarlanmis degerlerinden tasindi. Plan D12 bunlarin markdown
# ve SAYFA olceginde yeniden kalibre edilmesini sart kosuyor; sayfa basina
# metin az oldugu icin oranlarin varyansi belge olcegindekinden yuksek.
# Kalibrasyon C1 (E11 dogrulama kosusu) yapilmadan yapilamaz.

MD_ISARET = re.compile(r"[#|*`_>\-]+")

#: D7 geregi yalniz belge duzeyinde hesaplanabilen metrikler
BELGE_DUZEYI_METRIKLER = ("running_header_leak_ratio", "repetition_loop_ratio")

#: Sayfa skorunun ceza katsayilari. Degerler `config/smart_router.yaml` ->
#: `critic_ceza`, gomulu varsayilanlar `ayarlar.VARSAYILAN`. Kopya alinir: `AYAR`
#: dondurulmus ama sozlugu degil, burada yapilan bir degisiklik etkin profili de
#: degistirir ve `esik_version` yalan olurdu.
SAYFA_CEZA: Dict[str, float] = dict(AYAR.critic_ceza)


def markdown_isaretsiz(metin: str) -> str:
    """Markdown isaretlerini dusurup bosluklari tekilestirir (D4 tabani icin).

    src/critic_onarim_denemesi.py'de olculen `md_temiz` ile AYNI: taban
    karsilastirmasi olcumle tutarli kalsin diye birebir tasindi.
    """
    return re.sub(r"\s+", " ", MD_ISARET.sub("", metin)).strip()
