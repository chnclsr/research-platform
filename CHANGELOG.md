# Değişiklik Günlüğü

Platform sürümü: `v0.6.7`

Belge sürümü: `3.2`

Son güncelleme: `2026-07-20`

## v0.6.7 — 2026-07-20

- Run listesinde mevcut LangGraph aşamasını ve yaklaşık pipeline konumunu gösteren kompakt ilerleme çubuğu eklendi.
- Run detayına 17 düğümlü yatay flow chart eklendi; tamamlanan, aktif, bekleyen, atlanan, duraklatılan ve hatalı düğümler ayrı görünüyor.
- Her flow düğümü ziyaret sayısını ve aşamada geçirilen toplam süreyi gösteriyor.
- Coverage recovery döngüsü gerçekleştiğinde `PLAN_RECOVERY → SEARCH` geri dönüşü ayrıca işaretleniyor.
- Flow chart mobil/dar ekranda yatay kaydırılabilir ve aktif düğüm erişilebilirlik için `aria-current=step` taşıyor.
- Tam otomatik test sonucu `129 passed`.

## v0.6.6 — 2026-07-20

- Telegram `/research` komutu süre verilmediğinde işi hemen başlatmak yerine inline süre seçimi gösteriyor.
- Süre modları Hızlı (10 dk), Standart (30 dk), Derin (120 dk) ve Maksimum (180 dk) olarak tanımlandı.
- Callback yalnız isteği oluşturan kullanıcı ve chat tarafından, 15 dakika içinde, bir kez kullanılabiliyor.
- Seçimden sonra butonlar kaldırılıyor ve uygulanan süre ile kaynak politikası başlangıç mesajında gösteriliyor.
- `--minutes N` kullanan otomasyonlar ve ileri kullanıcılar için doğrudan başlatma yolu korundu.
- Telegram polling artık `callback_query` update türünü de alıyor.
- Tam otomatik test sonucu `127 passed`.

## v0.6.5 — 2026-07-20

- `ResearchBudget.max_sources` opsiyonel hale getirildi; boş/null değer global kaynak tavanı olmadığı anlamına geliyor.
- Telegram araştırmalarında `--sources` verilmezse kaynak sayısı süre bütçesine bağlı olarak sınırsızdır.
- `--sources N` ile pozitif herhangi bir kullanıcı limiti seçilebilir; yapay üst sınır kaldırıldı.
- MCP `start_research` aracında `max_sources` varsayılanı `null` yapıldı; Codex/Claude isterse sayı gönderebilir.
- Sınırsız modda discovery turundaki bütün kabul edilmiş yeni adaylar acquisition'a alınır; süre hard limit ve connector/tur limitleri korunur.
- Tam otomatik test sonucu `125 passed`.

## v0.6.4 — 2026-07-20

- Run wall-clock bütçesi gerçek hard deadline haline getirildi ve `budget_started_at` checkpoint içinde saklanarak worker restartında sayaç sıfırlanması engellendi.
- Süre dolduğunda run `completed_incomplete` olarak kapanıyor, `budget_exhausted` audit olayı ve mevcut corpus üzerinden çıktı paketi üretiliyor.
- Telegram işleri varsayılan olarak 20 dakika, 50 kaynak ve 3 turla sınırlandı; izin verilen üst süre 60 dakika.
- Telegram `/research` komutuna `--minutes` ve `--sources` seçenekleri eklendi; bot başlangıç mesajında uygulanan bütçeyi gösteriyor.
- Acquisition sırasında her tamamlanan URL için ilerleme olayı ve run heartbeat güncellemesi eklendi.
- Tam otomatik test sonucu `124 passed`.

## v0.6.3 — 2026-07-20

