import os
from pathlib import Path

import resend
from dotenv import load_dotenv


ENV_FILE = (
    Path(__file__).resolve().parent.parent
    / "apps"
    / "web"
    / ".env.local"
)

load_dotenv(ENV_FILE)


def configure_resend() -> None:
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY is not configured."
        )

    resend.api_key = api_key


def send_price_alert(
    recipient: str,
    product_name: str,
    product_url: str,
    desired_size: str | None,
    current_price: float | None,
    target_price: float | None,
):
    configure_resend()

    sender = os.getenv(
        "EMAIL_FROM",
        "Purchase Intelligence <onboarding@resend.dev>",
    )

    current_text = (
        f"₹{current_price:,.0f}"
        if current_price is not None
        else "Unknown"
    )

    target_text = (
        f"₹{target_price:,.0f}"
        if target_price is not None
        else "Any price"
    )

    size_text = desired_size or "Any"

    params: resend.Emails.SendParams = {
        "from": sender,
        "to": [recipient],
        "subject": f"Buy alert: {product_name}",
        "html": f"""
            <h2>Purchase Intelligence</h2>

            <p>
                Your tracked product now matches
                your purchase conditions.
            </p>

            <h3>{product_name}</h3>

            <p>
                <strong>Current price:</strong>
                {current_text}
            </p>

            <p>
                <strong>Your target:</strong>
                {target_text}
            </p>

            <p>
                <strong>Size:</strong>
                {size_text}
            </p>

            <p>
                <a href="{product_url}">
                    View product
                </a>
            </p>
        """,
    }

    return resend.Emails.send(params)
