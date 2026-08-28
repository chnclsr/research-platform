# Değişiklik Günlüğü

Platform sürümü: `v0.15.0`

Belge sürümü: `6.34`

Son güncelleme: `2026-08-28`

Ayrıntılı gerekçeler ve ölçümler
[DEVELOPMENTS_IMPLEMENTATION_REPORT.md](DEVELOPMENTS_IMPLEMENTATION_REPORT.md) ile
[MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md](MULTI_USER_AUTH_V0.10.0_IMPLEMENTATION_REPORT.md)
ve [DOCLING_GPU_SERVICE_V0.13.0_IMPLEMENTATION_REPORT.md](DOCLING_GPU_SERVICE_V0.13.0_IMPLEMENTATION_REPORT.md)
ve [HARDWARE_TELEMETRY_V0.14.0_IMPLEMENTATION_REPORT.md](HARDWARE_TELEMETRY_V0.14.0_IMPLEMENTATION_REPORT.md)
ve [ENV_MANAGED_CONFIGURATION_V0.15.0_IMPLEMENTATION_REPORT.md](ENV_MANAGED_CONFIGURATION_V0.15.0_IMPLEMENTATION_REPORT.md)
içindedir; v0.9.1 ve öncesinin raporları [previous_reports/](previous_reports/) altındadır.

## v0.15.0 — 2026-08-25

- **Literatürün Konu Haritası** ana gövdeden **Ek B**'ye taşındı. Ana rapor artık Özet,
  Araştırma Çerçevesi, Tematik Kanıt Sentezi ve Sonuç sırasını izliyor; kaynak kataloğu
  Ek C, iddia kaydı Ek D, koşullu kaynak figürü kaydı Ek E olarak raporlanıyor. Konu
  haritası görselleri Ek B.1/B.2 biçiminde numaralanıyor.
- Kaynak figürlerinin yayın dilindeki özgün açıklamaları denetim kaydında korunurken,
  raporda görünen caption artık Türkçe raporda Türkçe, İngilizce raporda İngilizce
  hazırlanıyor. Figür görselinin içindeki kaynak etiketlere dokunulmuyor.
- Figür caption'ı ve model yorumu artık iki yönlü bir dil kapısından geçiyor. Her seçili
  caption en fazla iki kez ayrı çevriliyor; `Fig 2`/`Figure 2`/`Şekil 2` etiketleri ve
  yerel sayı yazımları tanınıyor. Çeviri doğrulanamazsa yabancı caption yerine kısa yerel
  açıklama gösteriliyor; çevrilemeyen model yorumu gizlenip Ek E'de `—` kullanılıyor.
  Özgün caption ve ham analiz provenance için korunuyor.
- Panel üst çubuğundan kalıcı aydınlık/koyu tema seçilebiliyor. Açık palet tablolar,
  çekmece, akış, rozetler ve etkileşim kutuları için ayrı kontrastlarla uygulanıyor.
- **Kaynak Hunisi** artık **Referans Haritası** adını taşıyor. **Kabul Edilen Kaynaklar**
  tablosu en alakalı referans üstte olacak biçimde alaka yüzdesine göre sıralanıyor.
- Sentez bölümünün adı rapor dilini izliyor: Türkçede **Özet**, İngilizcede **Summary**.
  Word ve Markdown teslimleri aynı dil eşlemesini kullanıyor.
- Araştırma ayrıntısındaki başlıklar **Kalite ve Kapsam**, **Sorgu Dalları** gibi Türkçe
  başlık düzenine getirildi. **Kabul Edilen Kaynaklar** listesi varsayılan olarak kapalı,
  erişilebilir bir açılır/kapanır bölümdür.
- Raporun Türkçe ilk ana bölümü artık **Özet** adını taşıyor. Beş temalı uzun koşul
  sentezleri 8K model bağlamını doldurmayacak biçimde dengeli bütçeleniyor; geçersiz son
  sentez bir kez onarılıyor ve güvenli geri dönüş sözcük ya da atıf ortasında kesilmiyor.
- Modelin metin alanında JSON listesi döndürmesi Python liste gösterimi olarak rapora
  sızmıyor. Hangi tema veya overview katmanının onarım/geri dönüş kullandığı koşu olayında,
  yeniden üretilebilirlik manifestinde ve Word yöntem ekinde görülebiliyor.
- Güvenlik, kapasite, worker, veritabanı, kuyruk, telemetri, API/istemci ve pipeline
  davranışını belirleyen uygulama sabitleri `.env` üzerinden yönetilebilir hâle geldi;
  mevcut kurulumun değerleri değiştirilmeden `.env` ve `.env.example` içine yazıldı.
- `ACQUISITION_CONCURRENCY=4` artık yeni koşuların edinim paralelliğinin gerçek varsayılanı,
  `FRONTIER_MAX_DEPTH=2` ise citation frontier derinliğinin gerçek varsayılanıdır. İstemci
  protokolde açık değer gönderirse koşu-bazlı tercih üstün gelmeye devam eder.
- Redis bağlantısının başlangıç, olağan işlem ve sağlık sorgusu deneme sayıları ayrı
  değişkenlerdir; önceki `30 / 3 / 1` davranışı korunur. Gecikme de `.env` ile ayarlanır.
- Connector'a özgü yapılandırmalar, Telegram davranışı ve Docker/Compose değerleri bu
  sürümün kapsamına alınmadı.
- `HARDWARE_TELEMETRY_OUTPUT_TYPE` telemetri çıktı setini seçiyor: `csv` ham ölçüm CSV'si
  ile özet JSON'ı üretip çizilmiş SVG grafiğini atlıyor, `all` üçünü de üretiyor.
  Varsayılan `all` olduğu için anahtarı tanımlamayan kurulum aynı dosyaları almaya devam
  ediyor. `csv` modunda grafik üretilip atılmıyor, hiç çizilmiyor; koşunun teslimat
  paketleri de yalnız üretilmiş dosyaları alıyor.
- Pipeline zaman çizelgesi ayrı bölüm olmaktan çıkıp Araştırma Akışı'nın içine alındı.
  Ziyareti olan aşama kutusuna tıklanınca o aşamanın bütün turları süresi ve özetiyle
  listeleniyor, satır açılınca turun connector/parser/model dökümü görünüyor. Akış
  kutucuğunun tam ekran düğmesi var; Escape önce tam ekranı, sonra koşu çekmecesini
  kapatıyor.
- Uzun koşularda zaman çizelgesi sessizce kesiliyordu: panel olayların ilk 5.000'ini
  okuduğu için 207 `ACQUIRE` turu olan bir koşuda yalnız 63 tur görünüyordu. Aşama
  sınırları artık tavansız okunuyor ve tur listesi eksiksiz.
- Bir saniyenin altında süren aşamalar `0 sn` yerine gerçek değerlerini gösteriyor
  (`0,01 sn`, `0,31 sn`); böylece kısa süren aşama ile hiç iş yapmadan dönen aşama
  ayırt edilebiliyor.
