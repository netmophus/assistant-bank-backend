import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


def _auth_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        if token.lower().startswith("bearer "):
            headers["Authorization"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=os.getenv("PCB_API_URL", os.getenv("API_URL", "http://localhost:8000")))
    parser.add_argument("--token", default=os.getenv("PCB_TOKEN", os.getenv("TOKEN")))
    parser.add_argument("--type", default=None, dest="poste_type")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    params = {}
    if args.poste_type:
        params["type"] = args.poste_type

    url = args.api_url.rstrip("/") + "/api/pcb/postes"
    resp = requests.get(url, headers=_auth_headers(args.token), params=params, timeout=60)
    resp.raise_for_status()
    postes = resp.json()

    payload: Dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_url": args.api_url,
        "filters": {"type": args.poste_type} if args.poste_type else {},
        "count": len(postes) if isinstance(postes, list) else 0,
        "items": postes,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
