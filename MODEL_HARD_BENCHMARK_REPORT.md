# Araştırma Agentı Zor Model Karşılaştırması

Platform sürümü: `v0.2.1`

Belge sürümü: `1.1`

Benchmark sürümü: `1.1.0-hard`

Tarih: `2026-07-15`

> Bu belge iki modele aynı 4K/deterministik ayarların verildiği ilk karşılaştırmadır.
> Donanıma göre ayrı optimize edilmiş ve bağımsız holdout kullanılan güncel sonuç için
> `MODEL_HARDWARE_OPTIMIZED_BENCHMARK_REPORT.md` esas alınmalıdır.

## Sonuç

Mevcut agent iş yükünde `qwen3.5:9b`, `qwen3:4b-instruct-2507-q4_K_M` modelini
geçemedi. Eski 4B model toplam kalite puanında **71,59**, Qwen 3.5 9B ise **68,79**
aldı. 9B model sorgu ve kanıt görevlerinde bazı yerel iyileşmeler gösterse de nüanslı
entailment sınıflandırmasındaki kayıp toplam sonucu aşağı çekti.

V1 için varsayılan modelin 4B olarak korunması; 9B modelin ise ancak ayrı bir reasoning
verifier geliştirildikten sonra audit/adversarial review rolünde yeniden değerlendirilmesi
önerilir.

## Test düzeni

- Donanım: NVIDIA RTX 4060 8 GB, Intel UHD 770, 32 GB sistem RAM'i.
- Ollama: `0.31.2`.
- Context: 4.096 token.
- Thinking: kapalı.
- Temperature: 0.
- Paralellik: model başına tek benchmark akışı.
- Her modelden önce yüklü Ollama modelleri boşaltıldı.
- Dış web sonuçları yerine iki modele de aynı sabit fixture'lar verildi.

Zor test seti dokuz gerçek agent çağrısından oluşur:

1. İki çok boyutlu Türkçe araştırma sorusunda decomposition.
2. İki nedensellik ve karşı-kanıt odaklı konuda query generation.
3. Prompt injection, null sonuç, post-hoc alt grup, confounding ve sayısal çelişki içeren
   üç passage üzerinde evidence extraction.
4. Negasyon, tarih, güven aralığı, nedensellik ve ilgisizlik ayrımı içeren sekiz entailment
   çifti.
5. Desteklenen ve qualified iddiaları ayıran, sahte talimat ve URL içeren bir synthesis
   görevi.

Toplam skor ağırlıkları: decomposition `%15`, query generation `%15`, evidence extraction
`%35`, entailment `%25`, synthesis `%10`.

## Kalite sonuçları

| Ölçüm | Qwen 3 4B | Qwen 3.5 9B | Fark |
|---|---:|---:|---:|
| Toplam kalite | **71,59** | 68,79 | -2,80 |
| Decomposition | **83,57** | 83,00 | -0,57 |
| Query generation | 85,33 | 85,33 | 0,00 |
| Evidence extraction | 64,67 | **65,83** | +1,16 |
| Entailment | **62,50** | 50,00 | -12,50 |
| Synthesis | 80,00 | 80,00 | 0,00 |

9B model ilk prompt-injection fixture'ında sahte “productivity doubled” cümlesini kanıt
olarak almamış, 4B model ise almıştır. Üç fixture toplamında yasaklı cümle isabeti 4B için
iki, 9B için birdir. Buna karşılık 9B; tarih, kontrol grubu, güven aralığı ve confounding
gibi nüanslı entailment örneklerinin yalnız dördünü doğru sınıflandırmıştır.

## Performans sonuçları

| Ölçüm | Qwen 3 4B | Qwen 3.5 9B |
|---|---:|---:|
| Dokuz çağrı toplam süresi | **41,41 sn** | 70,34 sn |
| Üretim hızı | **80,48 token/sn** | 42,03 token/sn |
| Completion token | 2.878 | 2.509 |
| Tepe VRAM | **3.813 MiB** | 7.229 MiB |
| Ollama GPU yerleşimi | %100 GPU | %100 GPU |
| Hata / geçersiz JSON | 0 | 0 |

9B model 4K context'te tamamen GPU'ya sığdı. Aynı model 8K context'te `%86 GPU / %14 CPU`
olarak çalıştı, tepe VRAM yaklaşık 7,37 GB oldu ve toplam süre 90,04 saniyeye çıktı. Bu
donanımda Qwen 3.5 9B kullanılacaksa 4K context tercih edilmelidir.

## Thinking modu bulgusu

Qwen 3.5 9B'nin resmi GPQA avantajını temsil eden thinking modu ayrıca incelendi:

- Basit bir JSON matematik çağrısı `think=false` ile 7,19 saniyede ve 9 output token'da
  tamamlandı.
- Aynı çağrı `think=true` ile 45,16 saniye sürdü.
- Sekiz çiftlik entailment görevi thinking açık ve 4.096 output token bütçesiyle 124,3
  saniye sonunda geçerli JSON üretmedi.

Dolayısıyla resmi GPQA sonucu mevcut `format=json` agent akışına doğrudan taşınamıyor.
Thinking, her extraction çağrısında açılmamalıdır. Gelecekte ayrı bir verifier şu şekilde
tasarlanabilir:

1. Thinking çıktısını JSON gramerinden ayırmak.
2. Yalnız audit ve adversarial review düğümlerinde çağırmak.
3. Final cevabı ikinci, kısa ve thinking-kapalı JSON normalizasyon çağrısıyla almak.
4. Süre, boş final cevap ve parser başarısını ayrı kabul ölçütü yapmak.

## Uygulanan entegrasyon düzeltmesi

Ollama sağlayıcısına aşağıdaki açık sınırlar eklendi:

- `LLM_THINK=false`
- `LLM_CONTEXT_TOKENS`
- `LLM_MAX_OUTPUT_TOKENS=2048`

Bu ayarlar Qwen 3.5'in yapılandırılmış JSON çağrılarında sınırsız düşünerek final cevap
üretememesini engeller. Ayarlar environment üzerinden değiştirilebilir.

## Yeniden üretim

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_models.py `
  --context 4096 `
  --models qwen3:4b-instruct-2507-q4_K_M qwen3.5:9b `
  --output data\model-hard-benchmark-comparison-4k.json
```

Ham sonuç: `data/model-hard-benchmark-comparison-4k.json`

Benchmark kodu: `scripts/benchmark_models.py`

## Sınırlamalar

- Bu, GPQA'nın yeniden koşumu değil; araştırma platformuna özgü küçük ve zor bir kabul
  setidir.
- Entailment gold etiketleri rubric tabanlıdır; genişletilmiş sette ikinci insan denetimi
  yapılmalıdır.
- Temperature 0 kullanılmasına rağmen farklı runtime sürümlerinde küçük çıktı farkları
  görülebilir.
- Sonuçlar RTX 4060 8 GB ve Ollama 0.31.2 için geçerlidir.
