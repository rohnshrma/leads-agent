// WebiGeeks CRM front end - plain ES modules, no build step.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const S = {
  cfg: null,
  pipeline: store.get('pipeline', 'all'),
  view: 'today',
  openId: null,
  filters: { q: '', status: 'open', source: '' },
  logType: 'call',
};

// ------------------------------------------------------------------ api
async function api(method, url, body) {
  const isText = typeof body === 'string';
  const res = await fetch('/api' + url, {
    method,
    headers: body === undefined ? {} : { 'content-type': isText ? 'text/csv' : 'application/json' },
    body: body === undefined ? undefined : isText ? body : JSON.stringify(body),
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = new Error(data.error || res.statusText);
    e.data = data; e.status = res.status;
    throw e;
  }
  return data;
}

// ------------------------------------------------------------- helpers
const icon = (n) => `<svg class="ic" viewBox="0 0 24 24"><use href="#i-${n}"/></svg>`;
const pipes = () => S.cfg.pipelines;
const money = (n, p) => (n == null ? '-' : (p === 'admission' ? '₹' + Number(n).toLocaleString('en-IN') : '$' + Number(n).toLocaleString('en-US')));
const fmtAbs = (iso) => new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
function rel(iso) {
  const ms = Date.parse(iso) - Date.now();
  const a = Math.abs(ms);
  const m = a / 60000;
  let t;
  if (m < 1) return 'now';
  if (m < 60) t = `${Math.round(m)}m`;
  else if (m < 1440) t = `${Math.round(m / 60)}h`;
  else t = `${Math.round(m / 1440)}d`;
  return ms < 0 ? `${t} ago` : `in ${t}`;
}
function fmtMins(m) {
  if (m == null) return '-';
  if (m < 1) return '<1 min';
  if (m < 60) return `${m} min`;
  if (m < 1440) return `${(m / 60).toFixed(1)} h`;
  return `${(m / 1440).toFixed(1)} d`;
}
const toLocalInput = (d) => {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};
function chipDate(kind) {
  const d = new Date();
  if (kind === 'later') { d.setHours(d.getHours() + 3); return d; }
  const days = { tomorrow: 1, d2: 2, d3: 3, w1: 7 }[kind] ?? 1;
  d.setDate(d.getDate() + days); d.setHours(10, 0, 0, 0);
  return d;
}
const label = (s) => String(s || '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
  .replace(/^Whatsapp\b/, 'WhatsApp').replace(/^Linkedin\b/, 'LinkedIn').replace(/^Sms\b/, 'SMS')
  .replace(/^Google ads\b/, 'Google Ads');
function toast(msg, bad = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (bad ? ' bad' : '');
  el.textContent = msg;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), bad ? 5200 : 3200);
}
function firstName(l) {
  return l.business && l.business === l.name ? 'there' : String(l.name).split(' ')[0];
}
function fill(text, l) {
  return String(text || '')
    .replaceAll('{{name}}', firstName(l))
    .replaceAll('{{course}}', l.courseInterest || 'our course')
    .replaceAll('{{business}}', l.business || l.name)
    .replaceAll('{{mockup}}', l.mockupUrl || '[design preview link]');
}
function templateFor(l, channel, id) {
  const list = S.cfg.templates.filter((t) => t.pipeline === l.pipeline && t.channel === channel);
  const pick = list.find((t) => t.id === id);
  if (pick) return pick;
  // a lead with a design preview link gets the email that carries it
  return (l.mockupUrl && list.find((t) => t.body.includes('{{mockup}}'))) || list.find((t) => !t.body.includes('{{mockup}}')) || list[0];
}
function links(l, tplId) {
  const out = {};
  const num = (l.whatsapp || l.phone || '').replace(/\D/g, '');
  if (l.phone) out.call = `tel:${l.phone}`;
  if (num) {
    const t = templateFor(l, 'whatsapp', tplId);
    out.whatsapp = `https://wa.me/${num}${t ? '?text=' + encodeURIComponent(fill(t.body, l)) : ''}`;
  }
  if (l.email) {
    const t = templateFor(l, 'email', tplId);
    out.email = `mailto:${l.email}${t ? `?subject=${encodeURIComponent(fill(t.subject, l))}&body=${encodeURIComponent(fill(t.body, l))}` : ''}`;
  }
  return out;
}
const callWin = (l) => {
  const w = l.callWindow;
  if (!w?.applies) return '';
  if (w.allowed === null) return `<span class="win muted">${icon('clock')} Add state for call hours</span>`;
  return w.allowed
    ? `<span class="win ok">${icon('clock')} OK to call · ${esc(w.localTime)} there</span>`
    : `<span class="win no">${icon('clock')} Don't call · ${esc(w.localTime)} there</span>`;
};

// -------------------------------------------------------------- switcher
function renderSwitch() {
  const opts = S.view === 'pipeline' ? ['admission', 'agency'] : ['all', 'admission', 'agency'];
  if (!opts.includes(S.pipeline)) S.pipeline = opts[0];
  const names = { all: 'All', admission: 'Admissions', agency: 'Agency' };
  $('#switch').innerHTML = opts.map((k) => `<button role="tab" class="${S.pipeline === k ? 'on' : ''}" data-action="pipeline" data-key="${k}">${names[k]}</button>`).join('');
}

// ---------------------------------------------------------------- views
function leadRow(l) {
  const p = pipes()[l.pipeline];
  const ln = links(l);
  const dnc = l.doNotContact;
  const ov = l.overdue;
  const btns = dnc
    ? '<span class="chip red">Do not contact</span>'
    : [
      ln.call && `<a class="btn sm" href="${esc(ln.call)}" data-action="open" data-id="${l.id}" data-log="call">${icon('call')}Call</a>`,
      l.pipeline === 'admission' && ln.whatsapp && `<a class="btn sm" target="_blank" rel="noopener" href="${esc(ln.whatsapp)}" data-action="open" data-id="${l.id}" data-log="whatsapp">${icon('whatsapp')}WhatsApp</a>`,
      ln.email && `<a class="btn sm" href="${esc(ln.email)}" data-action="open" data-id="${l.id}" data-log="email">${icon('email')}Email</a>`,
      `<button class="btn sm" data-action="open" data-id="${l.id}" data-log="${esc(l.nextActionType || 'call')}">${icon('check')}Log</button>`,
    ].filter(Boolean).join('');
  return `<div class="card lead-row ${ov ? 'overdue' : ''}" data-action="open" data-id="${l.id}">
    <div>
      <div class="who">${esc(l.name)}${l.business && l.business !== l.name ? ` <span class="muted">· ${esc(l.business)}</span>` : ''}</div>
      <div class="sub">
        <span class="chip blue">${esc(p.brand)}</span><span class="chip">${esc(l.stageName)}</span>
        <span class="chip">${esc(label(l.source))}</span>
        ${l.city ? `<span>${esc(l.city)}${l.state ? ', ' + esc(l.state) : ''}</span>` : ''}
        ${l.rotting ? '<span class="chip amber">Going cold</span>' : ''}
        ${callWin(l)}
      </div>
      ${l.nextActionAt ? `<div class="next">${icon(l.nextActionType || 'call')}<span>${esc(l.nextActionNote || label(l.nextActionType))}</span>
        <span class="${ov ? 'due-over' : ''}">${ov ? 'Overdue · ' : ''}${rel(l.nextActionAt)}</span><span class="muted small">${fmtAbs(l.nextActionAt)}</span></div>` : ''}
    </div>
    <div class="acts">${btns}</div>
  </div>`;
}

