# Bulk insert çalışması: durum, değişiklikler ve yapılacaklar

Bu dosya deneyin kendi raporu değildir. `REPORT.md` ölçümü anlatır; bu not, üzerinde
kimin ne değiştirdiğini ve sıradaki işin ne olduğunu tutar. Deney üzerinde çalışan
herkes buradan devam edebilsin diye tutuluyor.

## Devam eden iş ve devralma notu

Son güncelleme: 2026-08-27, `ee768a7` commit'i sonrası.

Bu bölüm, çalışma yarıda kalırsa kaldığı yerden devam edilebilsin diye tutuluyor.
Aşağıdaki her şey commit'li; kaybolan tek şey koşunun kendisi olabilir.

### Commit geçmişi

| Commit | Ne yaptı |
|---|---|
| `04201d6` | İlk deney: beş yöntem, `postgres_bulk_insert_v1`. I/O ölçümü hatalıydı. |
| `3404703` | I/O ölçümü düzeltildi, üç kol eklendi, `save_passages` karakterizasyon testleri yazıldı. `v2`. |
| `5606fd9` | Temiz ağaçtan yeniden koşu, rapor ve bu not. |
| `ee768a7` | Re-ingest kolları eklendi (`v3`). **Bu koşunun sonucu henüz commit'li değil.** |

### v3 koşusu tamamlandı

`v3` düzeneğinin tam koşusu bitti: on kol, üç boyut, 7 tekrar, 210 koşunun 210'u geçerli.
Sonuç `results/postgres_bulk_insert.json` içinde ve commit'li. Komut, yeniden koşmak
gerekirse:

```bash
PYTHONPATH=src .venv311/bin/python scripts/benchmark_bulk_insert.py \
  --sizes 100 1000 5000 --repeats 7 --warmups 1 \
  --dimensions 768 --text-chars 512 --upsert-batch 1000 \
  --output research/bulk-insert/results/postgres_bulk_insert.json
```

Koşu kaldığı yerden devam etmez, baştan başlar. Container ayakta değilse önce
`docker compose -f research/bulk-insert/compose.yml up -d --wait postgres`. Koşu bitince
`PYTHONPATH=src .venv311/bin/python scripts/report_bulk_insert.py` ile rapor üretilir;
`REPORT.md` ve `results/postgres_bulk_insert_summary.csv` elle düzenlenmez.

### Bu koşuyla cevaplanan soru

Deneyin tamamı boş tabloya yazıyordu. Üretimde re-ingest dolu tabloya yazar ve
`ON CONFLICT DO UPDATE` INSERT dalını değil UPDATE dalını çalıştırır. UPDATE dalı INSERT
dalından pahalı olduğu için, kazancın re-ingest senaryosunda da korunup korunmadığı
bilinmiyordu. Eğer korunmuyorsa entegrasyonun gerekçesi kalmaz.

Cevap: kazanç korunuyor, hatta insert yolundan daha büyük. Batch upsert dolu tabloya
yazarken mevcut yönteme göre 5.29x / 6.91x / 6.58x hızlı. Upsert'in UPDATE dalı kendi
INSERT dalından yalnızca %7.7 / %5.5 / %4.5 pahalı; mevcut yöntem ise aynı geçişte
belirgin biçimde yavaşlıyor, çünkü UPDATE yolunda satır başına iki gidiş dönüşünün
üstüne ORM'in değişiklik takibi biniyor. Entegrasyonun gerekçesi re-ingest senaryosunda
da geçerli.

### Karara bağlananlar

- **Fallback konulmayacak.** Eski satır satır döngü silinecek, yerine yalnızca
  PostgreSQL ve SQLite destekli upsert gelecek. Gerekçe: testler SQLite'ta koştuğu için
  fallback hiç çalışmayan, test edilmeyen ölü kod olurdu.
- **Mentör onayı olmadan merge edilmeyecek.** Burası ingest yazma yolu. Rapor tek başına
  değil, hazırlanmış diff ile birlikte gösterilecek.
- Mentöre açıkça işaretlenecek iki nokta: eşzamanlılık/deadlock ölçülmedi (satırları
  sabit sıraya dizme önerisi argümandır, ölçüm değildir) ve pgvector ayrı, daha büyük
  bir karardır.

### Entegrasyon henüz yapılmadı

`src/research_platform/repository.py` içindeki `save_passages` **değiştirilmedi**. Tasarım
aşağıdaki bölümde; karakterizasyon testleri `tests/test_passage_persistence.py` içinde
hazır ve mevcut implementasyonda geçiyor. Değişiklik yapıldığında bu altı testin
değiştirilmeden geçmesi gerekir. Değiştirilmeleri gerekiyorsa davranış değişmiş
demektir ve bu ayrıca tartışılmalıdır.

