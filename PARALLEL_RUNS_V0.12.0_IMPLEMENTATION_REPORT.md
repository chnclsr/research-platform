# Donanıma göre paralel koşular — v0.12.0

Platform sürümü: `v0.12.0`

Belge sürümü: `1.0`

Son güncelleme: `2026-08-21`

Worker, API, boru hattı, edinim ve paneli birlikte ilgilendirdiği için kendi raporu var.
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) kapsam
tablosunda tek satırlık işaretçisi bulunuyor.

## Sorun

Worker `max_jobs = 1` ile çalışıyordu: aynı anda tek araştırma. Tek GPU'yu korumak için
konmuş bilinçli bir sınırdı, ama GPU'nun ihtiyaç duyduğundan **çok daha geniş** bir sınırdı.
Bir koşunun duvar saatinin büyük kısmı SEARCH, ACQUIRE ve NORMALIZE'da geçiyor — ağ ve CPU
işi, GPU o sırada boş. İkinci bir araştırma o boşluğu kullanamıyor, sırada bekliyordu.

## Paralellik koşu düzeyinde

Eşzamanlı olan şey **koşular**. Bir koşunun içinde hiçbir şey değişmedi: aşamalar yine
sırayla işliyor, `acquisition_concurrency` yine koşu başına 4, ve **tek bir araştırma bu
sürümde daha hızlı bitmiyor.** Değişen tek şey, ikinci bir araştırmanın birincinin bitmesini
beklemek zorunda olmaması.

Kazancın nereden geldiği de bu yüzden dar: bir koşu ağ ve CPU işindeyken (SEARCH, ACQUIRE,
NORMALIZE) diğeri GPU'yu kullanabiliyor. İki koşu aynı anda EXTRACT_EVIDENCE'a girerse
**örtüşme olmuyor** — model çağrıları tek sırada bekliyor ve o iki koşu, sırayla
çalıştırılmalarına kıyasla neredeyse hiçbir şey kazanmıyor. Yani `allowed = 4` "dört kat
hızlı" demek değil; "GPU boş dururken dört araştırma birden ilerleyebilir" demek.

**GPU'ya aynı anda birden fazla model yüklenmiyor.** Ollama LLM ve embedding modelini
yerleşik tutuyor ve çağrılar bizim semaforumuzda sıraya giriyor; kaç koşu çalışırsa çalışsın
karttaki model sayısı ve kapladığı VRAM aynı kalıyor. Ayrıntısı aşağıda, "GPU: çarpan
değil, önkoşul" başlığında.

## Sayı seçilmiyor, ölçülüyor

Yeni [capacity.py](src/research_platform/capacity.py) her kabul kararından önce makineyi
ölçüyor ve slot sayısını hesaplıyor:

```
slots_ram = floor((uygun_ram - ram_reserve_gb) / run_memory_budget_gb)
slots_cpu = floor((cpu_sayısı * (1 - cpu_headroom) - meşgul_çekirdek) / run_cpu_budget)
slots_gpu = modeller karta birlikte sığmıyorsa 1, aksi hâlde sınırsız
allowed   = max(1, min(slots_ram, slots_cpu, slots_gpu, ABSOLUTE_GUARD))
```

Elle verilen değerler **bütçe ve rezerv** — güvenlik parametreleri. Hiçbiri "en fazla şu
kadar koşu" diyen bir politika tavanı değil: donanım beş koşu taşıyorsa beş koşu açılıyor.

**Bu makinede canlı ölçülen** (worker konteynerinin içinden):

```
max_jobs: 4        (açılış tavanı)
allowed: 3         limited_by: cpu
slots: ram 7 · cpu 3 · gpu 8
uygun RAM 22.76 GB · 16 CPU · meşgul 1.22 çekirdek · yerleşik VRAM 4.29 GB
```

CPU sınırlıyor ve sayı makinedeki anlık yükle birlikte oynuyor — API'den aynı an okunduğunda
yük 0.27 çekirdeğe düştüğü için `allowed` 4 görünüyordu. İstenen davranış bu.

### Darboğaza girmeme garantisi tam olarak ne

- Kabul edildiğinde uygun RAM'i rezervin altına düşürecek koşu **kabul edilmiyor**.
- CPU bütçesi toplam çekirdekten değil, **o anki yükün üstüne** ekleniyor: makinede
  platform dışı bir iş başladığında slot sayısı kendiliğinden düşüyor.
- `allowed` her kabulde yeniden ölçülüyor, önbelleğe alınmıyor.
- Çalışan bir koşu kapasite için **asla** öldürülmüyor; yalnız acil önceleme duraklatıyor.
- `allowed` asla 0 olmuyor: hiçbir koşu çalıştırmamak, bir koşu çalıştırmaktan kötü.

`ABSOLUTE_GUARD = 8` politika değil, kaçak freni. Konteyner limiti kalkar ya da psutil
saçmalarsa cevap yine sonlu kalsın diye.

## GPU: çarpan değil, önkoşul

