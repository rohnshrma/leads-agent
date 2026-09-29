import express from 'express';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createService } from './service.js';
import { PIPELINES, SOURCES, ACTIVITY_TYPES, OUTCOMES, TEMPLATES } from './config.js';
import { HttpError, toCsv } from './lib/util.js';

const here = path.dirname(fileURLToPath(import.meta.url));

function safeEqual(a, b) {
  const x = Buffer.from(String(a));
  const y = Buffer.from(String(b));
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

export function createApp(db, { password = process.env.CRM_PASSWORD } = {}) {
  const svc = createService(db);
  const app = express();
  app.disable('x-powered-by');
  app.use(express.json({ limit: '5mb' }));
  app.use(express.text({ type: ['text/csv', 'text/plain'], limit: '5mb' }));

  // Optional shared password (HTTP Basic). Set CRM_PASSWORD when hosting online.
  if (password) {
    app.use((req, res, next) => {
      const [scheme, token] = (req.headers.authorization || '').split(' ');
      if (scheme === 'Basic' && token) {
        const pass = Buffer.from(token, 'base64').toString().split(':').slice(1).join(':');
        if (safeEqual(pass, password)) return next();
      }
      res.set('WWW-Authenticate', 'Basic realm="WebiGeeks CRM"').status(401).send('Password required');
    });
  }

  const api = express.Router();
  const id = (req) => {
    const n = Number(req.params.id);
    if (!Number.isInteger(n)) throw new HttpError(400, 'Bad id');
    return n;
  };

  api.get('/config', (_req, res) => {
    res.json({ pipelines: PIPELINES, sources: SOURCES, activityTypes: ACTIVITY_TYPES, outcomes: OUTCOMES, templates: TEMPLATES });
  });

  api.get('/leads', (req, res) => res.json(svc.listLeads(req.query)));
  api.post('/leads', (req, res) => res.status(201).json(svc.createLead(req.body, { force: req.query.force === '1' })));
  api.get('/leads/:id', (req, res) => res.json(svc.leadDetail(id(req))));
  api.patch('/leads/:id', (req, res) => res.json(svc.updateLead(id(req), req.body)));
  api.delete('/leads/:id', (req, res) => { svc.deleteLead(id(req)); res.status(204).end(); });
  api.post('/leads/:id/move', (req, res) => res.json(svc.moveLead(id(req), req.body)));
  api.post('/leads/:id/activities', (req, res) => res.status(201).json(svc.logActivity(id(req), req.body)));

  api.get('/today', (req, res) => res.json(svc.today(req.query)));
  api.get('/stats', (req, res) => res.json(svc.stats(req.query)));

  // CSV in (text/csv body, or {csv} JSON). ?dryRun=1 previews without saving.
  api.post('/import', (req, res) => {
    const text = typeof req.body === 'string' ? req.body : req.body?.csv;
    res.json(svc.importRows(text, { pipeline: req.query.pipeline || 'admission', dryRun: req.query.dryRun === '1' }));
  });

  // Full backup as CSV
  api.get('/export.csv', (_req, res) => {
    const rows = svc.listLeads({ limit: 5000 });
    const cols = ['id', 'name', 'business', 'pipeline', 'stage', 'status', 'phone', 'whatsapp', 'email', 'city', 'state',
      'country', 'source', 'courseInterest', 'feeQuoted', 'feeFinal', 'dealValue', 'website', 'niche', 'score',
      'temperature', 'nextActionType', 'nextActionAt', 'nextActionNote', 'attemptCount', 'lastContactAt',
      'lostReason', 'doNotContact', 'notes', 'createdAt'];
    res.type('text/csv').set('Content-Disposition', 'attachment; filename="webigeeks-crm-leads.csv"')
      .send(toCsv(rows, cols));
  });

  api.use((_req, res) => res.status(404).json({ error: 'Not found' }));
  app.use('/api', api);
  app.use(express.static(path.join(here, 'public')));

  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    if (err instanceof HttpError) return res.status(err.status).json({ error: err.message, ...err.extra });
    if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'Invalid JSON' });
    console.error(err);
    res.status(500).json({ error: 'Something went wrong' });
  });
  return app;
}