async function viewToday() {
  const end = new Date(); end.setHours(23, 59, 59, 999);
  const t = await api('GET', `/today?endOfDay=${encodeURIComponent(end.toISOString())}`);
  const by = (arr) => (S.pipeline === 'all' ? arr : arr.filter((l) => l.pipeline === S.pipeline));
  const overdue = by(t.overdue), due = by(t.dueToday), fresh = by(t.untouched);
  $('#badge-today').textContent = t.overdue.length;
  $('#badge-today').hidden = !t.overdue.length;
  const sec = (title, arr, cls, empty) => `<section class="section"><h3>${title} <span class="chip ${cls}">${arr.length}</span></h3>
    <div class="list">${arr.length ? arr.map(leadRow).join('') : `<div class="card empty">${empty}</div>`}</div></section>`;
  const allClear = !overdue.length && !due.length && !fresh.length;
  return `<div class="page-head"><h1>Today</h1><span class="muted">${new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</span></div>
    ${t.noNextAction ? `<div class="banner info section">${t.noNextAction} open lead(s) have no next action. Every open lead needs one - open them and set it.</div>` : ''}
    ${allClear ? `<div class="card empty section"><b>Nothing due.</b><br>Add new leads, or import today's batch from the leads agent.<br><br>
      <button class="btn primary" data-action="new-lead">${icon('plus')}New lead</button></div>` : ''}
    ${overdue.length ? sec('Overdue', overdue, 'red', '') : ''}
    ${due.length || !allClear ? sec('Due today', due, 'blue', 'Nothing else scheduled for today.') : ''}
    ${fresh.length ? sec('New and not yet contacted', fresh, 'amber', '') : ''}
    <p class="muted small">${t.upcoming} more lead(s) have follow-ups scheduled later.</p>`;
}

const KEEP_TERMINAL = 25;
async function viewPipeline() {
  const pk = S.pipeline;
  const p = pipes()[pk];
  const leads = await api('GET', `/leads?pipeline=${pk}&limit=3000`);
  const cols = p.stages.map((st) => {
    let items = leads.filter((l) => l.stage === st.key);
    const total = items.length;
    const value = items.reduce((a, l) => a + ((pk === 'admission' ? (st.terminal === 'won' ? l.feeFinal : l.feeQuoted) : l.dealValue) || 0), 0);
    if (st.terminal) items = items.slice(0, KEEP_TERMINAL);
    else items.sort((a, b) => Number(b.overdue) - Number(a.overdue) || b.score - a.score);
    return `<div class="col ${st.terminal || ''}" data-stage="${st.key}">
      <h4><b>${esc(st.name)}</b><span>${total}${value ? ' · ' + money(value, pk) : ''}</span></h4>
      ${items.map((l) => `<div class="card kcard" draggable="true" data-id="${l.id}" data-action="open">
        <div class="n">${esc(l.name)}</div>
        <div class="m">${esc(pk === 'admission' ? (l.courseInterest || label(l.source)) : (l.niche || l.business || ''))}${l.city ? ' · ' + esc(l.city) : ''}</div>
        <div class="f"><span class="${l.overdue ? 'due-over' : 'muted'}">${l.nextActionAt ? icon(l.nextActionType || 'call') + ' ' + rel(l.nextActionAt) : (st.terminal === 'lost' ? esc(l.lostReason || '') : '')}</span>
          <span>${l.rotting ? '<span class="chip amber">cold</span> ' : ''}<span class="dot ${l.temperature}" title="${l.temperature} (${l.score})"></span></span></div>
      </div>`).join('')}
    </div>`;
  }).join('');
  return `<div class="page-head"><h1>${esc(p.name)} pipeline</h1><span class="muted">Drag cards between stages. Moving a card schedules the next action for you.</span></div>
    <div class="board">${cols}</div>`;
}

async function viewLeads() {
  const f = S.filters;
  const qs = new URLSearchParams({ pipeline: S.pipeline, status: f.status || 'all', limit: 2000 });
  if (f.q) qs.set('q', f.q);
  if (f.source) qs.set('source', f.source);
  const rows = await api('GET', `/leads?${qs}`);
  return `<div class="page-head"><h1>Leads</h1><span class="muted">${rows.length} shown</span><div class="grow"></div>
      <a class="btn" href="/api/export.csv">${icon('download')}Export CSV</a></div>
    <div class="tools">
      <input class="search" type="search" id="f-q" placeholder="Search name, phone, email, city..." value="${esc(f.q)}" aria-label="Search leads">
      <select id="f-status" aria-label="Status">${['open', 'won', 'lost', 'all'].map((s) => `<option value="${s}" ${f.status === s ? 'selected' : ''}>${label(s)}</option>`).join('')}</select>
      <select id="f-source" aria-label="Source"><option value="">All sources</option>${S.cfg.sources.map((s) => `<option value="${s}" ${f.source === s ? 'selected' : ''}>${label(s)}</option>`).join('')}</select>
    </div>
    <div class="card table-wrap"><table>
      <thead><tr><th>Lead</th><th>Pipeline</th><th>Stage</th><th>Source</th><th>Next action</th><th>Last contact</th><th>Score</th></tr></thead>
      <tbody>${rows.map((l) => `<tr data-action="open" data-id="${l.id}">
        <td><b>${esc(l.name)}</b>${l.business && l.business !== l.name ? `<div class="muted small">${esc(l.business)}</div>` : ''}${l.doNotContact ? ' <span class="chip red">DNC</span>' : ''}</td>
        <td>${esc(pipes()[l.pipeline].brand)}</td>
        <td><span class="chip ${l.status === 'won' ? 'green' : l.status === 'lost' ? 'red' : ''}">${esc(l.stageName)}</span></td>
        <td>${esc(label(l.source))}</td>
        <td>${l.nextActionAt ? `<span class="${l.overdue ? 'due-over' : ''}">${rel(l.nextActionAt)}</span>` : '<span class="muted">-</span>'}</td>
        <td>${l.lastContactAt ? rel(l.lastContactAt) : '<span class="muted">never</span>'}</td>
        <td><span class="dot ${l.temperature}"></span> ${l.score}</td></tr>`).join('')}
        ${rows.length ? '' : '<tr><td colspan="7" class="empty">No leads match.</td></tr>'}</tbody></table></div>`;
}

