# Araştırma Kalitesi İyileştirme Raporu

Platform sürümü: `v0.2.0`  
Belge sürümü: `1.0`  
Son güncelleme: `2026-07-15`  
Nihai canlı koşu: `01KXJACJTMVH018MNP4E18ZT71`  
Model: `qwen3:4b-instruct-2507-q4_K_M` (Ollama)  
Embedding: `embeddinggemma:300m-qat-q4_0`

## Sonuç

İlk 12.000 karakteri modele verme yaklaşımı kaldırıldı. Belgenin tamamı yapısal pasajlara ayrılıyor, bütün pasajlar indeksleniyor, her araştırma sorusu için hibrit olarak geri getiriliyor ve yalnız seçilen pasajlar LLM'e gönderiliyor. Golden kabul setinde kritik bilgi recall'u **%33,3'ten %100'e** çıktı. Nihai koşudaki 90 kanıt bağlantısının tamamı hem seçilen pasajda hem de özgün belgedeki karakter aralığında birebir doğrulandı.

| Ölçüm | Önce | Sonra | Değişim |
|---|---:|---:|---:|
| Golden kritik bilgi recall'u | 3/9 (%33,3) | 9/9 (%100) | +66,7 puan |
| Bulunan claim | 15 | 90 | 6,0x |
| Raporlanabilir claim | 5 | 81 | 16,2x |
| Kesin kaynak konumu doğrulaması | ölçülmüyordu | 90/90 (%100) | yeni güvence |
| Query-branch coverage | düşük/başarısız | %100 | kabul eşiği geçti |
| Claim audit coverage | kısmi | %100 | kabul eşiği geçti |
| Uçtan uca süre | 42,27 sn | 120,96 sn | 2,86x daha uzun |

Zaman maliyeti öncelikli olmadığı için bu değişim kabul edilebilir. Artan süre ağırlıklı olarak 12 pasajdaki kanıt çıkarma ve nihai sentez çağrılarından geliyor; embedding maliyeti düşüktür.

## Uygulanan kalite hattı

1. HTML başlıkları, paragrafları ve bölüm hiyerarşisi korunuyor; script/style ve aktif içerik atılıyor.
2. Belgenin tamamı yaklaşık 700 token hedef ve 100 token örtüşmeyle bölümlere duyarlı biçimde parçalanıyor.
3. Her pasaj SHA-256, kaynak sürümü, bölüm yolu ve özgün karakter başlangıç/bitişiyle PostgreSQL'e yazılıyor.
4. Ollama embedding'leri ile anlamsal skor ve BM25 sözcüksel skor birleştiriliyor.
5. Ana soru ve alt sorular ayrı ayrı aranıyor; bölüm çeşitliliği korunuyor ve boilerplate bölümleri cezalandırılıyor.
6. Komşu pasajlar yalnız bağlam olarak veriliyor; claim alıntısı hedef pasajdan olmak zorunda.
7. LLM'in kaçırdığı fakat sorguyla açıkça ilgili kesin kaynak cümleleri deterministik olarak ekleniyor.
8. Aynı alıntıyı kullanan LLM paraphrase'i, kesin kaynak cümlesinin elenmesine artık yol açmıyor.
9. Evidence link; passage kimliği, bölüm yolu, sayfa, özgün karakter aralığı ve retrieval skorunu taşıyor.

## Canlı koşu ayrıntıları

- Corpus: AgentSearch GitHub README'sinin tamamı
- Üretilen pasaj: 36
- Toplam pasaj tokenı: 2.868
- Embed edilen pasaj: 36/36
- Araştırma için seçilen pasaj: 12/36
- Passage embedding süresi: 2,37 sn
- Query embedding süresi: 0,17 sn
- Ortalama entailment skoru: 0,814
- Entailment skoru >= 0,65: 74/90
- Qualified claim: 81; unresolved/excluded claim: 9
- Instrument edilmiş bir önceki aynı-hat koşusunda GPU tepe belleği: 4.744 MB; tepe kullanım: %98; tepe sıcaklık: 67 C

Seçilen bölümler doğrudan soruyla uyumluydu: `Limitations and security notes`, `Verify`, `Architecture`, `Development`, `Search engines`, `Browser render a JS page` ve `Content extraction`.

## Golden kabul seti

Nihai koşuda şu dokuz beklenen bilgi bulundu:

- self-hosted çalışma
- SearXNG bağımlılığı
- native Python çalıştırma
- in-memory rate-limit sınırlaması
- kimlik doğrulama sınırlaması/gereksinimi
- güvenilmeyen yönlendirme ve içerik güvenliği
- Tor modunun performans maliyeti
- testlerin SearXNG'i mock etmesi ve Docker gerektirmemesi
- CAPTCHA'yı aşmak yerine challenge olarak raporlama politikası

## Doğrulama

- `pytest`: 31 geçti, 0 başarısız
- Ruff: tüm kontroller geçti
- API sağlık kontrolü: PostgreSQL, Redis, Ollama, AgentSearch, Crawl4AI ve MinIO `ok`
- Crawl4AI salt-okunur container geçici dizin sahipliği düzeltildi.
- Crawl4AI secret varsayılanı minimum 32 karakter şartına getirildi.
- AgentSearch/SearXNG yeniden ayağa kaldırıldı ve `/health` başarılı.

## Sınırlamalar ve sonraki kalite adımları

Nihai durum `completed_incomplete` oldu; bu kalite hatasından değil, tek GitHub kaynağıyla çalışıldığı için iki bağımsız kaynak şartının ve kaynak ailesi coverage hedefinin karşılanmamasından kaynaklanıyor. Golden test recall ölçer; bütün claim'lerin aynı ölçüde önemli veya özlü olduğunu kanıtlamaz. 81 raporlanabilir claim tek README için hâlâ fazladır.

Bir sonraki yüksek değerli adımlar:

1. Claim kümeleme ve atomic-claim birleştirme ile tekrarları azaltmak.
2. Claim önem sınıflandırmasını soru bazlı kalibre edip rapora bölüm başına üst sınır koymak.
3. Bağımsız ikinci kaynaklarla contradiction ve source-independence ölçümünü gerçekten sınamak.
4. PDF'lerde başlık/tablo/şekil ve sayfa koordinatlarını koruyan parser eklemek.
5. Retrieval değerlendirmesini tek repo yerine akademik, mevzuat ve şirket dokümanlarından oluşan çok belgeli golden sete genişletmek.

## Çıktılar

- Nihai paket: `data/benchmark-quality-final-01KXJACJTMVH018MNP4E18ZT71.zip`
- Önceki kabul paketi: `data/benchmark-quality-accepted-01KXJA0QK68FM13Y5S01KBHEJ1.zip`
- İlk karşılaştırma paketi: `data/benchmark-final-01KXGHE5MMV22X2CTQPQVZY7VB.zip`
