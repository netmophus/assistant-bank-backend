import argparse
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo import MongoClient


DEFAULT_COLLECTION = "pcb_postes_reglementaires"


def _load_items(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    raise ValueError("JSON invalide: attendu une liste de postes ou un objet { items: [...] }")


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


def _normalize_parent_code(items: List[Dict[str, Any]]) -> None:
    id_to_code: Dict[str, str] = {}
    for p in items:
        pid = str(p.get("id") or p.get("_id") or "").strip()
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


def _build_doc(p: Dict[str, Any], *, organization_id: ObjectId, parent_id: Optional[ObjectId]) -> Dict[str, Any]:
    now = datetime.utcnow()

    doc: Dict[str, Any] = {
        "code": str(p.get("code") or "").strip(),
        "libelle": p.get("libelle"),
        "type": p.get("type"),
        "niveau": int(p.get("niveau") or 1),
        "parent_id": parent_id,
        "parent_code": p.get("parent_code"),
        "contribution_signe": p.get("contribution_signe") if p.get("contribution_signe") in ["+", "-"] else "+",
        "organization_id": organization_id,
        "ordre": int(p.get("ordre") or 0),
        "gl_codes": p.get("gl_codes") if isinstance(p.get("gl_codes"), list) else [],
        "calculation_mode": p.get("calculation_mode") or "gl",
        "parents_formula": p.get("parents_formula") if isinstance(p.get("parents_formula"), list) else [],
        "formule": p.get("formule") or "somme",
        "formule_custom": p.get("formule_custom"),
        "is_active": bool(p.get("is_active", True)),
        "updated_at": now,
    }

    # Si on fait un upsert, on ne met created_at qu'à l'insertion
    return doc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--db", default=os.getenv("MONGO_DB_NAME", "assistant_bank_db"))
    parser.add_argument("--collection", default=os.getenv("PCB_POSTES_COLLECTION", DEFAULT_COLLECTION))
    parser.add_argument("--direct", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--org-id", required=True, help="Mongo ObjectId de l'organisation")
    parser.add_argument("--in", required=True, dest="input_path")
    parser.add_argument("--mode", choices=["insert", "upsert"], default="upsert")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    org_id_raw = str(args.org_id).strip()
    org_oid: Optional[ObjectId] = None
    try:
        org_oid = ObjectId(org_id_raw)
    except Exception:
        org_oid = None

    items = _load_items(args.input_path)
    _normalize_parent_code(items)

    client = MongoClient(
        args.mongo_uri,
        directConnection=bool(args.direct),
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=8000,
    )
    db = client[args.db]
    col = db[args.collection]

    # Déterminer si organization_id est stocké en ObjectId ou en string.
    org_query_value: Any
    if org_oid is None:
        org_query_value = org_id_raw
    else:
        # Si aucun doc n'existe en ObjectId, on bascule en string.
        if col.count_documents({"organization_id": org_oid}, limit=1) == 0 and col.count_documents({"organization_id": org_id_raw}, limit=1) > 0:
            org_query_value = org_id_raw
        else:
            org_query_value = org_oid

    existing_by_code: Dict[str, ObjectId] = {}
    if args.mode == "upsert":
        for doc in col.find({"organization_id": org_query_value}, {"_id": 1, "code": 1}):
            code = str(doc.get("code") or "").strip()
            if code and isinstance(doc.get("_id"), ObjectId):
                existing_by_code[code] = doc["_id"]

    created_by_code: Dict[str, ObjectId] = dict(existing_by_code)

    ordered = _sorted_by_hierarchy(items)
    pending = ordered

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
            parent_oid: Optional[ObjectId] = None
            if parent_code:
                parent_oid = created_by_code.get(parent_code)
                if not parent_oid:
                    next_pending.append(p)
                    continue

            # organization_id doit respecter le type stocké dans la collection (ObjectId vs string)
            org_for_doc = org_query_value
            if isinstance(org_for_doc, ObjectId):
                doc = _build_doc(p, organization_id=org_for_doc, parent_id=parent_oid)
            else:
                # _build_doc attend un ObjectId, donc on construit ici manuellement.
                # On garde strictement les mêmes champs que le modèle.
                now = datetime.utcnow()
                doc = {
                    "code": str(p.get("code") or "").strip(),
                    "libelle": p.get("libelle"),
                    "type": p.get("type"),
                    "niveau": int(p.get("niveau") or 1),
                    "parent_id": parent_oid,
                    "parent_code": p.get("parent_code"),
                    "contribution_signe": p.get("contribution_signe") if p.get("contribution_signe") in ["+", "-"] else "+",
                    "organization_id": org_for_doc,
                    "ordre": int(p.get("ordre") or 0),
                    "gl_codes": p.get("gl_codes") if isinstance(p.get("gl_codes"), list) else [],
                    "calculation_mode": p.get("calculation_mode") or "gl",
                    "parents_formula": p.get("parents_formula") if isinstance(p.get("parents_formula"), list) else [],
                    "formule": p.get("formule") or "somme",
                    "formule_custom": p.get("formule_custom"),
                    "is_active": bool(p.get("is_active", True)),
                    "updated_at": now,
                }

            if args.dry_run:
                progressed = True
                continue

            if args.mode == "upsert":
                _id = existing_by_code.get(code)
                if _id:
                    col.update_one(
                        {"_id": _id, "organization_id": org_query_value},
                        {"$set": doc},
                    )
                    created_by_code[code] = _id
                    progressed = True
                else:
                    doc["created_at"] = datetime.utcnow()
                    res = col.insert_one(doc)
                    created_by_code[code] = res.inserted_id
                    progressed = True
            else:
                doc["created_at"] = datetime.utcnow()
                res = col.insert_one(doc)
                created_by_code[code] = res.inserted_id
                progressed = True

        pending = next_pending
        if not progressed:
            break

    if pending:
        missing = []
        for p in pending:
            missing.append({
                "code": str(p.get("code") or "").strip(),
                "parent_code": str(p.get("parent_code") or "").strip(),
            })
        raise SystemExit(
            "Import incomplet: parents manquants ou cycle détecté. Restants: "
            + json.dumps(missing, ensure_ascii=False, indent=2)
        )


if __name__ == "__main__":
    main()
