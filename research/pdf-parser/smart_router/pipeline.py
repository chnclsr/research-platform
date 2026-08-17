#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline.py
===========
Bu script sadece bir kullanım örneğidir (Demo).
Sistemin ana giriş noktası artık `router.py` içerisindeki `PDFRouter.route_document()` metodudur.
Ajanlar (Agent) doğrudan Router ile iletişim kurar.
"""

import sys
import json
from router import PDFRouter

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python pipeline.py <pdf_path>")
        sys.exit(1)
        
    pdf_file = sys.argv[1]
    
    # Ajanın yapacağı örnek çağrı:
    router = PDFRouter()
    decision = router.route_document(pdf_file)
    
    # Çıktıyı JSON olarak ekrana bas (diğer sistemler okuyabilsin)
    print(json.dumps(decision, indent=4, ensure_ascii=False))