- SEARCH ve ACQUIRE çalışırken bir saniyelik aralıklarla pause/cancel durumu denetleniyor; bloklayan I/O görevi iptal edilip run terminal duruma geçiriliyor.
- SEARCH için 600 saniye, ACQUIRE için 900 saniye kesin güvenlik zaman aşımı ve denetlenebilir `stage_timeout` olayı eklendi.
- Kuyruktaki işler worker beklenmeden doğrudan `cancelled` durumuna geçiriliyor.
- Worker yeniden başladığında eski ARQ in-progress/retry kilitleri temizleniyor; çalışan ve kuyruktaki işler PostgreSQL checkpoint'inden otomatik yeniden kuyruğa alınıyor.
- İptal, hard-timeout, null metadata ve worker recovery regresyon testleri eklendi; toplam test sonucu `121 passed`.

## v0.6.2 — 2026-07-17

- Kaynakça, bibliyografya, `How to Cite`, footer ve benzeri citation-shell bölümleri kanıt çıkarımından çıkarıldı.
- Bibliyografik kayıtların, soru biçimindeki çalışma başlıklarının ve kaynak başlığının iddia olarak raporlanmasını engelleyen fail-closed evidence quality gate eklendi.
- `qualified` ve `supported` raporlaması için en az bir geçerli destek kanıtı zorunlu hale getirildi; geçersiz kanıt nedenleri claim audit kaydına ekleniyor.
- Sentez yalnız doğrulanmış alıntıları alıyor ve protokolde seçilen rapor dilini açıkça uyguluyor.
- Zorunlu sentinel kaynaklar exact title, persistent ID ve canonical URL ile ayrı arama/acquisition görevlerine dönüştürüldü; eksik sentinel için hedefli recovery eklendi.
- arXiv kimliğinden ve açık HTML yayın metadata'sından edinim sonrası tarih enrichment eklendi.
- Beşten az discovery observation olduğunda tahmini completeness artık yanıltıcı `%100` yerine ölçülmemiş (`null`) gösteriliyor.
- Citation-capable connector bulunmadığında veya citation çağrıları hata verdiğinde `citation_frontier_degraded` olayı üretiliyor.
- Toplam otomatik test sayısı `115 passed` sonucuna ulaştı.

## v0.6.1 — 2026-07-17

- Kontrol paneli araştırma operasyon merkezine dönüştürüldü; hızlı ana görünüm korunurken ağır run ayrıntıları isteğe bağlı yükleniyor.
- Run drill-down ekranına LangGraph zaman çizelgesi, query branch sonuçları, kaynak hunisi, admission dağılımı ve yapılandırılmış event görünümü eklendi.
- Sentinel recall, estimated completeness, relative recall, citation novelty, reserve false-negative ve coverage nedenleri görselleştirildi.
- Kaynak kataloğu; connector, aile, keşif yöntemi, admission katmanı, relevance ve query branch provenance’ıyla panelden incelenebilir hale geldi.
- Connector ekranına health, credential durumu, canlı çağrı başarı oranı, sonuç/kabul katkısı, ortalama/p95 gecikme, 429/403/timeout hata sınıfları ve bağlantı testi eklendi.
- RTX 4060 kullanım, VRAM, sıcaklık ve güç değerleri ile CPU, RAM, disk ve Ollama model telemetrisi eklendi.
- Run çıktı paketleri güvenli panel proxy’si üzerinden indirilebilir hale getirildi; API token istemciye açılmıyor.
- Panelin LAN CIDR, Trusted Host, geçici control token ve CSP güvenlik sınırları korundu.
- Yeni panel özet, GPU ve güvenlik regresyonlarıyla tam test paketi `104 passed` sonucuna ulaştı.

## v0.6.0 — 2026-07-17

