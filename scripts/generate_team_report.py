import base64
import os

def get_base64_image(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")

def get_svg_content(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

img_acquire = get_base64_image(r"c:\Users\kirte\research-platform\docs\assets\panel-acquire-breakdown.png")
img_quality = get_base64_image(r"c:\Users\kirte\research-platform\docs\assets\panel-quality-coverage.png")
svg_arch = get_svg_content(r"c:\Users\kirte\research-platform\docs\diagrams\system-architecture.svg")
svg_pipe = get_svg_content(r"c:\Users\kirte\research-platform\docs\diagrams\pipeline-flow.svg")

html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Research Platform — Mimari ve Geliştirme Raporu</title>
<style>
  :root {{
    --bg-main: #0e131f;
    --bg-card: #161e2e;
    --bg-card-hover: #1c2638;
    --bg-accent: #232f46;
    --border-color: rgba(255, 255, 255, 0.08);
    --border-highlight: rgba(99, 102, 241, 0.4);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-blue: #38bdf8;
    --accent-indigo: #818cf8;
    --accent-emerald: #34d399;
    --accent-amber: #fbbf24;
    --accent-rose: #f43f5e;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background-color: var(--bg-main);
    color: var(--text-primary);
    font-family: var(--font-sans);
    line-height: 1.6;
    padding: 2.5rem 1rem;
  }}
  .container {{
    max-width: 1200px;
    margin: 0 auto;
  }}
  .header {{
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 2.5rem;
    margin-bottom: 2rem;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
  }}
  .header-badge {{
    display: inline-block;
    background: rgba(99, 102, 241, 0.2);
    color: var(--accent-indigo);
    padding: 0.35rem 0.85rem;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    margin-bottom: 1rem;
    border: 1px solid rgba(99, 102, 241, 0.4);
  }}
  h1 {{
    font-size: 2.2rem;
    font-weight: 800;
    color: #fff;
    margin-bottom: 0.75rem;
    letter-spacing: -0.02em;
  }}
  .subtitle {{
    color: var(--text-secondary);
    font-size: 1.1rem;
    max-width: 850px;
  }}
  .meta-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border-color);
    color: var(--text-muted);
    font-size: 0.9rem;
  }}
  .meta-item strong {{ color: var(--text-secondary); }}
  
  .section {{
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 2.25rem;
    margin-bottom: 2rem;
  }}
  h2 {{
    font-size: 1.5rem;
    font-weight: 700;
    color: #fff;
    margin-bottom: 1.25rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }}
  h2 .num {{
    background: var(--accent-indigo);
    color: #fff;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.95rem;
    font-weight: 700;
  }}
  p {{ color: var(--text-secondary); margin-bottom: 1rem; }}
  
  .grid-2 {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 1.5rem;
    margin: 1.5rem 0;
  }}
  .grid-4 {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
  }}
  
  .card {{
    background: var(--bg-accent);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.25rem;
  }}
  .card-title {{
    font-size: 1rem;
    font-weight: 600;
    color: #fff;
    margin-bottom: 0.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .card-badge {{
    font-size: 0.75rem;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-weight: 600;
  }}
  .badge-emerald {{ background: rgba(52, 211, 153, 0.15); color: var(--accent-emerald); border: 1px solid rgba(52, 211, 153, 0.3); }}
  .badge-blue {{ background: rgba(56, 189, 248, 0.15); color: var(--accent-blue); border: 1px solid rgba(56, 189, 248, 0.3); }}
  .badge-amber {{ background: rgba(251, 191, 36, 0.15); color: var(--accent-amber); border: 1px solid rgba(251, 191, 36, 0.3); }}
  
  .img-container {{
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--border-color);
    margin: 1.5rem 0;
    background: #000;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }}
  .img-container img {{
    width: 100%;
    height: auto;
    display: block;
  }}
  .img-caption {{
    background: rgba(14, 19, 31, 0.95);
    color: var(--text-muted);
    font-size: 0.85rem;
    padding: 0.75rem 1rem;
    border-top: 1px solid var(--border-color);
  }}
  
  .diagram-box {{
    background: #2d3142;
    border-radius: 12px;
    padding: 1.5rem;
    border: 1px solid var(--border-color);
    margin: 1.5rem 0;
    overflow-x: auto;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  }}
  .diagram-box svg {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1.5rem 0;
    font-size: 0.95rem;
  }}
  th, td {{
    padding: 0.85rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
  }}
  th {{
    background: rgba(255, 255, 255, 0.03);
    color: var(--text-primary);
    font-weight: 600;
  }}
  td {{ color: var(--text-secondary); }}
  tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

  code {{
    font-family: var(--font-mono);
    background: rgba(0, 0, 0, 0.35);
    padding: 0.2rem 0.45rem;
    border-radius: 4px;
    font-size: 0.85em;
    color: var(--accent-blue);
    border: 1px solid rgba(255,255,255,0.05);
  }}
  pre {{
    background: #090d16;
    padding: 1.25rem;
    border-radius: 10px;
    border: 1px solid var(--border-color);
    overflow-x: auto;
    font-family: var(--font-mono);
    font-size: 0.9rem;
    color: var(--accent-indigo);
    margin: 1rem 0;
    line-height: 1.5;
  }}
  
  .callout {{
    border-left: 4px solid var(--accent-indigo);
    background: rgba(99, 102, 241, 0.08);
    padding: 1.25rem;
    border-radius: 0 10px 10px 0;
    margin: 1.5rem 0;
  }}
  .callout-title {{
    font-weight: 700;
    color: #fff;
    margin-bottom: 0.35rem;
  }}

  @media print {{
    body {{ background: #fff; color: #000; padding: 0; }}
    .section, .header {{ border: 1px solid #ddd; background: #fff; color: #000; box-shadow: none; }}
    .card, .diagram-box {{ background: #f8fafc; color: #000; border: 1px solid #ddd; }}
    h1, h2, h3, .card-title, .callout-title {{ color: #000; }}
    p, td {{ color: #333; }}
  }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <div class="header-badge">SÜRÜM V0.10.0 • MİMARİ VE GELİŞTİRME RAPORU</div>
    <h1>Research Platform Bilgilendirme Raporu</h1>
    <div class="subtitle">
      Granüler ayrıştırıcı telemetrisi, yenilenen sistem ve pipeline akış şemaları, zorunlu plan onay kapısı (HITL) ve kalite/coverage metrik rehberi.
    </div>
    <div class="meta-bar">
      <div class="meta-item"><strong>Tarih:</strong> 19 Ağustos 2026</div>
      <div class="meta-item"><strong>Branch:</strong> <code>developments</code> (Commit <code>496a6ac</code>)</div>
      <div class="meta-item"><strong>Test Kapsamı:</strong> 269 test (%100 Başarı)</div>
    </div>
  </div>

  <!-- BÖLÜM 1 -->
  <div class="section">
    <h2><span class="num">1</span> Granüler Ayrıştırıcı & Araç Telemetrisi</h2>
    <p>
      Sistemde önceden kullanılan jenerik <code>pdf</code> ve <code>html</code> etiketleri yerine, fiilen çalışan özgün motor kimlikleri tanımlandı. Artık web kontrol panelinde ve denetim kayıtlarında hangi PDF ve HTML motorunun çalıştığı canlı olarak izlenebilir.
    </p>

    <div class="grid-4">
      <div class="card">
        <div class="card-title">pymupdf_fast <span class="card-badge badge-emerald">Öncelik: 10</span></div>
        <p>PyMuPDF (fitz) motoru. Akademik iki sütunlu makaleleri doğru insan okuma sırasıyla süper hızlı ayrıştırır.</p>
      </div>
      <div class="card">
        <div class="card-title">pypdf <span class="card-badge badge-blue">Öncelik: 0</span></div>
        <p>Saf Python tabanlı yedek PDF motoru. PyMuPDF'in hasarlı bulduğu dosyalarda otomatik fallback olarak çalışır.</p>
      </div>
      <div class="card">
        <div class="card-title">html_structured <span class="card-badge badge-emerald">Öncelik: 10</span></div>
        <p>Tabloları Markdown ızgarasına dönüştüren, kod bloklarını ve başlık hiyerarşisini koruyan HTML parser'ı.</p>
      </div>
      <div class="card">
        <div class="card-title">plain_text <span class="card-badge badge-amber">Öncelik: 0</span></div>
        <p>Düz metin, JSON ve XML anahtar-değer ağacı ayrıştırıcısı.</p>
      </div>
    </div>

    <div class="img-container">
      <img src="{img_acquire}" alt="Kontrol Paneli ACQUIRE Aşaması Telemetrisi">
      <div class="img-caption">Şekil 1.1: Web Kontrol Paneli ACQUIRE Aşamasında Edinim Yöntemleri ve Ayrıştırıcı Motorlarının Dağılımı</div>
    </div>

    <div class="callout">
      <div class="callout-title">Üç Katmanlı Köken (Provenance) Güvencesi</div>
      Ayrıştırıcı kimliği (<code>parser_id</code>); <strong>PostgreSQL</strong> (<code>source_versions.provenance</code>), <strong>MinIO</strong> ({'{run_id}'}/sources/{'{hash}'}.pdf) ve yerel çıktı paketindeki <strong><code>13_raw_sources.jsonl</code></strong> dosyasına kalıcı olarak yazılır.
    </div>
  </div>

  <!-- BÖLÜM 2 -->
  <div class="section">
    <h2><span class="num">2</span> Yenilenen Sistem & Veri Akış Şemaları</h2>
    <p>
      <code>docs/diagrams/</code> klasöründeki güncel mimari diyagramları, çok kullanıcılı güvenlik modelini, Long Poll Telegram botunu ve LangGraph tabanlı boru hattını modeller.
    </p>

    <h3 style="color: #fff; margin: 1.5rem 0 0.5rem;">2.1. Sistem Mimarisi Şeması</h3>
    <div class="diagram-box">
      {svg_arch}
    </div>
    <p style="font-size: 0.9rem; color: var(--text-muted); text-align: center;">
      Şekil 2.1: Entry Gateways, Core API/Worker ve Data/Collection Servisleri Mimarisi
    </p>

    <h3 style="color: #fff; margin: 2rem 0 0.5rem;">2.2. Boru Hattı (Pipeline) Akış Şeması</h3>
    <div class="diagram-box">
      {svg_pipe}
    </div>
    <p style="font-size: 0.9rem; color: var(--text-muted); text-align: center;">
      Şekil 2.2: LangGraph Aşamaları, Citation Frontier Atıf Ağacı ve Sentez Boru Hattı
    </p>
  </div>

  <!-- BÖLÜM 3 -->
  <div class="section">
    <h2><span class="num">3</span> Zorunlu Planlama Modu (HITL Plan Review) ve Süre</h2>
    <p>
      Araştırma motoru, gereksiz API tüketimini ve yanlış odaklı aramaları engellemek için arama başlamadan önce <strong>Plan Onay Kapısı</strong> sunar.
    </p>

    <div class="grid-2">
      <div class="card">
        <div class="card-title">1. Soru Ayrıştırma (Semantic Decomposition)</div>
        <p>Dil modeli (LLM), girilen ana soruyu 3 ila 8 arasında bağımsız alt araştırma boyutuna böler. Her alt soru bağımsız bir arama dalı (query branch) haline gelir.</p>
      </div>
      <div class="card">
        <div class="card-title">2. İnsan Onayı ve Müdahale (HITL)</div>
        <p>Kullanıcı Telegram veya Web Panelden planı inceleyip onaylayabilir (<code>approve</code>) ya da gerekçeli değişiklik isteyebilir (<code>reject &lt;gerekçe&gt;</code>). Reddedilirse sistem gerekçeyi dikkate alarak planı yeniden kurar.</p>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Parametre / Sınır</th>
          <th>Tür</th>
          <th>Açıklama</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><code>max_wall_minutes</code> (Süre)</td>
          <td><span class="card-badge badge-emerald">Bağlayıcı</span></td>
          <td>Araştırmanın zorunlu üst tavanıdır. Süre bittiğinde arama durur, rapor yazılır.</td>
        </tr>
        <tr>
          <td><code>max_sources</code> (Kaynak)</td>
          <td><span class="card-badge badge-amber">Bağlayıcı Değil</span></td>
          <td>Süre ve kapsam yeterli olduğu sürece kaynak sayısı kısıtlanmaz.</td>
        </tr>
        <tr>
          <td><code>max_rounds</code> (Tur: 3)</td>
          <td><span class="card-badge badge-amber">Bağlayıcı Değil</span></td>
          <td>Literatür tarama modunda süre bitene kadar atıf ağaçları taranmaya devam eder.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- BÖLÜM 4 -->
  <div class="section">
    <h2><span class="num">4</span> Kalite ve Kapsam (Quality & Coverage) Metrik Rehberi</h2>
    <p>
      Kontrol panelinde araştırmanın doygunluğunu ve güvenilirliğini gösteren 8 temel metrik bulunur:
    </p>

    <div class="img-container">
      <img src="{img_quality}" alt="Kontrol Paneli Kalite ve Coverage Kartları">
      <div class="img-caption">Şekil 4.1: Web Kontrol Paneli Kalite ve Kapsam Gösterge Kartları</div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Metrik</th>
          <th>Anlamı ve Çalışma Mantığı</th>
          <th>Hedef Değer</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Kaynak Ailesi</strong></td>
          <td>Akademik, regülasyon ve web kaynakları arasındaki hedef dağılım dengesi.</td>
          <td><code>%100</code></td>
        </tr>
        <tr>
          <td><strong>Sorgu Dalları</strong></td>
          <td>Oluşturulan alt soruların kaç tanesine geçerli kanıt bulunduğunu ölçer.</td>
          <td><code>%100</code></td>
        </tr>
        <tr>
          <td><strong>Claim Audit</strong></td>
          <td>Rapordaki ana iddiaların kaynak pasajlarıyla doğrulanma oranı.</td>
          <td><code>%100</code></td>
        </tr>
        <tr>
          <td><strong>Sentinel Recall</strong></td>
          <td>Önceden tanımlanmış kritik mihenk taşı makalelerin bulunma oranı.</td>
          <td><code>%100</code></td>
        </tr>
        <tr>
          <td><strong>Tahmini Tamlık</strong></td>
          <td><strong>Chao2 / Capture-Recapture</strong> ekolojik tür istatistiğiyle literatürün ne kadarına ulaşıldığının tahmini.</td>
          <td><code>%70+</code></td>
        </tr>
        <tr>
          <td><strong>Relative Recall</strong></td>
          <td>Ajanın doğrudan 'Accept' havuzuna aldığı kaynakların kalite doğruluğu.</td>
          <td><code>%90+</code></td>
        </tr>
        <tr>
          <td><strong>Citation Novelty</strong></td>
          <td>Kaynakların anahtar kelime yerine atıf ağaçlarından (citation frontier) gelme oranı.</td>
          <td>Tur 2+: <code>%30+</code></td>
        </tr>
        <tr>
          <td><strong>Reserve FN</strong></td>
          <td>Yanlış elenme oranı. Filtrenin gereksiz katı olmadığını gösterir.</td>
          <td><code>&lt; %20</code></td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- BÖLÜM 5 -->
  <div class="section">
    <h2><span class="num">5</span> Hızlı Başlangıç Komutları</h2>
    <pre># Telegram'dan 30 dakikalık planlı araştırma başlatma:
/research 30 AI in lung CT imaging diagnostic accuracy and clinical workflow

# Gelen planı onaylama:
/respond &lt;run_id&gt; approve

# Gerekçe belirterek revizyon isteme:
/respond &lt;run_id&gt; reject radyolog iş yükü ve maliyet tasarrufuna da odaklan

# Plan kapısını atlayarak doğrudan arama başlatma:
/research 20 --plansiz Soru metni...</pre>
  </div>

</div>
</body>
</html>
"""

os.makedirs(r"c:\Users\kirte\research-platform\docs\reports", exist_ok=True)
output_path = r"c:\Users\kirte\research-platform\docs\reports\GELISTIRME_VE_MIMARI_BILGILENDIRME_RAPORU.html"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print("Generated HTML report at:", output_path)
