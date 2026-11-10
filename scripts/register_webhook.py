"""Register (or find) the PayPal sandbox webhook for a deployed TrustLayer.

Usage: python scripts/register_webhook.py https://your-app.onrender.com
Prints the webhook id; set it as PAYPAL_WEBHOOK_ID so incoming events are signature-verified.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.app import paypal  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].startswith("https://"):
        raise SystemExit("usage: python scripts/register_webhook.py https://<public-host>  (PayPal requires HTTPS)")
    url = sys.argv[1].rstrip("/") + "/api/webhooks/paypal"
    for hook in paypal.list_webhooks().get("webhooks", []):
        if hook.get("url") == url:
            print(f"already registered: PAYPAL_WEBHOOK_ID={hook['id']}")
            return
    hook = paypal.create_webhook(url)
    print(f"registered {url} for {len(hook.get('event_types', []))} event types")
    print(f"PAYPAL_WEBHOOK_ID={hook['id']}")


if __name__ == "__main__":
    main()
