# Belge revizyonu uygulama raporu

- Tarih: `2026-09-14`
- Dal: `feature/document-revisions-codex`
- Taban: `origin/developments-supplementer` / `b64a580`

## Amaç

Tamamlanmış bir araştırmanın Word ve PowerPoint çıktılarının kullanıcı geri bildirimiyle
yeniden üretilmesini, önceki dosyaların korunmasını ve kabul edilmemiş bir taslağın mevcut
indirme bağlantılarını değiştirmemesini sağlamak.

## Kullanıcı akışı

1. Kullanıcı Telegram'da veya kontrol panelinde bir belgeyi seçip geri bildirim verir.
2. Ajan değişiklik planını hazırlar. Belirsizlik varsa kullanıcıdan açıklama ister.
3. Kullanıcı planı onaylar veya ek geri bildirimle yeniden hazırlatır.
4. Worker aynı içerik modelinden DOCX, PPTX ve iki ZIP paketini üretir.
5. Kullanıcı taslağı indirip inceler. Kabul edildiğinde dört çıktı tek transaction içinde
   güncel sürüme taşınır. Reddedilen veya başarısız taslaklar güncel sürümü etkilemez.

## Veri modeli ve durumlar

- `document_revisions`: revizyon numarası, temel revizyon, kullanıcı geri bildirimi,
  plan, netleştirme soruları, durum ve Telegram oturum bilgisi.
- `artifact_versions`: her revizyona ait değişmez nesne anahtarı, karma, boyut ve MIME tipi.
- `revision_citations`: revizyon oluşturulurken alınan atıf anlık görüntüsü.
- Durum akışı: `awaiting_feedback` → `queued` → `planning` → `clarifying` veya
  `awaiting_plan_approval` → `queued` → `rendering` → `validating` →
  `awaiting_revision_approval` → `accepted`.
- İptal, başarısızlık ve önceki kabulün yerini alma ayrı terminal durumlarıdır.
- Eski koşular ilk revizyon istenince mevcut teslimat manifestinden geriye dönük olarak
  başlatılır. Yeni koşular ilk kabul edilmiş revizyonu dışa aktarma sırasında oluşturur.

## Güvenlik sınırları

- Plan yalnızca tanımlı operasyonları kullanabilir: başlık/metin değişimi, bölüm yeniden
  yazma veya kısaltma, bölüm adlandırma/sıralama ve sınırlı biçim düzeltmeleri.
- `RevisionPlan` bilinmeyen alanları reddeder. İçerik operasyonları ortak modeli değiştirir
  ve DOCX/PPTX'e birlikte uygulanır; yalnız biçim operasyonları tek formata yöneltilebilir.
- Kaynak etiketleri, hedef başına atıf sayısı, doğrudan alıntılar ve sayısal bulgular
  değiştirilemez. Plan bu kilitleri kaldırmayı talep edemez.
- Biçim düzeltmeleri sadece mevcut PPTX şekillerinin sınırları/yazı boyutu ile DOCX stil
  yazı boyutunu değiştirebilir. Planlayıcı seçilen dosyanın şekil/stil kataloğunu görür;
  böylece doğal dildeki slayt tarifini güvenli hedefe eşleyebilir. Rastgele OOXML, dosya
  yolu veya komut yürütme yoktur.
- Kullanıcı sahipliği bütün API, panel ve MCP yollarında repository katmanında doğrulanır.
- Aynı `idempotency_key` tekrarlandığında yeni revizyon oluşmaz. Eski bir temele dayanan
  revizyon kabul edilirken çakışma hatası üretilir.
- Planlama veya render sürerken gelen iptal, sonraki worker geçişleri tarafından ezilmez.
  Kuyruktaki iş kaldırılır; çalışan iş güvenli durum sınırında durur.

## Entegrasyonlar

- API: revizyon oluşturma/listeleme, durum, netleştirme cevabı, plan onayı, geri bildirim,
  kabul, iptal, metin farkı, sürüm indirme ve geçmiş sürümden taslak oluşturma.
- Worker/ARQ: araştırma işleriyle aynı öncelik ve kapasite kapısı; yeniden başlatma sonrası
  yarım kalan planlama/üretim işleri tekrar kuyruğa alınır.
- Telegram: dosya seçimi, ajan geri bildirimi, plan onayı, taslak indirme ve kabul akışı.
- Kontrol paneli: revizyon geçmişi, eski/yeni metin farkı, geçmiş dosyaları indirme ve
  geçmiş sürümü yeni onay taslağı olarak geri yükleme.
- MCP: revizyon başlatma, durum sorgulama, soruya cevap verme, plan onayı, kabul ve sürüm
  listeleme araçları.

## Teslimat bütünlüğü

Her üretimde aşağıdaki dört mantıksal çıktı aynı revizyon kimliği altında saklanır:

- Koşu etiketini koruyan `16_<etiket>_report.docx`
- Koşu etiketini koruyan `16_<etiket>_report.pptx`
- `result_bundle.zip`
- `research_bundle.zip`

ZIP paketleri yeni Word ve PowerPoint dosyalarıyla yeniden kurulur. Üretimden sonra Office
paketleri ZIP/OOXML olarak yeniden açılır; gerekli girdiler, içerik tipleri, slayt/bölüm
sayısı ve şekil sınırları doğrulanır. Sunucuda Office veya LibreOffice olmadığı için worker
şu aşamada piksel tabanlı PDF/PNG karşılaştırması yapmaz; son görsel onay kullanıcıya
sunulan taslak üzerinden verilir.

## Doğrulama

- Revizyon motoru, kanıt kilitleri, sürümleme, sahiplik ve worker toparlama testleri.
- Gerçek DOCX/PPTX üretimi ve iki ZIP paketinde aynı yeni dosyaların bulunduğu entegrasyon
  testleri.
- Telegram callback boyutu, kalıcı oturum, plan/taslak/kabul ve sürüm indirme testleri.
- Kontrol paneli proxy ve UI sözleşmesi testleri.
- Değiştirilen Python dosyalarında derleme, kritik Ruff kontrolleri ve gömülü JavaScript
  için `node --check`.
- `0012` migration'ı geçici SQLite veritabanında `upgrade` → `downgrade` → `upgrade`
  turunu tamamladı.

İzole Windows ortamında `1128 passed, 5 skipped, 2 deselected` sonucu alındı. POSIX'e özgü
ölçekleme harness'i Windows'ta toplanamadığı için hariç tutuldu. Paylaşılan sanal ortamda
`pdf-inspector 1.14.1` kurulu olduğu halde dal `1.19.0` beklediği için bu sürüme bağlı iki
parser testi seçilmedi. Paylaşılan ortamı ve başka ajanın çalışmasını etkilememek için paket
yerinde yükseltilmedi.

## Canlıya alma

Bu dal canlı veritabanına migration uygulamaz ve çalışan servisleri yeniden başlatmaz.
Birleştirme sonrasında sırasıyla bağımlılıkların kilitli sürümlerle kurulması, `0012`
migration'ının uygulanması, API/worker/Telegram servislerinin birlikte yeniden başlatılması
ve örnek bir revizyonun uçtan uca kabul edilmesi gerekir.
