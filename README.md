# Phil, web app (Phase 1 + Phase 2)

A real, running version of Phil: sign up, sign in, roles (admin / mentor /
parent-carer / Phil staff), the 20-course library, pupil enrolment, session
recording with the mandatory safeguarding step, automatic progress tracking,
automatic PDF certificates, and a full internal Phil staff console for
running the business day to day (establishments, individual mentors, course
and support requests, billing, team, audit log). This now covers the Phase 1
MVP scope from `Phil_Technical_Build_Spec.docx` section 10, plus the Phase 2
Phil staff console from section 7.8 and 8.

## Why this isn't the Next.js app the spec recommends

The spec's suggested stack is Next.js, Postgres (Supabase), Stripe and
Netlify. This environment has no network access to the npm or pip package
registries (both return 403, blocked by allowlist), so none of those
packages, or any others, can be installed here.

Instead, this is a dependency-free Python application: the standard library's
`wsgiref` for the web server, `sqlite3` for the database, and `reportlab`
(already installed) for PDF generation. It implements the same data model and
the same user flows, and it genuinely runs, no install step, no external
account needed. It is meant as a working Phase 1 you can use and test today,
and as a clear functional reference for whoever builds the production
version, not a replacement for eventually building that Next.js app.

## Running it

Requires only Python 3.10+, nothing else to install.

```bash
cd phil-app
python3 seed.py   # loads the 20 courses into the database, run once
python3 run.py    # starts the server on http://localhost:8000
```

Then open http://localhost:8000, click "Get started", and sign up as an
establishment (free pilot or paid) or as an individual mentor.

`seed.py` also creates the first Phil staff account (`staff@phileducation.co.uk`
/ `philstaff123`), since spec section 7.8 is explicit that a `phil_staff`
account is never created through the public sign-up form. Change this
password before any real deployment; every other Phil staff account is
created from inside `/staff/team` once you're signed in as this one.

The database is a single file at `data/phil.db`. Delete it and re-run
`seed.py` to start over. Generated PDFs (certificates, session records) are
written to `data/pdfs/`.

## What's implemented

- Sign up: establishment pilot (3 seats, 10 pupils, 21 days), establishment
  paid (15 seats), or individual mentor (1 seat, lands straight in the mentor
  view, no admin console), per spec sections 7.1, 7.1a, 7.1b.
- Sign in / sign out, PBKDF2 password hashing, server-side sessions.
- The 20-course library, seeded from the same `courses_data.js` used to
  generate the Word course documents, browsable whether signed in or not.
- Mentor: add a pupil, enrol on a course with the parent/carer access toggle,
  record a session (mood/engagement ratings, mandatory safeguarding flag and
  note, what happened, reflection goal, mentor notes, resources used).
- `current_week` advances automatically on each recorded session; at week 5
  the enrolment completes and a certificate PDF is generated and issued
  immediately, matching spec section 7.6.
- Completion reflection: optional three-part mentor write-up, prompted after
  completion, never shown to parents.
- Admin: establishment overview, seat usage, mentor list, and establishment-
  wide access to any session record including safeguarding notes (a look-it-
  up capability, not a push notification, per spec section 8).
- Seat limit enforcement: adding a mentor beyond the plan's included seats
  creates a seat alert instead of the account, per spec section 7.2.
- Parent/carer view: shows only enrolments with `parent_access_enabled` on,
  the current week's home activity, and the certificate once issued. An
  enrolment with the toggle off is absent from the parent's app entirely,
  never a placeholder, matching spec section 7.5. Verified directly: a pupil
  with one enrolment toggled on and one toggled off shows only the first.
- Session record and certificate PDFs generated server-side with reportlab,
  including the mandatory safeguarding block and its standard disclaimer
  wording.
- In-app course builder (admin): create a course and its 5 weeks, edit it,
  publish or unpublish. A draft course is invisible everywhere except the
  admin course list until published, matching spec section 5.1. New courses
  auto-number after the existing 20.