- `v0.5.3` çalışma noktası `v0.5.3-research-quality-baseline` etiketi ve doğrulanmış bağımsız Git bundle ile korundu.
- Protokole bilinen kritik kaynak/sentinel listesi ve gerekli connector tanımı eklendi.
- İlk arama beş yerine sekiz sorgu dalını kullanıyor; connector sonuç limiti artık protokoldeki gerçek değeri koruyor.
- Connector bazlı query compiler doğal dil sorgularını sağlayıcıya uygun, kısa sorgulara dönüştürüyor; tarih aralığı API alanlarında uygulanmaya devam ediyor.
- Aday kabulü `accept / reserve / reject` katmanlarına ayrıldı; düşük metadata puanı alan güvenli adaylar küçük bir denetim örneğiyle içerik kapısına taşınıyor.
- Semantic Scholar ve OpenAlex citation ilişkileri, en fazla iki derinlikli ve tur başına sınırlı gerçek citation frontier adaylarına dönüştürüldü.
- Sentinel recall, incidence tabanlı tahmini completeness, relative recall, citation novelty, reserve false-negative ve kritik connector coverage ölçümleri stopping döngüsüne bağlandı.
- Semantic Scholar anahtarsız public modda tamamen devre dışı bırakılmıyor; düşük kapasiteli/degraded ama kullanılabilir olarak raporlanıyor.
- Anahtarsız Semantic Scholar fan-out’u tur başına iki sorguyla sınırlı; kritik connector coverage canlı çağrı başarı oranını da denetliyor.
- Provider provenance birleştirmesi connector katkılarını ve query branch’lerini kaynak üzerinde koruyor.
- Yeni kalite testleriyle toplam test sayısı 98’e yükseltildi.

## v0.5.3 — 2026-07-17

- MCP ağ geçidine bearer/CIDR korumalı istemci run listeleme, durum ve ZIP indirme uçları eklendi.
- Ekip paketi `.env` değerlerini otomatik okur; yeni işleri masaüstüne doğrulanmış ZIP olarak indirir.
- Codex ve Claude kurucuları ortak arka plan eşitleyicisini kurar; uygulama hook bağımlılığı kaldırıldı.
- Başarısız/iptal edilen işler için durum JSON'u ve tekrar denemeli eşitleme günlüğü eklendi.

## v0.5.2 — 2026-07-17

- Kontrol paneli ofis kullanımı için `0.0.0.0:8020` üzerinde dinleyecek biçimde yapılandırıldı.
- Loopback ve yapılandırılmış ofis CIDR'ı dışındaki istemcileri reddeden uygulama katmanı ağ koruması
  eklendi.
- Trusted Host listesine ofis sunucusu IP'si ve bilgisayar adı eklendi.
- Windows Firewall betiği yalnız `LocalSubnet` için MCP `8010/TCP` ve panel `8020/TCP` portlarını
  birlikte açacak biçimde güncellendi.
- Panel LAN adresi, ekip kurulum ve kontrol paneli belgelerine eklendi.

## v0.5.1 — 2026-07-17

- Göreli zaman ifadeleri zorunlu UTC araştırma kapsamına dönüştürüldü.
- Akademik sağlayıcılara tarih filtresi ve edinim sonrası tarih/alaka kapısı eklendi.
- Akademik yayın sorularında ilgisiz resmî ve kod kaynakları coverage uğruna zorlanmıyor.
- Claim alakasının yalnız kaynak puanından miras alınması engellendi.
- Ham veri modundaki yanlış claim-audit coverage eksiği giderildi.
- Yerel modelle belge-merkezli semantik kaynak kabul kapısı ve strict ham teslimde
  tekrar denemeli fail-closed politikası eklendi.
- Crossref için seri istek sınırı, `Retry-After` desteği ve yapılandırılabilir polite-pool
  e-posta alanı eklendi.
- Akademik başlık metadata'sında recall eşiği düşürüldü; nihai precision edinim sonrası
  deterministik ve LLM kapılarında korunuyor.
- `01KXNSZAGK5SBQEWFW5CY76385` için tarih ve alaka regresyon testleri eklendi.

## v0.5.0 — 2026-07-17

- Araştırma servislerinden bağımsız çalışan localhost kontrol paneli eklendi.
- API, worker, MCP ve Telegram süreçleri panelden başlatılabilir, durdurulabilir ve yeniden
  başlatılabilir.
- Aktif, sıradaki ve son tamamlanan run'lar; aşama, sıra, tur, kaynak ve iddia sayılarıyla
  görüntüleniyor.
