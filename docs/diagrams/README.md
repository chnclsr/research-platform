# Diyagramlar

| Dosya | Ne | Dil |
|---|---|---|
| `system-architecture-dark.html` | Sistem mimarisi — kaynak | Türkçe |
| `pipeline-flow-dark.html` | ResearchPipeline akışı — kaynak | Türkçe |
| `system-architecture.svg` | Aynı diyagramın kök `README.md` sürümü | İngilizce |
| `pipeline-flow.svg` | Aynı diyagramın kök `README.md` sürümü | İngilizce |

HTML dosyaları kaynaktır: yazı tipleri, başlık ve çerçeve onlarda. SVG'ler bu kaynaklardan
`<svg>` bloğu çıkarılıp metinleri İngilizce'ye çevrilerek üretildi; kök README İngilizce
olduğu için oraya bunlar gömülüdür.

**Bir diyagramı güncellerken önce HTML'i düzeltin, sonra SVG'yi eşitleyin.** İkisi ayrı
dosya olduğu için sessizce ayrışabilirler. SVG'lerde HTML yorumları temizlenmiştir ve
`<img>` içinde kullanılabilmeleri için `width`/`height` eklenmiştir.

Yazı tipleri (Geist, Instrument Serif) SVG'ye gömülü değildir; GitHub'da sistem
`sans-serif` / `monospace` / `serif` yedeklerine düşerler. Yerleşim buna göre paylıdır.