- Parent/carer invite: mentor or admin creates the parent's account and links
  it to a pupil directly from the pupil's profile, no database access needed.
- Session scheduling (7.4): optional planned dates for some or all of the 5
  weeks, pre-filled at one-per-week pace, purely a planning aid, doesn't
  affect `current_week`. Shown to the mentor and, where parent access is on,
  to the parent.
- Individual mentee report (7.5a): course, mentor, pupil, and week-by-week
  title/objective for weeks actually recorded, as HTML and PDF. Generatable
  by the mentor, the establishment admin, or the linked parent (only where
  `parent_access_enabled` is on). A completed enrolment's report appends the
  full CompletionReflection, but only for the mentor/admin copy, never the
  parent's, verified directly by comparing the same report rendered for both.
- Case load report (7.7): a mentor's own caseload as a table and PDF (pupil,
  course, started, scheduled end, progress, certificate status, reflection
  done/needed). Admin gets the same view for any single mentor or all of
  them, with a mentor column added when viewing "all". Both the case load
  report and the Full mentoring report below also export as `.xlsx`
  (openpyxl), alongside PDF.
- Full mentoring report (7.7a): a whole-establishment bulk export, or a
  single named pupil, in one PDF, one section per pupil. Same restricted
  fields as the individual mentee report (enrolment, course, week, session
  date, and the completion reflection where finished); ratings, mentor
  notes and safeguarding content are never included, verified directly by
  extracting the generated PDF's text and confirming none of those fields
  appear.
- In-app notifications: a `notifications` table drives two real alerts, a
  seat-limit breach notifies Phil staff, and a pilot with 5 or fewer days
  left notifies the establishment admin, both dismissible and
  duplicate-suppressed so the same alert doesn't stack. No email is sent,
  this is in-app only.
- Pilot-to-paid conversion: an admin on a pilot plan can convert to a paid
  plan at any time from their home screen, in place, no data moves or is
  lost (15 seats, no pupil cap, `payment_method` set to invoice).
- Phil staff console (7.8, 8), a separate internal role with no pupil or
  school data on its own home screen:
  - Establishments: list, manually create one (pilot or paid, creates the
    nominated admin account directly), view detail (plan, seat usage,
    admin contact), suspend or reactivate. A suspended establishment's
    admin and mentors are locked out immediately, phil_staff access is
    unaffected, verified directly (suspend, confirm a 403 for the admin,
    reactivate, confirm access returns).
  - Individual mentors: list and suspend/reactivate the same way, scoped
    to the `type='individual'` establishments.
  - Course requests: establishment admins submit a topic and note from
    their home screen, Phil staff triage the inbox and mark in progress.
  - Support requests: establishment admins and mentors submit a request,
    optionally referencing one pupil; Phil staff see it in an inbox and
    resolve it with a response. Where a pupil is referenced, that one
    record is visible on the ticket only, and the access is written to
    the audit log as `safeguarding_scoped_access`, matching the spec's
    rule that this is ticket-scoped, logged access, not standing
    visibility.
  - Billing & revenue: every establishment's current subscription,
    estimated MRR, and the invoice list, in one place.
  - Phil team: list the internal team and invite a new member (the only
    other way to create a `phil_staff` account besides the one-off seed
    step for the very first one).
  - Audit log: suspensions, reactivations, permanent deletions,
    ticket-scoped safeguarding access, course/support request handling,
    and pilot conversions, all with actor, target, and a plain-English
    detail line, last 200 shown.
- Admin case load management, so an establishment can look after itself day
  to day without waiting on Phil: a pupils list (active/archived), reassign
  a single enrolment to a different mentor (keeps every session record),
  remove a mentor (reassigns their active case load to someone else first,
  their seat frees up, their login stops working immediately), and
  permanently delete a pupil's whole record with a type-the-name
  confirmation. Deletion is deliberately different from archiving:
  archiving is reversible and keeps everything, this is not, and it is
  logged.

