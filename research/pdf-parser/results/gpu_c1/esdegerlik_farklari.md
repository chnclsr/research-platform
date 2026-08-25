# Cihaz eşdeğerliği — sayfa sayfa fark listesi

Aynı makinede CPU ve CUDA çıktıları karşılaştırıldı. **Hiçbir testte fark
çıkmadı**, bu yüzden bu dosya bir fark listesi değil, farkın yokluğunun
sayfa sayfa kanıtıdır.

## Test 1 — 9 belgelik korpus, sayfa markdown'ı

`kaynak: out/gpu_docling_cuda.json → esdegerlik.belgeler[]`
(taban: `out/gpu_docling_json_cpu/`, karşılaştırılan: `out/gpu_docling_json_cuda/`)

| belge | sayfa | farklı sayfa | farklı sayfa numaraları |
|---|---|---|---|
| `turkce_makale` | 6 | 0 | — |
| `resnet_2sutun_gorsel` | 12 | 0 | — |
| `vgg_tablo_agirlikli` | 14 | 0 | — |
| `attention_tablo` | 15 | 0 | — |
| `bert_2sutun_dipnot` | 16 | 0 | — |
| `sybil_tip_2sutun` | 17 | 0 | — |
| `gpt3_uzun_75sayfa` | 75 | 0 | — |
| `gpt4_uzun_gorsel` | 100 | 0 | — |
| `taranmis_bert_2sutun_dipnot` | 6 | 0 | — |
| **TOPLAM** | **261** | **0** | — |

Fark türü ayrımı (kozmetik / içerik kaybı) **yapılamadı ve gerekmedi**:
karşılaştırılacak tek bir farklı sayfa yok.

## Test 2 — C1 korpusu, sayfa metni + tablo yapıları

`kaynak: out/gpu/cache_esdegerlik.json`

| ölçü | değer |
|---|---|
| karşılaştırılan belge | 60 |
| sayfa metni farklı | 0 |
| tablo yapısı farklı | 0 |
| payload `device` — CPU tarafı | `cpu` |
| payload `device` — CUDA tarafı | `cuda:0` |

Bu test markdown'dan fazlasını karşılaştırır: üretimdeki `_table_grid`
çıktısı (tablo hücre ızgarası) ayrı bir çıktı yoludur ve markdown'ın aynı
olması onun da aynı olduğunu kanıtlamaz. İkisi de aynı çıktı.

## Test 3 — atıf: makine farkı çıkan 5 belge

`kaynak: out/gpu/atif_5belge.json`

Gönderilen CPU tabanı (başka makine) ile bu makinenin GPU koşusu arasında
heavy utility farkı çıkan 5 belge, **bu makinede** CPU ve CUDA ile yeniden
üretildi:

| belge | sayfa metni farklı | tablo yapısı farklı | CPU karakter | CUDA karakter | device |
|---|---|---|---|---|---|
| `data_135` | hayır | hayır | 9082 | 9082 | `cpu` / `cuda:0` |
| `data_52` | hayır | hayır | 620 | 620 | `cpu` / `cuda:0` |
| `data_175` | hayır | hayır | 1968 | 1968 | `cpu` / `cuda:0` |
| `data_59` | hayır | hayır | 8262 | 8262 | `cpu` / `cuda:0` |
| `data_53` | hayır | hayır | 14 | 14 | `cpu` / `cuda:0` |

**Sonuç:** cihazdan kaynaklı fark **YOK**. Aynı 201 belgede gözlenen 5
belgelik fark cihazdan değil, **makineden** geliyor.

---

## Karşılaştırma — önceki makine

`kaynak: taban_cpu/onceki_makine_gpu_docling_cuda.json → esdegerlik`

| belge | sayfa | farklı sayfa | sayfa numaraları |
|---|---|---|---|
| `turkce_makale` | 6 | 0 | — |
| `resnet_2sutun_gorsel` | 12 | 0 | — |
| `vgg_tablo_agirlikli` | 14 | 0 | — |
| `attention_tablo` | 15 | 0 | — |
| `bert_2sutun_dipnot` | 16 | 0 | — |
| `sybil_tip_2sutun` | 17 | 1 | 11 |
| `gpt3_uzun_75sayfa` | 75 | 2 | 49, 50 |
| `gpt4_uzun_gorsel` | 100 | 1 | 99 |
| `taranmis_bert_2sutun_dipnot` | 6 | 3 | 2, 3, 4 |
| **TOPLAM** | **261** | **7** | — |

O makine: RTX 4060, docling **2.120.3**. Bu makine: Quadro RTX 4000,
docling **2.120.1**. İki değişken birden farklı olduğu için 7 sayfalık
farkın GPU mimarisinden mi docling sürümünden mi geldiği **ayrılamaz**.
