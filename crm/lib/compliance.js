// US calling-hours guard.
//
// Federal rule (TCPA): telemarketing calls only between 8am and 9pm in the
// RECIPIENT's local time. A few states are stricter. This is a safety net,
// not legal advice - always check current state law before calling.
//
// Overrides used here:
//   FL, LA  - end at 8pm (from research)
//   RI      - 9am-6pm, Monday-Friday only (from research)
//   TX      - Sundays start at noon (from research)
//   AL, OK  - end at 8pm as a PRECAUTION (not confirmed in research; a
//             stricter window can only cost minutes, never a violation)

export const STATE_TZ = {
  AL: 'America/Chicago', AK: 'America/Anchorage', AZ: 'America/Phoenix', AR: 'America/Chicago',
  CA: 'America/Los_Angeles', CO: 'America/Denver', CT: 'America/New_York', DE: 'America/New_York',
  DC: 'America/New_York', FL: 'America/New_York', GA: 'America/New_York', HI: 'Pacific/Honolulu',
  ID: 'America/Boise', IL: 'America/Chicago', IN: 'America/Indiana/Indianapolis', IA: 'America/Chicago',
  KS: 'America/Chicago', KY: 'America/New_York', LA: 'America/Chicago', ME: 'America/New_York',
  MD: 'America/New_York', MA: 'America/New_York', MI: 'America/Detroit', MN: 'America/Chicago',
  MS: 'America/Chicago', MO: 'America/Chicago', MT: 'America/Denver', NE: 'America/Chicago',
  NV: 'America/Los_Angeles', NH: 'America/New_York', NJ: 'America/New_York', NM: 'America/Denver',
  NY: 'America/New_York', NC: 'America/New_York', ND: 'America/Chicago', OH: 'America/New_York',
  OK: 'America/Chicago', OR: 'America/Los_Angeles', PA: 'America/New_York', RI: 'America/New_York',
  SC: 'America/New_York', SD: 'America/Chicago', TN: 'America/Chicago', TX: 'America/Chicago',
  UT: 'America/Denver', VT: 'America/New_York', VA: 'America/New_York', WA: 'America/Los_Angeles',
  WV: 'America/New_York', WI: 'America/Chicago', WY: 'America/Denver',
};

const DOW = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
const EARLY_END = new Set(['FL', 'LA', 'AL', 'OK']);

export function timezoneFor({ country, state, timezone }) {
  if (timezone) return timezone;
  if (country === 'US') return STATE_TZ[String(state || '').toUpperCase()] || '';
  if (country === 'UK' || country === 'GB') return 'Europe/London';
  if (country === 'IN') return 'Asia/Kolkata';
  return '';
}

function localParts(date, tz) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const get = (t) => parts.find((p) => p.type === t)?.value;
  const h = Number(get('hour')) % 24;
  const m = Number(get('minute'));
  return { dow: DOW[get('weekday')], minutes: h * 60 + m };
}

function windowFor(state, dow) {
  let start = 8 * 60;
  let end = 21 * 60;
  if (EARLY_END.has(state)) end = 20 * 60;
  if (state === 'RI') {
    if (dow === 0 || dow === 6) return null;
    start = 9 * 60;
    end = 18 * 60;
  }
  if (state === 'TX' && dow === 0) start = 12 * 60;
  return { start, end };
}

function allowedAt(date, tz, state) {
  const { dow, minutes } = localParts(date, tz);
  const w = windowFor(state, dow);
  return !!w && minutes >= w.start && minutes < w.end;
}

function fmtLocal(date, tz) {
  return new Intl.DateTimeFormat('en-US', {
    timeZone: tz, weekday: 'short', hour: 'numeric', minute: '2-digit',
  }).format(date);
}

/** Can we phone this lead right now? Only applies to US leads. */
export function callWindow(lead, now = new Date()) {
  if (lead.country !== 'US') return { applies: false };
  const state = String(lead.state || '').toUpperCase();
  const tz = timezoneFor(lead);
  if (!tz) return { applies: true, allowed: null, reason: 'Add a state or timezone to check calling hours' };

  const allowed = allowedAt(now, tz, state);
  const out = {
    applies: true, allowed, tz,
    localTime: fmtLocal(now, tz),
    rule: state === 'RI' ? '9am-6pm Mon-Fri' : EARLY_END.has(state) ? '8am-8pm' : '8am-9pm',
  };
  if (!allowed) {
    // find the next time calls are allowed (15-minute steps, up to 8 days)
    for (let i = 1; i <= 8 * 96; i++) {
      const t = new Date(now.getTime() + i * 15 * 60000);
      if (allowedAt(t, tz, state)) { out.opensAt = t.toISOString(); break; }
    }
    out.reason = `Outside calling hours (${out.rule} local time)`;
  }
  return out;
}
