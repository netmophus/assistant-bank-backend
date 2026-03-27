import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient


def _serialize(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--db", default=os.getenv("MONGO_DB_NAME", "assistant_bank_db"))
    parser.add_argument("--collection", default=os.getenv("PCB_POSTES_COLLECTION", "pcb_postes_reglementaires"))
    parser.add_argument("--direct", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--org-id", required=True, help="Mongo ObjectId de l'organisation")
    parser.add_argument("--type", default=None, dest="poste_type")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--out", required=True)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    org_id_raw = str(args.org_id).strip()
    org_oid: Optional[ObjectId] = None
    try:
        org_oid = ObjectId(org_id_raw)
    except Exception:
        org_oid = None

    client = MongoClient(
        args.mongo_uri,
        directConnection=bool(args.direct),
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=8000,
    )
    db = client[args.db]
    col = db[args.collection]

    query: Dict[str, Any] = {"organization_id": org_oid} if org_oid is not None else {"organization_id": org_id_raw}
    if args.poste_type:
        query["type"] = str(args.poste_type)
    if not args.include_inactive:
        query["is_active"] = True

    # Certains environnements stockent organization_id en string et non ObjectId.
    # Si la query ne remonte rien en ObjectId, on retente en string.
    org_id_type = "objectid" if org_oid is not None else "string"
    if org_oid is not None:
        probe = dict(query)
        probe["organization_id"] = org_oid
        if col.count_documents(probe, limit=1) == 0:
            query["organization_id"] = org_id_raw
            org_id_type = "string"

    if args.debug:
        try:
            total_in_col = col.estimated_document_count()
        except Exception:
            total_in_col = None

        sys.stderr.write(
            "\n".join(
                [
                    "[DEBUG] Connected:",
                    f"[DEBUG] mongo_uri={args.mongo_uri}",
                    f"[DEBUG] db={args.db}",
                    f"[DEBUG] collection={args.collection}",
                    f"[DEBUG] estimated_document_count={total_in_col}",
                    f"[DEBUG] org_id_raw={org_id_raw}",
                    f"[DEBUG] org_oid_parsed={str(org_oid) if org_oid is not None else None}",
                    f"[DEBUG] org_id_type_selected={org_id_type}",
                    f"[DEBUG] query={query}",
                    "",
                ]
            )
            + "\n"
        )

        # Show sample docs (first 5) with organization_id types
        sample = list(col.find({}, {"_id": 1, "organization_id": 1, "code": 1, "type": 1}).limit(5))
        for i, d in enumerate(sample):
            oid = d.get("organization_id")
            sys.stderr.write(
                f"[DEBUG] sample[{i}] code={d.get('code')} type={d.get('type')} organization_id={oid} organization_id_pytype={type(oid).__name__}\n"
            )

        # List a few distinct organization_id values (best-effort)
        try:
            pipeline = [
                {"$group": {"_id": "$organization_id", "n": {"$sum": 1}}},
                {"$sort": {"n": -1}},
                {"$limit": 10},
            ]
            rows = list(col.aggregate(pipeline))
            for r in rows:
                _id = r.get("_id")
                n = r.get("n")
                sys.stderr.write(f"[DEBUG] org_id_distinct value={_id} pytype={type(_id).__name__} count={n}\n")
        except Exception as e:
            sys.stderr.write(f"[DEBUG] distinct_org_ids_failed error={e}\n")

    cursor = col.find(query).sort([("ordre", 1), ("code", 1)])
    items: List[Dict[str, Any]] = []
    for doc in cursor:
        items.append(_serialize(doc))

    payload: Dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "mongo_uri": args.mongo_uri,
        "db": args.db,
        "collection": args.collection,
        "organization_id": org_id_raw,
        "organization_id_type": org_id_type,
        "filters": {
            "type": args.poste_type,
            "include_inactive": bool(args.include_inactive),
        },
        "count": len(items),
        "items": items,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
