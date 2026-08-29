import os
from html import escape
from urllib.parse import urlparse

import resend

from crawler.emailer import configure_resend


def format_phase1_money(
    value: float | int | None,
    currency: str | None,
) -> str:
    if value is None:
        return "Unknown"

    currency = (
        currency or "INR"
    ).upper()

    if currency == "INR":
        return f"₹{float(value):,.0f}"

    return (
        f"{currency} "
        f"{float(value):,.2f}"
    )


def format_variant_requirements(
    requirements: dict,
) -> str:
    """
    Render generic variant requirements without assuming
    a product category such as shoes or phones.
    """

    if not requirements:
        return "Any variant"

    parts: list[str] = []

    for key in sorted(requirements):
        value = requirements[key]

        label = (
            key.replace("_", " ")
            .strip()
            .title()
        )

        parts.append(
            f"{label}: {value}"
        )

    return ", ".join(parts)


def build_phase1_email_params(
    notification: dict,
    recipient: str,
) -> resend.Emails.SendParams:
    """
    Build Resend parameters from a persisted Phase 1
    notification.

    Pure builder:
      - no database writes
      - no provider call
      - no email sent
    """

    recipient = recipient.strip()

    if not recipient:
        raise RuntimeError(
            "Phase 1 email recipient is required."
        )

    title = notification.get(
        "title"
    )

    body = notification.get(
        "body"
    )

    payload = (
        notification.get("payload")
        or {}
    )

    if not title:
        raise RuntimeError(
            "Phase 1 notification is missing its title."
        )

    if not body:
        raise RuntimeError(
            "Phase 1 notification is missing its body."
        )

    product_name = (
        payload.get("product_name")
        or "Tracked product"
    )

    product_url = payload.get(
        "product_url"
    )

    currency = payload.get(
        "currency"
    )

    current_price = payload.get(
        "current_price"
    )

    target_price = payload.get(
        "target_price"
    )

    variant_requirements = (
        payload.get("variant_requirements")
        or {}
    )

    if product_url:
        parsed = urlparse(
            product_url
        )

        if parsed.scheme not in (
            "http",
            "https",
        ):
            raise RuntimeError(
                "Phase 1 notification contains an "
                "unsupported product URL."
            )

    current_text = format_phase1_money(
        current_price,
        currency,
    )

    if target_price is None:
        target_text = "Any price"
    else:
        target_text = format_phase1_money(
            target_price,
            currency,
        )

    variant_text = (
        format_variant_requirements(
            variant_requirements
        )
    )

    safe_product_name = escape(
        str(product_name)
    )

    safe_body = escape(
        str(body)
    )

    safe_current = escape(
        current_text
    )

    safe_target = escape(
        target_text
    )

    safe_variant = escape(
        variant_text
    )

    product_link_html = ""

    if product_url:
        safe_url = escape(
            str(product_url),
            quote=True,
        )

        product_link_html = f"""
            <p>
                <a href="{safe_url}">
                    View product
                </a>
            </p>
        """

    sender = os.getenv(
        "EMAIL_FROM",
        "Purchase Intelligence <onboarding@resend.dev>",
    )

    params: resend.Emails.SendParams = {
        "from": sender,
        "to": [recipient],
        "subject": str(title),
        "html": f"""
            <h2>Purchase Intelligence</h2>

            <p>
                {safe_body}
            </p>

            <h3>
                {safe_product_name}
            </h3>

            <p>
                <strong>Current price:</strong>
                {safe_current}
            </p>

            <p>
                <strong>Your target:</strong>
                {safe_target}
            </p>

            <p>
                <strong>Variant:</strong>
                {safe_variant}
            </p>

            {product_link_html}
        """,
    }

    return params


def build_phase1_email_idempotency_key(
    notification: dict,
) -> str:
    """
    Build a stable provider-level idempotency key.

    The persisted notification ID identifies one logical
    notification. Retries of that notification therefore use
    the same Resend idempotency key.
    """

    notification_id = str(
        notification.get("id")
        or ""
    ).strip()

    if not notification_id:
        raise RuntimeError(
            "Phase 1 notification is missing its id."
        )

    return (
        "phase1-email:"
        f"{notification_id}"
    )


def send_phase1_email(
    notification: dict,
    recipient: str,
):
    """
    Send one Phase 1 email through Resend.

    The caller is responsible for:
      - notification preference checks
      - delivery claiming
      - recording sent/failed delivery state

    Resend idempotency protects against duplicate provider
    sends when the same persisted notification is retried.
    """

    configure_resend()

    params = build_phase1_email_params(
        notification,
        recipient,
    )

    options: resend.Emails.SendOptions = {
        "idempotency_key": (
            build_phase1_email_idempotency_key(
                notification
            )
        ),
    }

    return resend.Emails.send(
        params,
        options,
    )
