# Diyagramlar

| Dosya | Ne | Dil |
|---|---|---|
| `system-architecture-dark.html` | Sistem mimarisi — kaynak | Türkçe |
| `pipeline-flow-dark.html` | ResearchPipeline akışı — kaynak | Türkçe |
| `system-architecture.svg` | Aynı diyagramın kök `README.md` sürümü | İngilizce |
| `pipeline-flow.svg` | Aynı diyagramın `docs/ARCHITECTURE.md` sürümü | İngilizce |
| `langgraph-state-machine.html` | LangGraph durum makinesi — kaynak | İngilizce |
| `langgraph-state-machine.svg` | Kök `README.md` ve `ARCHITECTURE.md` sürümü | İngilizce |
| `e2e-system-flow.html` | Uçtan uca sistem akışı — kaynak | İngilizce |
| `e2e-system-flow.svg` | Kök `README.md` ve `ARCHITECTURE.md` sürümü | İngilizce |
| `smart-router-pipeline.svg` | Smart Router hattı | Türkçe |
| `quarantine-decision-matrix.svg` | Karantina karar matrisi | Türkçe |

Son iki satırdaki SVG'lerin HTML kaynağı yoktur; doğrudan SVG olarak eklenmişlerdir.

HTML dosyaları kaynaktır: yazı tipleri, başlık ve çerçeve onlarda. İlk dört satırda kaynak
Türkçe tutulup SVG'ye çevrilmiştir; `langgraph-state-machine` ve `e2e-system-flow` ise
**hem kaynakta hem SVG'de İngilizce**. Depo ve gömüldükleri belgeler (`README.md`,
`docs/ARCHITECTURE.md`) İngilizce olduğu için tek dilde tutuluyorlar — iki çeviriyi eşit
tutmaya çalışmak sessiz ayrışma üretiyordu.

**Bir diyagramı güncellerken önce HTML'i düzeltin, sonra SVG'yi eşitleyin.** İkisi ayrı
dosya olduğu için sessizce ayrışabilirler. SVG'lerde HTML yorumları temizlenmiştir ve
`<img>` içinde kullanılabilmeleri için `width`/`height` eklenmiştir.

Yazı tipleri SVG'ye gömülü değildir; GitHub'da sistem `sans-serif` / `monospace` / `serif`
yedeklerine düşerler. Yerleşim buna göre paylıdır.

## Tema

`system-architecture`, `langgraph-state-machine` ve `e2e-system-flow`, `diagram-design`
eklentisinin **Cezeri Robot** derisiyle üretilir. Açık zeminde kağıt `#f2f5f7`, mürekkep
`#1b242c`, vurgu `#0090ba`, bağlantı `#04253c`; sistem mimarisinin koyu sürümünde bunların
profildeki karşılıkları `#1b242c`, `#f2f5f7`, `#2bb3d8` ve `#8ec6de` kullanılır. Palet
<https://www.cezerirobot.com/tr/> adresinden ve marka logosundan örneklenmiştir; metin
ailesi sitenin yüklediği **Raleway**'dir. Marka monospace taşımadığı için `Geist Mono`
korunmuştur.

Deri, depo kökündeki `.diagram-design` işaretçisiyle seçilir (`profile: cezeri`); profilin
kendisi `~/.diagram-design/profiles/cezeri.md` altındadır ve depoda **değildir**. Başka bir
makinede diyagram üretmeden önce o profilin orada olması gerekir.
