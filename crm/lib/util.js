export const digits = (s) => String(s ?? '').replace(/\D/g, '');

/** Normalise a phone number to +<countrycode><number>. */
export function normalizePhone(raw, country = 'IN') {
  const text = String(raw ?? '').trim();
  const d = digits(text);
  if (!d) return '';
  if (text.startsWith('+')) return '+' + d;
  if (country === 'US') {
    if (d.length === 11 && d[0] === '1') return '+' + d;
    if (d.length === 10) return '+1' + d;
  } else if (country === 'IN') {
    if (d.length === 10) return '+91' + d;
    if (d.length === 12 && d.startsWith('91')) return '+' + d;
    if (d.length === 11 && d[0] === '0') return '+91' + d.slice(1);
  }
  return '+' + d;
}

export const snake = (s) => s.replace(/[A-Z]/g, (m) => '_' + m.toLowerCase());
export const camel = (s) => s.replace(/_([a-z0-9])/g, (_, c) => c.toUpperCase());
export const rowToObj = (r) =>
  r ? Object.fromEntries(Object.entries(r).map(([k, v]) => [camel(k), v])) : null;

export class HttpError extends Error {
  constructor(status, message, extra = {}) {
    super(message);
    this.status = status;
    this.extra = extra;
  }
}

/** Minimal RFC-4180 CSV parser (quotes, escaped quotes, CRLF, embedded newlines). */
export function parseCsv(text) {
  const rows = [];
  let row = [];
  let cur = '';
  let quoted = false;
  const src = String(text || '').replace(/^﻿/, '');
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (quoted) {
      if (c === '"') {
        if (src[i + 1] === '"') { cur += '"'; i++; } else quoted = false;
      } else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cur); cur = ''; }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && src[i + 1] === '\n') i++;
      row.push(cur); cur = '';
      if (row.some((x) => x !== '')) rows.push(row);
      row = [];
    } else cur += c;
  }
  row.push(cur);
  if (row.some((x) => x !== '')) rows.push(row);
  if (!rows.length) return [];
  const headers = rows[0].map((h) => h.trim());
  return rows.slice(1).map((r) => Object.fromEntries(headers.map((h, i) => [h, (r[i] ?? '').trim()])));
}

export function toCsv(rows, cols) {
  const esc = (v) => {
    const s = v == null ? '' : String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n');
}

export const median = (xs) => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