- `18_structured_extracts.json` her kayıtta kaynağı bulan connector'ı da yazıyor
  (`connector_id`). Dosya parser çıktısının ham hâli olduğu için, yanlış görünen bir
  tablonun izi artık hem connector'a hem parser'a kadar sürülebiliyor. Alan bundan sonra
  dışa aktarılan koşularda görünür.
- Word raporu koşunun konu etiketiyle adlandırılıyor: `16_research_report.docx` yerine
  `16_ai_in_lung_ct_report.docx`. Telegram'ın koşu yanında bastığı tutamağın aynısı
  kullanılıyor, böylece iki koşunun raporu aynı klasöre indirildiğinde hangisinin ne
  olduğu ad'dan anlaşılıyor. Etiketi olmayan koşularda eski ad korunuyor.
- Bir koşu `failed` olduğunda koşuyu başlatan kişiye Telegram'dan bildirim gidiyor: koşu
  adı, kimliği ve hata nedeni mesajda yer alıyor. Bildirim sahiplik üzerinden kurulduğu
  için MCP, API ve panelden başlatılan koşular da kapsanıyor; her koşu bir kez duyuruluyor
  ve duyuru kaydı bot yeniden başlasa da korunuyor. `TELEGRAM_FAILURE_NOTICE_WINDOW_H`
  (varsayılan 24 saat) ne kadar geriye bakılacağını belirliyor, böylece özellik açıldığında
  eski hatalar yeniden duyurulmuyor. Yalnız `failed` bildiriliyor — `cancelled` kullanıcının
  kendi iptali, `completed_incomplete` ise bir kapsam teşhisi.
- Panelin üst özet kartı GPU modelini artık kartın kendisinden okuyor. Önceden başlık
  `RTX 4060 VRAM` olarak sabitti ve gösterilecek kart adında `4060` aranarak seçiliyordu;
  başka bir GPU'lu makinede rakamlar doğru gelirken başlık yanlış kalıyordu. Kart yoksa
  nötr `GPU VRAM` yazıyor.
- `OFFICE_TEAM_SETUP.md` Ubuntu sunucusuna göre güncellendi. Sunucu tarafındaki komutlar
  bash oldu, panel ve MCP adresleri `10.0.10.171` olarak düzeltildi, olmayan `.env.office`
  referansları `.env` ile değiştirildi. Windows Firewall ve otomatik başlatma bölümlerinin
  yerini ufw'nin docker portlarını atlaması, `MCP_BIND_HOST` arayüz sınırı ve
  `CONTROL_PANEL_ALLOWED_HOSTS` aldı. Ekip bilgisayarlarındaki istemci kurulumu
  (`install_codex_client.ps1`, `install_claude_client.ps1`) PowerShell olarak korundu.
- Telegram'daki plan onay mesajı artık kapsam sorularına **verilen yanıtları** ve önceki
  geri bildirimin metnini gösteriyor; eskiden yalnız sorular sohbette kalıyor, geri bildirim
  ise `Önceki geri bildiriminiz: 1` gibi bir sayıya iniyordu.
- Strateji notu cümle ortasında kesilmiyor. Sabit 500 karakterlik dilim yerine mesajın
  kalan bütçesi kullanılıyor, kesme cümle veya kelime sınırında yapılıp `…` ile
  işaretleniyor. Plan çok uzunsa mesaj sınırı aşmak yerine türetilmiş blokları (sorgu
  dalları, alt sorular) düşürüyor; kullanıcının yanıtları ve geri bildirimi en son düşer.
- Planı reddedip "tarih aralığı son 1 yıl olsun" demek artık gerçekten tarihi
  değiştiriyor. Önceden reddetme notu yalnız yönlendirme olarak kullanılıyordu ve koşu
  plan aşamasına geri sardığında ilk seçilen pencere protokolün üzerine yeniden yazılıyordu;
  yani istek sessizce geri alınıyordu. Reddetme metni artık kapsam sorularıyla aynı
  sözlükten geçiyor. Kaynak ailesi yalnız açık bir "sadece/yalnızca" ifadesiyle
  değişiyor, tarih penceresi ise üç hazır seçenekle sınırlı değil ("son 2 yıl" da geçerli).
- Plan üç kez değiştirilmek istendikten sonra koşu iptal edilirse Telegram'dan bildirim
  gidiyor. Önceden bu iptal tamamen sessizdi: bildirim yalnız `failed` koşuları kapsıyordu
  ve `cancelled` kullanıcının kendi iptali sayıldığı için dışarıda bırakılmıştı. Kullanıcının
  kendi iptali sessiz kalmaya devam ediyor; ayrım artık statüye değil, kapının yazdığı olaya
  bakılarak yapılıyor.
- Plan mesajı son değişiklik hakkı kaldığında uyarıyor. Sınırın varlığı, dolana kadar
  kullanıcıya hiç söylenmiyordu.
- Kesme işareti içeren Türkçe sorular artık çalışıyor. `/research Akciğer BT'sinde yapay
  zeka` gibi bir komut, kesme işareti tırnak sayıldığı için koşu başlatmak yerine sessizce
  komut listesi bastırıyordu. Çift tırnaklı gruplama korundu.
- Yardım ve hata mesajları sorunun dilinde geliyor. Komut ayrıştırılamadığında dil yalnız
  Telegram istemcisinden okunuyordu, bu yüzden Türkçe soruya İngilizce yanıt dönebiliyordu.
- Plan limiti bildirimi üretimde çalışmıyordu: sorgu `json` sütunları üzerinde `DISTINCT`
  kullanıyordu ve PostgreSQL bu tip için eşitlik operatörü tanımlamıyor. Bekleyen iki koşu
  bildirimlerini alacak.
- Panel artık HITL checkpoint'lerini yanıtlamıyor, yalnız gösteriyor. Aynı kapıya hem
  sohbetten hem panelden cevap verilebilmesi çift başlılık üretiyordu: panelden onaylanan bir
  plan, Telegram'da bekleyen düğmeleri geçersiz kılıyordu. Karar artık koşunun başlatıldığı
  kanaldan veriliyor (Telegram düğmeleri, MCP `respond_to_research_checkpoint`). Bekleyen
  checkpoint panelde tam olarak görünmeye devam ediyor — sorular, planın tamamı, taslak ve
  kaynak domainleri — kartın altında kararın nerede verileceğini söyleyen bir not var.
- Panelin duraklat/devam/iptal ve öncelik düğmeleri değişmedi; bunlar kuyruk işlemleri.
- `CONTROL_PANEL_GUIDE.md` Ubuntu sunucusuna göre güncellendi: panel adresi `10.0.10.171`,
  olmayan `.env.office` referansları `.env`, PowerShell başlatma komutlarının yerine systemd,
  Windows Firewall yerine ufw. LAN'dan gelen `400 Invalid host header` ile `403`'ü ayıran not
  eklendi. Telemetri satırındaki sabit "RTX 4060" kaldırıldı; kart adı `pynvml`'den okunuyor.
