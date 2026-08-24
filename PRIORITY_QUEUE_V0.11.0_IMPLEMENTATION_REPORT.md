# Öncelikli koşu kuyruğu — v0.11.0

Platform sürümü: `v0.11.0`

Belge sürümü: `1.0`

Son güncelleme: `2026-08-21`

Şema göçü içerdiği ve API, worker, panel, Telegram, MCP ile Langflow'u birlikte
ilgilendirdiği için kendi raporu var.
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) kapsam
tablosunda tek satırlık işaretçisi bulunuyor.

## Sorun

Kuyruk tamamen ilk gelen ilk hizmet alır düzenindeydi. 180 dakikalık bir koşunun arkasına
düşen bir soru, ne kadar acil olursa olsun 180 dakika bekliyordu. Makinede tek GPU olduğu
için `max_jobs=1` bilinçli bir karar; eksik olan, "hangi iş önce" sorusunun cevabının
yalnızca "hangisi önce geldi" olmasıydı.

## İkinci bir arq kuyruğu neden açılmadı

arq'ta bir `Worker` tam olarak bir `queue_name` tüketir. İki gerçek kuyruk iki worker
süreci demektir; iki worker ise aynı GPU için yarışır ve bütün kurulumun üzerine kurulu
olduğu tek-iş serileştirmesini bozar — AGENTS.md'deki "ikinci bir worker aynı ARQ kuyruğu
ile GPU için yarışır" uyarısı tam olarak bu.

Bunun yerine tek kuyruğun **içinde iki bant** açıldı. Kullanıcı açısından davranış istenen
davranışın aynısı; ayrı süreç yok.

## Skor bandı nasıl çalışıyor

arq bekleyen işleri Redis'te bir sıralı kümede tutuyor. `_defer_until` verildiğinde işin
skoru o anın epoch milisaniyesi oluyor (`arq/connections.py:164`), worker ise
`zrangebyscore(min=-inf, max=now)` ile **artan skor sırasında** çekiyor
(`arq/worker.py:391`, `_queue_read_offset` her zaman 0). Yani skor, kuyruk sırasının
kendisi.

Acil işler kendi kuyruğa giriş anlarının **on yıl öncesine** kaydırılmış hâliyle giriyor
(`queueing.PRIORITY_SHIFT`). Kaydırma sabit olduğu için acil bandın kendi içinde ilk gelen
ilk hizmet alır düzeni bozulmuyor; on yıl da normal bandın tamamını üstte bırakacak kadar
uzak.

**Neden sabit küçük bir kaydırma değil.** Bir saatlik kaydırma yeterli olmazdı: bir saatten
uzun süredir bekleyen normal bir iş, az önce gelen acil işten hâlâ küçük skorlu olurdu.
Bant ayrımı ancak "hiçbir normal işin ulaşamayacağı kadar geri" ile sağlanıyor.
`tests/test_priority_queue.py` bunu bir yıl beklemiş normal bir işle karşılaştırarak
doğruluyor.

**`_expires` neden açıkça veriliyor.** arq, `_expires` verilmezse iş anahtarının TTL'ini
`score - enqueue_time_ms + 24 saat` diye hesaplıyor (`connections.py:170`). Geçmişe
kaydırılmış skorda bu ifade negatife düşer ve `psetex` çağrısı Redis tarafından
reddedilir — yani iş hiç kuyruğa girmez. `score_kwargs` bu yüzden her iki bantta da
`_expires=1 gün` gönderiyor ve bir test bunu sabitliyor.

## `queueing.py`: kuyruğun tek sahibi

Öncelik eklenmeden önce beş ayrı yerde elle `redis.enqueue_job` çağrılıyordu. Bir bantlama
kuralını beş çağrıya elle dağıtmak, birinin unutulması hâlinde **sessizce** yanlış sıra
demekti — geçen sürümde yaşananın aynısı (varsayılanı değiştirmek, değeri açıkça gönderen
çağıranları düzeltmiyor). Bu yüzden kuyruğa dokunan her şey tek modüle taşındı:
`job_id_for`, `score_kwargs`, `enqueue_run`, `rescore_run`, `discard_run_jobs`.

Beş çağrı yeri de buradan geçiyor: `api.py`'de koşu açma, resume, HITL yanıtı ve açılıştaki
uzlaştırma; `worker.py`'de kurtarma.

### İş kimliği deterministik hâle geldi ve bu mevcut bir hatayı kapattı

`resume` ve `respond` yolları rastgele iş kimliği üretiyordu. İki sonucu vardı:

- İptal edilen böyle bir koşunun kuyruktaki işi kaldırılamıyordu (`zrem` `run:<id>`
  arıyor), iş çalışıp aşama sınırında kendini durduruyordu.
- Panel sıra numarasını gösteremiyordu; `job_id.removeprefix("run:")` eşleşmiyordu.

