#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspector.py
============
Bu modül pdf-inspector uygulamasının akışını temsil eder.
Kullanıcının sisteminde inspector'un dokümanı okuyup çıkardığı "ham metin (text)" 
çıktısını simüle eder veya gerçek sistemde API'den çeker.
"""

import os
import pymupdf as fitz

class PDFInspectorMock:
    """
    Şimdilik geliştirme aşamasında fitz (pymupdf) ile hızlıca 
    metni çekerek pdf-inspector çıktısını simüle eden sınıf.
    Gerçek entegrasyonda burada inspector'ın kendi extract çağrısı yapılacaktır.
    """
    
    @staticmethod
    def extract_text(pdf_path: str) -> str:
        """PDF dosyasından pdf-inspector'ın çıkartacağı varsayılan metni döner."""
        if not os.path.exists(pdf_path):
            return ""
            
        text_content = []
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text_content.append(page.get_text("text"))
            doc.close()
        except Exception as e:
            return ""
            
        return "\n\n".join(text_content)