Model çağrıları süreç genelinde tek sıraya alındığı ve Ollama modeli bir kez yerleşik
tuttuğu için **koşu sayısı VRAM'i artırmıyor**. VRAM'in kararı şu: LLM ve embedding modeli
karta marjla birlikte sığıyor mu?

Sığmıyorsa Ollama her çağrı türü değiştiğinde model tahliye edip yeniden yüklüyor. Paralel
koşular completion ve embedding arasında tek koşudan çok daha sık gidip geldiği için bu
gerçek bir çırpınma sebebi — o durumda `allowed` 1'e sabitleniyor.

**VRAM neden Ollama'dan okunuyor.** Worker konteynerinde `nvidia-smi` **yok** (ölçüldü) ve
GPU'ya iş koyan tek şey zaten Ollama. `/api/ps` modellerin gerçekten kapladığı VRAM'i
veriyor; `nvidia-smi` olsaydı masaüstü bileşicisini de sayardı. Kartın toplam boyutu
(`gpu_vram_total_gb`) değişmeyen bir sayı olduğu için ayarda duruyor.

**Ollama'ya ulaşılamazsa** `resident_vram_gb` `None` oluyor ve GPU sınırlamıyor. Bilinmeyen
ile sıfır aynı şey değil: sonda ulaşılamamasını "GPU boş" diye okumak, savunulamayacak tek
yorum olurdu. RAM ve CPU cevabı yine sınırlıyor.

## Kabul kapısı: iki katman

arq'ın `max_jobs`'ı `Worker` kurulurken sabitleniyor ve çalışma anında değiştirilemiyor.
Bu yüzden:

- **`WorkerSettings.max_jobs = startup_ceiling()`** — açılışta, yalnız CPU/RAM toplamlarından,
  ağ çağrısı olmadan. Süreç ömrü boyunca donanım değişmiyor; değişen yük.
- **Canlı kapı** `execute_research_run` içinde, `pipeline.run()` çağrılmadan önce.

Slot yoksa koşu **bekliyor**: `queued` durumunda kalıyor (çalışmıyor, o yüzden `running`
demek yanlış olurdu), `awaiting_capacity` olayı ölçümle birlikte **bir kez** yazılıyor, ve
`capacity_poll_s` aralıklarla yeniden ölçülüyor.

**Neden kuyruğa geri konmuyor.** Ertelemeli yeniden kuyruğa alma acil bantla çakışıyor:
acil işin skoru `now - 10 yıl` olduğu için `_defer_until` ile verilen gecikme `now`'ın çok
altında kalıyor ve iş anında geri çekiliyor — gecikme kılığında bir dönen döngü. Beklemek
hem doğru hem ucuz (bir `asyncio.sleep`) ve kuyruk sırasını bozmuyor.

**Öncelik adaleti.** Kapı süreç içi, çünkü bütün koşuları tek worker süreci çalıştırıyor —
"şu an kaç koşu çalışıyor" bilgisinin tek doğru kopyası orada. Slot boşaldığında önce acil
bant, sonra kuyruğa giriş sırası alıyor. Bu olmadan hangi bekleyen önce yoklarsa slotu o
alırdı ve öncelik bandı kuyruğun kenarında sona ererdi.

## Model çağrıları tek sırada

`OllamaProvider.complete_json` ve `EmbeddingClient.embed` süreç genelinde paylaşılan tek
bir semaforu alıyor.

**Neden aşama düzeyinde değil.** EXTRACT_EVIDENCE'ı komple kilitlemek GPU'yu dakikalarca
tutar ve öteki koşunun bir saniyelik DECOMPOSE çağrısını o kadar bekletirdi. Çağrı düzeyi
aynı güvenceyi veriyor — hiçbir an iki model çağrısı birlikte uçmuyor — ve açlık üretmiyor.
Kilit tek bir POST'un değil, mantıksal çağrının tamamının etrafında: `complete_json` içinde
üç POST'lu bir biçim merdiveni var ve onun ortasına başka bir koşunun çağrısı girmemeli.

**Zaman aşımı bütçesi korunuyor.** `llm_timeout_s` (180 sn) httpx'e istek başına veriliyor,
yani sayaç semafor alındıktan **sonra** başlıyor. Tek GPU'da paralel koşuların en gerçek
riski buydu: kilitsizken iki koşu çağrı gecikmesini katlar ve zaman aşımları tetiklenirdi.

**Bilinen sınır:** semafor worker sürecinin içinde. API süreci corpus arama için ara sıra
embedding çağırıyor ve o çağrı bu sıranın dışında; Ollama onu kendi kuyruğuna alıyor.

## Paralelliğin ortaya çıkardığı üç kusur

Bunlar "iyi olur" değil; paralellik açılınca **yanlış davranış** üretecek yerlerdi.

**`DomainLimiter` koşu başına kuruluyordu.** Yani `domain_delay_s` N koşuda sessizce
`domain_delay_s / N` oluyor, aynı yayıncıya N kat hızlı gidiliyordu. Nezaket garantisi
paralellikle birlikte kırılıyordu; sonucu 429 ve engellenme. Limiter süreç genelinde tek
örneğe çekildi. Connector'lardaki 429 geri çekilmeleri bunun yerini tutmuyor: onlar
tepkisel, istekler çoktan gitmiş oluyor.

