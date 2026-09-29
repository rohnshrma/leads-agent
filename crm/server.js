import { openDb } from './db.js';
import { createApp } from './app.js';

const port = Number(process.env.PORT) || 4000;
// Local-only by default. Set HOST=0.0.0.0 (and CRM_PASSWORD) only when hosting online.
const host = process.env.HOST || '127.0.0.1';

const app = createApp(openDb());
app.listen(port, host, () => {
  console.log(`WebiGeeks CRM running at http://${host === '0.0.0.0' ? 'localhost' : host}:${port}`);
  if (host !== '127.0.0.1' && !process.env.CRM_PASSWORD) {
    console.warn('WARNING: exposed on the network without CRM_PASSWORD - set one.');
  }
});