## Card payments (Stripe)

`billing.py` and the `/admin/billing/checkout` and `/webhooks/stripe` routes
in `app.py` are a real Stripe Checkout integration, not a stub, but they
were written and reviewed without a live Stripe account (none was available
in the environment this was built in, and outbound calls to api.stripe.com
aren't reachable there either), so it has not been exercised against Stripe
itself yet. Test it in Stripe's test mode before relying on it for a real
charge. The code degrades safely if Stripe isn't configured: `billing.
is_configured()` checks that the `stripe` package installed, and that
`STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are both set, and every
route that touches Stripe checks this first, so a deployment with no Stripe
account yet just doesn't show the "Pay by card" button and keeps working
exactly as before on the existing invoice path. See `.env.example` for
every variable it reads.

The existing manual/invoice flow (`/admin/convert-pilot`, the establishment
admin marks itself as converted, Phil staff separately track and chase the
actual invoice, e.g. paid via a Tide Payment Link) is untouched and keeps
working whether or not Stripe is ever configured. The two are meant to
coexist: card payments for establishments that want automatic renewal,
invoice for those that pay by bank transfer or purchase order.

## What's deliberately not built yet

Native app packaging, offline mode, and MIS integration remain Phase 3 and
structurally out of reach here (no app store account to submit to, no
school MIS sandbox to integrate against). Real email delivery isn't wired
up anywhere, every "invite" (parent/carer, Phil team member) creates the
account directly rather than sending a link, and every place the spec
calls for an email (seat alerts, pilot-ending reminders) is an in-app
notification instead, that's a genuinely separate integration (Postmark or
Resend) from the payments work above and hasn't been started.

## Deploying to Railway

This app already runs as a plain Python process with a SQLite file, which
is exactly what Railway hosts (unlike Netlify, which only runs short-lived
serverless functions with no persistent storage, and can't run this app at
all without a much larger rewrite). `Procfile`, `railway.json`, and
`requirements.txt` are already in this repo for Railway to pick up
automatically. What's left is entirely account setup that has to happen in
your own browser, none of it can be done from inside this build:

1. **Push this code to GitHub.** Create a repository (or use one you
   already have) and push this folder to it. Railway deploys from a GitHub
   repo, and pushing was not possible from the environment this was built
   in.
2. **Create a Railway project** from that GitHub repo (railway.app, "New
   Project" > "Deploy from GitHub repo"). It will detect `requirements.txt`
   and `Procfile` automatically and start building.
3. **Add a volume** on the service (Settings > Volumes), mount it at
   `/data`, and set the `PHIL_DB_PATH` environment variable to
   `/data/phil.db` so the database survives every redeploy instead of
   resetting.
4. **Add a custom domain** (Settings > Networking > Custom Domain) pointing
   at your phileducation.co.uk DNS if you want Phil on your own domain
   rather than Railway's generated one.
5. **Run `python3 seed.py` once** against the deployed app (Railway's
   dashboard has a shell/one-off command runner) to load the 20 courses and
   create the first Phil staff account, same as local setup.
6. **If you want card payments**, create a Stripe account, switch it to
   test mode first, create a recurring Price for the school plan (and one
   for individual mentors if you sell to them separately), add a webhook
   endpoint pointing at `https://<your-railway-domain>/webhooks/stripe`
   listening for `checkout.session.completed` and
   `customer.subscription.deleted`, then set `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_SCHOOL`, and `APP_BASE_URL` as
   Railway environment variables. Test a full checkout in Stripe test mode
   before switching to a live key.
7. **If you're staying on invoice/Tide for now**, skip step 6 entirely,
   nothing else changes, the invoice path already works without Stripe.

None of steps 1, 2, 4, or 6 can be completed on your behalf, they each need
an account only you can create and log into. Everything else in this repo
(the code, the schema, the deploy config) is already in place for whenever
you're ready to do them.
