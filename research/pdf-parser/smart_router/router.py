#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
router.py
=========
PDF dosyasının yapısal özelliklerini (17 feature) çıkartır.
Çıktı olarak sadece bu analiz verilerini içeren bir JSON/Dict objesi döner.
"""

import fitz
import numpy as np
import re
from typing import Dict, Tuple

class PDFRouter:
    """PDF için 17 yapısal özelliği çıkarır ve karmaşıklık sınıfını belirler."""
    
    def __init__(self):
        # 17 özellik ağırlıkları
        self.feature_weights = {
            "cid_font_ratio": 0.6,
            "font_size_std": 0.3,
            "non_ascii_gibberish_ratio": 0.5,
            "avg_word_length": 0.3,
            "math_symbol_density": 0.5,
            "x0_coord_std": 0.4,
            "bbox_overlap_count_per_page": 0.7,
            "whitespace_ratio": 0.3,
            "orthogonal_lines_per_page": 0.5,
            "bezier_curves_per_page": 0.5,
            "filled_shapes_per_page": 0.4,
            "image_coverage_ratio": 0.7,
            "image_count_per_page": 0.6,
            "is_scanned_proxy": 1.0,
            "rotation_count": 0.3,
            "annotations_per_page": 0.3,
            "total_pages": 0.4,
        }
    
    def extract_features(self, pdf_path: str) -> Dict[str, float]:
        """PDF'den 17 özelliği çıkarır."""
        doc = fitz.open(pdf_path)
        
        total_pages = len(doc)
        chars, words, whitespaces = 0, 0, 0
        cid_fonts, total_spans = 0, 0
        font_sizes = []
        x0_coords = []
        overlap_boxes = 0
        orthogonal_lines = 0
        bezier_curves = 0
        drawings_filled = 0
        total_img_area = 0.0
        total_images = 0
        math_symbols = 0
        non_ascii = 0
        rotations = set()
        annotations = 0
        
        math_regex = re.compile(r'[+-=<>*/^_\u2211\u222b\u221a\u00b1\u2260\u2248\u221e\u03b1-\u03c9\u0391-\u03a9]')
        
        for page in doc:
            rotations.add(page.rotation)
            rect = page.rect
            page_area = max(rect.width * rect.height, 1.0)
            annotations += len(list(page.annots() or []))
            
            # Cizimler
            drawings = page.get_drawings()
            for draw in drawings:
                if draw.get("fill") is not None:
                    drawings_filled += 1
                for item in draw["items"]:
                    if item[0] == "l":  # Duz cizgi
                        p1, p2 = item[1], item[2]
                        if abs(p1.x - p2.x) < 1.0 or abs(p1.y - p2.y) < 1.0:
                            orthogonal_lines += 1
                    elif item[0] == "c":  # Bezier egrisi
                        bezier_curves += 1
            
            # Gorseller
            img_list = page.get_images()
            total_images += len(img_list)
            for img in img_list:
                try:
                    bbox = page.get_image_bbox(img)
                    total_img_area += (bbox.width * bbox.height) / page_area
                except Exception:
                    total_img_area += 0.05
            
            # Metin ve Font
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])
            bboxes = []
            
            for b in blocks:
                if b.get("type") == 0:  # Metin bloku
                    bboxes.append(b["bbox"])
                    x0_coords.append(b["bbox"][0])
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            total_spans += 1
                            text = span["text"]
                            chars += len(text)
                            whitespaces += text.count(" ")
                            words += len(text.split())
                            font_sizes.append(span["size"])
                            
                            if "Identity-H" in span["font"] or "CID" in span["font"]:
                                cid_fonts += 1
                            
                            math_symbols += len(math_regex.findall(text))
                            non_ascii += sum(1 for c in text if ord(c) > 127 and not c.isalnum())
            
            for i in range(len(bboxes)):
                for j in range(i + 1, len(bboxes)):
                    r1, r2 = fitz.Rect(bboxes[i]), fitz.Rect(bboxes[j])
                    if r1.intersects(r2) and not r1.contains(r2):
                        overlap_boxes += 1
        
        doc.close()
        
        font_size_std = float(np.std(font_sizes)) if font_sizes else 0.0
        x0_std = float(np.std(x0_coords)) if x0_coords else 0.0
        avg_chars = chars / max(total_pages, 1)
        
        return {
            "cid_font_ratio": cid_fonts / max(total_spans, 1),
            "font_size_std": font_size_std,
            "non_ascii_gibberish_ratio": non_ascii / max(chars, 1),
            "avg_word_length": chars / max(words, 1),
            "math_symbol_density": math_symbols / max(chars, 1),
            "x0_coord_std": x0_std,
            "bbox_overlap_count_per_page": overlap_boxes / max(total_pages, 1),
            "whitespace_ratio": whitespaces / max(chars, 1),
            "orthogonal_lines_per_page": orthogonal_lines / max(total_pages, 1),
            "bezier_curves_per_page": bezier_curves / max(total_pages, 1),
            "filled_shapes_per_page": drawings_filled / max(total_pages, 1),
            "image_coverage_ratio": total_img_area / max(total_pages, 1),
            "image_count_per_page": total_images / max(total_pages, 1),
            "is_scanned_proxy": 1.0 if (avg_chars < 60 and total_images > 0) else 0.0,
            "rotation_count": len(rotations),
            "annotations_per_page": annotations / max(total_pages, 1),
            "total_pages": total_pages,
            "raw_pdf_chars": chars,
            "raw_pdf_words": words
        }
    
    def normalize(self, val: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
        if max_val == min_val:
            return 50.0
        norm = (val - min_val) / (max_val - min_val) * 100.0
        return max(0.0, min(100.0, norm))
        
    def compute_total_score(self, features: Dict[str, float]) -> Tuple[float, Dict[str, Dict]]:
        score = 0.0
        components = {}
        
        for feat, weight in self.feature_weights.items():
            if feat not in features:
                continue
            
            try:
                val = features[feat]
                norm_val = self.normalize(val, 0.0, 100.0)
                contribution = norm_val * weight / 100.0 * 100.0
                score += contribution
                components[feat] = {
                    "val": val,
                    "norm": round(norm_val, 2),
                    "weight": weight,
                    "contribution": round(contribution, 2)
                }
            except (ValueError, TypeError):
                components[feat] = {"val": features[feat], "error": True}
        
        return round(score, 1), components
    
    def route_document(self, pdf_path: str) -> Dict:
        """
        Ana Orkestrasyon Metodu:
        1. Yapısal metrikleri hesaplar.
        2. Inspector'dan düz metni çeker.
        3. Critic'e danışarak nihai kararı verir.
        Ajanlar direkt bu metodu çağırır.
        """
        # 1. Router'ın kendi işi: Yapısal Analiz
        features = self.extract_features(pdf_path)
        total_score, components = self.compute_total_score(features)
        
        is_scanned = features.get("is_scanned_proxy", 0.0) >= 0.8
        
        if is_scanned:
            category = "high_complexity"
        elif total_score >= 120.0:
            category = "high_complexity"
        elif total_score >= 80.0:
            category = "medium_complexity"
        else:
            category = "low_complexity"
            
        router_json = {
            "pdf_path": pdf_path,
            "structural_score": total_score,
            "category": category,
            "is_scanned": is_scanned,
            "features": features,
            "component_contributions": components
        }
        
        # 2. Inspector'ı simüle et/çağır
        try:
            from inspector import PDFInspectorMock
            inspector_text = PDFInspectorMock.extract_text(pdf_path)
        except ImportError:
            inspector_text = ""
            
        # 3. Critic'ten destek al (Nihai kararı ver)
        try:
            from critic import PDFCritic
            critic = PDFCritic()
            final_decision = critic.evaluate(router_json, inspector_text)
            
            # Router, yapısal bilgileri de nihai json'a ekleyebilir
            final_decision["structural_category"] = category
            return final_decision
        except ImportError:
            return router_json

