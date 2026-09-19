import re
from pathlib import Path

TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def get_tunnel_url(log_path: str) -> str:
    content = Path(log_path).read_text(encoding="utf-8", errors="ignore")
    matches = TUNNEL_URL_PATTERN.findall(content)
    if not matches:
        raise RuntimeError(
            f"No trycloudflare.com URL found in tunnel log at {log_path}"
        )
    return matches[-1]
