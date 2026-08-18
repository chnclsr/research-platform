from __future__ import annotations


CONTROL_PANEL_HTML = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="control-token" content="__CONTROL_TOKEN__">
  <title>Research Platform · Operasyon Merkezi</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#090d12;--surface:#10161f;--surface2:#151e29;--surface3:#1b2633;
      --line:#273442;--text:#edf3f8;--muted:#8d9dad;--green:#43d49b;
      --amber:#f1bd59;--red:#ff707d;--blue:#68a8ff;--violet:#aa91ff;--cyan:#55c9de;
    }
    *{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}
    button,input,select{font:inherit} button{color:inherit} a{color:var(--blue)}
    .shell{max-width:1600px;margin:auto;padding:24px 28px 40px}
    header{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;margin-bottom:18px}
    .eyebrow{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}
    h1{font-size:clamp(25px,4vw,38px);line-height:1.08;letter-spacing:-.04em;margin:5px 0 5px}.sub{margin:0;color:var(--muted)}
    .actions,.inline-actions,.tabs,.chips{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
    .btn{border:1px solid var(--line);border-radius:9px;background:var(--surface2);padding:8px 12px;cursor:pointer;transition:.15s ease}
    .btn:hover{border-color:#506379;transform:translateY(-1px)}.btn:disabled{opacity:.45;cursor:wait;transform:none}
    .btn.primary{background:var(--green);border-color:var(--green);color:#06140e;font-weight:800}.btn.danger{border-color:#67343d;background:#2a171d;color:#ff9ba5}.btn.small{font-size:12px;padding:5px 8px}
    .tabs{border-bottom:1px solid var(--line);margin-bottom:18px}.tab{border:0;border-bottom:2px solid transparent;background:transparent;color:var(--muted);padding:11px 14px;cursor:pointer}.tab.active{color:var(--text);border-color:var(--blue)}
    .summary{display:grid;grid-template-columns:1.2fr repeat(4,minmax(140px,.75fr));gap:11px;margin-bottom:18px}
    .card,.panel{border:1px solid var(--line);background:var(--surface);border-radius:13px}.card{min-height:108px;padding:16px;display:flex;flex-direction:column;justify-content:space-between}
    .label{color:var(--muted);font-size:11px;font-weight:750;letter-spacing:.06em;text-transform:uppercase}.value{font-size:24px;font-weight:780;letter-spacing:-.03em}.note{color:var(--muted);font-size:12px}
    .signal{display:inline-flex;align-items:center;gap:8px}.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);box-shadow:0 0 0 4px #ffffff0a}.dot.running,.dot.ok,.dot.healthy{background:var(--green)}.dot.degraded,.dot.queued,.dot.paused{background:var(--amber)}.dot.stopped,.dot.unavailable,.dot.failed{background:var(--red)}
    .service-strip{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 18px}.service{display:flex;align-items:center;gap:7px;border:1px solid var(--line);background:#0d131b;padding:7px 10px;border-radius:99px;color:var(--muted);font-size:12px}.service strong{color:var(--text)}
    .view{display:none}.view.active{display:block}.grid-2{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(390px,.65fr);gap:16px}.panel{overflow:hidden;margin-bottom:16px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:55px;padding:12px 16px;border-bottom:1px solid var(--line)}
    h2,h3{margin:0;letter-spacing:-.01em}h2{font-size:15px}h3{font-size:13px}.count{color:var(--muted);font-size:12px}
    .table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:780px}th{padding:9px 12px;text-align:left;background:#0d131b;color:var(--muted);font-size:10px;letter-spacing:.06em;text-transform:uppercase}td{padding:11px 12px;border-top:1px solid #202c38;vertical-align:middle}tbody tr{transition:.12s}tbody tr.clickable{cursor:pointer}tbody tr:hover{background:#ffffff04}
    .run-title{max-width:430px}.run-title strong{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mono{font:11px ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted)}
    .badge{display:inline-flex;align-items:center;border-radius:99px;padding:4px 8px;background:#263342;color:#cbd5df;font-size:11px;font-weight:750}.badge.running,.badge.completed{background:#15352a;color:#75e4b7}.badge.queued,.badge.paused,.badge.awaiting_input{background:#372c17;color:#ffd27c}.badge.failed,.badge.cancelled,.badge.cancel_requested{background:#3c1f26;color:#ff9aa4}.badge.completed_incomplete{background:#30294b;color:#cabdff}.badge.reserve{background:#3a2e19;color:#ffd27c}.badge.reject{background:#3c1f26;color:#ff9aa4}.badge.accept{background:#15352a;color:#75e4b7}
    .pad{padding:16px}.codebox{margin-top:14px;padding:14px;border:1px solid var(--line);border-radius:11px;background:#0d131b}.codebox .code{font:22px/1.2 ui-monospace,SFMono-Regular,Consolas,monospace;letter-spacing:.16em;color:var(--green);font-weight:700}.codebox .secret{font:12px ui-monospace,Consolas,monospace;word-break:break-all;color:var(--amber)}.row-actions{display:flex;justify-content:flex-end;gap:5px}.empty{padding:34px 16px;text-align:center;color:var(--muted)}
    .metric-bar{height:7px;border-radius:99px;background:#202b36;overflow:hidden}.metric-bar span{display:block;height:100%;border-radius:inherit;background:var(--blue);transition:.3s width}.metric-bar.good span{background:var(--green)}.metric-bar.warn span{background:var(--amber)}.metric-bar.bad span{background:var(--red)}
    .resource-grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px;padding:16px}.resource{border:1px solid var(--line);border-radius:11px;background:var(--surface2);padding:14px}.resource .metric-bar{margin-top:12px}.resource-value{font-size:20px;font-weight:760;margin:8px 0 2px}
    .connector-status{display:flex;align-items:center;gap:7px}.connector-detail{max-width:360px;color:var(--muted);font-size:12px}.rate{font-weight:760}.rate.good{color:var(--green)}.rate.warn{color:var(--amber)}.rate.bad{color:var(--red)}
    pre{margin:0;min-height:520px;max-height:680px;overflow:auto;padding:16px;background:#070a0e;color:#cbd7e3;font:11.5px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap}.log-tools{padding:12px 16px;border-bottom:1px solid var(--line)}
    .footer{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;padding-top:5px}
    .drawer-backdrop{position:fixed;inset:0;background:#000b;z-index:30;opacity:0;pointer-events:none;transition:.18s}.drawer-backdrop.open{opacity:1;pointer-events:auto}.drawer{position:absolute;top:0;right:0;width:min(1180px,94vw);height:100%;overflow:auto;background:var(--bg);border-left:1px solid var(--line);transform:translateX(30px);transition:.18s}.drawer-backdrop.open .drawer{transform:none}
    .drawer-head{position:sticky;top:0;z-index:3;display:flex;justify-content:space-between;gap:16px;padding:18px 22px;background:#0b1017ee;backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}.drawer-title{min-width:0}.drawer-title h2{font-size:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.drawer-body{padding:20px 22px 50px}.drawer-section{margin-bottom:17px}.section-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px}
    .quality-grid{display:grid;grid-template-columns:repeat(4,minmax(145px,1fr));gap:9px}.quality-card{border:1px solid var(--line);background:var(--surface);border-radius:11px;padding:12px}.quality-card .q-value{font-size:21px;font-weight:780;margin:6px 0}.quality-card .metric-bar{margin-top:7px}
    .reason-list{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.reason{font-size:11px;border:1px solid #5b3340;background:#2a1820;color:#ffabb5;border-radius:99px;padding:4px 8px}
    .funnel{display:grid;gap:8px;border:1px solid var(--line);background:var(--surface);padding:14px;border-radius:11px}.funnel-row{display:grid;grid-template-columns:185px 1fr 54px;gap:10px;align-items:center}.funnel-row strong{text-align:right}.admission{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.admission span{border:1px solid var(--line);background:var(--surface2);padding:7px 10px;border-radius:8px}
    .timeline{display:flex;gap:7px;overflow:auto;padding-bottom:6px}.stage{min-width:150px;border:1px solid var(--line);border-radius:10px;background:var(--surface);padding:10px}.stage.active{border-color:var(--blue);box-shadow:inset 0 0 0 1px #68a8ff55}.stage-name{font-size:11px;font-weight:800}.stage-meta{font-size:11px;color:var(--muted);margin-top:5px}
    .stage-cell{min-width:145px}.stage-cell strong{display:block;font-size:11px;margin-bottom:6px}.stage-progress{height:5px;background:#202b36;border-radius:99px;overflow:hidden}.stage-progress span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),var(--cyan));transition:width .35s ease}.stage-progress.completed span{background:var(--green)}.stage-progress.failed span,.stage-progress.cancelled span{background:var(--red)}
    .flow-card{border:1px solid var(--line);background:linear-gradient(145deg,#101720,#0c1219);border-radius:13px;padding:15px}.flow-summary{display:grid;grid-template-columns:130px 1fr auto;gap:13px;align-items:center;margin-bottom:15px}.flow-percent{font-size:28px;font-weight:800;letter-spacing:-.04em}.flow-track{height:10px;background:#202b36;border-radius:99px;overflow:hidden}.flow-track span{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),var(--cyan));box-shadow:0 0 18px #55c9de55;transition:width .4s ease}.flow-scroll{overflow-x:auto;padding:4px 2px 10px}.flow-nodes{display:flex;align-items:stretch;min-width:max-content}.flow-node{width:135px;min-height:88px;border:1px solid var(--line);background:var(--surface2);border-radius:10px;padding:10px;position:relative}.flow-node.completed{border-color:#28694f;background:#10281f}.flow-node.active{border-color:var(--blue);background:#14263d;box-shadow:0 0 0 2px #68a8ff22,0 0 22px #68a8ff22}.flow-node.active:before{content:'';position:absolute;right:8px;top:8px;width:7px;height:7px;border-radius:50%;background:var(--blue);box-shadow:0 0 0 5px #68a8ff22}.flow-node.paused{border-color:var(--amber);background:#2b2417}.flow-node.error{border-color:var(--red);background:#30191e}.flow-node.skipped{opacity:.42}.flow-node-name{font-size:12px;font-weight:800;max-width:108px}.flow-node-code{font:9px ui-monospace,monospace;color:var(--muted);margin-top:4px}.flow-node-meta{font-size:10px;color:var(--muted);margin-top:8px}.flow-arrow{width:25px;display:grid;place-items:center;color:#52677d;font-size:18px}.flow-loop{display:inline-flex;align-items:center;gap:7px;margin-top:7px;border:1px solid #574b2b;background:#241f14;color:#e4c271;border-radius:8px;padding:7px 10px;font-size:11px}
    .hitl-card{border:1px solid #765f2e;background:linear-gradient(145deg,#292314,#17140d);border-radius:13px;padding:16px}.hitl-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.hitl-title strong{color:#ffdc8a}.hitl-data{background:#0d131a;border:1px solid var(--line);border-radius:9px;padding:12px;margin:10px 0;max-height:260px;overflow:auto}.hitl-question{display:grid;gap:6px;margin:10px 0}.hitl-question label,.domain-choice{font-size:12px;color:#cbd5df}.hitl-card input,.hitl-card textarea{width:100%;box-sizing:border-box;background:#0b1118;border:1px solid #354556;color:var(--text);border-radius:8px;padding:10px;font:inherit}.hitl-card textarea{min-height:85px;resize:vertical}.hitl-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.domain-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.domain-choice{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:8px;background:#121a23;border:1px solid var(--line);border-radius:8px;padding:9px}.domain-choice input{width:auto}
    .event-list{display:grid;gap:6px;max-height:440px;overflow:auto}.event{border:1px solid var(--line);border-radius:9px;background:var(--surface);padding:9px 11px}.event summary{cursor:pointer;display:flex;justify-content:space-between;gap:10px}.event code{display:block;margin-top:8px;white-space:pre-wrap;color:#b9c9d8;font-size:11px;word-break:break-word}.artifact-grid{display:grid;grid-template-columns:repeat(3,minmax(180px,1fr));gap:8px}.artifact{display:flex;justify-content:space-between;align-items:center;gap:8px;border:1px solid var(--line);background:var(--surface);padding:10px;border-radius:9px}.source-link{display:block;max-width:420px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .toast{position:fixed;right:22px;bottom:22px;z-index:60;max-width:440px;border:1px solid var(--line);border-radius:11px;background:#202c39;padding:12px 15px;box-shadow:0 15px 50px #0009;opacity:0;transform:translateY(12px);pointer-events:none;transition:.18s}.toast.show{opacity:1;transform:none}.toast.error{border-color:#723642;color:#ffabb4}
    @media(max-width:1100px){.summary{grid-template-columns:repeat(3,1fr)}.grid-2{grid-template-columns:1fr}.resource-grid,.quality-grid{grid-template-columns:repeat(2,1fr)}}
    @media(max-width:680px){.shell{padding:17px 12px 32px}header{flex-direction:column}.summary{grid-template-columns:1fr 1fr}.resource-grid,.quality-grid,.artifact-grid{grid-template-columns:1fr}.drawer{width:100vw}.drawer-body,.drawer-head{padding-left:14px;padding-right:14px}.funnel-row{grid-template-columns:130px 1fr 44px}.flow-summary{grid-template-columns:90px 1fr}.flow-summary .badge{grid-column:1/-1;width:max-content}.actions{justify-content:flex-start}.footer{display:block}}
  </style>
</head>
<body>
<main class="shell">
  <header>
    <div><div class="eyebrow">Local research operations</div><h1>Araştırma Operasyon Merkezi</h1><p class="sub">Servis sağlığı, kaynak recall’ı ve araştırma kararları tek görünümde.</p></div>
    <div class="actions">
      <span id="session-badge" class="service" title="Oturum"><strong id="session-name">…</strong><span id="session-role" class="note"></span></span>
      <button class="btn primary system-action admin-only" data-action="start" hidden>Başlat</button>
      <button class="btn system-action admin-only" data-action="restart" hidden>Yeniden başlat</button>
      <button class="btn danger system-action admin-only" data-action="stop" hidden>Servisleri durdur</button>
      <button id="logout" class="btn">Çıkış</button>
    </div>
  </header>
  <div class="summary">
    <div class="card"><span class="label">Sistem</span><span class="value signal"><i id="overall-dot" class="dot"></i><span id="overall">Yükleniyor</span></span><span id="overall-note" class="note">Durum alınıyor…</span></div>
    <div class="card"><span class="label">Aktif işler</span><span id="active-count" class="value">—</span><span class="note">Çalışan ve bekleyen</span></div>
    <div class="card"><span class="label">Kuyruk</span><span id="queue-count" class="value">—</span><span id="queue-note" class="note">Redis kontrol ediliyor</span></div>
    <div class="card"><span class="label">RTX 4060 VRAM</span><span id="gpu-memory" class="value">—</span><span id="gpu-note" class="note">GPU kontrol ediliyor</span></div>
    <div class="card"><span class="label">Yerel model</span><span id="model" class="value" style="font-size:16px">—</span><span id="model-note" class="note">Ollama kontrol ediliyor</span></div>
  </div>
  <div id="services" class="service-strip"></div>
  <nav class="tabs" aria-label="Panel bölümleri"><button class="tab active" data-view="overview">Araştırmalar</button><button class="tab" data-view="connectors">Connector’lar</button><button class="tab" data-view="system">Donanım</button><button class="tab admin-only" data-view="logs" hidden>Loglar</button><button class="tab" data-view="account">Hesabım</button></nav>

  <div id="view-overview" class="view active">
    <section class="panel"><div class="panel-head"><h2>Aktif ve sıradaki istekler</h2><span id="active-label" class="count">0 iş</span></div><div class="table-wrap"><table><thead><tr><th>Araştırma</th><th>Durum</th><th>Aşama</th><th>Sıra</th><th>Tur</th><th>Kaynak / İddia</th><th>Coverage</th><th>Süre</th><th></th></tr></thead><tbody id="active-runs"></tbody></table><div id="active-empty" class="empty">Aktif iş yok.</div></div></section>
    <section class="panel"><div class="panel-head"><h2>Son araştırmalar</h2><span class="count">Satıra tıklayarak ayrıntıları aç</span></div><div class="table-wrap"><table><thead><tr><th>Araştırma</th><th>Durum</th><th>Son aşama</th><th>Kaynak / İddia</th><th>Coverage</th><th>Süre</th><th>Güncelleme</th></tr></thead><tbody id="recent-runs"></tbody></table><div id="recent-empty" class="empty">Geçmiş kayıt yok.</div></div></section>
  </div>

  <div id="view-connectors" class="view"><section class="panel"><div class="panel-head"><div><h2>Connector operasyon görünümü</h2><span class="count">Health, canlı başarı oranı, gecikme ve özgün kaynak katkısı</span></div><button id="refresh-connectors" class="btn small">Yenile</button></div><div class="table-wrap"><table style="min-width:1150px"><thead><tr><th>Connector</th><th>Sağlık</th><th>Credential</th><th>Çağrı / Başarı</th><th>Sonuç</th><th>Kabul edilen</th><th>Ort. / p95</th><th>Hatalar</th><th>Son başarı</th><th></th></tr></thead><tbody id="connector-rows"></tbody></table><div id="connector-empty" class="empty">Connector bilgisi yükleniyor…</div></div></section></div>

  <div id="view-system" class="view"><section class="panel"><div class="panel-head"><h2>Donanım ve model telemetrisi</h2><span class="count">Dört saniyede bir güncellenir</span></div><div id="resources" class="resource-grid"></div></section><section class="panel"><div class="panel-head"><h2>GPU ayrıntıları</h2><span class="count">NVIDIA SMI</span></div><div class="table-wrap"><table><thead><tr><th>GPU</th><th>Kullanım</th><th>VRAM</th><th>Sıcaklık</th><th>Güç</th></tr></thead><tbody id="gpu-rows"></tbody></table><div id="gpu-empty" class="empty">NVIDIA GPU verisi bulunamadı.</div></div></section></div>

  <div id="view-logs" class="view"><section class="panel"><div class="panel-head"><h2>Servis logları</h2><span class="count">Son 24 KB · token ve credential değerleri gösterilmez</span></div><div class="log-tools"><div id="log-tabs" class="chips"></div></div><pre id="logs">Bir servis seç.</pre></section></div>
  <div id="view-account" class="view"><div class="grid-2">
    <section class="panel"><div class="panel-head"><h2>Telegram bağlantısı</h2><span class="count">Bottan başlattığınız araştırmalar hesabınıza ait olur</span></div>
      <div class="pad"><div id="tg-state" class="note">Yükleniyor…</div>
        <div class="inline-actions" style="margin-top:12px"><button id="tg-link" class="btn primary">Bağlantı kodu al</button><button id="tg-unlink" class="btn danger" hidden>Bağlantıyı kaldır</button></div>
        <div id="tg-code" hidden></div>
      </div></section>
    <section class="panel"><div class="panel-head"><h2>API anahtarları</h2><span class="count">Betik, Langflow ve MCP erişimi</span></div>
      <div class="pad"><div class="inline-actions"><input id="key-name" placeholder="Anahtar adı (örn. langflow)" style="flex:1;min-width:150px;padding:8px 10px;border:1px solid var(--line);border-radius:9px;background:var(--surface2);color:var(--text)"><button id="key-create" class="btn primary">Üret</button></div>
        <div id="key-new" hidden></div><div id="key-list" style="margin-top:14px"></div>
      </div></section>
  </div></div>
  <div class="footer"><span>Yalnız izinli ofis ağından erişilebilir · v0.7.0</span><span id="last-update">—</span></div>
</main>

<div id="drawer-backdrop" class="drawer-backdrop" aria-hidden="true"><aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><div class="drawer-head"><div class="drawer-title"><div class="eyebrow">Araştırma ayrıntısı</div><h2 id="drawer-title">Yükleniyor…</h2><div id="drawer-meta" class="note"></div></div><div class="inline-actions"><button id="drawer-refresh" class="btn small">Yenile</button><button id="drawer-close" class="btn">Kapat</button></div></div><div id="drawer-body" class="drawer-body"><div class="empty">Araştırma verileri yükleniyor…</div></div></aside></div>
<div id="toast" class="toast" role="status"></div>

<script>
const token=document.querySelector('meta[name="control-token"]').content;
const headers={'X-Control-Token':token};
const el=id=>document.getElementById(id);
const labels={running:'Çalışıyor',stopped:'Kapalı',degraded:'Kısmi',queued:'Sırada',awaiting_input:'Girdi bekliyor',paused:'Duraklatıldı',cancel_requested:'İptal bekliyor',cancelled:'İptal',completed:'Tamamlandı',completed_incomplete:'Eksik tamamlandı',failed:'Hata'};
const serviceLabels={api:'API',worker:'Worker',mcp:'MCP',telegram:'Telegram'};
let refreshing=false,currentRunId=null,lastStatus=null;
const h=(tag,className='',text='')=>{const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined&&text!==null)node.textContent=text;return node};
const fmt=iso=>iso?new Intl.DateTimeFormat('tr-TR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(iso)):'—';
const duration=s=>{s=Number(s||0);if(s<60)return`${Math.round(s)} sn`;if(s<3600)return`${Math.floor(s/60)} dk ${Math.round(s%60)} sn`;return`${Math.floor(s/3600)} sa ${Math.round((s%3600)/60)} dk`};
const bytes=n=>{n=Number(n||0);return n>1048576?`${(n/1048576).toFixed(1)} MB`:n>1024?`${(n/1024).toFixed(1)} KB`:`${n} B`};
const pct=v=>`${Math.round(Number(v||0)*100)}%`;
function toast(message,error=false){const t=el('toast');t.textContent=message;t.className=`toast show${error?' error':''}`;clearTimeout(t.timer);t.timer=setTimeout(()=>t.className='toast',4200)}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{...headers,...(options.headers||{})}});
// An expired or revoked session must land on the sign-in page rather than leaving the
// panel polling forever against 401s.
if(response.status===401){location.href='/login';throw new Error('Oturum sona erdi.')}
const type=response.headers.get('content-type')||'';const data=type.includes('json')?await response.json():await response.text();if(!response.ok)throw new Error(data.detail||data||`HTTP ${response.status}`);return data}
// Log tabs and the system buttons are administrator-only server-side; hiding them for
// everyone else keeps the UI honest instead of offering controls that return 403.
async function loadSession(){try{const s=await api('/api/session');el('session-name').textContent=s.display_name||s.email||'—';el('session-role').textContent=s.is_admin?'yönetici':'kullanıcı';if(s.is_admin){document.querySelectorAll('.admin-only').forEach(b=>b.hidden=false);el('log-panel')?.removeAttribute('hidden')}else{el('log-panel')?.setAttribute('hidden','')}return s}catch(e){return null}}
async function logout(){const form=document.createElement('form');form.method='post';form.action='/logout';document.body.append(form);form.submit()}
function badge(status){return h('span',`badge ${status}`,labels[status]||status||'—')}
function textCell(value,className=''){return h('td',className,value??'—')}
function runTitle(run){const td=h('td','run-title');td.append(h('strong','',run.question||run.title),h('span','mono',run.id));return td}
function coverageText(run){const c=run.coverage||{};if(c.sufficient)return'Yeterli';const reasons=c.reasons||[];return reasons.length?`${reasons.length} eksik`:'—'}
function stageCell(run){const td=h('td','stage-cell');td.append(h('strong','',run.current_stage||'INIT'));const bar=h('div',`stage-progress ${run.status||''}`),fill=h('span');fill.style.width=`${Math.max(0,Math.min(100,Number(run.progress_percent||0)))}%`;bar.append(fill);td.append(bar);return td}
function runButton(label,action,run){const b=h('button',`btn small${action==='cancel'?' danger':''}`,label);b.onclick=e=>{e.stopPropagation();runAction(run.id,action)};return b}
function renderRuns(id,emptyId,runs,active){const body=el(id);body.replaceChildren();el(emptyId).style.display=runs.length?'none':'block';for(const run of runs){const tr=h('tr','clickable');tr.tabIndex=0;tr.onclick=()=>openRun(run.id);tr.onkeydown=e=>{if(e.key==='Enter')openRun(run.id)};tr.append(runTitle(run));const st=h('td');st.append(badge(run.status));tr.append(st,stageCell(run));if(active)tr.append(textCell(run.queue_position||'—'),textCell(run.round_number));tr.append(textCell(`${run.sources_count} / ${run.claims_count}`),textCell(coverageText(run)),textCell(duration(run.elapsed_seconds)));if(active){const actions=h('td','row-actions');if(['running','queued'].includes(run.status))actions.append(runButton('Duraklat','pause',run));if(run.status==='paused')actions.append(runButton('Devam','resume',run));if(!['cancel_requested','cancelled'].includes(run.status))actions.append(runButton('İptal','cancel',run));tr.append(actions)}else tr.append(textCell(fmt(run.updated_at)));body.append(tr)}}
function renderServices(processes,queue){const box=el('services');box.replaceChildren();for(const[name,p]of Object.entries(processes)){const item=h('span','service');item.append(h('i',`dot ${p.running?'running':'stopped'}`),h('strong','',serviceLabels[name]||name),document.createTextNode(p.running?` ${p.detail||`PID ${p.pid}`}`:' Kapalı'));box.append(item)}const hb=h('span','service');hb.append(h('i',`dot ${queue.available&&queue.heartbeat_ttl_seconds>0?'running':'stopped'}`),document.createTextNode(queue.heartbeat_ttl_seconds>0?`Worker heartbeat ${queue.heartbeat_ttl_seconds} sn`:'Worker heartbeat yok'));box.append(hb)}
function resource(label,value,percentValue,note){const box=h('div','resource');box.append(h('span','label',label),h('div','resource-value',value),h('span','note',note||''));const bar=h('div',`metric-bar ${percentValue<70?'good':percentValue<90?'warn':'bad'}`);const fill=h('span');fill.style.width=`${Math.max(0,Math.min(100,percentValue))}%`;bar.append(fill);box.append(bar);return box}
function renderTelemetry(data){const t=data.telemetry||{},gpus=t.gpus||[],gpu=gpus.find(g=>String(g.name).includes('4060'))||gpus[0],used=Number(gpu?.memory_used_mb||0),total=Number(gpu?.memory_total_mb||0);el('gpu-memory').textContent=gpu&&total?`${(used/1024).toFixed(1)} / ${(total/1024).toFixed(1)} GB`:'—';el('gpu-note').textContent=gpu?`${gpu.utilization_percent??'N/A'}% kullanım · ${gpu.temperature_c??'N/A'}°C`:'NVIDIA verisi yok';const resources=el('resources');resources.replaceChildren(resource('CPU',`${t.cpu_percent||0}%`,t.cpu_percent||0,'Toplam sistem kullanımı'),resource('RAM',`${t.memory?.used_gb||0} / ${t.memory?.total_gb||0} GB`,t.memory?.percent||0,'Sistem belleği'),resource('Disk',`${t.disk?.used_gb||0} / ${t.disk?.total_gb||0} GB`,t.disk?.percent||0,'Platform diski'),resource('GPU VRAM',gpu&&total?`${(used/1024).toFixed(1)} / ${(total/1024).toFixed(1)} GB`:'—',total?used/total*100:0,gpu?gpu.name:'NVIDIA GPU yok'));const rows=el('gpu-rows');rows.replaceChildren();el('gpu-empty').style.display=gpus.length?'none':'block';for(const g of gpus){const tr=h('tr'),gUsed=Number(g.memory_used_mb||0),gTotal=Number(g.memory_total_mb||0),power=g.power_draw_w==null?'N/A':Number(g.power_draw_w).toFixed(1),limit=g.power_limit_w==null?'N/A':Number(g.power_limit_w).toFixed(0);tr.append(textCell(`${g.index} · ${g.name}`),textCell(`${g.utilization_percent??'N/A'}%`),textCell(gTotal?`${(gUsed/1024).toFixed(2)} / ${(gTotal/1024).toFixed(2)} GB`:'N/A'),textCell(`${g.temperature_c??'N/A'}°C`),textCell(`${power} / ${limit} W`));rows.append(tr)}}
async function refresh(){if(refreshing)return;refreshing=true;try{const data=await api('/api/status');lastStatus=data;el('overall').textContent=labels[data.overall]||data.overall;el('overall-dot').className=`dot ${data.overall}`;el('overall-note').textContent=data.action.busy?`${data.action.action} işlemi sürüyor`:`Veritabanı: ${data.database}`;el('active-count').textContent=data.runs.active.length;el('queue-count').textContent=data.queue.waiting;el('queue-note').textContent=data.queue.available?`${data.queue.running} çalışan · ${data.queue.waiting} bekleyen`:'Redis erişilemiyor';const models=data.health.ollama?.models||[];el('model').textContent=models[0]?.name||'Yüklü model yok';el('model-note').textContent=models[0]?.size_vram?`${(models[0].size_vram/1073741824).toFixed(1)} GB VRAM`:(data.health.ollama?.status==='ok'?'Ollama erişilebilir':'Ollama kapalı');renderServices(data.processes,data.queue);renderRuns('active-runs','active-empty',data.runs.active,true);renderRuns('recent-runs','recent-empty',data.runs.recent,false);el('active-label').textContent=`${data.runs.active.length} iş`;renderTelemetry(data);el('last-update').textContent=`Son yenileme ${new Date().toLocaleTimeString('tr-TR')}`;document.querySelectorAll('.system-action').forEach(b=>b.disabled=data.action.busy)}catch(e){toast(`Durum alınamadı: ${e.message}`,true)}finally{refreshing=false}}
function rateClass(value){return value>=.8?'good':value>=.5?'warn':'bad'}
async function loadConnectors(){el('connector-empty').style.display='block';try{const rows=await api('/api/connectors');const body=el('connector-rows');body.replaceChildren();el('connector-empty').style.display=rows.length?'none':'block';for(const c of rows){const tr=h('tr');const name=h('td');name.append(h('strong','',c.id),h('div','mono',c.family));const health=h('td');const hs=h('div','connector-status');hs.append(h('i',`dot ${c.enabled&&c.healthy?'healthy':c.enabled?'degraded':'stopped'}`),h('span','',c.enabled?(c.healthy?'Sağlıklı':'Degraded'):'Disabled'));health.append(hs,h('div','connector-detail',c.detail));const cred=c.requires_credentials?(c.missing_credentials.length?`Eksik: ${c.missing_credentials.join(', ')}`:'Yapılandırılmış'):'Gerekmez';const sr=h('td');sr.append(h('span',`rate ${rateClass(c.success_rate)}`,`${c.calls?Math.round(c.success_rate*100):0}%`),h('div','note',`${c.successes}/${c.calls} çağrı`));const errors=Object.entries(c.error_types||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')||`${c.errors||0}`;const actions=h('td');const test=h('button','btn small','Test et');test.onclick=()=>testConnector(c.id,test);actions.append(test);tr.append(name,health,textCell(cred),sr,textCell(c.result_count),textCell(c.accepted_sources),textCell(`${c.average_latency_seconds}s / ${c.p95_latency_seconds}s`),textCell(errors),textCell(fmt(c.last_success_at)),actions);body.append(tr)}}catch(e){toast(`Connector bilgisi alınamadı: ${e.message}`,true)}}
async function testConnector(id,button){button.disabled=true;button.textContent='Test…';try{const result=await api(`/api/connectors/${encodeURIComponent(id)}/test`,{method:'POST'});toast(`${id}: ${result.ok?'başarılı':'başarısız'} · ${result.result_count||0} sonuç`);await loadConnectors()}catch(e){toast(`${id}: ${e.message}`,true)}finally{button.disabled=false;button.textContent='Test et'}}
function qualityCard(label,value,note,invert=false){const available=value!==undefined&&value!==null,number=Number(value??0),percentValue=invert?Math.max(0,1-number):number;const box=h('div','quality-card');box.append(h('span','label',label),h('div','q-value',available?pct(number):'—'),h('span','note',available?note:`${note} · ölçülmedi`));const bar=h('div',`metric-bar ${available?(percentValue>=.8?'good':percentValue>=.5?'warn':'bad'):''}`);const fill=h('span');fill.style.width=available?`${Math.max(0,Math.min(100,percentValue*100))}%`:'0%';bar.append(fill);box.append(bar);return box}
function detailSection(title){const wrap=h('section','drawer-section'),head=h('div','section-title');head.append(h('h3','',title));wrap.append(head);return wrap}
function renderPipelineFlow(data){const flow=data.flow||{},section=detailSection('Araştırma akışı'),card=h('div','flow-card'),summary=h('div','flow-summary'),percent=Math.max(0,Math.min(100,Number(flow.progress_percent||0)));const value=h('div');value.append(h('div','flow-percent',`${Math.round(percent)}%`),h('div','note',`Tur ${flow.round_number||0} · ${flow.current_stage||'INIT'}`));const track=h('div','flow-track'),fill=h('span');fill.style.width=`${percent}%`;track.append(fill);summary.append(value,track,badge(data.run.status));card.append(summary);const scroll=h('div','flow-scroll'),nodes=h('div','flow-nodes');for(const[nodeIndex,node]of(flow.nodes||[]).entries()){if(nodeIndex)nodes.append(h('div','flow-arrow','→'));const item=h('div',`flow-node ${node.state}`);if(node.state==='active')item.setAttribute('aria-current','step');item.append(h('div','flow-node-name',node.label),h('div','flow-node-code',node.stage),h('div','flow-node-meta',node.visits?`${node.visits} ziyaret · ${duration(node.duration_seconds)}`:node.state==='skipped'?'Atlandı':'Bekliyor'));nodes.append(item)}scroll.append(nodes);card.append(scroll);if(flow.has_recovery_loop)card.append(h('div','flow-loop','↺ Coverage yetersiz bulundu: recovery planı üzerinden aramaya geri dönüldü.'));section.append(card);return section}
async function submitHitl(runId,interactionId,response){try{await api(`/api/runs/${runId}/respond`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({interaction_id:interactionId,response})});toast('Yanıt alındı; araştırma yeniden kuyruğa alındı.');await refresh();await openRun(runId)}catch(e){toast(`HITL yanıtı reddedildi: ${e.message}`,true)}}
function renderHitl(data){const interaction=data.run.interaction;if(!interaction)return null;const section=detailSection('Kullanıcı kararı gerekiyor'),card=h('div','hitl-card'),title=h('div','hitl-title');title.append(h('strong','',interaction.type),h('span','badge awaiting_input',labels[data.run.status]||data.run.status));card.append(title,h('div','note',`Interaction ${interaction.interaction_id} · Son yanıt zamanı ${fmt(interaction.expires_at)}`));const payload=interaction.data||{};
if(interaction.type==='planning_questions'){const inputs=[];for(const item of payload.questions||[]){const row=h('div','hitl-question'),label=h('label','',item.question),input=h('textarea');input.placeholder='Yanıtınızı yazın';input.dataset.question=item.question;row.append(label,input);card.append(row);inputs.push(input)}const actions=h('div','hitl-actions'),send=h('button','btn primary','Yanıtları gönder');send.onclick=()=>submitHitl(data.run.id,interaction.interaction_id,{answers:inputs.map(input=>({question:input.dataset.question,answer:input.value.trim()}))});actions.append(send);card.append(actions)}
else if(interaction.type==='plan_review'||interaction.type==='outline_review'){const view=h('div','hitl-data');view.append(h('code','',JSON.stringify(payload.plan||payload.outline||payload,null,2)));const guidance=h('textarea');guidance.placeholder='Değişiklik talebiniz (reddediyorsanız)…';const actions=h('div','hitl-actions'),approve=h('button','btn primary','Onayla'),reject=h('button','btn danger','Değişiklik iste');approve.onclick=()=>submitHitl(data.run.id,interaction.interaction_id,{approved:true});reject.onclick=()=>submitHitl(data.run.id,interaction.interaction_id,{approved:false,modifications:guidance.value.trim()});actions.append(approve,reject);card.append(view,guidance,actions)}
else if(interaction.type==='source_review'){const grid=h('div','domain-grid'),choices=[];for(const item of payload.domains||[]){const row=h('label','domain-choice'),check=h('input');check.type='checkbox';check.checked=item.ai_recommendation!=='exclude';row.append(check,h('span','',item.domain),h('span','note',`${item.source_count} · ${Math.round(Number(item.avg_relevance_score||0)*100)}%`));grid.append(row);choices.push({item,check})}const actions=h('div','hitl-actions'),send=h('button','btn primary','Kaynak seçimini uygula');send.onclick=()=>submitHitl(data.run.id,interaction.interaction_id,{included_domains:choices.filter(x=>x.check.checked).map(x=>x.item.domain),excluded_domains:choices.filter(x=>!x.check.checked).map(x=>x.item.domain)});actions.append(send);card.append(grid,actions)}
section.append(card);return section}
function renderDetail(data){const run=data.run,protocol=run.protocol||{},coverage=run.coverage||{},quality=data.quality||{};el('drawer-title').textContent=protocol.primary_question||protocol.title||run.id;el('drawer-meta').textContent=`${run.id} · ${labels[run.status]||run.status} · ${run.current_stage} · ${duration(run.elapsed_seconds)}`;const body=el('drawer-body');body.replaceChildren();body.append(renderPipelineFlow(data));const hitl=renderHitl(data);if(hitl)body.append(hitl);const summary=detailSection('Kalite ve coverage');const grid=h('div','quality-grid');grid.append(qualityCard('Kaynak ailesi',coverage.source_family_coverage,'Hedef aile dağılımı'),qualityCard('Sorgu dalları',coverage.query_branch_coverage,'Cevap üreten branch'),qualityCard('Claim audit',coverage.claim_audit_coverage,'Denetlenmiş major claim'),qualityCard('Sentinel recall',quality.sentinel_recall,'Bilinen kritik kaynaklar'),qualityCard('Tahmini tamlık',quality.estimated_completeness,'Incidence tahmini'),qualityCard('Relative recall',quality.relative_recall,'Accept-only geri çağırım'),qualityCard('Citation novelty',quality.citation_frontier_novelty,'Yeni citation katkısı',true),qualityCard('Reserve FN',quality.reserve_false_negative_rate,'Yanlış elenme sinyali',true));summary.append(grid);const reasons=h('div','reason-list');for(const reason of coverage.reasons||[])reasons.append(h('span','reason',reason));if(reasons.childNodes.length)summary.append(reasons);body.append(summary);
const funnelSection=detailSection('Kaynak hunisi');const funnel=h('div','funnel'),steps=data.funnel.steps||[],max=Math.max(1,...steps.map(s=>s.value));for(const step of steps){const row=h('div','funnel-row');row.append(h('span','',step.label));const bar=h('div','metric-bar');const fill=h('span');fill.style.width=`${step.value/max*100}%`;bar.append(fill);row.append(bar,h('strong','',String(step.value)));funnel.append(row)}const admission=h('div','admission');for(const key of ['accept','reserve','reject'])admission.append(h('span','',`${key}: ${data.funnel.admission[key]||0}`));funnelSection.append(funnel,admission);body.append(funnelSection);
const timelineSection=detailSection('Pipeline zaman çizelgesi');const timeline=h('div','timeline');for(const stage of data.timeline||[]){const item=h('div',`stage${stage.active?' active':''}`);item.append(h('div','stage-name',stage.stage),h('div','stage-meta',`Tur ${stage.round} · ${duration(stage.duration_seconds)}`),h('div','stage-meta',fmt(stage.started_at)));timeline.append(item)}if(!timeline.childNodes.length)timeline.append(h('div','empty','Henüz aşama olayı yok.'));timelineSection.append(timeline);body.append(timelineSection);
const branchSection=detailSection('Sorgu dalları');const branchWrap=h('div','table-wrap'),branchTable=h('table');const bh=h('thead'),bhr=h('tr');for(const x of ['Dal','Sorgu','Connector','Sonuç','Başarı','Toplam gecikme'])bhr.append(h('th','',x));bh.append(bhr);const bb=h('tbody');for(const b of data.query_branches||[]){const tr=h('tr');tr.append(textCell(b.branch_id),textCell(b.query),textCell(b.connectors.join(', ')),textCell(b.result_count),textCell(`${b.successful_calls}/${b.calls}`),textCell(`${b.latency_seconds.toFixed(1)} sn`));bb.append(tr)}branchTable.append(bh,bb);branchWrap.append(branchTable);branchSection.append(branchWrap);body.append(branchSection);
const sourceSection=detailSection(`Kabul edilen kaynaklar (${data.sources.length})`);const sourceWrap=h('div','table-wrap'),sourceTable=h('table');const sh=h('thead'),shr=h('tr');for(const x of ['Kaynak','Aile / Connector','Admission','Keşif','Alaka','Sorgu dalı'])shr.append(h('th','',x));sh.append(shr);const sb=h('tbody');for(const s of data.sources){const tr=h('tr');const title=h('td');const link=h('a','source-link',s.title);link.href=s.url;link.target='_blank';link.rel='noopener noreferrer';title.append(link,h('div','mono',s.persistent_id||s.id));const adm=h('td');adm.append(h('span',`badge ${s.admission_tier}`,s.admission_tier));tr.append(title,textCell(`${s.family} / ${s.connector_id}`),adm,textCell(s.discovery_method),textCell(`${Math.round(s.relevance_score*100)}%`),textCell((s.query_branches||[]).join(', ')));sb.append(tr)}sourceTable.append(sh,sb);sourceWrap.append(sourceTable);sourceSection.append(sourceWrap);body.append(sourceSection);
if(data.artifacts.length){const artSection=detailSection('Çıktılar');const arts=h('div','artifact-grid');for(const a of data.artifacts){const item=h('div','artifact');const info=h('div');info.append(h('strong','',a.name),h('div','note',bytes(a.size_bytes)));const dl=h('button','btn small','İndir');dl.onclick=()=>downloadArtifact(run.id,a.name,dl);item.append(info,dl);arts.append(item)}artSection.append(arts);body.append(artSection)}
const llmSection=detailSection('LLM ve kanıt özeti');const llmGrid=h('div','resource-grid');llmGrid.append(resource('LLM çağrısı',String(data.llm.calls),0,(data.llm.models||[]).join(', ')),resource('Üretim hızı',`${data.llm.tokens_per_second} tok/sn`,0,`${data.llm.completion_tokens} completion token`),resource('Claim',String(data.claim_summary.total),0,`${data.claim_summary.major} major`),resource('Evidence link',String(data.claim_summary.evidence_links),0,Object.entries(data.claim_summary.statuses||{}).map(([k,v])=>`${k}: ${v}`).join(' · ')));llmSection.append(llmGrid);body.append(llmSection);
const eventSection=detailSection('Yapılandırılmış olaylar');const eventList=h('div','event-list');for(const e of [...data.events].reverse()){const item=h('details','event'),sum=h('summary');sum.append(h('strong','',e.type),h('span','note',fmt(e.created_at)));item.append(sum,h('code','',JSON.stringify(e.payload,null,2).slice(0,8000)));eventList.append(item)}eventSection.append(eventList);body.append(eventSection)}
async function openRun(id){currentRunId=id;el('drawer-backdrop').classList.add('open');el('drawer-backdrop').setAttribute('aria-hidden','false');el('drawer-title').textContent=id;el('drawer-body').replaceChildren(h('div','empty','Araştırma verileri yükleniyor…'));try{renderDetail(await api(`/api/runs/${id}/detail`))}catch(e){el('drawer-body').replaceChildren(h('div','empty',e.message));toast(e.message,true)}}
function closeRun(){currentRunId=null;el('drawer-backdrop').classList.remove('open');el('drawer-backdrop').setAttribute('aria-hidden','true')}
async function downloadArtifact(runId,name,button){button.disabled=true;try{const response=await fetch(`/api/runs/${runId}/artifacts/${encodeURIComponent(name)}`,{headers});if(!response.ok)throw new Error(await response.text());const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url)}catch(e){toast(`İndirme başarısız: ${e.message}`,true)}finally{button.disabled=false}}
async function systemAction(action){if(action==='stop'&&!confirm('API, worker, MCP ve Telegram servisleri durdurulsun mu? Panel açık kalacak.'))return;document.querySelectorAll('.system-action').forEach(b=>b.disabled=true);toast(`${action} işlemi başladı…`);try{await api(`/api/system/${action}`,{method:'POST'});toast('Sistem işlemi tamamlandı.')}catch(e){toast(e.message,true)}finally{await refresh();document.querySelectorAll('.system-action').forEach(b=>b.disabled=false)}}
async function runAction(id,action){try{await api(`/api/runs/${id}/${action}`,{method:'POST'});toast(`${id}: ${action} kaydedildi.`);await refresh();if(currentRunId===id)await openRun(id)}catch(e){toast(e.message,true)}}
async function showLog(service){document.querySelectorAll('#log-tabs button').forEach(b=>b.classList.toggle('primary',b.dataset.service===service));el('logs').textContent='Yükleniyor…';try{el('logs').textContent=await api(`/api/logs/${service}`)}catch(e){el('logs').textContent=e.message}}
function switchView(view){document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.view===view));document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id===`view-${view}`));if(view==='connectors')loadConnectors();if(view==='account'){loadTelegram();loadKeys()}}
for(const service of ['worker','api','mcp','telegram','control-panel']){const b=h('button','btn small',serviceLabels[service]||'Panel');b.dataset.service=service;b.onclick=()=>showLog(service);el('log-tabs').append(b)}
document.querySelectorAll('.system-action').forEach(b=>b.onclick=()=>systemAction(b.dataset.action));document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>switchView(b.dataset.view));el('refresh-connectors').onclick=loadConnectors;el('drawer-close').onclick=closeRun;el('drawer-refresh').onclick=()=>currentRunId&&openRun(currentRunId);el('drawer-backdrop').onclick=e=>{if(e.target===el('drawer-backdrop'))closeRun()};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeRun()});

// --- Hesabım: Telegram bağlantısı ve API anahtarları ---
async function loadTelegram(){
  const box=el('tg-state');
  try{
    const s=await api('/api/telegram');
    const linked=(s.linked||[]).length>0;
    box.textContent=linked
      ? `Bağlı — Telegram ID ${s.linked.join(', ')}`
      : 'Bağlı değil. Bottan araştırma başlatabilmek için hesabınızı bağlayın.';
    el('tg-unlink').hidden=!linked;
    el('tg-link').textContent=linked?'Yeni kod al':'Bağlantı kodu al';
  }catch(e){box.textContent=e.message}
}
async function telegramCode(){
  const target=el('tg-code');
  try{
    const r=await api('/api/telegram/link-code',{method:'POST'});
    const dk=r.deep_link
      ? `<a class="btn primary" href="${r.deep_link}" target="_blank" rel="noopener" style="display:inline-block;text-decoration:none;margin-top:10px">Telegram'da aç</a>`
      : `<div class="note" style="margin-top:10px">Derin bağlantı için TELEGRAM_BOT_USERNAME ayarlanmalı.</div>`;
    target.innerHTML=`<div class="codebox"><div class="label">Bağlantı kodu</div>
      <div class="code">${r.code}</div>
      <div class="note" style="margin-top:8px">Bota şunu yazın: <code>${r.command}</code></div>
      ${dk}
      <div class="note" style="margin-top:10px">Kod ${Math.round(r.expires_in_seconds/60)} dakika geçerli ve yalnız bir kez kullanılabilir.</div></div>`;
    target.hidden=false;
  }catch(e){toast(e.message,true)}
}
async function telegramUnlink(){
  if(!confirm('Telegram bağlantısı kaldırılsın mı? Bottan araştırma başlatamazsınız.'))return;
  try{await api('/api/telegram',{method:'DELETE'});toast('Bağlantı kaldırıldı.');el('tg-code').hidden=true;await loadTelegram()}
  catch(e){toast(e.message,true)}
}
async function loadKeys(){
  const box=el('key-list');
  try{
    const keys=await api('/api/keys');
    if(!keys.length){box.innerHTML='<div class="note">Henüz anahtar yok.</div>';return}
    box.innerHTML='';
    for(const k of keys){
      const row=h('div','service');
      row.style.cssText='justify-content:space-between;width:100%;border-radius:9px;margin-bottom:6px';
      row.innerHTML=`<span><strong>${k.name}</strong> <span class="mono">${k.prefix}…</span></span>`;
      const del=h('button','btn small danger','İptal et');
      del.onclick=async()=>{if(!confirm(`"${k.name}" anahtarı iptal edilsin mi?`))return;
        try{await api(`/api/keys/${k.id}`,{method:'DELETE'});toast('Anahtar iptal edildi.');await loadKeys()}catch(e){toast(e.message,true)}};
      row.append(del);box.append(row);
    }
  }catch(e){box.textContent=e.message}
}
async function createKey(){
  const name=el('key-name').value.trim()||'panel';
  try{
    const r=await api('/api/keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
    el('key-new').innerHTML=`<div class="codebox"><div class="label">${r.name} — bir daha gösterilmeyecek</div>
      <div class="secret">${r.key}</div></div>`;
    el('key-new').hidden=false;el('key-name').value='';await loadKeys();
  }catch(e){toast(e.message,true)}
}
el('tg-link').onclick=telegramCode;el('tg-unlink').onclick=telegramUnlink;el('key-create').onclick=createKey;
el('logout').onclick=logout;
loadSession().then(s=>{if(s&&s.is_admin)showLog('worker')});refresh();setInterval(refresh,4000);
</script>
</body>
</html>"""


# Rendered with __ERROR__ replaced by a message or an empty string. Kept deliberately
# plain: the sign-in page is the one surface an unauthenticated caller can reach, so it
# loads no data and exposes no state beyond whether a submission failed.
LOGIN_HTML = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Research Platform · Giriş</title>
  <style>
    :root{color-scheme:dark;--bg:#090d12;--surface:#10161f;--surface2:#151e29;--line:#273442;
      --text:#edf3f8;--muted:#8d9dad;--green:#43d49b;--red:#ff707d;--blue:#68a8ff}
    *{box-sizing:border-box}
    body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
      background:var(--bg);color:var(--text);
      font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;padding:24px}
    .card{width:100%;max-width:380px;border:1px solid var(--line);background:var(--surface);
      border-radius:13px;padding:28px}
    .eyebrow{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.14em;
      text-transform:uppercase}
    h1{font-size:23px;line-height:1.15;letter-spacing:-.03em;margin:6px 0 4px}
    .sub{margin:0 0 22px;color:var(--muted);font-size:13px}
    label{display:block;color:var(--muted);font-size:11px;font-weight:750;
      letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px}
    input{width:100%;margin-bottom:16px;padding:10px 12px;border:1px solid var(--line);
      border-radius:9px;background:var(--surface2);color:var(--text);font:inherit}
    input:focus{outline:2px solid var(--blue);outline-offset:1px;border-color:var(--blue)}
    button{width:100%;padding:11px;border:1px solid var(--green);border-radius:9px;
      background:var(--green);color:#06140e;font:inherit;font-weight:800;cursor:pointer}
    button:hover{filter:brightness(1.07)}
    .error{margin-bottom:16px;padding:10px 12px;border:1px solid #67343d;border-radius:9px;
      background:#2a171d;color:#ff9ba5;font-size:13px}
    .foot{margin:18px 0 0;color:var(--muted);font-size:12px;line-height:1.5}
  </style>
</head>
<body>
  <form class="card" method="post" action="/login">
    <div class="eyebrow">Research Platform</div>
    <h1>Operasyon Merkezi</h1>
    <p class="sub">Devam etmek için hesabınızla giriş yapın.</p>
    __ERROR__
    <label for="email">E-posta</label>
    <input id="email" name="email" type="email" autocomplete="username" required autofocus>
    <label for="password">Parola</label>
    <input id="password" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Giriş yap</button>
    <p class="foot">Hesabınız yoksa yöneticinize başvurun.
      Hesaplar <code>research-admin</code> komutuyla oluşturulur.</p>
  </form>
</body>
</html>"""