- Üç açık iş `OPEN_ITEMS.md`'ye yazıldı: kanalsız başlatılan koşunun plan kapısında asılı
  kalabilmesi, panelde çağıranı olmayan koşu başlatma ucu ve `research_runs` sütunlarının
  `json` olması (bu sonuncusu bir sorguyu üretimde sessizce kırmıştı).

## v0.14.0 — 2026-08-25

- Araştırmalar kapasite kuyruğundan çıktıkları anda ortak Docker/WSL CPU-RAM ve toplam GPU
  yükünü kaydediyor; kuyrukta geçen süre ölçüme katılmıyor.
- Paralel koşular donanımı ayrı ayrı sorgulamıyor. Tek örnek her etkin koşunun kendi stage
  etiketi ve kimlik açıklamayan paralel-koşu sayısıyla kaydediliyor; grafik örtüşen süreyi
  gölgeliyor ve tüketimi tek bir koşuya atfetmiyor.
- Başarılı, eksik, başarısız ve iptal edilmiş admitted koşular CSV, özet JSON, SVG grafik
  ve bağımsız donanım ZIP paketi üretiyor. Tamamlanan koşuların ana teslimat paketleri de
  telemetri dosyalarını içeriyor.
- GPU veya NVML bulunmayan kurulumlarda CPU/RAM grafiği devam ediyor. Telemetri arızası
  araştırma durumunu değiştirmiyor, özgün pipeline hatasını maskelemiyor ve kapasite
  slotunun bırakılmasını engellemiyor.
- Kontrol paneli donanım SVG'sini sahiplik korumalı artifact yolu üzerinden önizliyor;
  ham örnek event'leri uzun koşuların panel zaman çizelgesi kotasını tüketmiyor.
- Paket, API, MCP gateway ve panel artık sürümü kurulu dağıtım metadata'sındaki tek
  değerden okuyor; health yanıtları, OpenAPI metadata'sı, `__version__` ve panel footer'ı
  aynı etiketi gösteriyor.
- Donanım SVG'sinde panel başlığı, legend ve üst eksen etiketleri için ayrılan alanlar
  ayrıştırıldı; küçük ve büyük önizlemelerdeki metin iç içe geçmeleri giderildi.

## v0.13.0 — 2026-08-25

- **Connector operasyon ekranındaki sahte “disabled” durumu giderildi.** Panel connector
  sağlığını eski `API_TOKEN` yerine kurulumun `SERVICE_TOKEN` değeriyle sorguluyor;
  çalışan connector'lar yeniden doğru etkin/sağlıklı durumlarıyla görünüyor. Değişiklik
  araştırma worker'larını veya devam eden koşuları yeniden başlatmıyor.
- **Commit ve push artık tam test kapısına bağlı.** Son kod değişikliğinden sonra bütün
  pytest paketi geçmeden yayın yapılmıyor; test ortamı çalışmıyorsa önceki bir koşunun
  sonucu yeterli sayılmıyor. Codex sandbox'ının sağlam `.venv` için üretebildiği yanıltıcı
  erişim hatasının teşhisi de geliştirici notlarına eklendi.
- **Sistem mimarisi diyagramı güncel çalışma biçimini gösteriyor.** Langflow ve panel
  girişleri, sahiplik korumalı API, acil/normal Redis öncelikleri, kapasite kapılı paralel
  koşular, Git/Jina dahil edinim kümesi ve ayrı Docling GPU servisi eklendi. Diyagram
  Cezeri Robot'un koyu kömür ve camgöbeği renkleriyle yenilendi.
- **GitHub repository URL'leri artık akıllı işleniyor.** Bir depo HTML sayfası gibi
  kazınmak yerine `--depth 1` ile geçici alana klonlanıyor; README, manifest ve kaynak
  dosyaları commit kimliğiyle birlikte yapılandırılmış metne dönüşüyor. Başarı, hata,
  zaman aşımı ve iptal yollarının tamamında klon ve çalışan Git süreci temizleniyor;
  işleyici başarısız olursa mevcut HTTP fallback zinciri devam ediyor.
- **Bot korumasına veya boş JavaScript kabuğuna takılan sayfalar için Jina Reader
  fallback'i eklendi.** Doğrudan indirme, AgentSearch ve Crawl4AI başarısız olursa
  anahtarsız browser motoru deneniyor; o da başarısızsa mevcut Scrapling yolu devam
  ediyor. Dış servis kapatılabilir veya self-host endpoint'e yönlendirilebilir.
- **PDF'lerin ağır ayrıştırma yolu artık gerçekten koşuyor.** Sayfa yönlendirme zaten
  vardı ama gönderdiği sayfaları alacak bir motor hiçbir yerde çalışmıyordu: 12 gerçek
  koşu PDF'i üzerinde ölçüldüğünde 372 sayfanın 138'i ağır motora yönlendiriliyor ve
  **hiçbiri** işlenmiyordu. Docling artık kendi servisinde koşuyor; aynı 12 belgede 138
  sayfanın 138'i işlendi, **120 tablo** yapısal olarak kurtarıldı (öncesi: 0) ve toplam
  metin %12,8 arttı. Belgeler artık `degraded` işaretlenmiyor.
- **NVIDIA kartı olan makinede GPU kullanılıyor.** `.env`'e iki satır eklemek yeterli;
  komutlar değişmiyor. Kartı olmayan makinede aynı yığın CPU'da çalışır — daha yavaş,
  ama eksiksiz.
- **Hangi cihazın ürettiği artık kayıt altında.** Aynı PDF, aynı Docling sürümü, CPU ve
  GPU'da farklı metin üretiyor. Bu yüzden cihaz tahmin edilmiyor: hangi cihazın
  isteneceği açıkça yazılıyor, istenen cihaz bulunamazsa servis başlamıyor, ve her
  belgenin kaydında hangi cihaz ve hangi sürümle ayrıştırıldığı duruyor.
- **Ağır motor ulaşılamazsa hiçbir sayfa kaybolmuyor.** Servis kapalıysa ya da zaman
  aşımına uğrarsa sayfa hızlı yol metnini koruyor, belge `degraded` işaretleniyor ve
  gerekçe kaydına yazılıyor.
- Sistem sağlığı ekranı artık ağır yolun durumunu ve hangi cihazda koştuğunu gösteriyor.
- **Ayrıştırmanın ne kadar sürdüğü kayıtta.** Toplam süre, sayfa yönlendirme kararının
  süresi ve ağır motorun süresi ayrı ayrı yazılıyor. Acquisition'ın kendi ölçümü indirme
  ile ayrıştırmayı birlikte sayıyordu; "bu belge indirilirken mi yoksa ayrıştırılırken mi
  yavaştı" sorusunu cevaplayamıyordu.
- **Bir koşunun PDF'lerini nasıl ayrıştırdığı tek komutla rapor edilebiliyor**
  (`scripts/inspect_bundle.py <run_id> --heavy --md <dizin>`): hangi sayfa hangi
  gerekçeyle ağır motora gitti, motor ne üretti, hangi cihazda ve ne kadar sürede.
  Ayrıntılar README'de.
