# Parsers

Ham baytları `ParsedDocument`'a çeviren servisler. Edinim stratejisi (direct, crawl4ai,
scrapling) hangisi olursa olsun ayrıştırma buradan geçer, böylece çıktı tutarlıdır.

Tasarım `connectors/` paketini birebir izler: `base.py` sözleşmeyi, ayrı modüller somut
uygulamaları, `registry.py` seçimi tutar.

## Yeni parser ekleme

1. `parsers/` altında bir modül aç ve `DocumentParser`'dan türet:

```python
class MyParser(DocumentParser):
    id = "my_parser"
    document_types = ("html",)
    capabilities = ("text", "tables")
    priority = 10          # ayni turde birden fazla parser varsa yuksek olan kazanir

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        ...
```

2. `registry.py` içindeki `build_parser_registry()` listesine ekle.
3. `pytest tests/test_parsers.py` çalıştır — uygunluk paketi yeni parser'ı otomatik kapsar
   (`ALL_PARSERS` listesine eklemeyi unutma).

## Uyulması zorunlu sözleşme

- **İstisna fırlatma.** Bozuk, kesik veya yanlış etiketlenmiş girdi gelebilir; bu durumda
  boş `ParsedDocument` döndür. Edinim katmanı zaten kısa metni reddediyor.
- **PDF sayfa başlıkları.** PDF üreten bir parser her sayfayı `# Page N` başlığıyla
  vermeli; `chunk_document()` pasajların `page_number` alanını buradan çıkarıyor
  (`passages.py`). Bunu bozmak alıntı konum bilgisini bozar.
- **Başlıkları koru.** `#` düzeyindeki markdown başlıkları bölüm yolunu (`section_path`)
  belirliyor. Başlık üretmeyen bir parser tüm belgeyi tek bölüm yapar.
- **Deterministik ol.** Aynı baytlar her zaman aynı metni vermeli. `content_hash`
  ayrıştırılmış metinden hesaplanıyor ve kaynak sürüm tekilleştirmesi, MinIO anahtarları ve
  pasaj offsetleri buna bağlı (`acquisition.py`, `repository.py`).
- **Yapıyı ayrıca ver.** Tablo ve kod bloklarını hem metne göm hem de `tables` /
  `code_blocks` alanlarına koy; ikisi farklı tüketiciler içindir.

## Mevcut parser'lar

| id | Türler | Yetenekler | Not |
|---|---|---|---|
| `html` | html | text, sections, tables, code, links | Tabloları markdown boru ayracıyla, kodu ``` çitiyle verir |
| `pdf` | pdf | text, pages | PyMuPDF ile okuma sırasına duyarlı; yoksa pypdf'e düşer |
| `plain_text` | text, json, xml | text | JSON/XML'i `anahtar.yolu: değer` satırlarına düzleştirir |

Çalışan kurulumda `GET /v1/parsers` kayıtlı parser'ları ve yeteneklerini döndürür.
