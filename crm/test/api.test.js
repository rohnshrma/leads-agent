import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { openDb } from '../db.js';
import { createApp } from '../app.js';
import { callWindow } from '../lib/compliance.js';
import { parseCsv, normalizePhone } from '../lib/util.js';

let server;
let base;
const call = async (method, url, body, headers = {}) => {
  const res = await fetch(base + url, {
    method,
    headers: typeof body === 'string' ? { 'content-type': 'text/csv', ...headers } : { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* not json */ }
  return { status: res.status, json, text };
};
const inDays = (d) => new Date(Date.now() + d * 864e5).toISOString();

before(async () => {
  const app = createApp(openDb(':memory:'), { password: null });
  await new Promise((r) => { server = app.listen(0, '127.0.0.1', r); });
  base = `http://127.0.0.1:${server.address().port}/api`;
});
after(() => server.close());

test('create lead: defaults to first stage with an immediate call, normalises phone', async () => {
  const r = await call('POST', '/leads', { name: 'Aman Verma', phone: '98765 43210', source: 'walk_in', courseInterest: 'MERN' });
  assert.equal(r.status, 201);
  assert.equal(r.json.phone, '+919876543210');
  assert.equal(r.json.stage, 'new');
  assert.equal(r.json.nextActionType, 'call');
  assert.ok(r.json.nextActionAt);
  assert.equal(r.json.timezone, 'Asia/Kolkata');
});

test('validation: name and a contact method are required', async () => {
  assert.equal((await call('POST', '/leads', { phone: '9876500000' })).status, 400);
  assert.equal((await call('POST', '/leads', { name: 'No contact' })).status, 400);
  assert.equal((await call('POST', '/leads', { name: 'X', phone: '1', source: 'nope' })).status, 400);
});

test('duplicate phone is rejected with a pointer to the existing lead', async () => {
  const r = await call('POST', '/leads', { name: 'Aman again', phone: '+91 9876543210' });
  assert.equal(r.status, 409);
  assert.ok(r.json.duplicateOf);
});

test('logging a call REQUIRES a next action; then updates counters', async () => {
  const { json: lead } = await call('POST', '/leads', { name: 'Neha', phone: '9811122233' });
  const bad = await call('POST', `/leads/${lead.id}/activities`, { type: 'call', outcome: 'no_answer' });
  assert.equal(bad.status, 400);
  assert.match(bad.json.error, /next action/i);

  const ok = await call('POST', `/leads/${lead.id}/activities`, {
    type: 'call', outcome: 'no_answer', next: { type: 'whatsapp', at: inDays(1), note: 'Ping on WhatsApp' },
  });
  assert.equal(ok.status, 201);
  assert.equal(ok.json.lead.attemptCount, 1);
  assert.ok(ok.json.lead.firstContactAt);
  assert.equal(ok.json.lead.nextActionType, 'whatsapp');
});

test('moving stage schedules the stage default next action; lost needs a valid reason', async () => {
  const { json: lead } = await call('POST', '/leads', { name: 'Rahul', phone: '9000011111' });
  const moved = await call('POST', `/leads/${lead.id}/move`, { stage: 'counselled' });
  assert.equal(moved.json.stage, 'counselled');
  assert.equal(moved.json.status, 'open');
  assert.ok(moved.json.nextActionAt);

  assert.equal((await call('POST', `/leads/${lead.id}/move`, { stage: 'lost' })).status, 400);
  assert.equal((await call('POST', `/leads/${lead.id}/move`, { stage: 'lost', lostReason: 'made up' })).status, 400);
  const lost = await call('POST', `/leads/${lead.id}/move`, { stage: 'lost', lostReason: 'Fee too high' });
  assert.equal(lost.json.status, 'lost');
  assert.equal(lost.json.nextActionAt, null);

  const won = await call('POST', '/leads', { name: 'Simran', phone: '9000022222' });
  const w = await call('POST', `/leads/${won.json.id}/move`, { stage: 'won', feeFinal: 15000 });
  assert.equal(w.json.status, 'won');
  assert.equal(w.json.feeFinal, 15000);
});

test('opt-out blocks outbound contact and closes the lead as lost', async () => {
  const { json: lead } = await call('POST', '/leads', {
    name: 'Mike Driving School', pipeline: 'agency', phone: '(864) 555-0142', state: 'SC', email: 'mike@example.com',
  });
  assert.equal(lead.phone, '+18645550142');
  assert.equal(lead.timezone, 'America/New_York');
  const r = await call('POST', `/leads/${lead.id}/activities`, {
    type: 'call', outcome: 'opted_out', summary: 'Said stop calling',
  });
  assert.equal(r.status, 201);
  assert.equal(r.json.lead.doNotContact, true);
  assert.equal(r.json.lead.status, 'lost');
  const blocked = await call('POST', `/leads/${lead.id}/activities`, {
    type: 'email', next: { at: inDays(1) },
  });
  assert.equal(blocked.status, 409);
});

test('call window: Boise/Greenville/Huntsville and state overrides', () => {
  const at = (iso) => new Date(iso);
  // 15:00 UTC on a Tuesday = 11:00 in New York, 09:00 in Boise
  const tue = at('2026-09-29T15:00:00Z');
  assert.equal(callWindow({ country: 'US', state: 'SC' }, tue).allowed, true);
  assert.equal(callWindow({ country: 'US', state: 'ID' }, tue).allowed, true);
  // 03:00 UTC = 23:00 in New York -> closed, and we know when it reopens
  const night = at('2026-09-30T03:00:00Z');
  const w = callWindow({ country: 'US', state: 'SC' }, night);
  assert.equal(w.allowed, false);
  assert.ok(w.opensAt);
  // 01:30 UTC = 20:30 CDT in Huntsville: federal window open, but AL/FL/LA cut off at 8pm
  const evening = at('2026-09-30T01:30:00Z');
  assert.equal(callWindow({ country: 'US', state: 'AL' }, evening).allowed, false);
  assert.equal(callWindow({ country: 'US', state: 'MN' }, evening).allowed, true);
  // Rhode Island: no weekend calls
  assert.equal(callWindow({ country: 'US', state: 'RI' }, at('2026-09-26T16:00:00Z')).allowed, false);
  // Texas Sunday: not before noon local
  assert.equal(callWindow({ country: 'US', state: 'TX' }, at('2026-09-27T15:00:00Z')).allowed, false);
  assert.equal(callWindow({ country: 'US', state: 'TX' }, at('2026-09-27T18:00:00Z')).allowed, true);
  assert.equal(callWindow({ country: 'IN', state: '' }, tue).applies, false);
  assert.equal(callWindow({ country: 'US', state: '' }, tue).allowed, null);
});

test('today queue groups overdue and untouched leads', async () => {
  const { json: lead } = await call('POST', '/leads', { name: 'Old task', phone: '9555500001' });
  await call('PATCH', `/leads/${lead.id}`, { next: { type: 'call', at: inDays(-2), note: 'late' } });
  const t = await call('GET', `/today?endOfDay=${encodeURIComponent(inDays(0.5))}`);
  assert.ok(t.json.overdue.some((l) => l.id === lead.id));
  assert.equal(t.json.noNextAction, 0);
});

test('a brand-new lead is "due now", not overdue; 30 minutes late is overdue', async () => {
  const { json: lead } = await call('POST', '/leads', { name: 'Fresh Lead', phone: '9555500077' });
  assert.equal(lead.overdue, false);
  const t = await call('GET', `/today?endOfDay=${encodeURIComponent(inDays(0.5))}`);
  assert.ok(t.json.dueToday.some((l) => l.id === lead.id));
  assert.ok(!t.json.overdue.some((l) => l.id === lead.id));
  const late = await call('PATCH', `/leads/${lead.id}`, { next: { type: 'call', at: new Date(Date.now() - 30 * 60000).toISOString() } });
  assert.equal(late.json.overdue, true);
});

test('CSV import: generic format, dedupe and dry run', async () => {
  const csv = 'Name,Mobile,Email,Course,Source\nAsha,9123456780,asha@x.com,Data Analytics,Instagram\nAman Verma,9876543210,,MERN,walk_in\nBad Row,,,,\n';
  const dry = await call('POST', '/import?pipeline=admission&dryRun=1', csv);
  assert.equal(dry.json.created, 1);
  assert.equal(dry.json.duplicates, 1);
  assert.equal(dry.json.invalid.length, 1);
  const real = await call('POST', '/import?pipeline=admission', csv);
  assert.equal(real.json.created, 1);
  const again = await call('POST', '/import?pipeline=admission', csv);
  assert.equal(again.json.created, 0);
});

test('CSV import: leads-agent format lands in the agency pipeline with state + score', async () => {
  const csv = 'source,source_id,name,category,address,city_query,niche_query,phone,website,rating,review_count,email,opportunity_score,reasons,lead_type,maps_url\n'
    + 'osm,n123,"Palmetto Driving Academy",driving_school,"12 Main St, Greenville, SC 29601",Greenville SC,driving school,(864) 555-0100,,4.6,31,,82,"No website | Few reviews",no_website,https://maps.example/x\n';
  const r = await call('POST', '/import', csv);
  assert.equal(r.json.format, 'leads-agent');
  assert.equal(r.json.created, 1);
  const list = await call('GET', '/leads?pipeline=agency&q=palmetto');
  const l = list.json[0];
  assert.equal(l.state, 'SC');
  assert.equal(l.city, 'Greenville');
  assert.equal(l.source, 'leads_agent');
  assert.equal(l.stage, 'prospect');
  assert.ok(l.score > 0);
  assert.match(l.notes, /No website/);
});

test('search matches by name and by phone digits, and does not match everything', async () => {
  const byName = await call('GET', '/leads?q=aman');
  assert.ok(byName.json.length >= 1 && byName.json.every((l) => /aman/i.test(l.name)));
  const byPhone = await call('GET', '/leads?q=98765');
  assert.ok(byPhone.json.some((l) => l.phone.includes('98765')));
  const none = await call('GET', '/leads?q=zzzznothing');
  assert.equal(none.json.length, 0);
  const total = (await call('GET', '/leads')).json.length;
  const one = await call('GET', '/leads?q=palmetto');
  assert.ok(one.json.length >= 1 && one.json.length < total);
});

test('stats: funnel, sources, lost reasons', async () => {
  const s = await call('GET', '/stats?pipeline=admission');
  assert.ok(s.json.total >= 4);
  assert.equal(s.json.won, 1);
  assert.ok(s.json.lostReasons.some((x) => x.reason === 'Fee too high'));
  assert.ok(s.json.funnel[0].reached >= 4);
  assert.equal(s.json.wonValueTotal, 15000);
  const all = await call('GET', '/stats');
  assert.equal(all.json.funnel, null);
});

test('export.csv and helpers', async () => {
  const r = await call('GET', '/export.csv');
  assert.equal(r.status, 200);
  assert.match(r.text.split('\n')[0], /^id,name,/);
  assert.deepEqual(parseCsv('a,b\n"x, y","he said ""hi"""\n'), [{ a: 'x, y', b: 'he said "hi"' }]);
  assert.equal(normalizePhone('07123456789', 'IN'), '+917123456789');
});

test('password protection when configured', async () => {
  const guarded = createApp(openDb(':memory:'), { password: 'secret' });
  const s = await new Promise((r) => { const x = guarded.listen(0, '127.0.0.1', () => r(x)); });
  const url = `http://127.0.0.1:${s.address().port}/api/config`;
  assert.equal((await fetch(url)).status, 401);
  const good = 'Basic ' + Buffer.from('rohan:secret').toString('base64');
  assert.equal((await fetch(url, { headers: { authorization: good } })).status, 200);
  s.close();
});

test('design preview link: imported from the agent CSV, validated, stamped as sent when logged', async () => {
  const url = 'https://demo.webigeeksdigital.com/acme-dental-abc123/';
  const csv = 'source,source_id,name,category,address,city_query,niche_query,phone,website,email,opportunity_score,reasons,lead_type,maps_url,mockup_path,mockup_url\n'
    + `osm,node/777,Acme Dental,dentist,"1 Main St, Omaha, NE 68102, USA",Omaha,dental clinic,(402) 555-0100,,hi@acme.test,70,No website,NO WEBSITE,,x,${url}\n`;
  const imp = await call('POST', '/import', csv);
  assert.equal(imp.json.created, 1);
  const list = await call('GET', '/leads?pipeline=agency');
  const lead = (list.json.leads || list.json).find((l) => l.name === 'Acme Dental');
  assert.equal(lead.mockupUrl, url);
  assert.equal(lead.mockupSentAt, null);

  const bad = await call('PATCH', `/leads/${lead.id}`, { mockupUrl: 'javascript:alert(1)' });
  assert.equal(bad.status, 400);

  // a note that mentions the link is not a send
  await call('POST', `/leads/${lead.id}/activities`, { type: 'note', summary: `Prepared ${url}` });
  assert.equal((await call('GET', `/leads/${lead.id}`)).json.lead.mockupSentAt, null);

  const sent = await call('POST', `/leads/${lead.id}/activities`, {
    type: 'email', summary: `Sent design preview: ${url}`,
    next: { type: 'call', at: inDays(3), note: 'Ask what they thought of the preview' },
  });
  assert.equal(sent.status, 201);
  const after = (await call('GET', `/leads/${lead.id}`)).json.lead;
  assert.ok(after.mockupSentAt);
  assert.equal(after.mockupUrl, url);
});