- **Teslimat paketindeki üretilebilirlik manifestosu artık her kaynağın nasıl
  ayrıştırıldığını da yazıyor.** Önceden yalnız "kullanıcı hangi parser'ı zorladı"
  bilgisi vardı; şimdi hangi parser'ın seçildiği, hangi motorun kaç sayfayı ürettiği,
  hangi cihazda ve hangi sürümle ürettiği kayıtta. Bir belgenin metnini yeniden
  üretmek isteyen biri için gereken bilgi buydu.
- README ve mimari belgelerdeki akış diyagramları güncel boru hattı, Smart PDF Router ve
  karantina kararlarını aynı terimlerle gösterecek biçimde yenilendi.
- Geliştirici ve ajan işletim yönergeleri tek kaynak olarak `AGENTS.md` altında toplandı;
  dal, rebuild, yedekleme ve dağıtım tuzakları artık ayrı kopyalarda ayrışmıyor.
- PDF ayrıştırma raporu artık `--fast` ile nihai metni Inspector'da kalan sayfaları,
  `--all` ile bütün PDF sayfalarını gösterebiliyor. Inspector sayfaları hiç
  yönlendirilmemiş, ağır motor fallback'i veya kalite karantinası olarak ayrılıyor.
  Rapor adı seçim modunu otomatik taşıyor (`_fast.md`, `_heavy.md`, `_all.md` veya
  `_page-3-8.md`); farklı görünümler artık aynı hedef verilse bile birbirini ezmiyor.

## v0.12.0 — 2026-08-21

- **Birden fazla araştırma aynı anda koşabiliyor.** Kaç tanesinin koşacağı elle
  ayarlanmıyor: her koşu başlamadan önce makinenin o anki uygun RAM'i, CPU yükü ve
  Ollama'nın bildirdiği yerleşik VRAM'i ölçülüp hesaplanıyor. Donanım dört-beş koşu
  taşıyorsa dört-beş koşu başlıyor; makinede başka bir iş yükselirse sayı kendiliğinden
  düşüyor. Bu makinede ölçülen değer 3-4 ve sınırlayıcı CPU.
- Makine asla son kaynağına kadar doldurulmuyor: işletim sistemine ayrılan bir RAM rezervi
  ve CPU payı var, ve bir koşu bu rezervi yiyecekse başlatılmıyor. Yer açılana kadar
  sırada bekliyor — çalışan hiçbir koşu kapasite için durdurulmuyor.
- **Model çağrıları tek sırada.** Paralel koşular GPU'yu aynı anda kullanmıyor; her LLM ve
  embedding çağrısı sırasını bekliyor. Karta aynı anda birden fazla model yüklenmiyor —
  kaç koşu çalışırsa çalışsın kaplanan VRAM aynı. Kazanç buradan geliyor: bir koşu kaynak
  toplarken diğeri analiz ediyor. Sırada beklemek çağrının zaman aşımı bütçesini yemiyor.
- Eşzamanlı olan **koşular**, koşunun içi değil: tek bir araştırma bu sürümde daha hızlı
  bitmiyor, yalnız ikincisi birincinin bitmesini beklemiyor. İki koşu aynı anda analiz
  aşamasındaysa örtüşme olmaz, sırayla ilerlerler.
- Panelde ve `/health` çıktısında kaç paralel koşuya izin verildiği ve **hangi kaynağın
  sınırladığı** görünüyor.
- Acil koşu artık yalnız boş yer yokken bir koşuyu duraklatıyor; yer varsa kimseyi
  durdurmadan başlıyor.
- **Koşular kalıcı olarak silinebiliyor.** `research-admin purge-runs --status cancelled`
  bir koşunun bütün izini kaldırıyor: kaynaklar, pasajlar, iddialar, kanıt bağları,
  olaylar, checkpoint'ler ve nesne deposundaki anlık görüntüler. İptal etmek koşuyu
  bitiriyordu ama panelde, corpus havuzunda ve diskte bırakıyordu. Komut önce eşleşenleri
  listeliyor; silmek için `--yes` gerekiyor.
- Paralellikle birlikte ortaya çıkan üç kusur giderildi: aynı yayıncıya gidiş hızını
  sınırlayan bekleme koşu başına kuruluyordu ve koşu sayısına bölünüyordu (artık ortak);
  veritabanı bağlantı havuzu paralel koşulara göre büyütüldü; ve bir araştırma çalışırken
  zamanlanmış bakım işleri (HITL zaman aşımı, öncelenen koşuyu devam ettirme) hiç
  çalışmıyordu.

## v0.11.0 — 2026-08-21

- **Acil koşular sırada öne geçiyor.** Kuyruk artık iki bantlı: acil olarak başlatılan bir
  araştırma bekleyen bütün normal koşuların önüne geçiyor, normal koşular onlardan sonra
  işleme alınıyor. Acil koşular kendi aralarında yine ilk gelen ilk hizmet alır düzeninde.
- **O sırada çalışan normal koşu duraklatılıyor.** Acil koşu geldiğinde çalışan koşu
  saniyeler içinde duruyor, acil olan bitince kendiliğinden kaldığı yerden devam ediyor.
  Duraklatılan koşu son aşama checkpoint'inden devam ettiği için o aşamada yapılan işin bir
  kısmı yeniden yapılıyor — acil işin saatlerce beklemesine tercih edildi.
- Panelde acil koşularda ⚡ rozeti, öncelik için duraklatılmış koşularda gerekçe görünüyor;
  kendiliğinden duran bir koşu artık açıklamasız değil.
- **Aciliyet başlatırken soruluyor.** Telegram'da süre adımından sonra `● Normal` / `⚡ Acil`
  düğmesi geliyor (`--acil` yazarsanız adım atlanıyor). MCP aracında `priority`, Langflow
  bileşeninde `Priority` listesi, panelde "Acile al / Normale al" düğmesi var.
- Sırada bekleyen bir koşunun önceliği sonradan değiştirilebiliyor:
  Telegram'da `/oncelik <ad|run_id> acil|normal`, panelde düğme. Çalışan bir koşuda
  reddediliyor — sırasını değiştirmediği için yanıltıcı olurdu.
- Ekip görünümünde başkalarının koşularının aciliyeti görünüyor; sıranın neden ilerlemediği
  aksi hâlde açıklanamıyordu. Başlık, soru ve koşu kimliği hâlâ sızmıyor.
- Kuyruğa girişin beş ayrı yolu tek yerde toplandı. Yan etkisi: `resume` ve HITL yanıtı
  yollarında koşuların iş kimliği rastgele üretiliyordu, bu yüzden bu koşular iptal
  edildiğinde kuyruktaki işleri kaldırılamıyor ve panelde sıra numaraları görünmüyordu;
  ikisi de düzeldi.

## v0.10.7 — 2026-08-20

