# Compliance: what the system enforces, and what you still do by hand

This is a plain summary, not legal advice. Where a rule was unclear, the stricter reading was built. Have a Canadian lawyer read
it once.

## What the system enforces

**Google Maps Platform**
- Only the Google `place_id` is stored. Google's name, address, phone, website, types and location are never saved in the
  database, a file, a log, a cache or a GitHub artifact. A model check refuses any save of a Google lead that carries them, and a
  test inspects every collection after a full flow.
- Opening a Google lead fetches Place Details live and returns it to the screen without saving. It sits in its own card labelled
  "Google Maps", apart from CRM data. Repeat opens within 10 minutes by the same person reuse an in-memory copy.
- Place Details is held to 30 a day and 950 a month. At the limit the card says "Google details limit reached - opens again
  tomorrow" and the lead's own data still shows.
- What a caller learns on a call goes in separate `confirmed` fields marked as from the business. They are never copied from Google.

**Open data credits**
- OpenStreetMap leads show "(c) OpenStreetMap contributors" with a link, and the CRM footer carries it.
- Overture leads show "Overture Maps Foundation" and, per Overture's attribution page (read 4 Nov 2026), Foursquare's notice
  ("Copyright 2024 Foursquare Labs, Inc. All rights reserved."). Overture's Places data is under CDLA-Permissive-2.0 (Meta,
  Microsoft and others), Apache-2.0 (Foursquare) and CC0 (AllThePlaces). Re-check that page if Overture changes providers.

**Calling Canadian businesses (CRTC)**
- The Call button asks the server first. It is blocked while the DNCL registration number is empty (red banner), when the lead or
  number is on the internal do-not-call list, when there is no number, when the province is unknown, and outside calling hours in
  the business's own time zone (weekdays 9:00-21:30, weekends 10:00-18:00). The old "log this call anyway" override is removed.
- "Do not call" records the number, who and when, and blocks that number on every lead, every partner and every future fetch at
  once. There is no undo route and no delete route, so entries are kept (at least three years).
- A call script banner shows the caller, "on behalf of WebiGeeks Digital", the purpose, a callback number and email, and a reminder
  to offer and honour removal.
- A hand-typed number with no sign it is a business is flagged "may be a home line".
- Every call attempt (allowed or blocked) is logged with who and when, and cannot be deleted by a partner.
- No automatic dialer, no recorded messages, no bulk SMS exists in the code. The single "text the mockup link" action is shown only
  when the business has agreed on a call (you told Quo: cold calling yes, cold messaging no).

**Email to Canadian businesses (CASL)**
- Sending is blocked unless a consent basis is recorded: express (call date, who, exact words) or implied (a person confirmed the
  address is published by the business on its own website, no "no unsolicited messages" notice, and the email is about their
  business; page and date kept). Map, Google and listing addresses never count.
- The lead finder never extracts, guesses or saves email addresses. The old website email-harvesting code is removed, and finder
  rows are stripped of any email on ingest.
- Every email carries the sender's name, "WebiGeeks Digital", the Gurugram office address, a reply address and a one-click
  unsubscribe (link and the mail app's own button). Unsubscribing suppresses the address at once and for good, and stops follow-ups.
- No consent-request emails and no bulk or automatic sequences exist.

**US leads**: the US market stays switched off. US calling and email law differs and needs its own review before it is turned on.

## What you must still do by hand

1. **Register with the National DNCL operator** (free) and enter the number in the red banner. Calls stay blocked until you do.
2. **Read the draft Terms of Use and Privacy Policy** (`/terms`, `/privacy` on the website). They are marked DRAFT and hidden from
   search engines until you remove `noindex` and the draft notice. Google requires pages that refer to its terms and privacy policy.
3. **Have a Canadian lawyer review** this document, the scripts, the consent wording and the do-not-call handling once.
4. **Add the "number belongs to WebiGeeks" line** to the partner agreement.
5. Provincial **statutory holidays** are not built in (see CHANGES.md). Do not call on them until a list is added.
6. Keep the do-not-call log, fetch records and call outcomes for at least three years. Partners cannot delete them; do not delete
   them in the database either.
7. Do the four cost steps in `COST_SAFETY.md`.