## Durum

İlk deney (commit `04201d6`) beş yöntemi süre, WAL ve I/O açısından ölçmüştü. İnceleme
sırasında ölçüm tarafında bir hata ve kapsam tarafında üç eksik bulundu; ikisi de
düzeltildi ve deney yeniden koşuldu (commit `3404703` ve sonrası).

Zaman ve throughput sonuçları ilk koşuda da doğruydu, sıralama değişmedi. Değişen,
I/O tablosunun geçerliliği ve matrisin kapsamı.

## Düzeltilen ölçüm hatası

`pg_stat_io` sayaçları backend'e özeldir ve paylaşılan belleğe saniyede en fazla bir kez
yazılır. `pg_stat_clear_snapshot()` yalnızca okuyucunun görünümünü tazeler, backend'in
bekleyen sayaçlarını yayımlamaz. İlk sürümde bu nedenle bir saniyeden kısa süren her
ölçüm penceresi kendi I/O'sunu sıfır raporlamış, yükü bir sonraki pencereye taşımıştı.

Kanıt, ilk koşunun kendi ham verisinden: bir saniyenin altında biten 40 koşunun 28'i
sıfır `extends` bildirmişti, bir saniyenin üstündeki 35 koşunun hiçbiri bildirmemişti.
Boş tabloya 1.000 satır yazarken relation'ın genişlememesi fiziksel olarak mümkün
değildir. Kontrollü doğrulama: ardışık dört adet 100 satırlık COPY, flush zorlanmadan
`extends = 0`, zorlandığında her pencerede kararlı `extends = 63`.

Çözüm iki parçalı, ikisi de gerekli:

- Her `pg_stat_io` okumasından önce, yazan backend'de `pg_stat_force_next_flush()`.
- `pool_size=1`, böylece flush edilen backend ile yazan backend aynı olur.

Doğrulama: düzeltmeden sonra aynı tabloya yazan tüm kollar her boyutta aynı `extends`
değerini veriyor (63 / 532 / 2605). Hâlâ anlamlı fark üreten sütun `extend_time`, ki
beklenen davranış budur.

## Matrise eklenenler

| Kol | Neden eklendi |
|---|---|
| `core_upsert_batched` | İlk raporun üretim için önerdiği yöntem ölçülmemişti. Repository'nin idempotent semantiğini taşıyan tek bulk yol. |
| `copy_records` | "Toplu yazma"nın kanonik yöntemi matriste yoktu. |
| `vector_executemany` | Görev tanımı "PostgreSQL **ve vektör kayıtları**" diyordu; native pgvector hiç ölçülmemişti. |

Ayrıca tekrar sayısı 5'ten 7'ye çıkarıldı (repository kolunun varyansı yüksekti) ve
istemci tarafı serileştirme maliyeti ayrı bir metrik olarak ölçülmeye başlandı.

## Dosya bazında değişiklikler