- Run bazında pause, resume ve cancel kontrolleri eklendi.
- Redis queue derinliği, ARQ worker heartbeat, Ollama modeli ve servis PID'leri izleniyor.
- API, worker, MCP, Telegram ve panel logları tek ekrandan okunabiliyor.
- Panel yalnız `127.0.0.1:8020` üzerinde çalışıyor; yönetim çağrıları sayfaya özgü geçici kontrol
  tokenıyla korunuyor.
- Oturum açılışında paneli başlatan Scheduled Task ve masaüstü kısayolu eklendi.

## v0.4.3 — 2026-07-16

- Ofis sunucusu başlangıcında Docker servisleri sağlıklı olana kadar bekleme eklendi.
- API Redis bağlantısına yeniden deneme ve çalışma sırasında yeniden bağlanma eklendi.
- Redis kuyruğu yokken sessiz `queued / INIT` run oluşturulması engellendi.
- Açılışta eski queued ve cancel_requested run kayıtları uzlaştırılıyor.
- Terminal run'lara ait yarım kalmış ARQ queue/in-progress anahtarları temizleniyor.
- Worker düğüm sınırlarında run durumunu veritabanından yenileyerek uzak pause/cancel isteklerini
  görüyor.
- API ve durum betiği kuyruk/worker sağlığını doğru raporluyor.
- Worker heartbeat aralığı 30 saniyeye indirildi.

## v0.4.2 — 2026-07-16

- Aynı Wi-Fi ağındaki Codex ve Claude Code istemcileri için ofis sunucusu modu eklendi.
- Native Research API varsayılan bind adresi `127.0.0.1` yapılarak gereksiz LAN erişimi kapatıldı.
- Non-loopback MCP için en az 32 karakter rastgele bearer token ve `MCP_ALLOWED_NETWORKS`
  zorunlu hale getirildi.
- MCP gateway'e kimlik doğrulamalı `/health`, sabit-zaman token karşılaştırması ve istemci CIDR
  kontrolü eklendi.
- Wi-Fi IP/token üretimi, güvenli ekip erişim dosyası, durum kontrolü, firewall ve kullanıcı
  oturumunda otomatik başlatma PowerShell scriptleri eklendi.
- Prize bağlı kullanımda sunucunun uykuya girmesini engelleyen güç ayarı scripti eklendi.
- Codex ve Claude Code ekip istemcileri için kurulum scriptleri eklendi.
- Telegram botuna yetki vermeden kullanıcı/chat kimliğini gösteren `/whoami` komutu eklendi;
  bütün araştırma komutları allowlist arkasında kaldı.
- `OFFICE_TEAM_SETUP.md` işletim ve güvenlik dokümantasyonu eklendi.

## v0.4.1-dev — 2026-07-16

- Coverage eksikleri `CoverageGap` nesnelerine, sonraki tur aramaları bütçeli
  `SearchMission` görevlerine dönüştürüldü.
- Kaynak ailesi, otorite, claim desteği ve cevapsız sorgu dalı için ayrı recovery
  stratejileri eklendi.
- Acquisition öncesi kalıcı corpus novelty filtresi ve tekrar bulunan kaynağı yeniden
  indirmeden metadata/query-branch ile zenginleştirme eklendi.
- Resmî-domain görevlerinde sonuç URL'sinin gerçekten izinli domaine ait olduğu doğrulandı.
- MCP, Codex, Claude Code ve Telegram için doğrulanmış resmî doküman ve kaynak depo seed
  registry'si eklendi.
- İlk tur ve sonraki turlar için ayrı kaynak bütçeleri ile mission-balanced aday seçimi
  eklendi.
- Coverage yalnız gerçek edinilmiş kaynak ve kanıtlardan hesaplanmaya başladı; recovery
  görevlerinin paydada sahte sorgu dalı oluşturması engellendi.
- Yeni kaynak yoksa eski source version'ların chunk, embedding ve claim extraction
  işlemlerine yeniden girmesi engellendi.
