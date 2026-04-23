"""
Migration : met email_verified=true sur tous les users existants qui n'ont
pas ce champ (ou l'ont a false). Necessaire pour ne pas bloquer la connexion
des comptes crees avant l'introduction du flow OTP.

Usage :
    # DRY-RUN (par defaut : ne modifie rien, affiche seulement le decompte)
    python scripts/migrate_email_verified.py --mongo-uri "mongodb+srv://..." --db assistant_banque_db --dry-run

    # Migration reelle
    python scripts/migrate_email_verified.py --mongo-uri "mongodb+srv://..." --db assistant_banque_db

Le filtre cible *tous* les users (demo ET non-demo) sans email_verified=true,
car aucun user existant n'a valide par OTP (le flow n'existait pas).
"""
import argparse
import asyncio
import sys

from motor.motor_asyncio import AsyncIOMotorClient


FILTER = {
    "$or": [
        {"email_verified": {"$exists": False}},
        {"email_verified": False},
    ]
}


async def run(mongo_uri: str, db_name: str, dry_run: bool) -> int:
    client = AsyncIOMotorClient(mongo_uri)
    try:
        db = client[db_name]
        col = db["users"]

        total_users = await col.count_documents({})
        affected = await col.count_documents(FILTER)

        print(f"[INFO] Base          : {db_name}")
        print(f"[INFO] Users total   : {total_users}")
        print(f"[INFO] A migrer      : {affected}  (sans email_verified=true)")
        print(f"[INFO] Mode          : {'DRY-RUN' if dry_run else 'APPLY'}")

        if affected == 0:
            print("[OK] Rien a faire.")
            return 0

        # Apercu des 10 premiers comptes concernes
        print()
        print("[PREVIEW] 10 premiers users concernes :")
        cursor = col.find(
            FILTER,
            {"email": 1, "is_demo": 1, "email_verified": 1, "created_at": 1},
        ).limit(10)
        async for doc in cursor:
            is_demo = doc.get("is_demo", False)
            verified = doc.get("email_verified", "<absent>")
            created = doc.get("created_at")
            print(
                f"  - {doc.get('email', '?')} | is_demo={is_demo} | "
                f"email_verified={verified} | created_at={created}"
            )

        if dry_run:
            print()
            print("[DRY-RUN] Aucune modification ecrite. Relancez sans --dry-run pour appliquer.")
            return 0

        print()
        print("[APPLY] Mise a jour en cours...")
        result = await col.update_many(FILTER, {"$set": {"email_verified": True}})
        print(f"[OK] Matched={result.matched_count}, Modified={result.modified_count}")
        return 0
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Migration email_verified=true")
    parser.add_argument("--mongo-uri", required=True, help="URI MongoDB")
    parser.add_argument("--db", default="assistant_banque_db", help="Nom de la base")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'applique rien, affiche uniquement le decompte",
    )
    args = parser.parse_args()

    try:
        rc = asyncio.run(run(args.mongo_uri, args.db, args.dry_run))
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(rc)


if __name__ == "__main__":
    main()