**Veritabanı havuzu** varsayılan 5+10 ile çalışıyordu. Her koşu ana oturumun yanında
`_interruptible` ve checkpoint için kısa ömürlü oturumlar açıyor; 4-5 paralel koşuda havuz
sınıra dayanırdı. Havuz artık açılış tavanından türetiliyor (SQLite'ta atlanıyor).

**Cron işleri `max_jobs`'a takılıyordu.** arq cron'ları aynı sıralı kümeye koyuyor ve
`_poll_iteration` yalnız `job_counter < max_jobs` iken çekiyor — yani `max_jobs=1` iken bir
araştırma çalışırken `expire_hitl_interactions` ve `resume_preempted_runs` **hiç
çalışmıyordu**. Mevcut bir hataydı; tavanın yükselmesi kendiliğinden kapattı.

## v0.11.0 önceleme kurallarının güncellenmesi

Önceleme "tek slot" varsayımıyla yazılmıştı ([scheduler.py](src/research_platform/scheduler.py)):

- `preempt_for` artık **yalnız boş slot yokken** önceliyor. Slot varsa acil koşu kimseyi
  duraklatmadan başlıyor — öncelemenin bedeli (duraklatılan koşunun checkpoint'ten devam
  edip o aşamanın işini yeniden yapması) boşuna ödenmiyor.
- `resume_preempted` "çalışan normal koşu yok" yerine "boş slot var" koşuluna geçti.

`free_slot()` sayıyı veritabanından okuyor, süreç içi kapıdan değil: aynı soru API
sürecinden de soruluyor ve orada kapı boş görünürdü.

## Görünürlük

Kapasite kararı görünmezse ayarlanamaz. Panel telemetrisinde ve API `/health` çıktısında
`allowed`, slot dökümü ve **hangi kaynağın sınırladığı** duruyor.

**Plandan sapma:** koşu satırına `awaiting_capacity` rozeti koymadım. Panel satırları
doğrudan `research_runs`'tan okunuyor; rozet için her yenilemede olay tablosuna ek bir
sorgu ya da yeni bir kolon gerekirdi. Bekleyen koşu zaten `queued` ve sıra numarasıyla
görünüyor, kapasite kartı da sıranın **neden** ilerlemediğini söylüyor — kozmetik bir rozet
için o maliyet haklı çıkmıyor.

## Doğrulama

| Ne | Sonuç |
|---|---|
| Test | 362 geçiyor |
| Lint | `ruff --select E4,E7,E9,F` temiz |
| Konteynerde | `max_jobs=4`, canlı `allowed=3`, `limited_by=cpu`, VRAM 4.29 GB okunuyor |
| API `/health` | Kapasite özeti dönüyor |
| Formül | Her kaynağın tek tek sınırlayıcı olduğu durumlar; rezerv asla harcanmıyor; `allowed` asla 0 değil; guard tutuyor |
| Kapı | Slot doluyken bekliyor, `awaiting_capacity` bir kez yazılıyor, boşalınca ilerliyor |
| Adalet | Boşalan slotu acil bekleyen alıyor |
| Model kirası | Dört eşzamanlı çağrıda üst üste binme yok |
| Limiter | İki `AcquisitionService` aynı limiter örneğini paylaşıyor |
| Önceleme | Boş slot varken hiçbir koşu duraklamıyor; dolu iken duraklıyor |

Elle yapılacak uçtan uca doğrulama (gerçek koşu süresi gerektirdiği için otomatik teste
alınmadı):

1. Üç araştırma arka arkaya başlatılsın → üçü birden `running`, dördüncü `queued` kalmalı
   ve olaylarında `awaiting_capacity` görünmeli.
2. **`run_memory_budget_gb` ölçülmeli:** iki koşu paralel çalışırken worker'ın RSS'i
   izlenip varsayılan 2.5 GB tahmini gerçek değerle değiştirilmeli. Şu an bir tahmindir.
3. Aynı yayıncıya iki koşudan giden istekler arasındaki mesafe `domain_delay_s`'in altına
   düşmemeli.
4. İki koşu aynı anda EXTRACT_EVIDENCE'ta iken `stage_timeout` olayı çıkmamalı.

## Bilinen sınırlar

- **`run_memory_budget_gb` ölçülmedi, tahmin edildi.** Bütün formülün en zayıf terimi.
  Yukarıdaki 2. maddeyle düzeltilmeli.
- **API'nin embedding çağrıları model kirasının dışında.** Ayrı süreç; Ollama kendi
  kuyruğuna alıyor.
- **`psutil` konteyner içinde WSL2 sanal makinesini görüyor**, Windows host'u değil. Bu
  makinede sanal makine host'un büyük kısmını alıyor, dolayısıyla sayı gerçeğe yakın; farklı
  bir Docker yapılandırmasında rezerv değerinin gözden geçirilmesi gerekir.
- **Kapı süreç içi.** İkinci bir worker süreci çalıştırılırsa iki kapı birbirini görmez.
  Bu kurulumda tek worker var ve tek GPU bunu zaten zorunlu kılıyor.