- **Koşu adı artık kimliğin yerini tam olarak tutuyor.** `/status`, `/cancel`, `/pause`,
  `/resume`, `/get` ve `/respond` komutlarında ULID yerine botun gösterdiği adı
  yazabilirsiniz. Önceden bot adı gösteriyor ama o adı kabul etmiyordu; kimliği eski
  mesajlarda aramak gerekiyordu. Büyük/küçük harf fark etmiyor ve etiketi olmayan eski
  koşular da sorusundan türetilen adla bulunuyor.
- Aynı ada uyan birden çok koşu varsa bot **tahmin etmiyor**: eşleşmeleri kimlik, durum ve
  tarihle listeliyor ve hiçbirine dokunmuyor. `/cancel` geri alınamadığı için en yenisini
  seçmek yanlış koşuyu iptal edebilirdi.
- Yeni **`/kosular`** komutu (`/runs` eş adı) son koşularınızı adı, durumu ve tarihiyle
  listeliyor. Her satırın altında hazır komut var; dokununca tamamı panoya kopyalanıyor.
- **Adlar kısaldı.** `Research_artificial_intelligence_studies_that_last_3m` yerine
  `artificial_intelligence_last_3m` gibi. Ad artık komuta yazıldığı için dolgu kelimeler
  (`research`, `studies`, `that`, `using`, …) atılıyor ve uzunluk 32 karakterle
  sınırlanıyor. Mevcut koşuların adları değişmiyor.

## v0.10.6 — 2026-08-20

- **Kapsam sorularının ilk ikisi artık gerçekten ayar.** Tarih aralığı ve kaynak ağırlığı
  soruları sabit; şıkları protokolün kendi değerlerini taşıyor ve seçiminiz
  `scope.start_date` ile `connectors.included_families` alanlarına yazılıyor. Eskiden her
  cevap yalnız istemlere ek metin olarak giriyordu, yani "resmî kaynaklara öncelik ver"
  seçmek connector listesini değiştirmiyordu. Kalan iki soru bugünkü gibi yönlendirme.
  Kendi cevabınızı yazarsanız hiçbir alan değişmez — yazılan cevap yönlendirme olarak
  kalır.
- Tarih aralığı artık **soruluyor**. "Son 3 ay" gibi ifadelerden sessizce çıkarılan pencere
  ilk şık olarak sunuluyor; başka bir aralık ya da "tarih sınırı olmasın" seçebiliyorsunuz.
- Uygulanan ayarlar plan ekranında ve Telegram mesajında ayrı bir satırda listeleniyor:
  hangi cevabın hangi alanı neye çevirdiği görünüyor.
- Botun sorduğu **"hangi dilde ilerleyelim?"** sorusu artık isteğin dilinde. Eskiden
  Telegram istemcisinin dil ayarından geliyordu, yani Türkçe bir istek İngilizce bir
  soruyla karşılanabiliyordu. Çok kısa isteklerde dil anlaşılamıyorsa istemci ayarına
  düşülmeye devam ediyor.
- **Plan onayı artık düğmeyle.** Telegram'da plan mesajının altında "Onayla" ve "Değişiklik
  iste" düğmeleri var; `/respond <run_id> approve` yazmak gerekmiyor. Değişiklik istenirse
  bot gerekçeyi soruyor — gerekçesiz reddetme aynı planı yeniden kurup koşuyu revizyon
  sınırına kadar döndürüyordu. `/respond` komutu duruyor: bot yeniden başlarsa düğmeler
  geçersiz kalıyor ve komut tek yol oluyor.
- **Mesajlar koşuyu konusuyla anıyor.** `01M0FG…: yanıt alındı` yerine
  `ai_in_lung_ct_last_3m: yanıt alındı`. ULID kayboluyor değil — dokunulunca kopyalanacak
  şekilde mesajın içinde duruyor ve komutların argümanı hâlâ o.
- Mesajların içindeki **değerler de çevriliyor**: `durum queued` yerine `durum sırada`,
  `Aşama: DECOMPOSE` yerine `Aşama: Ayrıştırma`. Cümleler geçen sürümde iki dilli olmuştu,
  içlerine gömülen enum değerleri olmamıştı.
- Plan mesajı zengin metin: başlıklar kalın, alt sorular ve sorgu dalları katlanmış alıntı
  bloklarında — dokununca açılıyor. Biçimlendirme Telegram tarafından reddedilirse mesaj
  düz metin olarak yeniden gönderiliyor; eskiden böyle bir hata mesajın hiç görünmemesine
  yol açıyordu.

## v0.10.5 — 2026-08-20

- Telegram botu artık tek dilde konuşuyor. İngilizce başlatılan bir araştırmada plan
  onaylandıktan sonra gelen `yanıt alındı, durum queued` gibi karışık cümleler kalktı;
  yardım metninden hata mesajlarına kadar her şey iki dilli.
- Konuşmanın dilini **kullanıcı seçiyor**: `/research` önce "Türkçe / English" düğmesini
  gösteriyor, `--dil en` (ya da `--lang en`) yazılmışsa soru atlanıyor. Seçim sohbeti,
  planlama sorularını, plan ekranını ve raporun dilini belirliyor.
- Araştırma dili değişmedi: arama, edinim ve kanıt çıkarımı İngilizce yürümeye devam
  ediyor.
- **Araştırma başlamadan önce şıklı sorular geliyor.** Model, soruya göre 3-4 daraltıcı
  soru üretiyor; kullanıcı düğmeye basıyor ya da kendi yanıtını yazıyor. Son soruda
  "eklemek istediğiniz bir şey var mı?" diye soruluyor, plan ancak bundan sonra kuruluyor.
- Cevaplar artık alt soru olarak eklenmiyor, **yönlendirme** olarak kullanılıyor. Şık
  cevapları kısa ifadeler olduğu için ("Klinik") eskiden kendi başına bir sorgu dalı
  üretirlerdi. Ölçüm: "iş yükü" seçildiğinde alt soru `radiologist workload` üzerine
  kuruldu ve sorgu dallarına yansıdı.
- Yinelenen şıklar eleniyor: canlı ölçümde model bir soruyu beş kez aynı şıkla döndürdü.
  Böyle bir soru kullanıcıya hiçbir şey sormadığı için atılıyor.
- Panelde de aynı sorular şıklı görünüyor; yanıt biçimi değişmediği için mevcut akış
  bozulmadı.
- Süre düğmesine basan ama hesabı bağlı olmayan kullanıcıda **botu düşüren** bir hata
  giderildi (`_link_hint` yanlış çağrılıyordu).

## v0.10.4 — 2026-08-20

- Araştırma artık soru hangi dilde gelirse gelsin **İngilizce yürüyor**: soru ve alt
  sorular ilk aşamada çevriliyor, kullanıcının yazdığı metin protokolde saklanıyor.
