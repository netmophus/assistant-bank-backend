import argparse
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import requests


def _auth_headers(token: Optional[str]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        if token.lower().startswith("bearer "):
            headers["Authorization"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def _load_items(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    raise ValueError("JSON invalide: attendu une liste de postes ou un objet { items: [...] }")


def _fetch_existing_by_code(api_url: str, token: Optional[str]) -> Dict[str, str]:
    url = api_url.rstrip("/") + "/api/pcb/postes"
    resp = requests.get(url, headers=_auth_headers(token), timeout=60)
    resp.raise_for_status()
    items = resp.json()
    out: Dict[str, str] = {}
    if isinstance(items, list):
        for p in items:
            if not isinstance(p, dict):
                continue
            code = str(p.get("code") or "").strip()
            pid = str(p.get("id") or "").strip()
            if code and pid:
                out[code] = pid
    return out


def _normalize_parent_code(items: List[Dict[str, Any]]) -> None:
    id_to_code: Dict[str, str] = {}
    for p in items:
        pid = str(p.get("id") or "").strip()
        code = str(p.get("code") or "").strip()
        if pid and code:
            id_to_code[pid] = code

    for p in items:
        parent_code = p.get("parent_code")
        parent_id = p.get("parent_id")
        if (not parent_code) and parent_id:
            pc = id_to_code.get(str(parent_id))
            if pc:
                p["parent_code"] = pc


def _sorted_by_hierarchy(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key_fn(p: Dict[str, Any]) -> Tuple[int, int, str]:
        niveau = p.get("niveau")
        ordre = p.get("ordre")
        try:
            n = int(niveau) if niveau is not None else 1
        except Exception:
            n = 1
        try:
            o = int(ordre) if ordre is not None else 0
        except Exception:
            o = 0
        code = str(p.get("code") or "")
        return (n, o, code)

    return sorted(items, key=key_fn)


def _build_create_payload(p: Dict[str, Any], parent_id: Optional[str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "code": p.get("code"),
        "libelle": p.get("libelle"),
        "type": p.get("type"),
        "niveau": p.get("niveau", 1),
        "parent_id": parent_id,
        "parent_code": p.get("parent_code"),
        "contribution_signe": p.get("contribution_signe", "+"),
        "ordre": p.get("ordre", 0),
        "gl_codes": p.get("gl_codes", []),
        "calculation_mode": p.get("calculation_mode", "gl"),
        "parents_formula": p.get("parents_formula", []),
        "formule": p.get("formule", "somme"),
        "formule_custom": p.get("formule_custom"),
        "is_active": p.get("is_active", True),
    }

    # Nettoyage minimal (évite d'envoyer des None inutiles sur certains champs)
    for k in list(payload.keys()):
        if payload[k] is None:
            payload.pop(k, None)

    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=os.getenv("PCB_API_URL", os.getenv("API_URL", "http://localhost:8000")))
    parser.add_argument("--token", default=os.getenv("PCB_TOKEN", os.getenv("TOKEN")))
    parser.add_argument("--in", required=True, dest="input_path")
    parser.add_argument("--mode", choices=["create", "upsert"], default="upsert")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    items = _load_items(args.input_path)
    _normalize_parent_code(items)

    existing_by_code: Dict[str, str] = {}
    if args.mode == "upsert":
        existing_by_code = _fetch_existing_by_code(args.api_url, args.token)

    created_code_to_id: Dict[str, str] = {}
    # Si upsert, on pré-remplit avec les existants (utile pour rattacher les enfants)
    created_code_to_id.update(existing_by_code)

    url_postes = args.api_url.rstrip("/") + "/api/pcb/postes"

    ordered = _sorted_by_hierarchy(items)
    pending = ordered

    # Import en passes successives pour résoudre les parents
    max_passes = 10
    for _pass in range(max_passes):
        if not pending:
            break

        next_pending: List[Dict[str, Any]] = []
        progressed = False

        for p in pending:
            code = str(p.get("code") or "").strip()
            if not code:
                continue

            parent_code = str(p.get("parent_code") or "").strip()
            parent_id: Optional[str] = None
            if parent_code:
                parent_id = created_code_to_id.get(parent_code)
                if not parent_id:
                    next_pending.append(p)
                    continue

            payload = _build_create_payload(p, parent_id)

            if args.dry_run:
                progressed = True
                continue

            if args.mode == "upsert" and code in existing_by_code:
                poste_id = existing_by_code[code]
                resp = requests.put(
                    args.api_url.rstrip("/") + f"/api/pcb/postes/{poste_id}",
                    headers=_auth_headers(args.token),
                    data=json.dumps(payload),
                    timeout=60,
                )
                resp.raise_for_status()
                out = resp.json()
                new_id = str((out or {}).get("id") or "").strip()
                if new_id:
                    created_code_to_id[code] = new_id
                progressed = True
            else:
                resp = requests.post(url_postes, headers=_auth_headers(args.token), data=json.dumps(payload), timeout=60)
                resp.raise_for_status()
                out = resp.json()
                new_id = str((out or {}).get("id") or "").strip()
                if new_id:
                    created_code_to_id[code] = new_id
                progressed = True

        pending = next_pending
        if not progressed:
            break

    if pending:
        missing = []
        for p in pending:
            code = str(p.get("code") or "").strip()
            parent_code = str(p.get("parent_code") or "").strip()
            missing.append({"code": code, "parent_code": parent_code})
        raise SystemExit(
            "Import incomplet: certains postes n'ont pas pu être importés (parents manquants ou cycles). "
            + json.dumps(missing, ensure_ascii=False, indent=2)
        )


if __name__ == "__main__":
    main()
