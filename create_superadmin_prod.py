"""
Script pour créer un superadmin directement en production (MongoDB Atlas).

Usage:
    python create_superadmin_prod.py \
        --mongo-uri "mongodb+srv://user:pass@cluster.mongodb.net/dbname" \
        --email admin@novabank.com \
        --password MonMotDePasse123 \
        --name "Super Admin"

Ou avec les variables d'environnement :
    set MONGO_URI=mongodb+srv://...
    set DATABASE_NAME=assistant_banque_db
    python create_superadmin_prod.py --email ... --password ... --name ...
"""

import asyncio
import sys
import argparse
import os
from datetime import datetime

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

USERS_COLLECTION = "users"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def create_superadmin(mongo_uri: str, db_name: str, email: str, password: str, full_name: str):
    print(f"\n{'='*60}")
    print("  Création du SuperAdmin en production")
    print(f"{'='*60}")
    print(f"  Base     : {db_name}")
    print(f"  Email    : {email}")
    print(f"  Nom      : {full_name}")
    print(f"{'='*60}\n")

    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]

    try:
        # Vérifier si l'utilisateur existe déjà
        existing = await db[USERS_COLLECTION].find_one({"email": email})

        if existing:
            print(f"[INFO] L'utilisateur '{email}' existe déjà.")
            confirm = input("Voulez-vous réinitialiser son mot de passe et le passer en superadmin ? (o/n) : ").strip().lower()
            if confirm != 'o':
                print("[ANNULÉ]")
                return

            await db[USERS_COLLECTION].update_one(
                {"email": email},
                {"$set": {
                    "password_hash": hash_password(password),
                    "role": "superadmin",
                    "organization_id": None,
                    "is_active": True,
                    "updated_at": datetime.utcnow(),
                }}
            )
            print(f"\n[OK] Compte '{email}' mis à jour → superadmin")
            return

        # Créer le superadmin
        doc = {
            "email": email,
            "full_name": full_name,
            "organization_id": None,
            "password_hash": hash_password(password),
            "role": "superadmin",
            "is_active": True,
            "created_at": datetime.utcnow(),
        }

        result = await db[USERS_COLLECTION].insert_one(doc)

        print(f"[OK] SuperAdmin créé avec succès !")
        print(f"     ID       : {result.inserted_id}")
        print(f"     Email    : {email}")
        print(f"     Rôle     : superadmin")
        print(f"     Org      : aucune (accès global)\n")

    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Créer un superadmin en production")
    parser.add_argument("--mongo-uri", type=str, help="URI MongoDB Atlas (ou via MONGO_URI env)")
    parser.add_argument("--db-name",   type=str, help="Nom de la base (ou via DATABASE_NAME env)", default=None)
    parser.add_argument("--email",     type=str, required=True,  help="Email du superadmin")
    parser.add_argument("--password",  type=str, required=True,  help="Mot de passe (min 6 caractères)")
    parser.add_argument("--name",      type=str, default="Super Admin", help="Nom complet")
    args = parser.parse_args()

    # Récupérer le mongo_uri
    mongo_uri = args.mongo_uri or os.getenv("MONGO_URI")
    if not mongo_uri:
        print("[ERREUR] --mongo-uri requis ou variable d'environnement MONGO_URI non définie.")
        sys.exit(1)

    # Récupérer le nom de la base
    db_name = args.db_name or os.getenv("DATABASE_NAME") or os.getenv("MONGO_DB_NAME") or "assistant_banque_db"

    # Valider le mot de passe
    if len(args.password) < 6:
        print("[ERREUR] Le mot de passe doit contenir au moins 6 caractères.")
        sys.exit(1)

    asyncio.run(create_superadmin(mongo_uri, db_name, args.email, args.password, args.name))


if __name__ == "__main__":
    main()
