import {
  PIPELINES, SOURCES, ACTIVITY_TYPES, TOUCH_TYPES, OUTCOMES, SOURCE_WEIGHT,
} from './config.js';
import { callWindow, timezoneFor } from './lib/compliance.js';
import {
  HttpError, normalizePhone, digits, snake, rowToObj, median, parseCsv,
} from './lib/util.js';

const nowIso = () => new Date().toISOString();
// A follow-up only counts as overdue once it is this far past due, so a lead
// that was just added (or a batch import) is "due now", not an alarm.
const GRACE_MS = 15 * 60000;
const isOverdue = (l, now = Date.now()) => !!(l.nextActionAt && Date.parse(l.nextActionAt) < now - GRACE_MS);
const isIso = (s) => typeof s === 'string' && !Number.isNaN(Date.parse(s));

// Fields a client may set directly (stage/status/counters are managed by the service).
const EDITABLE = [
  'name', 'business', 'phone', 'whatsapp', 'email', 'city', 'state', 'country', 'timezone',
  'source', 'sourceDetail', 'courseInterest', 'feeQuoted', 'feeFinal', 'dealValue',
  'website', 'mockupUrl', 'niche', 'notes', 'temperature',
];
const INT_FIELDS = new Set(['feeQuoted', 'feeFinal', 'dealValue']);