- Sorun yalnız sorgu dili değildi — alaka kapıları soru ile belge arasında sözcük
  örtüşmesi arıyor, dolayısıyla Türkçe soruda İngilizce makaleler LLM'e ulaşmadan
  eleniyordu. Aynı soruda ölçülen: `openalex` 0 → 320, `crossref` 0 → 160,
  `europe_pmc` 0 → 155, `arxiv` 0 → 120 sonuç.
- Alaka kapıları hem İngilizce hem özgün soruyla eşleşiyor; Türkiye'ye özgü bir konuda
  Türkçe resmî belge çevirinin ters etkisiyle elenmiyor.
- İddia metinleri İngilizce üretiliyor ama **alıntılar asla çevrilmiyor** — alıntı
  kaynaktan birebir kopyalanıp pasajda doğrulanıyor, çevrilmiş bir alıntı denetimden
  geçemez ve iddiayı sessizce düşürürdü.
- Rapor kullanıcının seçtiği dilde yazılmaya devam ediyor; `report_language` artık
  yalnız `tr` ve `en` kabul ediyor, çünkü sentezin dil denetimi yalnız bu ikisini
  doğrulayabiliyor.
- Plan onay ekranı sorunun geldiği dilde okunuyor: bölüm başlıkları, sınır açıklamaları,
  alt sorular ve strateji notu. Sorgu dalları İngilizce kalıyor — connector'lara birebir
  o dizeler gidiyor.
- Kullanıcının kendi cümlesi planda önde, İngilizce araştırma sorusu altında duruyor;
  yanlış çeviri bütçe harcanmadan önce yakalanabiliyor.
- Çeviri başarısız olursa koşu düşmüyor, özgün dille devam edip olayı kaydediyor.

## v0.10.3 — 2026-08-19

- **Koşu, planı onaylanmadan aramaya başlamıyor.** Arama öncesi bir plan üretilip
  kullanıcıya sunuluyor; onaylanana kadar hiçbir connector çağrılmıyor.
- Plan, koşunun yapacağı her şeyi yazıyor: sorular, sorgu dalları, kaynak seçimi,
  tarih kapsamı, bütçe, **hangi sınırın gerçekten bağlayıcı olduğu**, durdurma ölçütleri,
  modeller, edinim strateji sırası, parser'lar ve üretilecek çıktılar.
- Sorunun metninden otomatik çıkarılan tarih aralığı artık planda açıkça görünüyor;
  daha önce her sorguyu sessizce daraltıyordu.
- Plan reddedilirse gerekçe alınıp alt sorular ve sorgular yeniden üretiliyor; en fazla
  üç tur, sonra koşu iptal ediliyor.
- **Araştırma süresi zorunlu hâle geldi.** Süresi belirtilmemiş bir protokol artık hiçbir
  yoldan kurulamıyor; sessiz 45 dakika varsayılanı kalktı. MCP aracında da zorunlu
  parametre, Langflow bileşenine girdi eklendi.
- Süre, plan onaylanırken değiştirilebiliyor.
- Telegram botu plan beklediğinde sohbete plan özetini ve onay komutlarını yazıyor;
  `--plansiz` bayrağı kapıyı atlamak isteyenler için.
- Telegram'dan başlatılan koşular `401 Unauthorized` alıyordu: bot `API_TOKEN`, API ise
  `SERVICE_TOKEN` bekliyordu. Bot artık servis jetonunu kullanıyor.
- PDF ve HTML ayrıştırma motorları ayrıştı: `pymupdf_fast` (birincil, iki sütunlu
  akademik makalelerde doğru okuma sırası), `pypdf` (yedek), `html_structured`,
  `plain_text`. Birincil motor bozuk bir PDF'te düşerse edinim durmuyor, sıradaki motora
  geçiyor ve hangi motorun çalıştığı provenance'a yazılıyor.

## v0.10.2 — 2026-08-19

- Kontrol panelinde zaman çizelgesindeki aşama kartları tıklanabilir: bir karta
  tıklayınca o aşamada çalışan connector, edinim yöntemi, parser, LLM ve embedding
  dökümü açılıyor — çağrı, başarı, sonuç, token ve süre kırılımıyla.
- Her kart bir aşama **ziyareti**; aynı aşamanın turlar arası tekrarları ayrı tablolar
  gösteriyor.
- Edinim olayına `parser_id` eklendi, böylece hangi belgenin hangi parser'la okunduğu
  panelden görülebiliyor.
- **İkili içeriğin koşuyu düşürmesi giderildi.** Bir DOI'nin JPEG ek dosyasına çözülmesi
  hâlinde içerik "metin" sayılıyor, mojibake üretiliyor ve içindeki NUL baytı
  veritabanı yazımını reddettirip **o turda toplanan her şeyi** götürüyordu. Artık
  ikili içerik tanınıp atlanıyor.
- README'deki düşük kaliteli mermaid şeması ve ASCII yaşam döngüsü çizimi, mimari ve
  pipeline akışını gösteren SVG diyagramlarla değiştirildi.

## v0.10.1 — 2026-08-18

- MCP artık paylaşılan jeton değil **kişisel API anahtarı** istiyor; `MCP_BEARER_TOKEN`
  kaldırıldı. Böylece ajandan (Claude Code, Codex) başlatılan koşunun gerçek bir sahibi
  oluyor.
- Belirti yanıltıcıydı: paylaşılan jetonla `tools/list` 200 dönüyor ve araçlar görünüyor,
  yalnız *çağrılar* 401 alıyordu — çünkü paylaşılan jeton sistem asli kimliğine eşleniyor
  ve API sahipsiz koşuyu reddediyor.
- Yedekleme betiği ve istemci kurucuları kişisel anahtar kullanacak biçimde güncellendi.

## v0.10.0 — 2026-08-18

- **Panel giriş gerektiriyor ve her kullanıcı yalnız kendi koşularını görüyor.** Kayıt
  formu yok; hesaplar `research-admin` ile kabuktan açılıyor.
- Üç kimlik bilgisi türü tek bir `Principal` kavramına çözülüyor: oturum çerezi, kişisel
  API anahtarı (`rp_...`) ve servis jetonu + `X-Actor-User`.
- Sahiplik route'ta değil **veri katmanında** zorlanıyor: `run_id` alan her `Repository`
  metodu bir metasınıf tarafından otomatik korunuyor, yeni metot eklemek ek iş
  gerektirmiyor.
- Yabancı bir koşu 404 döndürüyor, 403 değil — 403 koşunun var olduğunu doğrulardı.
- Yetki ayrımı: container başlat/durdur, log okuma ve connector testi yalnız yöneticide.
  Bu ayrım olmadan giriş koymak, giren herkese worker'ı durdurma düğmesi vermek olurdu.
- Telegram hesabını kullanıcı kendi bağlıyor: panelden alınan tek kullanımlık, 5 dakika
  geçerli kod bota veriliyor. `TELEGRAM_ALLOWED_USER_IDS` birebir sohbetlerde emekli
  edildi, grup sohbetlerinde korundu.