function bars(rows, { red = false, fmt = (r) => r.value } = {}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return rows.map((r) => `<div class="bar-row"><span class="lbl" title="${esc(r.label)}">${esc(r.label)}</span>
    <div class="bar ${red ? 'red' : ''}"><span style="width:${Math.round((r.value / max) * 100)}%"></span></div><span class="val">${fmt(r)}</span></div>`).join('');
}

async function viewDashboard() {
  const key = S.pipeline;
  const s = await api('GET', `/stats?pipeline=${key}`);
  const singles = key === 'all' ? await Promise.all(['admission', 'agency'].map((k) => api('GET', `/stats?pipeline=${k}`))) : [s];
  const tile = (l, v, hint = '', cls = '') => `<div class="card tile ${cls}"><div class="l">${l}</div><div class="v">${v}</div>${hint ? `<div class="hint">${hint}</div>` : ''}</div>`;
  const one = key !== 'all';
  const funnel = (st) => `<div class="card panel"><h3>${esc(pipes()[st.pipeline].name)} funnel</h3>
    ${bars(st.funnel.map((f) => ({ label: f.name, value: f.reached, pct: f.fromPrev })), { fmt: (r) => r.value + (r.pct != null ? ` <span class="small">(${r.pct}%)</span>` : '') })}
    <p class="muted small">Leads that ever reached each stage, with % of the previous stage.</p></div>`;
  return `<div class="page-head"><h1>Dashboard</h1><span class="muted">Only the numbers that change what you do next.</span></div>
    <div class="tiles">
      ${tile('Open leads', s.open, `${s.total} total`)}
      ${tile('Won this month', s.wonThisMonth, one ? money(s.wonValueThisMonth, key) : '', s.wonThisMonth ? 'good' : '')}
      ${tile('Win rate', s.winRate + '%', `${s.closedWinRate}% of closed leads`)}
      ${tile('Median first contact', fmtMins(s.medianFirstContactMinutes), 'Aim for under 1 hour')}
      ${tile('Overdue follow-ups', s.overdue, 'Should be 0', s.overdue ? 'alert' : 'good')}
      ${tile('Going cold', s.rotting, 'No contact for too long', s.rotting ? 'alert' : '')}
      ${tile('Not yet contacted', s.untouched, '', s.untouched ? 'alert' : '')}
      ${tile('No next action', s.noNextAction, 'Should always be 0', s.noNextAction ? 'alert' : 'good')}
      ${s.demoShowRate != null ? tile('Demo show rate', s.demoShowRate + '%', 'Scheduled → attended') : ''}
      ${s.avgAttemptsWon != null ? tile('Attempts before a win', s.avgAttemptsWon, s.avgAttemptsLost != null ? `vs ${s.avgAttemptsLost} before a loss` : '') : ''}
    </div>
    <div class="grid2 section">${singles.map(funnel).join('')}
      <div class="card panel"><h3>Where leads come from</h3>
        ${s.bySource.length ? bars(s.bySource.map((r) => ({ label: label(r.source), value: r.leads, won: r.won, rate: r.rate })), { fmt: (r) => `${r.value} · ${r.won} won` }) : '<p class="muted">No leads yet.</p>'}
        <p class="muted small">Leads per source and how many became customers.</p></div>
      <div class="card panel"><h3>Why leads are lost</h3>
        ${s.lostReasons.length ? bars(s.lostReasons.map((r) => ({ label: r.reason, value: r.count })), { red: true }) : '<p class="muted">No lost leads yet.</p>'}
        <p class="muted small">If one reason dominates, that is your next thing to fix.</p></div>
      <div class="card panel"><h3>Outreach per week (calls, messages, emails)</h3>
        <div class="spark" style="margin-top:22px">${(() => { const m = Math.max(1, ...s.activityByWeek.map((w) => w.count)); return s.activityByWeek.map((w) => `<div style="height:${Math.round((w.count / m) * 100)}%" title="Week ending ${w.weekEnding}"><span>${w.count}</span></div>`).join(''); })()}</div>
        <p class="muted small">Last 8 weeks. Consistency beats bursts.</p></div>
    </div>`;
}

function viewImport() {
  return `<div class="page-head"><h1>Import leads</h1></div>
    <div class="grid2">
      <div class="card panel">
        <h3>1. Paste or choose a CSV</h3>
        <div class="field"><label for="imp-file">CSV file</label><input type="file" id="imp-file" accept=".csv,text/csv"></div>
        <div class="field"><label for="imp-text">...or paste it here</label><textarea id="imp-text" rows="9" placeholder="name,phone,email,course,source&#10;Asha,9123456780,asha@example.com,MERN,instagram"></textarea></div>
        <div class="field"><label for="imp-pipe">Pipeline (for plain CSVs)</label><select id="imp-pipe">${Object.values(pipes()).map((p) => `<option value="${p.key}">${esc(p.name)}</option>`).join('')}</select></div>
        <div class="chips"><button class="btn" data-action="import" data-dry="1">Preview</button><button class="btn primary" data-action="import">Import</button>
          <button class="btn" data-action="template">${icon('download')}Template</button></div>
        <div id="imp-result" style="margin-top:14px"></div>
      </div>
      <div class="card panel">
        <h3>What it understands</h3>
        <p><b>Leads-agent files</b> (<code>out/leads-YYYY-MM-DD.csv</code>) are detected automatically. They go to the Agency pipeline with city, state, niche, notes and the opportunity score filled in.</p>
        <p><b>Plain CSVs</b> need a header row. Recognised columns: <code>name</code>, <code>phone</code>, <code>whatsapp</code>, <code>email</code>, <code>city</code>, <code>state</code>, <code>country</code>, <code>source</code>, <code>course</code>, <code>business</code>, <code>website</code>, <code>mockup_url</code>, <code>niche</code>, <code>notes</code>.</p>
        <p>Duplicates (same phone, email or agent ID) are skipped, so re-importing a file is safe. Use <b>Preview</b> first to see what would happen.</p>
        <p class="muted small">Every imported lead gets its first next action automatically, so they all appear in Today.</p>
      </div></div>`;
}

