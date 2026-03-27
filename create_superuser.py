"""
Script pour créer un super utilisateur (admin).

Usage interactif:
    python create_superuser.py

Usage avec arguments:
    python create_superuser.py --email admin@example.com --password secret123 --name "Admin User"
"""
import asyncio
import sys
import argparse
from datetime import datetime
from bson import ObjectId

from app.core.db import get_database, get_client
from app.core.security import hash_password

USERS_COLLECTION = "users"


async def create_superuser(email: str, password: str, full_name: str, force_update: bool = False):
    """Crée un super utilisateur."""
    db = get_database()
    
    # Vérifier si l'utilisateur existe déjà
    existing_user = await db[USERS_COLLECTION].find_one({"email": email})
    if existing_user:
        print(f"[INFO] L'utilisateur avec l'email '{email}' existe deja.")
        if not force_update:
            response = input("Voulez-vous reinitialiser son mot de passe? (o/n): ")
            if response.lower() != 'o':
                print("Annule.")
                return None
        
        # Mettre à jour le mot de passe et s'assurer que organization_id est None pour super admin
        new_password_hash = hash_password(password)
        await db[USERS_COLLECTION].update_one(
            {"email": email},
            {"$set": {
                "password_hash": new_password_hash,
                "role": "superadmin",
                "organization_id": None,  # Super admin n'a pas d'organisation
                "is_active": True,
                "updated_at": datetime.utcnow()
            }}
        )
        print(f"[OK] Mot de passe de l'utilisateur '{email}' mis a jour.")
        print(f"[OK] Role defini comme 'superadmin'.")
        print(f"[OK] Organization_id mis a None (super admin).")
        return existing_user["_id"]
    
    # Le super admin n'est PAS lié à une organisation
    # Il gère toutes les organisations du système
    
    # Créer le super utilisateur sans organization_id
    doc = {
        "email": email,
        "full_name": full_name,
        "organization_id": None,  # Super admin n'a pas d'organisation
        "password_hash": hash_password(password),
        "role": "superadmin",
        "is_active": True,
        "created_at": datetime.utcnow(),
    }
    
    result = await db[USERS_COLLECTION].insert_one(doc)
    user_id = result.inserted_id
    
    print(f"\n{'='*60}")
    print(f"[OK] Super utilisateur cree avec succes!")
    print(f"{'='*60}")
    print(f"Email: {email}")
    print(f"Nom: {full_name}")
    print(f"Rôle: superadmin (super administrateur)")
    print(f"Organisation: Aucune (gère toutes les organisations)")
    print(f"User ID: {user_id}")
    print(f"{'='*60}\n")
    
    return user_id


async def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Créer un super utilisateur (admin)")
    parser.add_argument("--email", type=str, help="Email du super utilisateur")
    parser.add_argument("--password", type=str, help="Mot de passe")
    parser.add_argument("--name", type=str, help="Nom complet", default="Administrateur")
    parser.add_argument("--force", action="store_true", help="Forcer la mise à jour si l'utilisateur existe déjà")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Création d'un super utilisateur")
    print("="*60 + "\n")
    
    # Récupérer les informations (arguments ou input interactif)
    if args.email:
        email = args.email.strip()
    else:
        email = input("Email du super utilisateur: ").strip()
    
    if not email:
        print("[ERREUR] L'email est requis.")
        sys.exit(1)
    
    if args.password:
        password = args.password.strip()
    else:
        import getpass
        password = getpass.getpass("Mot de passe: ").strip()
    
    if not password:
        print("[ERREUR] Le mot de passe est requis.")
        sys.exit(1)
    
    if len(password) < 6:
        print("[ERREUR] Le mot de passe doit contenir au moins 6 caracteres.")
        sys.exit(1)
    
    if args.name:
        full_name = args.name.strip()
    else:
        full_name = input("Nom complet (défaut: Administrateur): ").strip()
        if not full_name:
            full_name = "Administrateur"
            print(f"Nom complet par défaut: {full_name}")
    
    try:
        await create_superuser(email, password, full_name, force_update=args.force)
    except Exception as e:
        print(f"\n[ERREUR] Erreur lors de la creation: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Fermer la connexion MongoDB
        client = get_client()
        client.close()


if __name__ == "__main__":
    asyncio.run(main())

