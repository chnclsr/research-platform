from __future__ import annotations


CONTROL_PANEL_HTML = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="control-token" content="__CONTROL_TOKEN__">
  <title>Research Platform · Kontrol</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0d1117; --panel: #151b23; --panel-2: #1b2330; --line: #2a3441;
      --text: #e8edf4; --muted: #8d9aab; --green: #46d39a; --amber: #f3bd54;
      --red: #ff6b78; --blue: #67a7ff; --violet: #a78bfa;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font: 14px/1.45 Inter, ui-sans-serif, system-ui, sans-serif; }
    button { font: inherit; }
    .shell { max-width: 1440px; margin: 0 auto; padding: 28px; }
    header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
    .eyebrow { color: var(--blue); font-size: 12px; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
    h1 { margin: 5px 0 4px; font-size: clamp(25px, 4vw, 38px); line-height: 1.12; letter-spacing: -.035em; }
    .sub { margin: 0; color: var(--muted); }
    .actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
    .btn { border: 1px solid var(--line); border-radius: 9px; color: var(--text); background: var(--panel-2); padding: 9px 13px; cursor: pointer; transition: .15s ease; }
    .btn:hover { border-color: #526277; transform: translateY(-1px); }
    .btn:disabled { cursor: wait; opacity: .45; transform: none; }
    .btn.primary { color: #07140f; border-color: var(--green); background: var(--green); font-weight: 750; }
    .btn.danger { color: var(--red); border-color: #63333b; background: #26191e; }
    .btn.small { padding: 5px 8px; border-radius: 7px; font-size: 12px; }
    .summary { display: grid; grid-template-columns: 1.25fr repeat(3, minmax(145px, .75fr)); gap: 12px; margin-bottom: 22px; }
    .card, section { border: 1px solid var(--line); background: var(--panel); border-radius: 13px; }
    .card { min-height: 114px; padding: 17px; display: flex; flex-direction: column; justify-content: space-between; }
    .card-label { color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
    .card-value { font-size: 25px; font-weight: 760; letter-spacing: -.025em; }
    .card-note { color: var(--muted); font-size: 12px; }
    .signal { display: inline-flex; align-items: center; gap: 8px; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--muted); box-shadow: 0 0 0 4px #ffffff0b; }
    .dot.running, .dot.ok { background: var(--green); }.dot.degraded { background: var(--amber); }.dot.stopped, .dot.unavailable { background: var(--red); }
    .service-strip { display: flex; flex-wrap: wrap; gap: 8px; margin: -10px 0 22px; }
    .service { display: inline-flex; align-items: center; gap: 7px; border: 1px solid var(--line); background: #111720; padding: 7px 10px; border-radius: 99px; color: var(--muted); font-size: 12px; }
    .service strong { color: var(--text); font-weight: 650; }
    section { overflow: hidden; margin-bottom: 18px; }
    .section-head { min-height: 58px; display: flex; align-items: center; justify-content: space-between; padding: 13px 17px; border-bottom: 1px solid var(--line); gap: 12px; }
    h2 { margin: 0; font-size: 15px; letter-spacing: -.01em; }
    .count { color: var(--muted); font-size: 12px; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 980px; }
    th { color: var(--muted); font-size: 11px; letter-spacing: .05em; text-transform: uppercase; font-weight: 700; text-align: left; padding: 10px 14px; background: #111720; }
    td { border-top: 1px solid #222b37; padding: 12px 14px; vertical-align: middle; }
    tbody tr:hover { background: #ffffff03; }
    .run-title { max-width: 390px; }
    .run-title strong { display: block; font-weight: 680; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .run-id { color: var(--muted); font: 11px ui-monospace, SFMono-Regular, Consolas, monospace; }
    .metrics { color: var(--muted); white-space: nowrap; }
    .metrics strong { color: var(--text); }
    .badge { display: inline-flex; align-items: center; padding: 4px 8px; border-radius: 99px; background: #263140; color: #c6d0dc; font-size: 11px; font-weight: 700; }
    .badge.running, .badge.completed { background: #153329; color: #74e4b7; }
    .badge.queued, .badge.paused { background: #352a16; color: #ffd179; }
    .badge.failed, .badge.cancelled, .badge.cancel_requested { background: #3b1e25; color: #ff929c; }
    .badge.completed_incomplete { background: #302849; color: #c4b5fd; }
    .row-actions { display: flex; gap: 5px; justify-content: flex-end; }
    .empty { padding: 34px 16px; color: var(--muted); text-align: center; }
    .lower { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
    .log-tabs { display: flex; gap: 5px; flex-wrap: wrap; }
    pre { min-height: 300px; max-height: 420px; overflow: auto; margin: 0; padding: 16px; color: #c9d4e1; background: #0a0e13; font: 11.5px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; }
    .footer { display: flex; align-items: center; justify-content: space-between; color: var(--muted); font-size: 12px; padding: 4px 2px 18px; }
    .toast { position: fixed; right: 22px; bottom: 22px; max-width: 420px; border: 1px solid var(--line); border-radius: 11px; background: #202937; padding: 12px 15px; box-shadow: 0 14px 50px #0008; opacity: 0; transform: translateY(12px); pointer-events: none; transition: .2s ease; }
    .toast.show { opacity: 1; transform: translateY(0); }.toast.error { border-color: #713641; color: #ffabb3; }
    @media (max-width: 900px) { .summary { grid-template-columns: 1fr 1fr; } .lower { grid-template-columns: 1fr; } header { flex-direction: column; } .actions { justify-content: flex-start; } }
    @media (max-width: 560px) { .shell { padding: 18px 13px; } .summary { grid-template-columns: 1fr; } .card { min-height: 95px; } }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div><div class="eyebrow">Local control plane</div><h1>Research Platform</h1><p class="sub">Servisler, kuyruk ve araştırma işleri — tek ekranda.</p></div>
      <div class="actions">
        <button class="btn primary system-action" data-action="start">Başlat</button>
        <button class="btn system-action" data-action="restart">Yeniden başlat</button>
        <button class="btn danger system-action" data-action="stop">Servisleri durdur</button>
      </div>
    </header>

    <div class="summary">
      <div class="card"><span class="card-label">Sistem</span><span class="card-value signal"><i id="overall-dot" class="dot"></i><span id="overall">Yükleniyor</span></span><span id="overall-note" class="card-note">Durum alınıyor…</span></div>
      <div class="card"><span class="card-label">Aktif işler</span><span id="active-count" class="card-value">—</span><span class="card-note">Çalışan ve bekleyen</span></div>
      <div class="card"><span class="card-label">Kuyruk</span><span id="queue-count" class="card-value">—</span><span id="queue-note" class="card-note">Redis kontrol ediliyor</span></div>
      <div class="card"><span class="card-label">Yerel model</span><span id="model" class="card-value" style="font-size:17px">—</span><span id="model-note" class="card-note">Ollama kontrol ediliyor</span></div>
    </div>

    <div id="services" class="service-strip"></div>

    <section>
      <div class="section-head"><h2>Aktif ve sıradaki istekler</h2><span id="active-label" class="count">0 iş</span></div>
      <div class="table-wrap"><table><thead><tr><th>Araştırma</th><th>Durum</th><th>Aşama</th><th>Sıra</th><th>Tur</th><th>Kaynak / İddia</th><th>Güncelleme</th><th></th></tr></thead><tbody id="active-runs"></tbody></table><div id="active-empty" class="empty">Aktif iş yok.</div></div>
    </section>

    <div class="lower">
      <section>
        <div class="section-head"><h2>Son tamamlananlar</h2><span class="count">Son 20 kayıt</span></div>
        <div class="table-wrap"><table style="min-width:720px"><thead><tr><th>Araştırma</th><th>Durum</th><th>Kaynak / İddia</th><th>Zaman</th></tr></thead><tbody id="recent-runs"></tbody></table><div id="recent-empty" class="empty">Geçmiş kayıt yok.</div></div>
      </section>
      <section>
        <div class="section-head"><h2>Servis logları</h2><div id="log-tabs" class="log-tabs"></div></div>
        <pre id="logs">Bir servis seç.</pre>
      </section>
    </div>

    <div class="footer"><span>Yalnız izinli ofis ağından erişilebilir · v0.5.2</span><span id="last-update">—</span></div>
  </main>
  <div id="toast" class="toast" role="status"></div>
  <script>
    const token = document.querySelector('meta[name="control-token"]').content;
    const headers = {'X-Control-Token': token};
    let refreshing = false;
    const statusLabels = {running:'Çalışıyor',stopped:'Kapalı',degraded:'Kısmi',queued:'Sırada',paused:'Duraklatıldı',cancel_requested:'İptal bekliyor',cancelled:'İptal',completed:'Tamamlandı',completed_incomplete:'Eksik tamamlandı',failed:'Hata'};
    const serviceLabels = {api:'API',worker:'Worker',mcp:'MCP',telegram:'Telegram'};
    const fmt = iso => iso ? new Intl.DateTimeFormat('tr-TR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(iso)) : '—';
    const el = id => document.getElementById(id);
    const badge = status => { const b=document.createElement('span'); b.className=`badge ${status}`; b.textContent=statusLabels[status]||status; return b; };
    function toast(message, error=false){ const t=el('toast'); t.textContent=message; t.className=`toast show${error?' error':''}`; clearTimeout(t.timer); t.timer=setTimeout(()=>t.className='toast',4200); }
    async function api(path, options={}) { const response=await fetch(path,{...options,headers:{...headers,...(options.headers||{})}}); const type=response.headers.get('content-type')||''; const data=type.includes('json')?await response.json():await response.text(); if(!response.ok) throw new Error(data.detail||data||`HTTP ${response.status}`); return data; }
    function textCell(value, className=''){ const td=document.createElement('td'); td.textContent=value??'—'; if(className)td.className=className; return td; }
    function runTitle(run){ const td=document.createElement('td'); td.className='run-title'; const strong=document.createElement('strong'); strong.textContent=run.question||run.title; strong.title=run.question||run.title; const id=document.createElement('span'); id.className='run-id'; id.textContent=run.id; td.append(strong,id); return td; }
    function actionButton(label, action, run){ const b=document.createElement('button'); b.className=`btn small${action==='cancel'?' danger':''}`; b.textContent=label; b.onclick=()=>runAction(run.id,action); return b; }
    function renderActive(runs){ const body=el('active-runs'); body.replaceChildren(); el('active-empty').style.display=runs.length?'none':'block'; el('active-label').textContent=`${runs.length} iş`; for(const run of runs){ const tr=document.createElement('tr'); tr.append(runTitle(run)); const st=document.createElement('td'); st.append(badge(run.status)); tr.append(st,textCell(run.current_stage),textCell(run.queue_position||'—'),textCell(run.round_number)); const m=document.createElement('td'); m.className='metrics'; m.textContent=`${run.sources_count} / ${run.claims_count}`; tr.append(m,textCell(fmt(run.updated_at))); const actions=document.createElement('td'); actions.className='row-actions'; if(run.status==='running'||run.status==='queued') actions.append(actionButton('Duraklat','pause',run)); if(run.status==='paused') actions.append(actionButton('Devam','resume',run)); if(!['cancel_requested','cancelled'].includes(run.status)) actions.append(actionButton('İptal','cancel',run)); tr.append(actions); body.append(tr); } }
    function renderRecent(runs){ const body=el('recent-runs'); body.replaceChildren(); el('recent-empty').style.display=runs.length?'none':'block'; for(const run of runs){ const tr=document.createElement('tr'); tr.append(runTitle(run)); const st=document.createElement('td'); st.append(badge(run.status)); tr.append(st,textCell(`${run.sources_count} / ${run.claims_count}`,'metrics'),textCell(fmt(run.updated_at))); body.append(tr); } }
    function renderServices(processes,queue){ const box=el('services'); box.replaceChildren(); for(const [name,p] of Object.entries(processes)){ const item=document.createElement('span'); item.className='service'; const dot=document.createElement('i'); dot.className=`dot ${p.running?'running':'stopped'}`; const label=document.createElement('strong'); label.textContent=serviceLabels[name]||name; item.append(dot,label,document.createTextNode(p.running?` PID ${p.pid}`:' Kapalı')); box.append(item); } const hb=document.createElement('span'); hb.className='service'; const hdot=document.createElement('i'); hdot.className=`dot ${queue.available&&queue.heartbeat_ttl_seconds>0?'running':'stopped'}`; hb.append(hdot,document.createTextNode(queue.heartbeat_ttl_seconds>0?`Worker heartbeat ${queue.heartbeat_ttl_seconds} sn`:'Worker heartbeat yok')); box.append(hb); }
    async function refresh(){ if(refreshing)return; refreshing=true; try{ const data=await api('/api/status'); el('overall').textContent=statusLabels[data.overall]||data.overall; el('overall-dot').className=`dot ${data.overall}`; el('overall-note').textContent=data.action.busy?`${data.action.action} işlemi sürüyor`:`Veritabanı: ${data.database}`; const active=data.runs.active; el('active-count').textContent=active.length; el('queue-count').textContent=data.queue.waiting; el('queue-note').textContent=data.queue.available?`${data.queue.running} çalışan · ${data.queue.waiting} bekleyen`:'Redis erişilemiyor'; const models=data.health.ollama?.models||[]; el('model').textContent=models[0]?.name||'Yüklü model yok'; el('model-note').textContent=data.health.ollama?.status==='ok'?'Ollama erişilebilir':'Ollama kapalı'; renderServices(data.processes,data.queue); renderActive(active); renderRecent(data.runs.recent); el('last-update').textContent=`Son yenileme ${new Date().toLocaleTimeString('tr-TR')}`; document.querySelectorAll('.system-action').forEach(b=>b.disabled=data.action.busy); }catch(e){ toast(`Durum alınamadı: ${e.message}`,true); }finally{ refreshing=false; } }
    async function systemAction(action){ if(action==='stop'&&!confirm('API, worker, MCP ve Telegram servisleri durdurulsun mu? Panel açık kalacak.'))return; document.querySelectorAll('.system-action').forEach(b=>b.disabled=true); toast(`${action} işlemi başladı…`); try{ await api(`/api/system/${action}`,{method:'POST'}); toast('Sistem işlemi tamamlandı.'); }catch(e){ toast(e.message,true); }finally{ await refresh(); document.querySelectorAll('.system-action').forEach(b=>b.disabled=false); } }
    async function runAction(id,action){ try{ await api(`/api/runs/${id}/${action}`,{method:'POST'}); toast(`${id}: ${action} kaydedildi.`); await refresh(); }catch(e){ toast(e.message,true); } }
    async function showLog(service){ document.querySelectorAll('#log-tabs button').forEach(b=>b.classList.toggle('primary',b.dataset.service===service)); el('logs').textContent='Yükleniyor…'; try{ el('logs').textContent=await api(`/api/logs/${service}`); }catch(e){ el('logs').textContent=e.message; } }
    for(const service of ['worker','api','mcp','telegram','control-panel']){ const b=document.createElement('button'); b.className='btn small'; b.dataset.service=service; b.textContent=serviceLabels[service]||'Panel'; b.onclick=()=>showLog(service); el('log-tabs').append(b); }
    document.querySelectorAll('.system-action').forEach(b=>b.onclick=()=>systemAction(b.dataset.action));
    showLog('worker'); refresh(); setInterval(refresh,3000);
  </script>
</body>
</html>"""