export function createService(db) {
  const q = (sql, params = {}) => db.prepare(sql).all(params).map(rowToObj);
  const one = (sql, params = {}) => rowToObj(db.prepare(sql).get(params));
  const run = (sql, params = {}) => db.prepare(sql).run(params);

  // ---------------------------------------------------------------- helpers
  function pipelineOf(key) {
    const p = PIPELINES[key];
    if (!p) throw new HttpError(400, `Unknown pipeline "${key}"`);
    return p;
  }
  function stageOf(pipeline, key) {
    const s = pipelineOf(pipeline).stages.find((x) => x.key === key);
    if (!s) throw new HttpError(400, `Unknown stage "${key}" for ${pipeline}`);
    return s;
  }
  function defaultNext(stage, from = new Date()) {
    if (!stage.next) return null;
    return {
      type: stage.next.type,
      at: new Date(from.getTime() + stage.next.afterHours * 3600e3).toISOString(),
      note: stage.next.note,
    };
  }
  function validNext(n) {
    if (!n || typeof n !== 'object' || !isIso(n.at)) {
      throw new HttpError(400, 'A next action with a due date is required');
    }
    if (n.type && !ACTIVITY_TYPES.includes(n.type)) throw new HttpError(400, `Bad next action type "${n.type}"`);
    return { type: n.type || 'call', at: new Date(n.at).toISOString(), note: n.note || '' };
  }

  function computeScore(lead, inbound = 0, agentScore = null) {
    const p = pipelineOf(lead.pipeline);
    const openStages = p.stages.filter((s) => !s.terminal);
    const idx = Math.max(0, openStages.findIndex((s) => s.key === lead.stage));
    let score = SOURCE_WEIGHT[lead.source] ?? 5;
    if (lead.source === 'leads_agent' && agentScore != null) score = Math.min(40, Math.round(agentScore * 0.4));
    score += idx * 9;
    if (inbound > 0) score += 15;
    if (lead.feeQuoted || lead.dealValue) score += 8;
    if (lead.attemptCount >= 4 && inbound === 0) score -= 8;
    score = Math.max(0, Math.min(100, score));
    return { score, temperature: score >= 55 ? 'hot' : score >= 30 ? 'warm' : 'cold' };
  }

  function rescore(id) {
    const lead = one('SELECT * FROM leads WHERE id=$id', { id });
    if (!lead) return;
    const inbound = one("SELECT count(*) c FROM activities WHERE lead_id=$id AND direction='in' AND type!='note'", { id }).c;
    const { score, temperature } = computeScore(lead, inbound, lead.agentScore);
    run('UPDATE leads SET score=$score, temperature=$temperature WHERE id=$id', { id, score, temperature });
  }

  function enrich(lead) {
    if (!lead) return lead;
    const p = PIPELINES[lead.pipeline];
    const st = p?.stages.find((s) => s.key === lead.stage);
    const ref = lead.lastContactAt || lead.createdAt;
    const idleDays = Math.floor((Date.now() - Date.parse(ref)) / 864e5);
    const open = lead.status === 'open';
    return {
      ...lead,
      doNotContact: !!lead.doNotContact,
      stageName: st?.name || lead.stage,
      idleDays,
      rotting: !!(open && st?.rotDays && idleDays >= st.rotDays),
      overdue: open && isOverdue(lead),
      callWindow: callWindow(lead),
    };
  }

  function findDuplicate({ phone, whatsapp, email, externalId }, exceptId = null) {
    const conds = [];
    const params = {};
    if (externalId) { conds.push('external_id=$externalId'); params.externalId = externalId; }
    if (phone) { conds.push('phone=$phone OR whatsapp=$phone'); params.phone = phone; }
    if (whatsapp) { conds.push('phone=$whatsapp OR whatsapp=$whatsapp'); params.whatsapp = whatsapp; }
    if (email) { conds.push('lower(email)=$email'); params.email = email.toLowerCase(); }
    if (!conds.length) return null;
    let sql = `SELECT id, name, stage, status FROM leads WHERE (${conds.join(' OR ')})`;
    if (exceptId) { sql += ' AND id != $exceptId'; params.exceptId = exceptId; }
    return one(sql + ' LIMIT 1', params);
  }

  function addHistory(leadId, from, to, at) {
    run('INSERT INTO stage_history (lead_id, from_stage, to_stage, at) VALUES ($leadId,$from,$to,$at)',
      { leadId, from, to, at });
  }
  function addActivity(leadId, a) {
    run(`INSERT INTO activities (lead_id, type, direction, outcome, summary, at)
         VALUES ($leadId,$type,$direction,$outcome,$summary,$at)`, {
      leadId, type: a.type, direction: a.direction || 'out',
      outcome: a.outcome || null, summary: a.summary || null, at: a.at || nowIso(),
    });
  }

  // ----------------------------------------------------------------- leads
  function getLead(id) {
    const lead = one('SELECT * FROM leads WHERE id=$id', { id });
    if (!lead) throw new HttpError(404, 'Lead not found');
    return lead;
  }

  function cleanFields(input, country) {
    const out = {};
    for (const k of EDITABLE) {
      if (input[k] === undefined) continue;
      let v = input[k];
      if (typeof v === 'string') v = v.trim();
      if (v === '') v = null;
      if (INT_FIELDS.has(k) && v != null) {
        v = Math.round(Number(v));
        if (Number.isNaN(v) || v < 0) throw new HttpError(400, `${k} must be a positive number`);
      }
      out[k] = v;
    }
    if (out.phone) out.phone = normalizePhone(out.phone, country);
    if (out.whatsapp) out.whatsapp = normalizePhone(out.whatsapp, country);
    if (out.email) out.email = out.email.toLowerCase();
    if (out.mockupUrl && !/^https?:\/\/\S+$/i.test(out.mockupUrl)) throw new HttpError(400, 'Design preview link must start with http:// or https://');
    if (out.state && country === 'US') out.state = out.state.toUpperCase();
    if (out.source && !SOURCES.includes(out.source)) throw new HttpError(400, `Unknown source "${out.source}"`);
    return out;
  }

  function createLead(input, { force = false } = {}) {
    const pipeline = input.pipeline || 'admission';
    const p = pipelineOf(pipeline);
    const country = input.country || p.defaultCountry;
    const f = cleanFields({ ...input, country }, country);
    if (!f.name) throw new HttpError(400, 'Name is required');
    if (!f.phone && !f.whatsapp && !f.email) throw new HttpError(400, 'Add a phone, WhatsApp or email');
    f.country = country;
    f.timezone = f.timezone || timezoneFor({ country, state: f.state }) || null;
    f.source = f.source || 'other';

    const externalId = input.externalId || null;
    if (!force) {
      const dup = findDuplicate({ phone: f.phone, whatsapp: f.whatsapp, email: f.email, externalId });
      if (dup) throw new HttpError(409, `Already in the CRM as "${dup.name}"`, { duplicateOf: dup.id });
    }

    const first = p.stages[0];
    const t = nowIso();
    const next = input.next ? validNext(input.next) : defaultNext(first);
    const row = {
      ...f, pipeline, stage: first.key, status: 'open', externalId,
      agentScore: input.agentScore != null ? Number(input.agentScore) : null,
      nextActionType: next.type, nextActionAt: next.at, nextActionNote: next.note,
      stageEnteredAt: t, createdAt: t, updatedAt: t,
      attemptCount: 0, doNotContact: 0, score: 0, temperature: 'cold',
    };
    const cols = Object.keys(row).filter((k) => row[k] !== undefined);
    const info = run(
      `INSERT INTO leads (${cols.map(snake).join(',')}) VALUES (${cols.map((c) => '$' + c).join(',')})`,
      Object.fromEntries(cols.map((c) => [c, row[c] ?? null])),
    );
    const id = Number(info.lastInsertRowid);
    addHistory(id, null, first.key, t);
    addActivity(id, { type: 'note', direction: 'in', summary: `Lead added (${f.source})`, at: t });
    rescore(id);
    return enrich(getLead(id));
  }

  function updateLead(id, input) {
    const lead = getLead(id);
    const country = input.country || lead.country;
    const f = cleanFields(input, country);
    if ('name' in f && !f.name) throw new HttpError(400, 'Name cannot be empty');

    const merged = { ...lead, ...f };
    if (!merged.phone && !merged.whatsapp && !merged.email) throw new HttpError(400, 'Keep at least one of phone, WhatsApp or email');
    const dup = findDuplicate({ phone: f.phone, whatsapp: f.whatsapp, email: f.email }, id);
    if (dup) throw new HttpError(409, `Already in the CRM as "${dup.name}"`, { duplicateOf: dup.id });

    if (('state' in f || 'country' in f) && !('timezone' in f)) {
      f.timezone = timezoneFor({ country: merged.country, state: merged.state }) || merged.timezone;
    }
    const sets = { ...f };
    if ('doNotContact' in input) {
      sets.doNotContact = input.doNotContact ? 1 : 0;
      sets.dncReason = input.doNotContact ? (input.dncReason || 'Marked manually') : null;
      sets.optOutAt = input.doNotContact ? nowIso() : null;
    }
    if (input.next !== undefined) {
      if (lead.status !== 'open') throw new HttpError(400, 'Only open leads have a next action');
      const n = validNext(input.next);
      sets.nextActionType = n.type; sets.nextActionAt = n.at; sets.nextActionNote = n.note;
    }
    sets.updatedAt = nowIso();
    const cols = Object.keys(sets);
    run(`UPDATE leads SET ${cols.map((c) => `${snake(c)}=$${c}`).join(',')} WHERE id=$id`,
      { id, ...Object.fromEntries(cols.map((c) => [c, sets[c] ?? null])) });
    rescore(id);
    return enrich(getLead(id));
  }

  function moveLead(id, { stage, lostReason, lostNote, next, feeFinal, dealValue } = {}) {
    const lead = getLead(id);
    const p = pipelineOf(lead.pipeline);
    const target = stageOf(lead.pipeline, stage);
    const t = nowIso();
    const sets = { stage: target.key, stageEnteredAt: t, updatedAt: t };

    if (target.terminal === 'lost') {
      if (!lostReason || !p.lostReasons.includes(lostReason)) {
        throw new HttpError(400, 'Pick a lost reason', { lostReasons: p.lostReasons });
      }
      Object.assign(sets, {
        status: 'lost', lostReason, lostNote: lostNote || null,
        nextActionType: null, nextActionAt: null, nextActionNote: null,
      });
    } else if (target.terminal === 'won') {
      Object.assign(sets, {
        status: 'won', wonAt: t, lostReason: null, lostNote: null,
        nextActionType: null, nextActionAt: null, nextActionNote: null,
      });
      if (feeFinal != null) sets.feeFinal = Math.round(Number(feeFinal));
      if (dealValue != null) sets.dealValue = Math.round(Number(dealValue));
    } else {
      const n = next ? validNext(next) : defaultNext(target);
      Object.assign(sets, {
        status: 'open', lostReason: null, lostNote: null, wonAt: null,
        nextActionType: n.type, nextActionAt: n.at, nextActionNote: n.note,
      });
    }
    if (target.key === lead.stage && lead.status === 'open' && !target.terminal) {
      return enrich(lead); // dropped on the same column - nothing to do
    }
    const cols = Object.keys(sets);
    run(`UPDATE leads SET ${cols.map((c) => `${snake(c)}=$${c}`).join(',')} WHERE id=$id`,
      { id, ...Object.fromEntries(cols.map((c) => [c, sets[c] ?? null])) });
    addHistory(id, lead.stage, target.key, t);
    addActivity(id, {
      type: 'note', direction: 'in', at: t,
      summary: target.terminal === 'lost'
        ? `Marked lost: ${lostReason}${lostNote ? ' - ' + lostNote : ''}`
        : `Moved ${stageOf(lead.pipeline, lead.stage).name} → ${target.name}`,
    });
    rescore(id);
    return enrich(getLead(id));
  }

  function logActivity(id, input) {
    const lead = getLead(id);
    const type = input.type;
    if (!ACTIVITY_TYPES.includes(type)) throw new HttpError(400, `Unknown activity type "${type}"`);
    const direction = input.direction === 'in' ? 'in' : 'out';
    if (input.outcome && !OUTCOMES.includes(input.outcome)) throw new HttpError(400, `Unknown outcome "${input.outcome}"`);
    const isTouch = TOUCH_TYPES.includes(type);
    const at = isIso(input.at) ? new Date(input.at).toISOString() : nowIso();
    const optedOut = input.outcome === 'opted_out';

    if (lead.doNotContact && direction === 'out' && isTouch) {
      throw new HttpError(409, 'This lead is marked Do Not Contact - outbound contact is blocked');
    }
    // The core rule: an open lead is never left without a next action.
    let next = null;
    if (lead.status === 'open' && isTouch && !optedOut) next = validNext(input.next);

    addActivity(id, { type, direction, outcome: input.outcome, summary: input.summary, at });

    const sets = { updatedAt: nowIso() };
    // Sending the design preview link (email, WhatsApp, SMS, LinkedIn or a demo) records when it went out.
    if (isTouch && direction === 'out' && lead.mockupUrl && !lead.mockupSentAt
        && String(input.summary || '').includes(lead.mockupUrl)) sets.mockupSentAt = at;
    if (isTouch) {
      sets.lastContactAt = at;
      if (!lead.firstContactAt) sets.firstContactAt = at;
      if (direction === 'out') sets.attemptCount = (lead.attemptCount || 0) + 1;
    }
    if (next) Object.assign(sets, { nextActionType: next.type, nextActionAt: next.at, nextActionNote: next.note });
    const cols = Object.keys(sets);
    run(`UPDATE leads SET ${cols.map((c) => `${snake(c)}=$${c}`).join(',')} WHERE id=$id`,
      { id, ...Object.fromEntries(cols.map((c) => [c, sets[c] ?? null])) });

    if (optedOut) {
      run('UPDATE leads SET do_not_contact=1, dnc_reason=$r, opt_out_at=$t WHERE id=$id',
        { id, r: 'Asked not to be contacted', t: nowIso() });
      if (lead.status === 'open') {
        moveLead(id, { stage: 'lost', lostReason: 'Opted out (do not contact)', lostNote: input.summary });
      }
    }
    rescore(id);
    const updated = enrich(getLead(id));
    const inbound = one("SELECT count(*) c FROM activities WHERE lead_id=$id AND direction='in' AND type!='note'", { id }).c;
    return { lead: updated, suggestLost: updated.status === 'open' && updated.attemptCount >= 6 && inbound === 0 };
  }

  function deleteLead(id) {
    getLead(id);
    run('DELETE FROM leads WHERE id=$id', { id });
  }

  function listLeads({ pipeline, status, stage, source, q: search, limit = 1000 } = {}) {
    const conds = [];
    const params = { limit: Math.min(Number(limit) || 1000, 5000) };
    if (pipeline && pipeline !== 'all') { conds.push('pipeline=$pipeline'); params.pipeline = pipeline; }
    if (status && status !== 'all') { conds.push('status=$status'); params.status = status; }
    if (stage) { conds.push('stage=$stage'); params.stage = stage; }
    if (source) { conds.push('source=$source'); params.source = source; }
    if (search) {
      const parts = ["lower(name) LIKE $s", "lower(coalesce(business,'')) LIKE $s",
        "lower(coalesce(email,'')) LIKE $s", "lower(coalesce(city,'')) LIKE $s"];
      params.s = `%${String(search).toLowerCase()}%`;
      const d = digits(search);
      if (d) { parts.push('phone LIKE $phoneDigits'); params.phoneDigits = `%${d}%`; }
      conds.push(`(${parts.join(' OR ')})`);
    }
    const where = conds.length ? 'WHERE ' + conds.join(' AND ') : '';
    return q(`SELECT * FROM leads ${where} ORDER BY updated_at DESC LIMIT $limit`, params).map(enrich);
  }

  function leadDetail(id) {
    const lead = enrich(getLead(id));
    const activities = q('SELECT * FROM activities WHERE lead_id=$id ORDER BY at DESC, id DESC', { id });
    return { lead, activities };
  }

  // ----------------------------------------------------------------- today
  function today({ endOfDay } = {}) {
    const now = Date.now();
    const end = isIso(endOfDay) ? Date.parse(endOfDay) : now + 864e5;
    const open = q("SELECT * FROM leads WHERE status='open'").map(enrich);
    // untouched inbound leads are the most valuable to call fast (speed-to-lead)
    const rank = (l) => (l.attemptCount === 0 && l.source !== 'leads_agent' ? 1000 : 0) + (l.score || 0);
    const byRank = (a, b) => rank(b) - rank(a) || Date.parse(a.nextActionAt) - Date.parse(b.nextActionAt);
    const overdue = open.filter((l) => isOverdue(l, now)).sort(byRank);
    const dueToday = open.filter((l) => l.nextActionAt && !isOverdue(l, now)
      && Date.parse(l.nextActionAt) <= end).sort(byRank);
    const listed = new Set([...overdue, ...dueToday].map((l) => l.id));
    const untouched = open.filter((l) => l.attemptCount === 0 && !listed.has(l.id)).sort(byRank);
    const upcoming = open.filter((l) => !listed.has(l.id) && l.attemptCount > 0
      && l.nextActionAt && Date.parse(l.nextActionAt) > end).length;
    const noNextAction = open.filter((l) => !l.nextActionAt).length;
    return { overdue, dueToday, untouched, upcoming, noNextAction, openTotal: open.length };
  }

  // ----------------------------------------------------------------- stats
  function stats({ pipeline } = {}) {
    const key = pipeline && pipeline !== 'all' ? pipeline : null;
    const leads = q(`SELECT * FROM leads ${key ? 'WHERE pipeline=$p' : ''}`, key ? { p: key } : {});
    const ids = new Set(leads.map((l) => l.id));
    const history = q('SELECT * FROM stage_history').filter((h) => ids.has(h.leadId));
    const acts = q("SELECT * FROM activities WHERE type!='note' OR direction='out'").filter((a) => ids.has(a.leadId));

    const now = Date.now();
    const total = leads.length;
    const won = leads.filter((l) => l.status === 'won');
    const lost = leads.filter((l) => l.status === 'lost');
    const open = leads.filter((l) => l.status === 'open');
    const monthStart = new Date(); monthStart.setUTCDate(1); monthStart.setUTCHours(0, 0, 0, 0);
    const wonThisMonth = won.filter((l) => l.wonAt && Date.parse(l.wonAt) >= monthStart.getTime());
    const valueOf = (l) => (l.pipeline === 'admission' ? l.feeFinal : l.dealValue) || 0;

    // funnel: how many leads ever reached each stage
    const stageKeys = key
      ? PIPELINES[key].stages.filter((s) => !s.terminal).map((s) => s.key)
      : null;
    const reached = {};
    for (const h of history) {
      (reached[h.toStage] ||= new Set()).add(h.leadId);
    }
    const funnel = key
      ? stageKeys.map((k, i) => {
        const n = reached[k]?.size || 0;
        const prev = i ? reached[stageKeys[i - 1]]?.size || 0 : null;
        return { key: k, name: PIPELINES[key].stages[i].name, reached: n, fromPrev: prev ? Math.round((n / prev) * 100) : null };
      })
      : null;
    const currentByStage = {};
    for (const l of open) currentByStage[l.stage] = (currentByStage[l.stage] || 0) + 1;

    const bySourceMap = {};
    for (const l of leads) {
      const s = (bySourceMap[l.source || 'other'] ||= { source: l.source || 'other', leads: 0, won: 0, lost: 0, open: 0 });
      s.leads++; s[l.status]++;
    }
    const bySource = Object.values(bySourceMap)
      .map((s) => ({ ...s, rate: s.leads ? Math.round((s.won / s.leads) * 100) : 0 }))
      .sort((a, b) => b.leads - a.leads);

    const lostReasons = {};
    for (const l of lost) lostReasons[l.lostReason || 'Unknown'] = (lostReasons[l.lostReason || 'Unknown'] || 0) + 1;

    const firstContactMins = leads
      .filter((l) => l.firstContactAt)
      .map((l) => (Date.parse(l.firstContactAt) - Date.parse(l.createdAt)) / 60000)
      .filter((m) => m >= 0);

    // activity volume for the last 8 weeks (touches only)
    const weeks = [];
    for (let i = 7; i >= 0; i--) {
      const to = now - i * 7 * 864e5;
      const from = to - 7 * 864e5;
      weeks.push({
        weekEnding: new Date(to).toISOString().slice(0, 10),
        count: acts.filter((a) => TOUCH_TYPES.includes(a.type) && Date.parse(a.at) > from && Date.parse(a.at) <= to).length,
      });
    }

    const scheduled = reached.demo_scheduled?.size || 0;
    const attended = reached.demo_attended?.size || 0;
    const mean = (xs) => (xs.length ? +(xs.reduce((a, b) => a + b, 0) / xs.length).toFixed(1) : null);

    return {
      pipeline: key || 'all',
      total, open: open.length, won: won.length, lost: lost.length,
      winRate: total ? Math.round((won.length / total) * 100) : 0,
      closedWinRate: won.length + lost.length ? Math.round((won.length / (won.length + lost.length)) * 100) : 0,
      wonThisMonth: wonThisMonth.length,
      wonValueThisMonth: wonThisMonth.reduce((a, l) => a + valueOf(l), 0),
      wonValueTotal: won.reduce((a, l) => a + valueOf(l), 0),
      openPipelineValue: open.reduce((a, l) => a + ((l.pipeline === 'admission' ? l.feeQuoted : l.dealValue) || 0), 0),
      overdue: open.filter((l) => isOverdue(l, now)).length,
      noNextAction: open.filter((l) => !l.nextActionAt).length,
      rotting: open.map(enrich).filter((l) => l.rotting).length,
      untouched: open.filter((l) => !l.attemptCount).length,
      medianFirstContactMinutes: firstContactMins.length ? Math.round(median(firstContactMins)) : null,
      avgAttemptsWon: mean(won.map((l) => l.attemptCount || 0)),
      avgAttemptsLost: mean(lost.map((l) => l.attemptCount || 0)),
      demoShowRate: key === 'admission' || !key ? (scheduled ? Math.round((attended / scheduled) * 100) : null) : null,
      funnel, currentByStage, bySource,
      lostReasons: Object.entries(lostReasons).map(([reason, count]) => ({ reason, count })).sort((a, b) => b.count - a.count),
      activityByWeek: weeks,
    };
  }

  // ---------------------------------------------------------------- import
  const ALIASES = {
    name: ['name', 'full name', 'contact', 'contact name', 'student name'],
    business: ['business', 'company', 'business name', 'company name'],
    phone: ['phone', 'mobile', 'phone number', 'mobile number', 'contact number'],
    whatsapp: ['whatsapp', 'whatsapp number'],
    email: ['email', 'email address', 'e-mail'],
    city: ['city'], state: ['state'], country: ['country'],
    source: ['source', 'lead source'],
    courseInterest: ['course', 'course interest', 'course_interest', 'interested in'],
    website: ['website', 'url', 'site'],
    mockupUrl: ['mockup_url', 'mockup', 'preview link', 'design preview'],
    niche: ['niche', 'category', 'industry'],
    notes: ['notes', 'note', 'remarks', 'comment', 'comments'],
    pipeline: ['pipeline'],
  };

  function mapAgentRow(r) {
    // CSV written by leadagent/report.py (Business.as_row)
    const address = r.address || '';
    const m = address.match(/,\s*([^,]+),\s*([A-Z]{2})\s*\d{5}/);
    let city = m?.[1] || '';
    let state = m?.[2] || '';
    if (!state && r.city_query) {
      const c = r.city_query.match(/^(.*?),\s*([A-Z]{2})\b/);
      if (c) { city = city || c[1].trim(); state = c[2]; }
      else city = city || r.city_query;
    }
    const notes = [
      r.lead_type && `Lead type: ${r.lead_type}`,
      r.reasons && `Why: ${r.reasons}`,
      r.site_verdict && `Site: ${r.site_verdict}`,
      r.rating && `Google rating: ${r.rating} (${r.review_count || 0} reviews)`,
      r.maps_url,
    ].filter(Boolean).join('\n');
    return {
      pipeline: 'agency', country: 'US', name: r.name, business: r.name,
      phone: r.phone, email: r.email, website: r.website, mockupUrl: r.mockup_url || null, city, state,
      niche: r.niche_query || r.category, source: 'leads_agent',
      sourceDetail: r.city_query, externalId: r.source_id, notes,
      agentScore: Number(r.opportunity_score) || 0,
    };
  }

  function mapGenericRow(r, defaults) {
    const lower = Object.fromEntries(Object.entries(r).map(([k, v]) => [k.toLowerCase().trim(), v]));
    const out = { ...defaults };
    for (const [field, names] of Object.entries(ALIASES)) {
      const hit = names.find((n) => lower[n]);
      if (hit) out[field] = lower[hit];
    }
    if (out.source) out.source = out.source.toLowerCase().replace(/\s+/g, '_');
    if (out.source && !SOURCES.includes(out.source)) { out.sourceDetail = out.source; out.source = 'other'; }
    return out;
  }

  function importRows(text, { pipeline = 'admission', dryRun = false } = {}) {
    const rows = parseCsv(text);
    if (!rows.length) throw new HttpError(400, 'No rows found. The first line must be the column headers.');
    const isAgent = 'source_id' in rows[0] && 'opportunity_score' in rows[0];
    const result = { format: isAgent ? 'leads-agent' : 'generic', total: rows.length, created: 0, duplicates: 0, invalid: [], sample: [] };
    const seen = new Set();
    rows.forEach((r, i) => {
      const input = isAgent ? mapAgentRow(r) : mapGenericRow(r, { pipeline });
      try {
        // detect duplicates inside the file itself as well as against the DB
        const country = input.country || PIPELINES[input.pipeline || pipeline].defaultCountry;
        const keys = [input.externalId, normalizePhone(input.phone, country), (input.email || '').toLowerCase()].filter(Boolean);
        if (keys.some((k) => seen.has(k))) { result.duplicates++; return; }
        keys.forEach((k) => seen.add(k));
        if (dryRun) {
          if (!input.name) throw new HttpError(400, 'Name is required');
          if (!input.phone && !input.whatsapp && !input.email) throw new HttpError(400, 'Add a phone, WhatsApp or email');
          if (findDuplicate({ phone: normalizePhone(input.phone, country), email: input.email, externalId: input.externalId })) {
            result.duplicates++;
          } else {
            result.created++;
            if (result.sample.length < 5) result.sample.push({ name: input.name, phone: input.phone, city: input.city, state: input.state });
          }
        } else {
          createLead(input);
          result.created++;
        }
      } catch (e) {
        if (e instanceof HttpError && e.status === 409) result.duplicates++;
        else result.invalid.push({ row: i + 2, error: e.message });
      }
    });
    return result;
  }

  return {
    createLead, updateLead, moveLead, logActivity, deleteLead, listLeads, leadDetail,
    today, stats, importRows, enrich, getLead,
  };
}
