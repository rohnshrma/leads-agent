import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

const SCHEMA = `
CREATE TABLE IF NOT EXISTS leads (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT NOT NULL,
  business          TEXT,
  phone             TEXT,
  whatsapp          TEXT,
  email             TEXT,
  city              TEXT,
  state             TEXT,
  country           TEXT,
  timezone          TEXT,
  pipeline          TEXT NOT NULL,
  stage             TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'open',   -- open | won | lost
  source            TEXT DEFAULT 'other',
  source_detail     TEXT,
  external_id       TEXT,                            -- e.g. place id from the leads agent
  course_interest   TEXT,
  fee_quoted        INTEGER,
  fee_final         INTEGER,
  deal_value        INTEGER,
  website           TEXT,
  mockup_url        TEXT,                            -- free design preview link (demo.webigeeksdigital.com/...)
  mockup_sent_at    TEXT,
  niche             TEXT,
  score             INTEGER DEFAULT 0,
  agent_score       INTEGER,                         -- opportunity score from the leads agent
  temperature       TEXT DEFAULT 'cold',
  next_action_type  TEXT,
  next_action_at    TEXT,
  next_action_note  TEXT,
  do_not_contact    INTEGER DEFAULT 0,
  dnc_reason        TEXT,
  opt_out_at        TEXT,
  attempt_count     INTEGER DEFAULT 0,
  first_contact_at  TEXT,
  last_contact_at   TEXT,
  stage_entered_at  TEXT,
  lost_reason       TEXT,
  lost_note         TEXT,
  won_at            TEXT,
  notes             TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_pipeline ON leads(pipeline, status);
CREATE INDEX IF NOT EXISTS idx_leads_next ON leads(status, next_action_at);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_ext ON leads(external_id);

CREATE TABLE IF NOT EXISTS activities (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id    INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  type       TEXT NOT NULL,
  direction  TEXT DEFAULT 'out',
  outcome    TEXT,
  summary    TEXT,
  at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_act_lead ON activities(lead_id, at);

CREATE TABLE IF NOT EXISTS stage_history (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id    INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  from_stage TEXT,
  to_stage   TEXT NOT NULL,
  at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hist_lead ON stage_history(lead_id);
`;

export function openDb(file = process.env.CRM_DB || path.join(here, 'data', 'crm.db')) {
  if (file !== ':memory:') fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
  db.exec(SCHEMA);
  // Databases created before the design-preview feature need the new columns.
  const have = new Set(db.prepare('PRAGMA table_info(leads)').all().map((c) => c.name));
  for (const col of ['mockup_url', 'mockup_sent_at']) {
    if (!have.has(col)) db.exec(`ALTER TABLE leads ADD COLUMN ${col} TEXT`);
  }
  return db;
}