Deterministik kimliğe geçmenin tek engeli arq'ın "bu kimlikte iş zaten var" kontrolüydü:
biten bir işin sonuç anahtarı `keep_result=60` boyunca duruyor ve bu iki yol tam da yeni
bitmiş bir işi yeniden kuyruğa koyuyor. `enqueue_run` bu yüzden kuyruğa koymadan önce, iş
**çalışmıyorsa**, bayat `job_key` ve `result_key` anahtarlarını siliyor. Çalışan bir işin
anahtarlarına dokunulmuyor — worker'ın kendi kayıt tutmasını bozardı.

## Önceleme

Sıralama tek başına yetmiyor: başlamış bir koşu bütçesi boyunca GPU'yu tutuyor, dolayısıyla
bir dakika sonra gelen acil soru yine saatlerce bekleyebilirdi. `scheduler.preempt_for`
çalışan normal koşuyu duraklatıyor.

- Boru hattı bunu **saniyeler içinde** görüyor: `_interruptible` her poll turunda koşunun
  durumunu yeniden okuyup uçuştaki düğümü iptal ediyor, aşamanın bitmesi beklenmiyor.
- **Bedeli:** duraklatılan koşu son aşama checkpoint'inden devam ediyor, yani o aşamanın
  checkpoint'ten sonraki işi yeniden yapılıyor. ACQUIRE ortasında öncelenen bir koşu için
  bu dakikalar olabilir. Bilinçli takas: acil işin beklemesi bundan pahalı sayıldı.
- Acil koşular birbirini **öncelemiyor**; aralarında ilk gelen ilk hizmet alır.

**Sahiplik sınırı bilinçli olarak geçiliyor.** Duraklatılan koşu başkasına ait olabilir, bu
yüzden yazma `Principal.system()` ile yapılıyor. Zamanlama platform düzeyinde bir karar;
acil koşuyu başlatan kişi başkasının koşusunu duraklatma yetkisine sahip değil, **planlayıcı**
sahip. Koşunun sahibine görünen şey `paused` durumu ve `preempted` olayı; panel bunu
"Öncelikli koşu için duraklatıldı" rozetiyle açıklıyor — yoksa kullanıcı koşusunun
kendiliğinden durduğunu görürdü.

## `preempted_at` neden ayrı bir alan

Kullanıcının duraklattığı koşu ile planlayıcının duraklattığı koşu `status` alanında
birbirinin aynısı. Bu ayrım olmadan otomatik devam ettirme, birinin bilerek durdurduğu
koşuyu yeniden başlatırdı. `preempted_at` yalnız planlayıcı tarafından yazılıyor ve devam
ettirirken temizleniyor; `tests/test_priority_queue.py` her iki yönü de doğruluyor.

## Otomatik devam neden cron'da, worker'da değil

"Acil iş bitince duraklatılanı yeniden kuyruğa koy" mantığını işi bitiren worker'a bağlamak
mümkündü ama o worker çökerse duraklatılmış koşu kalıcı olarak orada kalırdı — hiçbir şey
onu bir daha almazdı. Bunun yerine `expire_hitl_interactions` ile aynı kalıpta 30 saniyelik
bir cron (`resume_preempted_runs`): her turda çalışan koşu yoksa **ve** kuyrukta acil koşu
yoksa, en eski `preempted_at` koşusu `QUEUED`'a çekiliyor. Bekleyen bir `interaction` varsa
atlanıyor — API'nin resume kuralı da bunu reddediyor. Bir turda yalnız bir koşu alınıyor;
worker zaten tek iş çalıştırıyor.

## Aciliyet neden protokolde değil kolonda

`ResearchProtocol` *neyin araştırılacağını* tarif ediyor ve kullanıcı onu plan kapısında
onaylıyor. Zamanlama kararını oraya koymak, onay belgesine araştırmayla ilgisi olmayan bir
alan eklemek ve plan revizyonunda sıranın değişebilmesi demek olurdu. Ayrıca planlayıcı her
turda "kuyrukta acil iş var mı" diye soruyor; bu bir sorgu, jsonb içinden değil indeksten
cevaplanmalı.

Bu yüzden `research_runs.priority` kolonu ve API sözleşmesinde protokolün **yanında**
duran `ResearchRunCreate.priority`.

## Şema: `0009_run_priority`

| Kolon | Tip | Not |
|---|---|---|
| `priority` | `varchar(10) NOT NULL DEFAULT 'normal'` | Bant |
| `preempted_at` | `timestamptz NULL` | Planlayıcının duraklattığı koşuyu işaretler |

`ix_research_runs_status_priority` (status, priority) — planlayıcının iki sorusu da bu iki
kolonu birlikte filtreliyor. Mevcut satırlar `server_default` sayesinde `normal` bandında
kalıyor; geri alma kolonları ve indeksi düşürüyor.