| Dosya | Durum | Ne değişti |
|---|---|---|
| `scripts/benchmark_bulk_insert.py` | değişti | (`ee768a7`) `preseed` bayrağı, `seed_variant`, `preseed_table` ve iki re-ingest kolu; doğrulama artık kalan seed satırı varsa koşuyu başarısız sayar. Çıktı sürümü `v3`. (`3404703`) Stats flush düzeltmesi, `pool_size=1`, üç yeni kol, `StrategySpec`/`StrategyContext`/`StrategyResult` modeli, tablo bazında parametrelenmiş `stats_snapshot`/`validate_rows`/`row_count`, `passages_vector` tablosunun kurulumu, `client_serialization_ms`, `--upsert-batch`. Çıktı sürümü `postgres_bulk_insert_v2`. |
| `scripts/report_bulk_insert.py` | yeni (commit'lendi) | (`ee768a7`) Re-ingest bölümü, "Yol" sütunu, re-ingest kolları için ayrı karşılaştırma tabanı; grafiklerden çıkarıldılar. (`3404703`) Sekiz kol için etiket ve renk, iki satırlı legend, şema sütunu, `pg_stat_io` ölçüm notu bölümü, serileştirme tavanı bölümü, upsert/COPY/pgvector bulguları, elma-armut çekincesi, CSV'ye I/O sütunları. |
| `tests/test_bulk_insert_benchmark.py` | değişti | Yeni yardımcılar için testler; rotasyon testi kol sayısından bağımsız hale geldi. `test_bulk_benchmark_upsert_updates_every_mutable_column` upsert'in hiçbir sütunu atlamadığını yapısal olarak doğrular. |
| `tests/test_passage_persistence.py` | yeni | `save_passages` için karakterizasyon testleri. Aşağıya bakınız. |
| `research/bulk-insert/REPORT.md` | yeniden üretildi | Yalnızca `report_bulk_insert.py` üretir, elle düzenlenmez. |
| `research/bulk-insert/results/` | yeniden üretildi | Kanonik ham veri ve özet CSV. |

## `save_passages` test kapsamı

Bu metodun **hiç doğrudan testi yoktu**. Bulk'a çevirmeden önce mevcut davranış
`tests/test_passage_persistence.py` ile sabitlendi. Altı test de mevcut satır satır
implementasyonda geçiyor, yani yeniden yazımın karşılaması gereken sözleşme bunlar:

1. Tüm alanlar (metadata dahil) yazılır.
2. Aynı chunk yeniden kaydedilince yerinde güncellenir, kopya oluşmaz.
3. **Yeni passage id ile re-ingest'te satır kimliği korunur.** Chunk kimliği
   `(source_version_id, chunk_index)`; `id` değil. Claim'ler saklanan satıra referans
   verdiği için bu davranış korunmak zorunda.
4. Karışık batch: bir kısmı yeni, bir kısmı mevcut.
5. Farklı `source_version_id` altında aynı `chunk_index` çakışmaz.
6. Boş liste no-op.

## Bulgular

Ayrıntı `REPORT.md`'de. Karar açısından önemli olanlar:

- Bulk yazım satır başına commit'e göre 2.7x-3.0x, mevcut repository yöntemine göre
  5.6x-5.7x daha hızlı (1.000 ve 5.000 kayıt).
- **Idempotent olmanın bedeli yok sayılabilir.** `core_upsert_batched` ile çakışma
  çözümü yapmayan `core_executemany` arasında -2.4% / +1.3% / +4.3% fark var. Bulk'a
  geçerken repository semantiğinden vazgeçmek için ölçülmüş bir gerekçe yok.
- **COPY beklendiği kadar ayrışmadı** (5.9% / 2.9% / 5.6%). Sebebi serileştirme tavanı.
- **Serileştirme tavanı:** 5.000 kayıtta `json.dumps` tek başına ~1.350 ms, en hızlı
  kolun toplam süresinin yaklaşık %38'i. Hiçbir yazma yöntemi bunu düşürmez.
- **En büyük tekil kazanç yöntemden değil şemadan geldi.** Native `vector` sütunu aynı
  statement şekliyle 1.25x-1.34x daha hızlı; karşılığında tablo %19-24 büyüyor, çünkü
  pgvector JSONB gibi TOAST sıkıştırmasından yararlanmaz.

## Sıradaki iş

### Ölçülmemiş, entegrasyondan önce ölçülmesi gereken

- [x] **UPDATE yolu.** `ee768a7` ile iki re-ingest kolu eklendi ve koşuldu; yukarıdaki
      devralma notuna bakınız.
- [ ] **Kısmi çakışma.** Re-ingest kolları tüm satırların çakıştığı durumu ölçer. Bir
      belgenin bazı chunk'larının değişip bazılarının eklendiği karışık batch ölçülmedi.
- [ ] **Eşzamanlı writer.** Lock contention, deadlock ve retry davranışı matriste yok.
      Batch'li upsert'e geçerken en gerçek risk bu.

### Ölçülmemiş, ayrı karar

- [ ] **pgvector şema kararı.** Yazma tarafında ölçüldü, ama HNSW/IVFFlat indeksi
      kurulmadı; indeksli tabloda yazma maliyeti belirgin artar. Okuma tarafı (benzerlik
      sorgusu) hiç ölçülmedi. Ayrı bir deney konusu.
- [ ] pgvector'e COPY protokolüyle yazmak asyncpg için binary codec gerektiriyor,
      matriste yok.

### Entegrasyon

- [ ] `save_passages`'ın batch'li `ON CONFLICT DO UPDATE` ile değiştirilmesi. Tasarım
      aşağıda; açık kararlar var.
- [ ] N passage'ın batch başına tek INSERT ürettiğini doğrulayan test
      (`before_cursor_execute` dinleyicisi). Değişikliğin asıl amacı bu, testi olmalı.
- [ ] Batch sınırını aşan girdi için test (sabiti patch'leyerek).
- [ ] Batch ortasında hata olduğunda rollback ve tekrar deneme davranışı.

## Entegrasyon tasarımı

Hedef: `src/research_platform/repository.py` içindeki `save_passages`. Bugün her passage
için bir varlık sorgusu çalıştırıyor; session autoflush önceki bekleyen INSERT'i sonraki
SELECT öncesinde gönderdiği için N kayıt `2N` gidiş dönüşü üretiyor.

```python
PASSAGE_UPSERT_BATCH = 1000
_PASSAGE_UPSERT_COLUMNS = ("section_path", "page_number", "start_char", "end_char",
                           "text", "token_count", "content_hash", "embedding", "metadata")
_UPSERT_DIALECTS = {"postgresql": postgresql_insert, "sqlite": sqlite_insert}

async def save_passages(self, passages: list[Passage]) -> None:
    if not passages:
        return
    rows = self._merge_passages_by_chunk(passages)
    statement = _UPSERT_DIALECTS[self.session.get_bind().dialect.name](PassageRow)
    upsert = statement.on_conflict_do_update(
        index_elements=[PassageRow.source_version_id, PassageRow.chunk_index],
        set_={name: statement.excluded[name] for name in _PASSAGE_UPSERT_COLUMNS},
    )
    for start in range(0, len(rows), PASSAGE_UPSERT_BATCH):
        await self.session.execute(upsert, rows[start : start + PASSAGE_UPSERT_BATCH])
    await self.session.commit()
```

Doğrulanmış olanlar:

- SQLite (test ortamı) ve PostgreSQL aynı `on_conflict_do_update` API'sini destekliyor.
  SQLite'ta ayrıca denendi: satır kimlikleri korunuyor, semantik birebir aynı.
- `id`, `source_version_id` ve `chunk_index` SET listesinde yok; kalan tüm fiziksel
  sütunlar var. `test_bulk_benchmark_upsert_updates_every_mutable_column` bunu yapısal
  olarak doğruluyor, yani şemaya yeni sütun eklenirse test kırılır.
- Ownership: `save_passages` `run_id` almıyor, dolayısıyla `_OwnershipEnforced`
  metaclass'ı onu sarmıyor. İmza değişmediği sürece yetkilendirme davranışı değişmez.

### Karara bağlanacak dört nokta

1. **`id` güncellenmiyor.** Mevcut davranışla uyumlu ve karakterizasyon testi 3 bunu
   sabitliyor. Değiştirilmemeli.
2. **Aynı çağrıda tekrarlanan chunk.** PostgreSQL tek statement'ta aynı satırı iki kez
   güncellemeyi reddeder; eski döngü sessizce "son yazan kazanır" davranıyordu.
   `_merge_passages_by_chunk` bunu *ilk yazılan id + son gelen içerik* olarak birleştirip
   eski davranışı birebir üretir. Pratikte chunker tekrar üretmez, ama semantik farkı
   bırakmamak gerekir.
3. **Deadlock önlemi.** Satırların `(source_version_id, chunk_index)` sırasına dizilmesi
   öneriliyor. Eşzamanlı iki writer aynı chunk'lara farklı sırayla kilit alırsa deadlock
   olur; sabit sıra bunu kapatır. Fiziksel satır sırası önemsiz, sorgular `order_by`
   kullanıyor.
4. **Fallback koyulsun mu?** İlk rapor "eski yöntemi güvenli fallback olarak tut"
   diyordu. Koymamak öneriliyor: testler SQLite'ta koştuğu için fallback hiç
   çalışmayan, test edilmeyen ölü kod olur. İki dialect destekli sözlük ve bilinmeyen
   dialect'te net hata daha dürüst. Fallback tercih edilirse ona da test yazılmalı.

## Yeniden çalıştırma

```bash
docker compose -f research/bulk-insert/compose.yml up -d --wait postgres
PYTHONPATH=src .venv311/bin/python scripts/benchmark_bulk_insert.py \
  --sizes 100 1000 5000 --repeats 7 --warmups 1 \
  --dimensions 768 --text-chars 512 --upsert-batch 1000 \
  --output research/bulk-insert/results/postgres_bulk_insert.json
PYTHONPATH=src .venv311/bin/python scripts/report_bulk_insert.py
```

`REPORT.md` ve `results/postgres_bulk_insert_summary.csv` üretilen dosyalardır, elle
düzenlenmemelidir. Benchmark yalnızca `127.0.0.1:55433/bulk_benchmark` hedefine yazar ve
başka bir hedefte çalışmayı reddeder.

## Provenance notu

Nihai koşu `3404703` commit'i üzerinden yapıldı ve o sırada **izlenen hiçbir dosyada
değişiklik yoktu**; `git status --porcelain --untracked-files=no` boştu. Rapordaki
"Ölçüm sırasında çalışma ağacı: Değişiklik içeriyordu" satırı yalnızca izlenmeyen
dosyalardan kaynaklanıyor: bu not dosyası ve koşunun kendi ürettiği çıktılar. Benchmark
`git status --porcelain` kullandığı için izlenen ve izlenmeyen ayrımını yapmıyor.
Bayrağın "Temizdi" okuması isteniyorsa bu not ve çıktılar commit'lendikten sonra koşu
tekrarlanmalıdır; ölçüm değerlerini etkilemez.