- Ulaşılamayan Zotero ve anahtarsız/degraded connector'lar her arama çağrısında hata
  üretmek yerine health preflight ile atlanıyor.
- Prompt-injection benzeri discovery başlıkları karantinaya alınıyor; named-product
  araştırmalarında alakasız official/legal sonuçlar coverage'a giremiyor.
- Akademik/web ve code/data aileleri için ayrı coverage eligibility eşikleri eklendi.
- `raw` modu claim extraction ve model sentezini gerçekten atlıyor; MCP ve Telegram
  output mode seçimi protokole taşınıyor.
- Canlı doğrulama run'ı `01KXNFSF8B53543WY39NGJNNE4`, 14 kaynakla aile coverage `1.0`,
  sorgu dalı coverage `0.9167`, otorite coverage `1.0` ve doygunluk `1` üreterek
  `completed` durumunda bitti.

## v0.4.0-dev — 2026-07-16

- Platformun rolü, tek başına cevap veren yerel ajandan Codex ve Claude gibi genel amaçlı
  ajanlara kanıt sağlayan yerel Research Gateway'e genişletildi.
- `raw`, `result` ve `both` teslimat modları eklendi.
- Ham kaynak sürümlerini ve normalize passage'ları taşıyan `13_raw_sources.jsonl` ve
  `14_raw_passages.jsonl` artifact'leri eklendi.
- `raw_bundle.zip`, `result_bundle.zip` ve birleşik `research_bundle.zip` üretimi eklendi.
- Codex ve Claude istemcileri için MCP server ve yedi araştırma aracı eklendi.
- Streamable HTTP MCP endpoint'ine bearer token ve Origin allowlist koruması eklendi.
- Telegram long-polling botu; araştırma başlatma, durum, teslimat, pause/resume/cancel
  komutları ve kullanıcı/chat allowlist'i ile eklendi.
- Codex ve Claude örnek MCP yapılandırmaları ile Agent Gateway mimari raporu eklendi.

## v0.3.0 — 2026-07-16

- OpenAlex connector'ı güncel API key, abstract reconstruction, OA location, version,
  retraction ve citation relation metadata ile yenilendi.
- Semantic Scholar Academic Graph connector'ı; DOI/S2/CorpusId eşleme, rate limiting,
  açık PDF metadata ve citation/reference traversal ile eklendi.
- Zotero Local API ve Web API connector'ları, attachment full-text, collection/tag
  filtresi ve incremental library-version sync desteğiyle eklendi.
- Zotero kullanıcı notları corpus'ta saklanabilse de bilimsel evidence extraction dışında
  tutuldu.
- DOI/PMID/PMCID/arXiv/OpenAlex/S2/Zotero kimliklerini birleştiren scholarly identity
  katmanı ve provider snapshot kaydı eklendi.
- PostgreSQL `source_relations` citation graph ve `connector_sync_cursors` tabloları
  eklendi.
- Federated akademik sonuçlarda RRF sinyali, açık tam metin, çalışma türü, retraction ve
  Zotero priority-tag sinyalleri reranking'e eklendi.
- Citation graph, academic coverage, Zotero collections ve Zotero sync API'leri eklendi.
- PaperQA2 mevcut pipeline'ı değiştirmeyen, varsayılan kapalı optional shadow evidence
  backend'i olarak eklendi.

## v0.2.7 — 2026-07-16

- Nitel model değerlendirme metodolojisindeki sayısal ölçüm sınırı netleştirildi.
- Hız, token, VRAM, context, hata oranı ve formatter oranı gibi nesnel metriklerin
  sayısal raporlanmasına izin verildi.
- Etiketleri önceden dondurulmuş corpus üzerinde retrieval precision, recall, hit-rate,
  MRR ve nDCG ölçüm kuralları eklendi.
- Yasak, nesnel ölçümlere değil; öznel kalite boyutlarını keyfî ağırlıklarla tek bileşik
  model puanına dönüştürmeye sınırlandı.

## v0.2.6 — 2026-07-16