- Ortak korpus okuması koşunun **sahibine** göre kapsamlanıyor; çağırana göre
  kapsamlamak her kullanıcının metnini her koşuya verirdi.
- Panelden parola değiştirme eklendi; parola değişimi kullanıcının tüm oturumlarını
  düşürüyor.
- Kullanıcı, başkalarının süren koşularını **sansürlü** görüyor — yalnız kim, durum,
  aşama, kuyruk sırası ve geçen süre. Tek GPU paylaşıldığı için bu olmadan kendi koşusu
  sırada beklerken bomboş bir tablo görüp sistemi bozuk sanardı.
- `mcp-gateway` portu tüm arayüzlere bağlıydı, loopback'e alındı.

## v0.9.4 — 2026-08-17

- Word raporundaki `[Sxx]` etiketleri kaynak kataloğuna bağlandı; okuyucu iddiadan
  kaynağa tek tıkla gidebiliyor.

## v0.9.3 — 2026-08-14

- Tamamlanan her koşu, tüm çıktılarını içeren tek bir ZIP olarak yerel yedek klasörüne
  iniyor; teslimat dizini yanlış sahiplikle oluşturulduğu için çalışmayan yedekleme
  devreye alındı.
- Ayrıştırma `parsers/` paketine taşındı: HTML tabloları markdown'a çevriliyor, kod
  blokları korunuyor, PDF okuma sırası düzeltildi.
- Parser seçimi deterministik: içerik sinyallerinden seçiliyor, protokoldeki açık
  override kaydediliyor ve seçilen parser `source_versions.provenance` içine yazılıyor.
  Determinizm şart, çünkü `content_hash` ayrıştırılmış metinden hesaplanıyor ve kaynak
  sürüm tekilleştirmesi buna bağlı.

## v0.9.2 — 2026-08-13

- AgentSearch adaptörü eklendi ve compose yığınına alındı; 3939 portundaki SearXNG
  beklenen sözleşmeye çevriliyor.
- **NORMALIZE checkpoint boyut hatası giderildi.** Büyük PDF içeren koşular
  PostgreSQL'in 256 MiB jsonb sınırında çöküyor ve toplanan tüm belgeler geri
  alınıyordu; ham gövde artık checkpoint'e girmiyor.
- Checkpoint'ler tamamlanan koşularda temizleniyor ve boyut koruması eklendi.
- Kontrol paneli Docker yığınını yönetebiliyor (`CONTROL_PANEL_DEPLOYMENT=docker`);
  `native` modda kalırsa panel 8000/8010 portlarında çakışan süreçler başlatıyordu.
- MinIO verisi named volume yerine host klasörüne (bind mount) alındı: `docker compose
  down -v` artık bu veriyi silmiyor ve klasör doğrudan yedeklenebiliyor.

## v0.9.1 — 2026-07-30

- Modelin raporda yorumlamaya değer bulduğu kaynak figürleri, PDF sayfasındaki
  vektör/raster sınırlarından otomatik olarak kırpılıp ilgili sentez bölümüne
  yerleştiriliyor.
- Özgün figür, kaynak caption'ı, `[Sxx]`, sayfa, paper başlığı, URL, hak/lisans
  uyarısı ve model yorumu tek bir görsel blok halinde sunuluyor.
- Aynı figür için mevcut yapılandırılmış yorumlama, sınırlılık ve güven puanı
  korunuyor; görsel artık yorumun yanında gerçekten görülebiliyor.
- Kaynak figürü güvenli biçimde ayrılamazsa açık değer veya süreç düğümlerinden
  deterministik rekonstrüksiyon yedek davranış olarak devam ediyor.
- Çok parçalı dikey akış şemaları component clustering ile tek figür olarak
  ayrılıyor; aynı sayfadaki iki bağımsız grafik birbirine karıştırılmıyor.
- Kaynak figürü ekleme varsayılan olarak kurum içi araştırma incelemesi içindir;
  dış dağıtım öncesi lisans doğrulama uyarısı caption altında gösteriliyor.
- Canlı doğrulamada dört özgün kaynak figürü Word raporuna yerleştirildi; `6/6`
  görsel alternatif metinli, erişilebilirlik uyarısı sıfır, test sonucu
  `155 passed` ve Ruff temiz.

## v0.9.0 — 2026-07-29

- PDF sayfaları ve HTML `figure/img` öğelerinden source/version/hash bağlantılı
  figure candidate çıkarımı eklendi.
- Kurulu `qwen3.5:4b` yalnız figure analyst olarak kullanılıyor; ana sentez modeli
  değişmedi ve iki model RTX 4060 üzerinde sıralı çalışıyor.
- Vision cevabı figür türü, eksen, seri, açık veri noktaları, süreç adımları,
  ana bulgu, sınırlılık ve uygun rapor bölümüne normalize ediliyor.
- Yaklaşık veya açıkça yazılmayan sayılar chart pipeline'ına alınmıyor; bilinmeyen
  değerlerin LLM tarafından tamamlanması engelleniyor.
- Kaynağa özgü 1–5 puan ölçekleri klinik duyarlılık, özgüllük veya AUC yüzdesi
  olarak yorumlanamıyor; hem bulgu hem caption hem limitation deterministik
  güvenlik uyarısı taşıyor.
- Açık çubuk değerleri ve görünür akış düğümleri Python/Pillow ile deterministik
  yeniden çiziliyor; özgün yayın görseli Word raporuna kopyalanmıyor.
- Yeniden çizilen figürler ilgili tematik sentez bölümünün hemen arkasına caption,
  `[Sxx]` citation ve erişilebilirlik açıklamasıyla yerleştiriliyor.
- Bütün vision gözlemleri Word `Ek D` ve `17_figure_observations.json` içinde
  provenance kaydıyla korunuyor.
- `figure_observations` tablosu ve `0006_figure_observations` migration'ı eklendi;
  aynı source image hash/model/schema tekrar analiz edilmiyor.
- Canlı akciğer görüntüleme run'ında kaynak PDF'deki performans çubuk grafiği ve
  veri ön işleme akış şeması başarıyla okunup yeniden çizildi.
- Ruff temiz; regresyon paketi `154 passed`.

## v0.8.0 — 2026-07-29

- Tek ve büyük rapor çağrısı; en fazla beş temaya ayrılan, küçük kanıt paketleriyle
  çalışan çok aşamalı LLM sentez pipeline'ıyla değiştirildi.
- Her tematik taslak yalnız izin verilen `[Sxx]` kaynak kimliklerine atıf yapabilir;
  bilinmeyen kaynak, URL ve bozuk citation biçimi deterministik kapıda reddedilir.
- Qwen 4B'nin dil veya citation biçimini bozduğu tema taslakları için yeni bilgi
  eklemeyen çeviri/format onarım çağrısı ve güvenli geri dönüş eklendi.
- Word raporunun ana gövdesi kaynak envanterinden yönetici sentezi, tematik
  çalışmalar-arası değerlendirme, ayrışmalar, uygulama anlamı ve sonuç yapısına geçti.
