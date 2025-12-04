"""
Script pour mettre à jour le rôle d'un utilisateur existant.

Usage:
    python update_user_role.py --email adminbsic@bsic.ne --role admin
"""
import asyncio
import sys
import argparse
from datetime import datetime
from bson import ObjectId

from app.core.db import get_database, get_client

USERS_COLLECTION = "users"


async def update_user_role(email: str, role: str):
    """Met à jour le rôle d'un utilisateur."""
    db = get_database()
    
    # Vérifier si l'utilisateur existe
    user = await db[USERS_COLLECTION].find_one({"email": email})
    if not user:
        print(f"❌ L'utilisateur avec l'email '{email}' n'existe pas.")
        return False
    
    # Vérifier que le rôle est valide
    valid_roles = ["user", "admin", "superadmin"]
    if role not in valid_roles:
        print(f"❌ Rôle invalide. Rôles valides: {', '.join(valid_roles)}")
        return False
    
    # Si on essaie de créer un super admin, vérifier qu'il n'a pas d'organisation
    if role == "superadmin" and user.get("organization_id"):
        print(f"⚠ L'utilisateur a une organisation ({user.get('organization_id')}).")
        print(f"  L'organization_id sera mis à None pour le super admin.")
        # Mettre organization_id à None pour super admin
        await db[USERS_COLLECTION].update_one(
            {"email": email},
            {"$set": {"organization_id": None}}
        )
    
    # Si on définit comme admin d'organisation, vérifier qu'il a une organisation
    if role == "admin" and not user.get("organization_id"):
        print(f"⚠ L'utilisateur n'a pas d'organisation.")
        print(f"  Un admin d'organisation doit avoir une organisation assignée.")
    
    # Mettre à jour le rôle
    await db[USERS_COLLECTION].update_one(
        {"email": email},
        {"$set": {
            "role": role,
            "updated_at": datetime.utcnow()
        }}
    )
    
    print(f"\n{'='*60}")
    print(f"✓ Rôle de l'utilisateur '{email}' mis à jour avec succès!")
    print(f"{'='*60}")
    print(f"Email: {email}")
    print(f"Nom: {user.get('full_name', 'N/A')}")
    print(f"Ancien rôle: {user.get('role', 'user')}")
    print(f"Nouveau rôle: {role}")
    print(f"Organisation: {user.get('organization_id', 'Aucune')}")
    print(f"{'='*60}\n")
    
    return True


async def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Mettre à jour le rôle d'un utilisateur")
    parser.add_argument("--email", type=str, required=True, help="Email de l'utilisateur")
    parser.add_argument("--role", type=str, required=True, choices=["user", "admin", "superadmin"], help="Nouveau rôle")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Mise à jour du rôle d'un utilisateur")
    print("="*60 + "\n")
    
    try:
        success = await update_user_role(args.email.strip(), args.role.strip())
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur lors de la mise à jour: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Fermer la connexion MongoDB
        client = get_client()
        client.close()


if __name__ == "__main__":
    asyncio.run(main())

