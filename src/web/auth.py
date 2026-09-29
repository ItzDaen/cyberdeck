# Author: Daen
# CyberDeck Workstation & Audio System

import secrets
import subprocess
from pathlib import Path

TOKEN_PATH = Path.home() / ".config" / "cyberdeck" / "auth.token"

def get_or_create_auth_token() -> str:
    """Retrieve existing auth token or create a new cryptographically secure 256-bit token."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        try:
            token = TOKEN_PATH.read_text(encoding="utf-8").strip()
            if len(token) >= 32:
                return token
        except Exception:
            pass

    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    TOKEN_PATH.chmod(0o600)  # Restrict permissions: only readable by the current user
    return token

def get_tailscale_ip() -> str:
    """Fetch the Tailscale IPv4 address dynamically."""
    try:
        res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            ip = res.stdout.strip().split("\n")[0]
            if ip:
                return ip
    except Exception:
        pass
    return "127.0.0.1"

def verify_token(provided_token: str, expected_token: str) -> bool:
    """Constant-time token verification to prevent timing attacks."""
    if not provided_token or not expected_token:
        return False
    return secrets.compare_digest(provided_token.strip(), expected_token.strip())
