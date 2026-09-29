# WebiGeeks CRM

One small CRM for both businesses: **Admissions** (WebiGeeks) and **Agency outreach** (WebiGeeks Digital).
Node 22+, built-in SQLite, no paid services, no build step.

    cd crm
    npm install
    npm start          # http://localhost:4000
    npm test

Data lives in `crm/data/crm.db` (git-ignored). Back it up with **Leads > Export CSV**.

## How it works
- Every open lead always has ONE next action with a due date. Logging a call/message/email forces you to set the next one.
- **Today** is the daily work queue: overdue, due today, and new leads not yet contacted.
- **Pipeline** boards: drag cards between stages; the CRM schedules the stage's default next action.
- Losing a lead requires a reason from a fixed list, so the Dashboard shows why leads are lost.
- US leads show the recipient's local time and block/warn outside calling hours (8am-9pm, plus FL/LA/AL/OK 8pm, RI 9-6 weekdays, TX Sunday noon). This is a safety net, not legal advice.
- "They asked not to be contacted" marks the lead Do Not Contact, closes it, and blocks further outbound logging.
- **Import**: drop in `out/leads-YYYY-MM-DD.csv` from the leads agent (auto-detected) or any CSV with a header row. Duplicates are skipped.

## Customise
Stages, lost reasons, follow-up timings and message templates are all in `config.js`.

## Settings (environment variables)
| Variable | Default | Purpose |
|---|---|---|
| `PORT` | 4000 | Port |
| `HOST` | 127.0.0.1 | Set `0.0.0.0` only if hosting online |
| `CRM_PASSWORD` | none | Shared password (HTTP Basic). Set it whenever `HOST` is not local |
| `CRM_DB` | `crm/data/crm.db` | Database file |
