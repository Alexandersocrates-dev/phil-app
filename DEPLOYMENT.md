# Deploying Phil, step by step

Everything code-side is already done and committed to a local git repository
in this folder (`git log` shows it). What's left below is account setup in
your own browser, none of it can be done on your behalf, each step needs a
login only you have. Work through it in order, ticking off as you go.

## 1. Push to GitHub

- [ ] Go to github.com/new
- [ ] Repository name: `phil-app` (or whatever you'd like)
- [ ] Visibility: your choice, private is reasonable since it's your product,
      though nothing secret is committed, real keys never go in the repo
- [ ] **Do not** check "Add a README" or "Add .gitignore", this repo already
      has both and GitHub will refuse the push if they conflict
- [ ] Click **Create repository**
- [ ] Open Terminal on your Mac, `cd` into this folder (drag the folder onto
      the Terminal window to fill in the path automatically), then run the
      three commands GitHub shows you under "...or push an existing
      repository from the command line". They'll look like:
  ```
  git remote add origin https://github.com/<your-username>/phil-app.git
  git branch -M main
  git push -u origin main
  ```
  Terminal may open a browser window to confirm you're logged into GitHub,
  or ask for a personal access token, follow whatever it prompts.

## 2. Create the Railway project

- [ ] Go to railway.app, sign in (GitHub login is the fastest option here)
- [ ] **New Project** → **Deploy from GitHub repo** → select `phil-app`
- [ ] Authorize Railway to access the repo if prompted
- [ ] Wait for the first build to finish, Railway detects `requirements.txt`
      and `Procfile` automatically, no configuration needed from you here
- [ ] Once it's deployed: click the service → **Settings** → **Networking**
      → **Generate Domain**. This gives you a `*.up.railway.app` URL you can
      open right away to confirm Phil is actually running

## 3. Add persistent storage

Without this, every redeploy wipes the database back to empty.

- [ ] On the service: **Settings** → **Volumes** → **New Volume**
- [ ] Mount path: `/data`
- [ ] Go to the **Variables** tab, add:
  ```
  PHIL_DB_PATH=/data/phil.db
  ```
- [ ] Railway redeploys automatically when you add a variable. Once it's
      back up, reopen your `*.up.railway.app` URL, the app auto-seeds the
      20 courses and the first Phil staff login on this first real boot
      (`staff@phileducation.co.uk` / `philstaff123`, change that password
      once you're in). No separate seed command needed.

At this point Phil is live and fully usable on the invoice/Tide payment
path. Steps 4 and 5 below are optional, do them whenever you're ready.

## 4. Point your domain at it (optional)

- [ ] Service → **Settings** → **Networking** → **Custom Domain**, enter
      something like `app.phileducation.co.uk`
- [ ] Railway shows you a CNAME record to add. Add it in whatever DNS
      provider manages phileducation.co.uk
- [ ] Once it's added, also set the `APP_BASE_URL` variable (Variables tab)
      to `https://app.phileducation.co.uk`, this is only needed if you also
      set up Stripe below, it's what Stripe redirects an admin back to
      after checkout

## 5. Turn on card payments via Stripe (optional)

Pricing to use, from `Phil_Pricing_Plan.docx`: **individual £22/month or
£220/year**, **establishment £750/year for 15 seats**. Test everything in
Stripe's test mode first, a live key isn't needed until you're ready for a
real charge.

- [ ] Create a Stripe account at stripe.com
- [ ] Make sure you're in **Test mode** (toggle, top right of the dashboard)
- [ ] **Product catalog** → **Add product**:
  - Name: `Phil - Establishment plan`
  - Pricing: recurring, £750.00 GBP, billed yearly
  - Save, then copy the **price ID** it generates (starts `price_...`)
- [ ] If you'll also sell to individual mentors directly through Stripe,
      repeat for a second product:
  - Name: `Phil - Individual plan`
  - Pricing: recurring, £22.00 GBP, billed monthly (add a second price on
    the same product for the £220/year annual option if you want both)
  - Copy this price ID too
- [ ] **Developers** → **Webhooks** → **Add endpoint**
  - Endpoint URL: `https://<your-railway-or-custom-domain>/webhooks/stripe`
  - Events to send: `checkout.session.completed` and
    `customer.subscription.deleted`
  - Save, then reveal and copy the **signing secret** (starts `whsec_...`)
- [ ] **Developers** → **API keys**, copy the **Secret key** (starts
      `sk_test_...` while in test mode)
- [ ] Back in Railway, Variables tab, add:
  ```
  STRIPE_SECRET_KEY=sk_test_...
  STRIPE_WEBHOOK_SECRET=whsec_...
  STRIPE_PRICE_ID_SCHOOL=price_...
  STRIPE_PRICE_ID_INDIVIDUAL=price_...
  APP_BASE_URL=https://app.phileducation.co.uk
  ```
- [ ] Redeploy, log into an admin account on Phil, you should now see a
      **Pay by card** button. Run through a full test checkout using
      Stripe's test card number `4242 4242 4242 4242`, any future expiry,
      any CVC, and confirm the subscription updates in Phil afterward
- [ ] Once you're confident it works, switch the Stripe dashboard to
      **Live mode**, repeat the product/webhook/key steps there (test and
      live are entirely separate in Stripe), and swap the Railway variables
      for the live versions (`sk_live_...`, a new live webhook secret, live
      price IDs)

## If something breaks

Paste the exact error, whichever step it's from (a Railway build log, a
Stripe dashboard message, a browser error) back into the chat and it can be
debugged from there, most of what goes wrong at this stage is a typo'd
variable name or a webhook pointed at the wrong URL, both quick to spot
once the actual error text is visible.
