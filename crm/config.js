// Pipelines, sources and templates. Edit this file to change stages,
// lost reasons or message templates - no other code needs to change.
//
// Design rules (from the CRM research):
//  - every OPEN lead always has exactly one next action with a due date
//  - stages are objective events, not feelings
//  - lost reasons are a picklist, never free text (so they can be analysed)
//  - rotDays: an open lead with no COMPLETED activity for this many days is
//    flagged as rotting (a scheduled future task does not hide it)
//  - next: what the CRM schedules automatically when a lead enters the stage

export const PIPELINES = {
  admission: {
    key: 'admission',
    name: 'Admissions',
    brand: 'WebiGeeks',
    defaultCountry: 'IN',
    valueField: 'feeFinal',
    stages: [
      { key: 'new', name: 'New Enquiry', rotDays: 1, next: { type: 'call', afterHours: 0, note: 'First call - understand goal, budget, background' } },
      { key: 'contacted', name: 'Contacted', rotDays: 2, next: { type: 'whatsapp', afterHours: 24, note: 'Send syllabus, batch timings and fee details' } },
      { key: 'counselled', name: 'Counselled', rotDays: 3, next: { type: 'call', afterHours: 48, note: 'Invite to free demo class' } },
      { key: 'demo_scheduled', name: 'Demo Scheduled', rotDays: 2, next: { type: 'whatsapp', afterHours: 24, note: 'Confirm demo slot' } },
      { key: 'demo_attended', name: 'Demo Attended', rotDays: 2, next: { type: 'call', afterHours: 24, note: 'Get feedback, discuss fee / EMI' } },
      { key: 'negotiation', name: 'Fee / EMI Talk', rotDays: 3, next: { type: 'call', afterHours: 48, note: 'Close - registration fee' } },
      { key: 'won', name: 'Enrolled', terminal: 'won' },
      { key: 'lost', name: 'Lost', terminal: 'lost' },
    ],
    lostReasons: [
      'Fee too high',
      'Chose a competitor',
      'Chose online / self-study',
      'Timing or exams',
      'Location or distance',
      "Parents didn't approve",
      'Job / placement doubts',
      'No response after 6+ attempts',
      'Not interested / wrong fit',
      'Duplicate or junk',
      'Opted out (do not contact)',
    ],
  },

  agency: {
    key: 'agency',
    name: 'Agency outreach',
    brand: 'WebiGeeks Digital',
    defaultCountry: 'US',
    valueField: 'dealValue',
    stages: [
      { key: 'prospect', name: 'Prospect', rotDays: 3, next: { type: 'email', afterHours: 0, note: 'Send personalised intro email with mockup' } },
      { key: 'contacting', name: 'Contacting', rotDays: 3, next: { type: 'call', afterHours: 48, note: 'Follow-up call referencing the email' } },
      { key: 'engaged', name: 'Engaged', rotDays: 4, next: { type: 'call', afterHours: 24, note: 'Book discovery call' } },
      { key: 'discovery', name: 'Discovery done', rotDays: 5, next: { type: 'email', afterHours: 48, note: 'Send proposal' } },
      { key: 'proposal', name: 'Proposal sent', rotDays: 5, next: { type: 'call', afterHours: 72, note: 'Follow up on proposal' } },
      { key: 'negotiation', name: 'Negotiation', rotDays: 5, next: { type: 'call', afterHours: 48, note: 'Agree terms, collect deposit' } },
      { key: 'won', name: 'Won', terminal: 'won' },
      { key: 'lost', name: 'Lost / Nurture', terminal: 'lost' },
    ],
    lostReasons: [
      'No response (sequence finished)',
      'Not interested',
      'Already has a vendor / agency',
      'Budget',
      'Bad timing',
      'Trust concerns (offshore)',
      'Went with a local vendor',
      'Wrong contact',
      'Duplicate or junk',
      'Opted out (do not contact)',
    ],
  },
};

export const SOURCES = [
  'walk_in', 'google_ads', 'instagram', 'whatsapp', 'phone', 'website',
  'referral', 'cold_email', 'linkedin', 'leads_agent', 'other',
];

export const ACTIVITY_TYPES = ['call', 'whatsapp', 'email', 'linkedin', 'sms', 'visit', 'demo', 'note'];
// Types that count as a "touch" towards the lead (and are blocked for do-not-contact leads).
export const TOUCH_TYPES = ['call', 'whatsapp', 'email', 'linkedin', 'sms', 'visit', 'demo'];
export const OUTCOMES = [
  'connected', 'no_answer', 'voicemail', 'replied', 'interested',
  'not_interested', 'callback', 'bounced', 'opted_out',
];

// Base score by source (rule-based lead score, 0-100).
export const SOURCE_WEIGHT = {
  referral: 25, walk_in: 25, google_ads: 15, website: 15, whatsapp: 15,
  phone: 15, instagram: 10, cold_email: 5, linkedin: 5, leads_agent: 5, other: 5,
};

// {{name}} {{course}} {{business}} are filled in by the UI.
export const TEMPLATES = [
  { id: 'adm-welcome', pipeline: 'admission', channel: 'whatsapp', name: 'First message',
    body: 'Hi {{name}}, this is Rohan from WebiGeeks, Gurugram. Thanks for your interest in {{course}}. Can I call you today to share the syllabus, batch timings and fee details?' },
  { id: 'adm-demo', pipeline: 'admission', channel: 'whatsapp', name: 'Demo confirmation',
    body: 'Hi {{name}}, your free demo class for {{course}} is booked. Please reply YES to confirm you will join. - Rohan, WebiGeeks' },
  { id: 'adm-fee', pipeline: 'admission', channel: 'whatsapp', name: 'Fee follow-up',
    body: 'Hi {{name}}, following up on {{course}}. We can also discuss instalment options so the fee fits your budget. When is a good time to talk?' },
  { id: 'agy-intro', pipeline: 'agency', channel: 'email', name: 'Intro email',
    subject: 'Quick idea for {{business}}',
    body: 'Hi {{name}},\n\nI took a look at {{business}} online and put together a quick idea for how your website could bring in more enquiries.\n\nWould it be OK if I sent it over?\n\nRohan Sharma\nWebiGeeks Digital' },
  { id: 'agy-followup', pipeline: 'agency', channel: 'email', name: 'Follow-up email',
    subject: 'Re: Quick idea for {{business}}',
    body: 'Hi {{name}},\n\nJust following up on my note about {{business}}. Happy to share the mockup - no obligation.\n\nRohan Sharma\nWebiGeeks Digital' },
];
