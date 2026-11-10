"""Mint a PayPal sandbox access token from .env and store it for the PayPal AI Toolkit plugin.

The plugin's MCP server (mcp.sandbox.paypal.com) reads PAYPAL_SANDBOX_ACCESS_TOKEN from the
"env" block of ~/.claude/settings.json. Tokens expire after ~9 hours, so re-run this when the
paypal-sandbox MCP tools start returning 401, then restart Claude Code.

Usage:  python scripts/refresh_paypal_token.py
"""
import base64
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SETTINGS = pathlib.Path.home() / ".claude" / "settings.json"


def load_env(path: pathlib.Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def mint_token(env: dict) -> dict:
    creds = f"{env['PAYPAL_CLIENT_ID']}:{env['PAYPAL_CLIENT_SECRET']}".encode()
    base = env.get("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    req = urllib.request.Request(
        f"{base}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": "Basic " + base64.b64encode(creds).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> None:
    tok = mint_token(load_env(ROOT / ".env"))
    settings = json.loads(SETTINGS.read_text(encoding="utf-8")) if SETTINGS.exists() else {}
    settings.setdefault("env", {})["PAYPAL_SANDBOX_ACCESS_TOKEN"] = tok["access_token"]
    SETTINGS.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    hours = tok["expires_in"] / 3600
    print(f"Token saved to {SETTINGS} (valid ~{hours:.1f} h). Restart Claude Code to load it.")


if __name__ == "__main__":
    main()
