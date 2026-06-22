"""
RMS → Koenig-Stride SSO token generator (Python reference implementation).

Usage (command line):
    python rms_sso_token.py \
        --secret "your-shared-secret" \
        --email "praveen.chaudhary@koenig-solutions.com" \
        --name "Praveen Chaudhary" --role Admin \
        --base-url https://strides.example.com \
        --panel ask-strides --expires-in 300

It prints a ready-to-use URL the RMS dashboard tile should open.

Works with stdlib only — no PyJWT dependency required.

Important — Koenig-Stride accepts only @koenig-solutions.com email addresses.
"""

import argparse
import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode


ALLOWED_DOMAIN = "@koenig-solutions.com"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def mint_token(secret: str, email: str, name: str = "", role: str = "Employee",
               expires_in: int = 300) -> str:
    """Create an HS256-signed JWT for Koenig-Stride SSO.

    `email` MUST be a @koenig-solutions.com address; other domains will be
    rejected by Strides at verification time.
    """
    email = (email or "").strip().lower()
    if not email.endswith(ALLOWED_DOMAIN):
        raise ValueError(f"Only {ALLOWED_DOMAIN} email addresses are allowed.")

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "email": email,
        "name": str(name) or email.split("@", 1)[0],
        "role": "Admin" if str(role).lower() == "admin" else "Employee",
        "exp": int(time.time()) + int(expires_in),
        "iat": int(time.time()),
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def build_url(base_url: str, token: str, panel: str = "", embed: bool = True) -> str:
    params = {"token": token}
    if embed:
        params["embed"] = "true"
    if panel:
        params["panel"] = panel
    return f"{base_url.rstrip('/')}/?{urlencode(params)}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Mint Koenig-Stride SSO URL")
    p.add_argument("--secret", required=True, help="Shared RMS_SSO_SECRET")
    p.add_argument("--email", required=True,
                   help="Koenig email (must end with @koenig-solutions.com)")
    p.add_argument("--name", default="", help="Full name (optional)")
    p.add_argument("--role", default="Employee", choices=["Admin", "Employee"])
    p.add_argument("--base-url", required=True, help="Strides base URL")
    p.add_argument("--panel", default="", help="Deep-link panel slug")
    p.add_argument("--expires-in", type=int, default=300,
                   help="Token validity in seconds (default 300)")
    p.add_argument("--no-embed", action="store_true",
                   help="Don't add ?embed=true (show Streamlit chrome)")
    args = p.parse_args()

    tok = mint_token(args.secret, args.email, args.name, args.role, args.expires_in)
    url = build_url(args.base_url, tok, args.panel, embed=not args.no_embed)
    print(url)