- Kaynak, claim ve coverage sayaç grafikleri ana gövdeden çıkarıldı; yerlerine
  araştırma katkı türleri grafiği ile çalışma–sentez teması kanıt matrisi eklendi.
- Tam kaynak kataloğu, claim register, coverage ve yeniden üretilebilirlik ölçümleri
  kaybolmadan Word raporunun denetim eklerine taşındı.
- Markdown yönetici özeti ve tam rapor da sentez-öncelikli düzene geçirildi.
- Gerçek 16 kaynaklı akciğer görüntüleme araştırması üzerinde yeni DOCX ve iki
  konu grafiği yeniden üretildi; 149 test ve Ruff kontrolü geçti.

## v0.7.2 — 2026-07-29

- Word teslimatı yayın kalitesinde literatür raporu yapısına yükseltildi: kapak,
  içindekiler, yönetici değerlendirmesi, kapsam/kanıt sağlığı, kaynaklı ana
  bulgular, literatür haritası, tam kaynak kataloğu, claim register ve
  yeniden üretilebilirlik bölümü eklendi.
- OpenAlex API anahtarı isteğe bağlı hale getirildi; anahtarsız çalışan açık
  uç nokta artık connector'ı devre dışı bırakmıyor.
- OpenAlex ediniminde açık PDF/landing page tercih edildi; tam metin
  erişilemediğinde doğrulanabilir başlık-yazar-özet metadatası
  `abstract_and_metadata` provenance'ıyla korunuyor.
- Literatür taramasında reserve adayların bütün acquisition kapasitesini
  tüketmesi engellendi; reserve payı en fazla yaklaşık yüzde 25 oldu.
- Zayıf sorgu dallarının düşük ilgili adayları mission balancing ile öne
  taşıması engellendi ve Türkçe tıbbi terimler İngilizce akademik eş anlamlılarla
  genişletildi.
- Süre bütçeli uzun literatür taramalarını erken bitiren sabit LangGraph
  recursion limiti, protokolün dakika bütçesine göre ölçeklenir hale getirildi.
- Aşırı uzun veya geçersiz crawler frontier URL'leri bütün run'ı düşürmek yerine
  audit event'iyle reddediliyor; checkpoint'i olan failed run'lar API üzerinden
  yeniden kuyruğa alınabiliyor.

## v0.7.1 — 2026-07-29

- Her tamamlanan araştırma artık `16_research_report.docx` artifact'ını üretir.
- Word raporu LLM'in serbest dosya üretiminden değil; denetlenmiş claim, evidence,
  source ve coverage kayıtlarından deterministik olarak oluşturulur.
- DOCX içinde kaynak ailesi ve iddia denetim durumu grafikleri, coverage tablosu,
  kaynaklı bulgular ve tıklanabilir kaynak kataloğu bulunur.
- `python-docx` ve Pillow production bağımlılıkları olarak eklendi; iki grafik ayrıca
  PNG artifact olarak teslim paketine dahil edilir.
- Çok aşamalı / küçük parçalara bölünmüş LLM rapor planlayıcısı sonraki sürüm için
  exporter sözleşmesini bozmadan eklenebilecek şekilde ayrıştırıldı.

## v0.7.0 — 2026-07-21

- Varsayılan araştırma amacı seçici cevap üretiminden yüksek-recall `literature_scan`
  moduna geçirildi; eski katı davranış `focused_answer` olarak korunmuştur.
- Bütün alt sorgular ve recovery görevleri ana sorunun konu anchor'larını provider sorgusunda
  miras alır; genel web sorguları güvenli uzunluğa sıkıştırılır.
- Bilinmeyen yayın tarihi literatür modunda otomatik dışlama yerine provenance uyarısıdır.
- Deterministik ve LLM relevance kapıları doğrudan ile bağlamsal literatürü ayırır; yalnız
  açıkça alakasız merkezî konu nihai corpus dışında bırakılır.
- Düşük metadata puanlı reserve adayların acquisition kotası genişletildi; query branch ve
  recovery görevlerine daha fazla edinim slotu verildi.
- Coverage yeterli görünse veya standart gap sorguları tükense bile süre bütçesi varken
  sistematik derleme, dış doğrulama, negatif sonuç, guideline ve replication taramaları sürer.
- `05_source_catalog.csv` literatür rolü, tarih, içerik relevance ve claim sayılarını taşır.
- Kabul edilen her kaynak için “bu kaynak ne söylüyor?” kartı üreten
  `15_literature_inventory.md` eklendi; artifact sayısı 18'e yükseldi.
- Citation talimatı içeren preprint kabuk metinleri evidence olmaktan çıkarıldı.
- Ruff temiz; tam regresyon paketi `141 passed`.

## v0.6.10 — 2026-07-20

- `max_wall_minutes` global pipeline öldürme süresi olmaktan çıkarılıp bilgi toplama
  (`SEARCH/ACQUIRE`) bütçesi olarak düzeltildi.
- Süre dolduğunda tamamlanmış acquisition sonuçları korunur; bekleyen indirmeler iptal edilir
  ve `NORMALIZE → EVIDENCE → AUDIT → SYNTHESIZE_EXPORT` zinciri sonuna kadar çalışır.
- Sert `asyncio.wait_for` iptali kaldırılarak timeout sırasında görülen SQLAlchemy transaction
  kapanma/rollback çakışması giderildi.
- Worker güvenlik süresi post-processing ve senteze izin verecek şekilde 24 saate çıkarıldı.
- Telegram başlangıç mesajı sürenin toplama bütçesi olduğunu açıkça belirtir.
- Tam regresyon paketi `136 passed`.

## v0.6.9 — 2026-07-20

- Telegram `/research both 2 <soru>` kısa yazımı artık `2` değerini dakika olarak algılar
  ve süre seçim menüsünü tekrar açmadan araştırmayı doğrudan başlatır.
- Açık `--minutes 2` biçimi ve süre verilmediğinde gösterilen butonlu seçim akışı korunmuştur.
- Tam regresyon paketi `135 passed`.

## v0.6.8 — 2026-07-20

- Dört seçilebilir human-in-the-loop checkpoint eklendi: planlama soruları, plan,
  kaynak-domain seçimi ve rapor taslağı incelemesi.
- `awaiting_input` durumu, tip güvenli `/respond` API'si ve yanlış/eskimiş interaction
  yanıtlarına karşı `400/409` doğrulaması eklendi.
- Beş dakika yanıt gelmeyen işler state korunarak `paused` durumuna alınır; yanıt sonrası
  en yüksek kullanılabilir öncelikle yeniden kuyruğa girer. Kullanıcı bekleme süresi araştırma
  çalışma bütçesinden düşülmez.
- Kontrol paneline checkpoint kartları, plan/taslak onayı, serbest metin yönlendirmesi ve
  domain bazlı kaynak seçimi eklendi.
- Telegram'a `--hitl` ve `/respond`; MCP'ye checkpoint yapılandırması ve yanıt aracı eklendi.

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