const VIEWS = { today: viewToday, pipeline: viewPipeline, leads: viewLeads, dashboard: viewDashboard, import: viewImport };
async function render() {
  const view = (location.hash.replace(/^#\//, '') || 'today').split('/')[0];
  S.view = VIEWS[view] ? view : 'today';
  $$('[data-nav]').forEach((a) => a.classList.toggle('active', a.dataset.nav === S.view));
  renderSwitch();
  try {
    $('#view').innerHTML = await VIEWS[S.view]();
  } catch (e) {
    $('#view').innerHTML = `<div class="card empty">Could not load: ${esc(e.message)}</div>`;
  }
  if (S.view !== 'today') updateBadge();
}
async function updateBadge() {
  try {
    const t = await api('GET', '/today');
    $('#badge-today').textContent = t.overdue.length;
    $('#badge-today').hidden = !t.overdue.length;
  } catch { /* ignore */ }
}
async function refresh() {
  await render();
  if (S.openId) await openLead(S.openId, { keep: true });
}

// --------------------------------------------------------------- drawer
function typeButtons(current) {
  return S.cfg.activityTypes.map((t) => `<button type="button" class="pick ${t === current ? 'on' : ''}" data-action="log-type" data-type="${t}">${icon(t)} ${label(t)}</button>`).join('');
}
function nextFields(prefix, def = {}) {
  const d = def.at ? new Date(def.at) : chipDate('tomorrow');
  return `<div class="chips" style="margin-bottom:8px">
      ${[['later', 'In 3 hours'], ['tomorrow', 'Tomorrow'], ['d2', '2 days'], ['d3', '3 days'], ['w1', '1 week']].map(([k, t]) => `<button type="button" class="pick" data-action="chip" data-kind="${k}" data-target="${prefix}-at">${t}</button>`).join('')}</div>
    <div class="row">
      <div class="field"><label for="${prefix}-type">Next action</label><select id="${prefix}-type">${S.cfg.activityTypes.filter((t) => t !== 'note').map((t) => `<option value="${t}" ${t === (def.type || 'call') ? 'selected' : ''}>${label(t)}</option>`).join('')}</select></div>
      <div class="field"><label for="${prefix}-at">When</label><input type="datetime-local" id="${prefix}-at" value="${toLocalInput(d)}"></div>
    </div>
    <div class="field"><label for="${prefix}-note">What to do</label><input type="text" id="${prefix}-note" value="${esc(def.note || '')}" placeholder="e.g. Ask about budget"></div>`;
}
function readNext(prefix) {
  const raw = $(`#${prefix}-at`).value;
  const at = raw ? new Date(raw) : null;
  if (!at || Number.isNaN(at.getTime())) throw new Error('Pick when to follow up - every open lead needs a next action');
  return { type: $(`#${prefix}-type`).value, at: at.toISOString(), note: $(`#${prefix}-note`).value.trim() };
}

function detailsForm(l) {
  const adm = l.pipeline === 'admission';
  const f = (id, lab, val = '', type = 'text') => `<div class="field"><label for="d-${id}">${lab}</label><input type="${type}" id="d-${id}" value="${esc(val)}"></div>`;
  return `<details class="block"><summary>Details and notes</summary>
    <div class="row">${f('name', 'Name', l.name)}${f('business', 'Business', l.business)}</div>
    <div class="row">${f('phone', 'Phone', l.phone, 'tel')}${f('whatsapp', 'WhatsApp (if different)', l.whatsapp, 'tel')}</div>
    <div class="row">${f('email', 'Email', l.email, 'email')}${f('website', 'Website', l.website)}</div>
    ${l.pipeline === 'agency' ? f('mockupUrl', 'Design preview link', l.mockupUrl) : ''}
    <div class="row">${f('city', 'City', l.city)}${f('state', 'State', l.state)}${f('country', 'Country', l.country)}</div>
    <div class="row">${adm
    ? f('courseInterest', 'Course interest', l.courseInterest) + f('feeQuoted', 'Fee quoted (₹)', l.feeQuoted, 'number') + f('feeFinal', 'Fee agreed (₹)', l.feeFinal, 'number')
    : f('niche', 'Niche', l.niche) + f('dealValue', 'Deal value ($)', l.dealValue, 'number')}</div>
    <div class="field"><label for="d-source">Source</label><select id="d-source">${S.cfg.sources.map((s) => `<option value="${s}" ${l.source === s ? 'selected' : ''}>${label(s)}</option>`).join('')}</select></div>
    <div class="field"><label for="d-notes">Notes</label><textarea id="d-notes" rows="4">${esc(l.notes)}</textarea></div>
    <label style="display:flex;gap:8px;align-items:center;font-weight:500;color:var(--text)"><input type="checkbox" id="d-dnc" ${l.doNotContact ? 'checked' : ''} style="width:auto"> Do not contact${l.dncReason ? ` <span class="muted small">(${esc(l.dncReason)})</span>` : ''}</label>
    <div class="chips" style="margin-top:12px"><button class="btn primary" data-action="save-details" data-id="${l.id}">Save changes</button>
      <button class="btn danger" data-action="delete-lead" data-id="${l.id}">${icon('trash')}Delete lead</button></div>
    <div id="d-err" class="err"></div></details>`;
}

function renderDrawer({ lead: l, activities }, logType) {
  const p = pipes()[l.pipeline];
  const open = l.status === 'open';
  const ln = links(l);
  const tpls = S.cfg.templates.filter((t) => t.pipeline === l.pipeline);
  const w = l.callWindow;
  const win = w?.applies
    ? (w.allowed === null
      ? `<div class="banner info">${esc(w.reason)}</div>`
      : w.allowed
        ? `<div class="banner ok">${icon('clock')}<div>OK to call now. It is ${esc(w.localTime)} for them (${esc(w.rule)} rule).</div></div>`
        : `<div class="banner no">${icon('clock')}<div><b>Do not call now.</b> It is ${esc(w.localTime)} for them (${esc(w.rule)} rule).${w.opensAt ? ` Opens ${fmtAbs(w.opensAt)} your time.` : ''}</div></div>`)
    : '';
  const dnc = l.doNotContact;
  const disabled = dnc ? 'disabled' : '';
  const tl = activities.map((a) => `<div class="tl"><div class="ico">${icon(a.type)}</div><div>
      <div>${esc(a.summary || label(a.type))}${a.outcome ? ` <span class="chip">${esc(label(a.outcome))}</span>` : ''}${a.direction === 'in' && a.type !== 'note' ? ' <span class="chip blue">from them</span>' : ''}</div>
      <div class="t">${label(a.type)} · ${fmtAbs(a.at)} · ${rel(a.at)}</div></div></div>`).join('');
  const isNote = logType === 'note';

  $('#drawer').innerHTML = `
    <div class="d-head"><div class="grow"><h2>${esc(l.name)}</h2>
      <div class="muted">${l.business && l.business !== l.name ? esc(l.business) + ' · ' : ''}${esc(p.brand)}${l.city ? ' · ' + esc(l.city) + (l.state ? ', ' + esc(l.state) : '') : ''}</div></div>
      <button class="btn sm" data-action="close-drawer" aria-label="Close">${icon('x')}</button></div>
    <div class="d-body">
      <div class="chips">
        <span class="chip ${l.status === 'won' ? 'green' : l.status === 'lost' ? 'red' : 'blue'}">${esc(l.stageName)}</span>
        <span class="chip ${l.temperature}"><span class="dot ${l.temperature}"></span> ${label(l.temperature)} · ${l.score}</span>
        <span class="chip">${esc(label(l.source))}</span><span class="chip">${l.attemptCount} attempt${l.attemptCount === 1 ? '' : 's'}</span>
        ${l.rotting ? `<span class="chip amber">No contact for ${l.idleDays}d</span>` : ''}
        ${dnc ? '<span class="chip red">Do not contact</span>' : ''}
        ${l.lostReason ? `<span class="chip red">${esc(l.lostReason)}</span>` : ''}
      </div>
      <div class="field" style="margin:0"><label for="d-stage">Stage</label>
        <select id="d-stage" data-action="stage-change" data-id="${l.id}">${p.stages.map((s) => `<option value="${s.key}" ${s.key === l.stage ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></div>
      ${win}
      <div class="block"><h3>Contact</h3>
        <div class="chips">
          ${ln.call ? `<a id="lk-call" class="btn ${disabled}" href="${esc(ln.call)}" data-action="log-type" data-type="call">${icon('call')}${esc(l.phone)}</a>` : ''}
          ${ln.whatsapp ? `<a id="lk-whatsapp" class="btn ${disabled}" target="_blank" rel="noopener" href="${esc(ln.whatsapp)}" data-action="log-type" data-type="whatsapp">${icon('whatsapp')}WhatsApp</a>` : ''}
          ${ln.email ? `<a id="lk-email" class="btn ${disabled}" href="${esc(ln.email)}" data-action="log-type" data-type="email">${icon('email')}${esc(l.email)}</a>` : ''}
          ${l.website ? `<a class="btn" target="_blank" rel="noopener" href="${esc(/^https?:/.test(l.website) ? l.website : 'https://' + l.website)}">${icon('linkedin')}Website</a>` : ''}
        </div>
        ${tpls.length ? `<div class="field" style="margin:10px 0 0"><label for="tpl">Message template</label>
          <select id="tpl" data-action="tpl" data-id="${l.id}">${tpls.map((t) => `<option value="${t.id}" ${l.mockupUrl && t.body.includes('{{mockup}}') ? 'selected' : ''}>${label(t.channel)}: ${esc(t.name)}</option>`).join('')}</select></div>` : ''}
        ${dnc ? '<p class="err">Outbound contact is blocked for this lead.</p>' : ''}
      </div>
      ${l.pipeline === 'agency' && l.mockupUrl ? `<div class="block"><h3>Design preview</h3>
        <p class="small" style="margin:0 0 8px;word-break:break-all"><a target="_blank" rel="noopener" href="${esc(l.mockupUrl)}">${esc(l.mockupUrl)}</a></p>
        <div class="chips">
          <a class="btn" target="_blank" rel="noopener" href="${esc(l.mockupUrl)}">Open preview</a>
          <button class="btn" data-action="copy-mockup" data-url="${esc(l.mockupUrl)}">Copy link</button>
          ${l.mockupSentAt ? `<span class="chip green">Sent ${fmtAbs(l.mockupSentAt)}</span>` : (dnc ? '' : `<button class="btn" data-action="mockup-sent" data-id="${l.id}">Log as sent</button>`)}
        </div>
        ${l.mockupSentAt ? '' : '<p class="muted small" style="margin:8px 0 0">Not sent yet. Use the email button above; the Email with design preview template includes this link.</p>'}
      </div>` : ''}
      ${open ? `<div class="block"><h3>Next action</h3>
        ${l.nextActionAt ? `<div class="next" style="margin:0 0 8px">${icon(l.nextActionType || 'call')}<b>${esc(l.nextActionNote || label(l.nextActionType))}</b>
          <span class="${l.overdue ? 'due-over' : ''}">${l.overdue ? 'Overdue · ' : ''}${rel(l.nextActionAt)}</span><span class="muted small">${fmtAbs(l.nextActionAt)}</span></div>` : '<p class="err">No next action set.</p>'}
        <details><summary class="muted small" style="cursor:pointer">Change next action</summary><div style="margin-top:10px">${nextFields('ne', { type: l.nextActionType, at: l.nextActionAt, note: l.nextActionNote })}
          <button class="btn sm" data-action="save-next" data-id="${l.id}">Save next action</button></div></details></div>` : ''}
      <div class="block"><h3>Log what happened</h3>
        <form id="log-form" data-id="${l.id}" autocomplete="off">
          <div class="chips" id="log-types" style="margin-bottom:10px">${typeButtons(logType)}</div>
          <div class="row">
            <div class="field"><label for="lg-outcome">Outcome</label><select id="lg-outcome"><option value="">-</option>${S.cfg.outcomes.map((o) => `<option value="${o}">${label(o)}</option>`).join('')}</select></div>
            <div class="field"><label>&nbsp;</label><label style="display:flex;gap:6px;align-items:center;font-weight:500;color:var(--text);margin:8px 0 0"><input type="checkbox" id="lg-in" style="width:auto"> They contacted me</label></div>
          </div>
          <div class="field"><label for="lg-summary">Notes</label><textarea id="lg-summary" rows="3" placeholder="What did they say? Budget, objections, decision maker..."></textarea></div>
          <div id="lg-next" ${!open || isNote ? 'hidden' : ''}>
            <h3 style="margin:4px 0 8px">Set the next step</h3>${nextFields('lg', {})}
          </div>
          <div class="chips"><button class="btn primary" type="submit">${icon('check')}Save</button></div>
          <div id="lg-err" class="err"></div>
        </form></div>
      ${detailsForm(l)}
      <div><h3 style="margin-bottom:10px">Timeline</h3><div class="timeline">${tl}</div></div>
    </div>`;
}

async function openLead(id, { log, keep } = {}) {
  try {
    const detail = await api('GET', `/leads/${id}`);
    S.openId = id;
    if (log) S.logType = log;
    else if (!keep) S.logType = detail.lead.nextActionType && detail.lead.nextActionType !== 'demo' ? detail.lead.nextActionType : 'call';
    const top = $('#drawer').scrollTop;
    renderDrawer(detail, S.logType);
    if (keep) $('#drawer').scrollTop = top;
    $('#drawer').classList.add('open');
    $('#drawer').setAttribute('aria-hidden', 'false');
    $('#scrim').hidden = false;
  } catch (e) { toast(e.message, true); }
}
function closeDrawer() {
  S.openId = null;
  $('#drawer').classList.remove('open');
  $('#drawer').setAttribute('aria-hidden', 'true');
  $('#scrim').hidden = true;
}

// --------------------------------------------------------------- modals
function modal(title, body, foot) {
  const m = $('#modal');
  m.innerHTML = `<div class="m-head"><h2>${title}</h2><button class="btn sm" data-action="close-modal" aria-label="Close">${icon('x')}</button></div>
    <div class="m-body">${body}</div>${foot ? `<div class="m-foot">${foot}</div>` : ''}`;
  if (!m.open) m.showModal();
  return m;
}
const closeModal = () => { const m = $('#modal'); if (m.open) m.close(); };

function newLeadModal(defPipeline) {
  const start = defPipeline || (S.pipeline === 'all' ? 'admission' : S.pipeline);
  const src = (sel) => S.cfg.sources.map((s) => `<option value="${s}" ${s === sel ? 'selected' : ''}>${label(s)}</option>`).join('');
  const m = modal('New lead', `<form id="nl" autocomplete="off">
    <div class="seg" style="margin-bottom:14px">${Object.values(pipes()).map((p) => `<button type="button" class="${p.key === start ? 'on' : ''}" data-action="nl-pipe" data-key="${p.key}">${esc(p.name)}</button>`).join('')}</div>
    <input type="hidden" id="nl-pipeline" value="${start}">
    <div class="row"><div class="field"><label for="nl-name">Name *</label><input type="text" id="nl-name" required></div>
      <div class="field"><label for="nl-phone">Phone / WhatsApp</label><input type="tel" id="nl-phone" placeholder="98xxxxxx10"></div></div>
    <div class="row"><div class="field"><label for="nl-email">Email</label><input type="email" id="nl-email"></div>
      <div class="field"><label for="nl-source">Source</label><select id="nl-source">${src(start === 'admission' ? 'walk_in' : 'cold_email')}</select></div></div>
    <div id="nl-adm" class="${start === 'admission' ? '' : 'hidden'}"><div class="field"><label for="nl-course">Course interest</label>
      <select id="nl-course"><option value="">-</option><option>MERN Stack</option><option>Data Analytics</option><option>Other</option></select></div></div>
    <div id="nl-agy" class="${start === 'agency' ? '' : 'hidden'}">
      <div class="row"><div class="field"><label for="nl-business">Business name</label><input type="text" id="nl-business"></div>
        <div class="field"><label for="nl-niche">Niche</label><input type="text" id="nl-niche" placeholder="driving school"></div></div>
      <div class="row"><div class="field"><label for="nl-city">City</label><input type="text" id="nl-city"></div>
        <div class="field"><label for="nl-state">State (e.g. SC)</label><input type="text" id="nl-state" maxlength="2" style="text-transform:uppercase"></div>
        <div class="field"><label for="nl-country">Country</label><select id="nl-country">${['US', 'UK', 'CA', 'AU', 'AE', 'IN'].map((c) => `<option>${c}</option>`).join('')}</select></div></div>
      <div class="field"><label for="nl-website">Website</label><input type="text" id="nl-website"></div></div>
    <div class="field"><label for="nl-notes">Notes</label><textarea id="nl-notes" rows="2"></textarea></div>
    <div id="nl-err" class="err"></div>
    <p class="muted small">Only a name plus one contact method is required. The first call is scheduled automatically.</p></form>`,
  `<button class="btn" data-action="close-modal">Cancel</button><button class="btn primary" data-action="nl-save">Add lead</button>`);
  setTimeout(() => $('#nl-name', m).focus(), 30);
  $('#nl', m).addEventListener('submit', (e) => { e.preventDefault(); saveNewLead(); });
}
async function saveNewLead(force = false) {
  const v = (id) => ($('#' + id)?.value || '').trim();
  const pipeline = v('nl-pipeline');
  const body = {
    pipeline, name: v('nl-name'), phone: v('nl-phone'), email: v('nl-email'), source: v('nl-source'), notes: v('nl-notes'),
    ...(pipeline === 'admission'
      ? { courseInterest: v('nl-course') }
      : { business: v('nl-business'), niche: v('nl-niche'), city: v('nl-city'), state: v('nl-state'), country: v('nl-country'), website: v('nl-website') }),
  };
  if (pipeline === 'agency' && body.business && !body.name) body.name = body.business;
  try {
    const l = await api('POST', `/leads${force ? '?force=1' : ''}`, body);
    closeModal();
    toast(`Added ${l.name}. First action is due ${rel(l.nextActionAt)}.`);
    await refresh();
  } catch (e) {
    $('#nl-err').innerHTML = `${esc(e.message)}${e.data?.duplicateOf ? ` <button type="button" class="btn sm" data-action="open-dup" data-id="${e.data.duplicateOf}">Open existing</button> <button type="button" class="btn sm" data-action="nl-force">Add anyway</button>` : ''}`;
  }
}
function lostModal(l) {
  const p = pipes()[l.pipeline];
  modal(`Why was ${esc(l.name)} lost?`, `<div class="field"><label for="lost-reason">Reason *</label>
    <select id="lost-reason">${p.lostReasons.map((r) => `<option>${esc(r)}</option>`).join('')}</select></div>
    <div class="field"><label for="lost-note">Note (optional)</label><input type="text" id="lost-note"></div><div id="lost-err" class="err"></div>`,
  `<button class="btn" data-action="cancel-move">Cancel</button><button class="btn primary" data-action="confirm-lost" data-id="${l.id}">Mark as lost</button>`);
}
function wonModal(l) {
  const adm = l.pipeline === 'admission';
  modal(`${esc(l.name)} - ${adm ? 'enrolled' : 'won'}`, `<div class="field"><label for="won-val">${adm ? 'Fee agreed (₹)' : 'Deal value ($)'}</label>
    <input type="number" id="won-val" min="0" value="${(adm ? l.feeFinal ?? l.feeQuoted : l.dealValue) ?? ''}"></div><div id="won-err" class="err"></div>`,
  `<button class="btn" data-action="cancel-move">Cancel</button><button class="btn primary" data-action="confirm-won" data-id="${l.id}">Confirm</button>`);
}
async function doMove(id, body) {
  try {
    await api('POST', `/leads/${id}/move`, body);
    closeModal();
    toast('Moved');
    await refresh();
  } catch (e) { toast(e.message, true); await refresh(); }
}

// -------------------------------------------------------------- actions
const ACTIONS = {
  pipeline(el) { S.pipeline = el.dataset.key; store.set('pipeline', S.pipeline); render(); },
  'new-lead': () => newLeadModal(),
  'nl-pipe'(el) {
    $$('[data-action="nl-pipe"]').forEach((b) => b.classList.toggle('on', b === el));
    const k = el.dataset.key;
    $('#nl-pipeline').value = k;
    $('#nl-adm').classList.toggle('hidden', k !== 'admission');
    $('#nl-agy').classList.toggle('hidden', k !== 'agency');
    $('#nl-source').value = k === 'admission' ? 'walk_in' : 'cold_email';
  },
  'nl-save': () => saveNewLead(),
  'nl-force': () => saveNewLead(true),
  'open-dup'(el) { closeModal(); openLead(Number(el.dataset.id)); },
  open(el) { openLead(Number(el.dataset.id), { log: el.dataset.log }); },
  async 'copy-mockup'(el) {
    try { await navigator.clipboard.writeText(el.dataset.url); toast('Link copied'); }
    catch { toast('Could not copy - select the link and copy it', true); }
  },
  'mockup-sent'(el) {
    // Pre-fill the log form as an email that carries the link; saving it stamps the sent date.
    el.closest('.drawer, body').querySelector('#log-types [data-type="email"]')?.click();
    const s = $('#lg-summary');
    if (s) { s.value = `Sent design preview: ${$$('[data-action="copy-mockup"]')[0]?.dataset.url || ''}`; s.scrollIntoView({ block: 'center' }); s.focus(); }
  },
  'close-drawer': closeDrawer,
  'close-modal': closeModal,
  'cancel-move': () => { closeModal(); refresh(); },
  'log-type'(el) {
    S.logType = el.dataset.type;
    $$('#log-types .pick').forEach((b) => b.classList.toggle('on', b.dataset.type === S.logType));
    const n = $('#lg-next');
    if (n) n.hidden = S.logType === 'note' || n.dataset.closed === '1';
    const nt = $('#lg-type');
    if (nt && S.logType !== 'note') nt.value = ['call', 'whatsapp', 'email'].includes(S.logType) ? S.logType : 'call';
  },
  chip(el) { $('#' + el.dataset.target).value = toLocalInput(chipDate(el.dataset.kind)); },
  async 'stage-change'(el) {
    const id = Number(el.dataset.id);
    const stage = el.value;
    const { lead } = await api('GET', `/leads/${id}`);
    const st = pipes()[lead.pipeline].stages.find((s) => s.key === stage);
    if (st.terminal === 'lost') return lostModal(lead);
    if (st.terminal === 'won') return wonModal(lead);
    doMove(id, { stage });
  },
  'confirm-lost'(el) { doMove(Number(el.dataset.id), { stage: 'lost', lostReason: $('#lost-reason').value, lostNote: $('#lost-note').value.trim() }); },
  'confirm-won'(el) {
    const val = $('#won-val').value;
    doMove(Number(el.dataset.id), { stage: 'won', ...(val !== '' ? { feeFinal: Number(val), dealValue: Number(val) } : {}) });
  },
  async 'save-next'(el) {
    try {
      await api('PATCH', `/leads/${el.dataset.id}`, { next: readNext('ne') });
      toast('Next action updated');
      refresh();
    } catch (e) { toast(e.message, true); }
  },
  async 'save-details'(el) {
    const v = (id) => $('#d-' + id)?.value;
    const num = (id) => (v(id) === undefined || v(id) === '' ? null : Number(v(id)));
    const l = (await api('GET', `/leads/${el.dataset.id}`)).lead;
    const body = {
      name: v('name'), business: v('business'), phone: v('phone'), whatsapp: v('whatsapp'), email: v('email'),
      website: v('website'), ...(l.pipeline === 'agency' ? { mockupUrl: v('mockupUrl') } : {}), city: v('city'), state: v('state'), country: v('country') || l.country, source: v('source'), notes: v('notes'),
      ...(l.pipeline === 'admission'
        ? { courseInterest: v('courseInterest'), feeQuoted: num('feeQuoted'), feeFinal: num('feeFinal') }
        : { niche: v('niche'), dealValue: num('dealValue') }),
    };
    if ($('#d-dnc').checked !== l.doNotContact) body.doNotContact = $('#d-dnc').checked;
    try { await api('PATCH', `/leads/${el.dataset.id}`, body); toast('Saved'); refresh(); }
    catch (e) { $('#d-err').textContent = e.message; }
  },
  async 'delete-lead'(el) {
    if (!confirm('Delete this lead and its history? This cannot be undone.')) return;
    await api('DELETE', `/leads/${el.dataset.id}`);
    closeDrawer(); toast('Deleted'); render();
  },
  tpl(el) {
    api('GET', `/leads/${el.dataset.id}`).then(({ lead }) => {
      const ln = links(lead, el.value);
      if (ln.whatsapp && $('#lk-whatsapp')) $('#lk-whatsapp').href = ln.whatsapp;
      if (ln.email && $('#lk-email')) $('#lk-email').href = ln.email;
    });
  },
  async import(el) {
    const text = $('#imp-text').value.trim();
    if (!text) return toast('Paste a CSV or choose a file first', true);
    const dry = el.dataset.dry === '1';
    try {
      const r = await api('POST', `/import?pipeline=${$('#imp-pipe').value}${dry ? '&dryRun=1' : ''}`, text);
      $('#imp-result').innerHTML = `<div class="banner ${r.invalid.length ? 'info' : 'ok'}"><div><b>${dry ? 'Preview' : 'Imported'}:</b> ${r.created} ${dry ? 'would be added' : 'added'},
        ${r.duplicates} duplicate${r.duplicates === 1 ? '' : 's'} skipped, ${r.invalid.length} invalid. <span class="muted">(${esc(r.format)} format, ${r.total} rows)</span></div></div>
        ${r.invalid.length ? `<pre class="mono">${r.invalid.slice(0, 8).map((i) => `Row ${i.row}: ${esc(i.error)}`).join('\n')}</pre>` : ''}
        ${dry && r.sample.length ? `<p class="small muted">First rows: ${r.sample.map((s) => esc(s.name)).join(', ')}</p>` : ''}`;
      if (!dry) { toast(`${r.created} lead(s) imported`); updateBadge(); }
    } catch (e) { toast(e.message, true); }
  },
  template() {
    const blob = new Blob(['name,phone,email,course,source,city,notes\nAsha Singh,9123456780,asha@example.com,Data Analytics,instagram,Gurugram,Asked about weekend batch\n'], { type: 'text/csv' });
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'webigeeks-leads-template.csv' });
    a.click(); URL.revokeObjectURL(a.href);
  },
};

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const fn = ACTIONS[el.dataset.action];
  if (!fn) return;
  if (el.tagName === 'SELECT') return; // handled on change
  // links (tel:/wa.me/mailto:) keep their default behaviour; we only open the log drawer alongside
  if (el.tagName !== 'A') e.preventDefault();
  if (el.dataset.action === 'open' && e.target.closest('a, button') && e.target.closest('a, button') !== el) return;
  fn(el, e);
  if (el.tagName === 'A' && el.dataset.action === 'open') e.stopPropagation();
});
document.addEventListener('change', (e) => {
  const el = e.target;
  if (el.tagName === 'SELECT' && el.dataset.action) ACTIONS[el.dataset.action]?.(el, e);
  if (el.id === 'f-status') { S.filters.status = el.value; render(); }
  if (el.id === 'f-source') { S.filters.source = el.value; render(); }
  if (el.id === 'lg-outcome') {
    const n = $('#lg-next');
    if (n) { n.dataset.closed = el.value === 'opted_out' ? '1' : ''; n.hidden = el.value === 'opted_out' || S.logType === 'note'; }
  }
  if (el.id === 'imp-file' && el.files[0]) el.files[0].text().then((t) => { $('#imp-text').value = t; });
});
let searchTimer;
document.addEventListener('input', (e) => {
  if (e.target.id !== 'f-q') return;
  clearTimeout(searchTimer);
  const val = e.target.value;
  searchTimer = setTimeout(async () => {
    S.filters.q = val;
    await render();
    const i = $('#f-q'); if (i) { i.focus(); i.setSelectionRange(val.length, val.length); }
  }, 250);
});
document.addEventListener('submit', async (e) => {
  if (e.target.id !== 'log-form') return;
  e.preventDefault();
  const id = Number(e.target.dataset.id);
  const nextEl = $('#lg-next');
  const body = {
    type: S.logType,
    direction: $('#lg-in').checked ? 'in' : 'out',
    outcome: $('#lg-outcome').value || undefined,
    summary: $('#lg-summary').value.trim() || undefined,
  };
  try {
    if (nextEl && !nextEl.hidden) body.next = readNext('lg');
    const r = await api('POST', `/leads/${id}/activities`, body);
    toast('Logged');
    if (r.suggestLost) toast('6+ attempts and no reply. Consider marking this lead lost.');
    S.logType = 'call';
    await refresh();
    $('#drawer').scrollTop = 0;
  } catch (err) { $('#lg-err').textContent = err.message; }
});
document.addEventListener('keydown', (e) => {
  const tag = (e.target.tagName || '').toLowerCase();
  if (e.key === 'Escape' && !$('#modal').open && S.openId) closeDrawer();
  if (e.key.toLowerCase() === 'n' && !e.metaKey && !e.ctrlKey && !['input', 'textarea', 'select'].includes(tag) && !$('#modal').open) {
    e.preventDefault(); newLeadModal();
  }
});

// drag and drop (pipeline board)
let dragId = null;
document.addEventListener('dragstart', (e) => {
  const c = e.target.closest?.('.kcard');
  if (!c) return;
  dragId = Number(c.dataset.id);
  c.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', String(dragId));
});
document.addEventListener('dragend', () => { $$('.dragging').forEach((c) => c.classList.remove('dragging')); $$('.col.over').forEach((c) => c.classList.remove('over')); });
document.addEventListener('dragover', (e) => {
  const col = e.target.closest?.('.col');
  if (!col || dragId == null) return;
  e.preventDefault();
  $$('.col.over').forEach((c) => c !== col && c.classList.remove('over'));
  col.classList.add('over');
});
document.addEventListener('drop', async (e) => {
  const col = e.target.closest?.('.col');
  if (!col || dragId == null) return;
  e.preventDefault();
  col.classList.remove('over');
  const id = dragId; dragId = null;
  const stage = col.dataset.stage;
  const { lead } = await api('GET', `/leads/${id}`);
  if (lead.stage === stage) return;
  const st = pipes()[lead.pipeline].stages.find((s) => s.key === stage);
  if (st.terminal === 'lost') return lostModal(lead);
  if (st.terminal === 'won') return wonModal(lead);
  doMove(id, { stage });
});

window.addEventListener('hashchange', () => { closeDrawer(); render(); });
(async function init() {
  try {
    S.cfg = await api('GET', '/config');
  } catch (e) {
    $('#view').innerHTML = `<div class="card empty">Could not reach the server: ${esc(e.message)}</div>`;
    return;
  }
  if (!location.hash) location.hash = '#/today';
  render();
})();