## İstemciler

| Yüzey | Nasıl soruluyor |
|---|---|
| Telegram | Süre adımından sonra `● Normal` / `⚡ Acil` düğmesi; `--acil` / `--urgent` adımı atlar; `/oncelik <ad\|id> acil\|normal` bekleyen koşuyu taşır; `/kosular` acil koşuları ⚡ ile işaretler |
| MCP | `start_research(..., priority="normal"\|"urgent")` |
| Langflow | `Start Research Run` bileşeninde `Priority` açılır listesi |
| Panel | Bekleyen/duraklatılmış koşularda "Acile al / Normale al", acil koşuda ⚡ rozeti, öncelenen koşuda gerekçe rozeti |
| API | `POST /v1/research-runs` gövdesinde `priority`; `POST /v1/research-runs/{id}/priority` |

Telegram akışı: `/research` → dil → süre → **aciliyet** → kapsam soruları → plan onayı.

Öncelik ucu yalnız `queued` ve `paused` koşularda çalışıyor. Çalışan bir koşuyu yeniden
bantlamak sırasını değiştirmiyor, düşürmek ise "duraklat"ın kafa karıştırıcı bir yolu
olurdu; ikisi de `409` alıyor. Sahiplik `Repository` gardiyanında — başkasının koşusu 404.

## Ekip görünümü: 13. bölüm kararının bilinçli genişletilmesi

`TeamActivity`'ye `priority` eklendi.
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) 13. bölüm bu
tipi "silinerek değil, taşıyamayacak şekilde" kurmuş ve her alanı tek tek gerekçelendirmişti.
Öncelik eklemenin gerekçesi o bölümün kendi gerekçesi: sırada bekleyen kullanıcı boş bir
tablo görüp platformu bozuk sanmasın diye açılan görünüm, öncelik gösterilmezse bu sefer
sıra numarasının neden ilerlemediğini açıklayamaz. Başlık, soru, sayı ve **koşu kimliği**
sızmamaya devam ediyor. `tests/test_run_ownership.py` ve `tests/test_control_panel.py`
alan kümesini sabitliyor, yani bir sonraki alan da aynı tartışmayı zorunlu kılacak.

## Doğrulama

| Ne | Sonuç |
|---|---|
| Test | 346 geçiyor |
| Göç | `0008_telegram_link_codes -> 0009_run_priority` uygulandı; kolonlar ve indeks Postgres'te |
| Bant | Acil iş, bir yıl beklemiş normal işin bile önünde; bant içinde FIFO |
| `_expires` | Her iki bantta da açıkça veriliyor |
| İş kimliği | Beş yolun hepsinde `run:<id>`; biten koşu 60 saniye içinde yeniden kuyruğa girebiliyor |
| Önceleme | Çalışan normal koşu `paused` + `preempted_at` + `preempted` olayı; acil acili öncelemiyor |
| Otomatik devam | Yalnız `preempted_at` koşuları; kullanıcının duraklattığı duruyor; acil iş varken bekliyor; `interaction` varsa atlıyor |
| Öncelik ucu | Çalışanda 409, bekleyende yeniden puanlama, başkasınınkinde 404 |
| Planlayıcı okumaları | Sistem/yönetici dışına kapalı (`RunAccessDenied`) |

Uçtan uca elle doğrulanacaklar (tek GPU ve gerçek koşu süresi gerektirdiği için otomatik
teste alınmadı):

1. Uzun bir normal koşu ACQUIRE'a girsin; Telegram'dan acil bir koşu başlatın → ilki
   saniyeler içinde duraklamalı, panelde gerekçe rozeti görünmeli.
2. Acil koşu bitince duraklatılan koşu 30 saniye içinde kendiliğinden `queued` olmalı.
3. Sırada bekleyen bir koşuyu `/oncelik <ad> acil` ile yükseltin → panelde sıra numarası
   1'e düşmeli.
4. Elle duraklatılmış bir koşu, cron çalışmasına rağmen duraklatılmış kalmalı.

## Bilinen sınırlar

- **Öncelik iki seviye.** Üçüncü bir bant skor kaydırmasını çoğaltmayı gerektirir; ihtiyaç
  görülmediği için açılmadı.
- **Acil koşuyu kim işaretleyebilir sınırlanmadı.** Herkes kendi koşusunu acile alabilir;
  tek kullanıcılı bu kurulumda kota anlamsız olurdu. Çok kullanıcılı bir kullanımda bunun
  bir kota ya da yönetici onayı gerektireceği açık.
- **Öncelenen koşunun sahibi bildirilmiyor.** Panelde rozet görünüyor ama Telegram'da bir
  mesaj gitmiyor; koşuyu izleyen bot yalnız plan kapılarını bildiriyor.
