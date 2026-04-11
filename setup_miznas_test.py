"""
Script de création de l'organisation MIZNAS TEST
-------------------------------------------------
Crée :
  - L'organisation  MIZNAS (code: MIZNAS_TEST)
  - Une licence test active (valable 1 an, 100 utilisateurs)
  - Les permissions d'accès : formations + questions uniquement
  - Un quota de 5 questions/mois
  - Un utilisateur test : test@miznas.com / MiznasTest2024!

Usage :
    python setup_miznas_test.py
"""

import asyncio
from datetime import datetime, timedelta
from bson import ObjectId

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.core.db import get_database
from app.core.security import hash_password


# ── Config ────────────────────────────────────────────────────────────────────

ORG_NAME        = "MIZNAS"
ORG_CODE        = "MIZNAS_TEST"
ORG_COUNTRY     = "UEMOA"
QUESTION_QUOTA  = 5          # questions/mois pour les utilisateurs test
LICENSE_PLAN    = "test"
MAX_USERS       = 100

TEST_USER_EMAIL    = "test@miznas.com"
TEST_USER_PASSWORD = "MiznasTest2024!"
TEST_USER_NAME     = "Utilisateur Test"

# Onglets accessibles
ALLOWED_TABS = ["formations", "questions"]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_or_create_org(db) -> str:
    existing = await db["organizations"].find_one({"code": ORG_CODE})
    if existing:
        print(f"  + Organisation existante : {existing['_id']}")
        return str(existing["_id"])

    result = await db["organizations"].insert_one({
        "name": ORG_NAME,
        "code": ORG_CODE,
        "country": ORG_COUNTRY,
        "status": "active",
        "question_quota": QUESTION_QUOTA,
        "created_at": datetime.utcnow(),
    })
    print(f"  + Organisation creee : {result.inserted_id}")
    return str(result.inserted_id)


async def ensure_question_quota(db, org_id: str):
    """S'assure que le champ question_quota est bien sur l'org."""
    await db["organizations"].update_one(
        {"_id": ObjectId(org_id)},
        {"$set": {"question_quota": QUESTION_QUOTA}}
    )
    print(f"  + Quota questions : {QUESTION_QUOTA}/mois")


async def get_or_create_license(db, org_id: str) -> str:
    existing = await db["licenses"].find_one({
        "organization_id": ObjectId(org_id),
        "status": "active"
    })
    if existing:
        print(f"  + Licence existante : {existing['_id']}")
        return str(existing["_id"])

    now = datetime.utcnow()
    result = await db["licenses"].insert_one({
        "organization_id": ObjectId(org_id),
        "plan": LICENSE_PLAN,
        "max_users": MAX_USERS,
        "start_date": now,
        "end_date": now + timedelta(days=365),
        "status": "active",
        "features": ALLOWED_TABS,
        "created_at": now,
    })
    print(f"  + Licence creee : {result.inserted_id}")
    return str(result.inserted_id)


async def setup_tab_permissions(db, org_id: str):
    """Configure les permissions d'onglets : formations + questions activés, tout le reste désactivé."""
    all_tabs = ["formations", "questions", "credit", "pcb", "impayes"]

    # Règle SEGMENT sans restriction = accès à tous les utilisateurs de l'org
    open_rule = {
        "rule_type": "SEGMENT",
        "department_id": None,
        "service_id": None,
        "role_departement": None,
        "user_id": None,
    }

    configured_tabs = []
    for tab_id in all_tabs:
        enabled = tab_id in ALLOWED_TABS
        configured_tabs.append({
            "tab_id": tab_id,
            "enabled": enabled,
            "rules": [open_rule] if enabled else [],
        })

    await db["tab_permissions"].update_one(
        {"organization_id": ObjectId(org_id)},
        {"$set": {
            "organization_id": ObjectId(org_id),
            "tabs": configured_tabs,
            "updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    print(f"  + Permissions onglets : {ALLOWED_TABS} actives")


async def get_or_create_test_user(db, org_id: str) -> str:
    existing = await db["users"].find_one({"email": TEST_USER_EMAIL})
    if existing:
        print(f"  + Utilisateur test existant : {existing['_id']}")
        return str(existing["_id"])

    result = await db["users"].insert_one({
        "email": TEST_USER_EMAIL,
        "full_name": TEST_USER_NAME,
        "password_hash": hash_password(TEST_USER_PASSWORD),
        "role": "user",
        "organization_id": ObjectId(org_id),
        "is_active": True,
        "created_at": datetime.utcnow(),
    })
    print(f"  + Utilisateur test cree : {result.inserted_id}")
    return str(result.inserted_id)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("\n===========================================")
    print("   SETUP ORGANISATION MIZNAS TEST")
    print("===========================================\n")

    db = get_database()

    print("1. Organisation...")
    org_id = await get_or_create_org(db)

    print("2. Quota questions...")
    await ensure_question_quota(db, org_id)

    print("3. Licence...")
    await get_or_create_license(db, org_id)

    print("4. Permissions onglets...")
    await setup_tab_permissions(db, org_id)

    print("5. Utilisateur test...")
    await get_or_create_test_user(db, org_id)

    print("\n-------------------------------------------")
    print("OK  Setup termine !\n")
    print(f"  Organisation  : {ORG_NAME} (code: {ORG_CODE})")
    print(f"  Onglets actifs: {', '.join(ALLOWED_TABS)}")
    print(f"  Quota         : {QUESTION_QUOTA} questions / mois")
    print(f"  Compte test   : {TEST_USER_EMAIL}")
    print(f"  Mot de passe  : {TEST_USER_PASSWORD}")
    print("-------------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