- Sayısal model sıralaması yerine ham çıktıların uzman yorumuna dayanan nitel değerlendirme
  metodolojisi önceden kilitlenmiş belge olarak eklendi.
- Körleştirme, formatter ayrımı, tartışmalı gold etiketleri ve metodoloji ihlali kuralları
  tanımlandı.
- Önceki otomatik holdout'un model ve parser geliştirmesinde kullanıldığı için bağımsız
  holdout sayılamayacağı belgelendi.

## v0.2.5 — 2026-07-16

- Nanbeige4.1-3B Q8_0, Q6_K ve Q4_K_M quantization adayları RTX 4060 üzerinde incelendi.
- Q8_0 için 36.864 token tam-GPU context ve 32.768-token reasoning profili doğrulandı.
- Ollama sampling arayüzüne `min_p` ve `repeat_penalty` desteği eklendi.
- Thinking finali geçerli JSON ise gereksiz formatter çağrısı atlanmaya başlandı.
- Evidence extraction top-level JSON array ve `{claims: [...]}` biçimlerini kabul ediyor.
- Nanbeige maksimum-quality profili bağımsız holdout üzerinde iki temiz koşuyla ölçüldü.

## v0.2.4 — 2026-07-15

- Qwen 3.5 4B için 24K context ve 20.480-token reasoning tavanlı profil eklendi.
- Serbest thinking çağrısını ayrı deterministic JSON formatter çağrısına bağlayan iki
  aşamalı Ollama structured-output desteği eklendi.
- Maksimum-thinking profili bağımsız holdout üzerinde üç kez doğrulandı.
- Reasoning ve formatting süre/token metrikleri ayrı kaydedilmeye başlandı.

## v0.2.3 — 2026-07-15

- Qwen 3.5 9B benchmark adaylarından ve yerel Ollama kurulumundan çıkarıldı.
- Qwen 3 4B ile Qwen 3.5 4B için model başına tam-GPU profil taraması yapıldı.
- Qwen 3.5 4B'nin 73.728 token tam-GPU context sınırı doğrulandı.
- Bağımsız holdout üzerinde üç tekrarlı Qwen 4B nesil karşılaştırması eklendi.

## v0.2.2 — 2026-07-15

- RTX 4060 üzerinde model başına tam-GPU context ve sampling profil taraması eklendi.
- Ayrı geliştirme ve bağımsız holdout setleriyle üç tekrarlı model benchmarkı eklendi.
- Ollama sağlayıcısına temperature, top-p, top-k ve presence-penalty ayarları eklendi.
- Qwen 3 4B için 24K, Qwen 3.5 9B için 4K tam-GPU profilleri doğrulandı.

## v0.2.1 — 2026-07-15

- Qwen 3 4B ve Qwen 3.5 9B için araştırma-agentına özgü hard benchmark eklendi.
- Ollama structured-output çağrılarına açık thinking, context ve output token sınırları eklendi.
- RTX 4060 üzerinde 4K/8K context GPU yerleşimi ve kalite/hız karşılaştırması raporlandı.

## v0.2.0 — 2026-07-15

- Yapısal passage üretimi ve belgenin tamamını kapsayan extraction eklendi.
- BM25, yerel embedding, RRF ve ikinci aşama reranking eklendi.
- Kalıcı yerel corpus araması ve `/v1/corpus/search` API'si eklendi.
- Canonical URL, içerik hash'i, raw snapshot ve provenance kapsamı genişletildi.
- Kontrollü link frontier, PDF normalizasyonu ve Scrapling fallback eklendi.
- Migration işlemi transaction güvenli hale getirildi ve Compose migrate servisi eklendi.
- Araştırma kalitesi golden recall ölçümünde %33,3'ten %100'e yükseldi.

## v0.1.0 — 2026-07-14

- FastAPI, LangGraph worker, connector registry ve çıktı paketiyle ilk çalışan V1 oluşturuldu.
- PostgreSQL, Redis, MinIO, AgentSearch, Crawl4AI, Langflow ve Ollama entegrasyonları eklendi.
