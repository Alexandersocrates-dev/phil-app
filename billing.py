"""
Phil - Stripe billing.

Handles the "pay by card" path for an establishment's subscription: a
Stripe Checkout Session (subscription mode) for the initial purchase, and a
webhook endpoint that keeps the `subscriptions` table in sync with what
Stripe actually charged, so the app's own idea of "is this establishment
paid up" never has to guess or poll Stripe directly.

This module is written to degrade gracefully when Stripe isn't configured,
which happens in three cases: the `stripe` package isn't installed (true in
the sandbox this was built in, which has no package-registry access), or
STRIPE_SECRET_KEY/STRIPE_WEBHOOK_SECRET aren't set as environment variables
(true until you've actually created a Stripe account and put its keys into
Railway). In all three cases, `is_configured()` returns False and the
existing manual/invoice payment path (see app.py's /admin/convert-pilot)
keeps working exactly as it did before, this module just isn't reachable
yet. Nothing about local development or the invoice-based flow depends on
Stripe being present.
"""

import os

try:
    import stripe
    _STRIPE_IMPORT_OK = True
except ImportError:  # pragma: no cover - expected in this sandbox
    stripe = None
    _STRIPE_IMPORT_OK = False

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID_SCHOOL = os.environ.get("STRIPE_PRICE_ID_SCHOOL")
STRIPE_PRICE_ID_INDIVIDUAL = os.environ.get("STRIPE_PRICE_ID_INDIVIDUAL")
# Where Stripe should send the establishment admin after checkout. Set this
# to your real domain once you have one, e.g. https://app.phileducation.co.uk
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000")

if _STRIPE_IMPORT_OK and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def is_configured():
    """True once the stripe package is installed and both keys are set.
    Every route in app.py that touches Stripe checks this first and falls
    back to a plain error message otherwise, so an unconfigured deployment
    fails safely rather than crashing."""
    return _STRIPE_IMPORT_OK and bool(STRIPE_SECRET_KEY) and bool(STRIPE_WEBHOOK_SECRET)


def create_checkout_session(establishment_id, establishment_name, admin_email, plan_type):
    """Creates a subscription-mode Checkout Session for one establishment
    and returns its hosted URL to redirect the admin to. `plan_type` is
    'school' or 'individual', matching the price IDs configured above.
    Raises RuntimeError with a plain message if Stripe isn't configured or
    the relevant price ID is missing, callers should catch this and show
    the message rather than a stack trace."""
    if not is_configured():
        raise RuntimeError("Card payments are not set up yet on this deployment.")

    price_id = STRIPE_PRICE_ID_SCHOOL if plan_type == "school" else STRIPE_PRICE_ID_INDIVIDUAL
    if not price_id:
        raise RuntimeError(f"No Stripe price is configured for the '{plan_type}' plan.")

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=admin_email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{APP_BASE_URL}/billing/success?establishment_id={establishment_id}",
        cancel_url=f"{APP_BASE_URL}/billing/cancel",
        client_reference_id=str(establishment_id),
        metadata={"establishment_id": str(establishment_id), "establishment_name": establishment_name},
        subscription_data={"metadata": {"establishment_id": str(establishment_id)}},
    )
    return session.url


def verify_webhook(payload, sig_header):
    """Verifies a webhook request actually came from Stripe using the
    signing secret. Raises on failure, never trust an unverified payload,
    per Stripe's own guidance, anyone can POST a fake 'payment succeeded'
    event to a guessed URL otherwise."""
    if not is_configured():
        raise RuntimeError("Stripe is not configured on this deployment.")
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)


def already_processed(conn, event_id):
    return conn.execute("SELECT 1 FROM stripe_events WHERE id=?", (event_id,)).fetchone() is not None


def mark_processed(conn, event_id, event_type, now):
    conn.execute(
        "INSERT INTO stripe_events (id, type, processed_at) VALUES (?,?,?)",
        (event_id, event_type, now),
    )
