"""
Script de migration pour ajouter le champ scope aux chunks existants.
À exécuter une seule fois après le déploiement.
"""
import asyncio
from app.core.db import get_database


async def migrate_existing_chunks():
    """Ajoute scope="ORG" aux chunks existants qui n'ont pas de scope."""
    db = get_database()
    
    # Mettre à jour tous les chunks existants sans scope
    result = await db["document_chunks"].update_many(
        {"scope": {"$exists": False}},  # Chunks sans scope
        {
            "$set": {
                "scope": "ORG"
            }
        }
    )
    
    print(f"✅ Migration terminée: {result.modified_count} chunks mis à jour avec scope='ORG'")
    
    # Vérifier qu'il n'y a plus de chunks sans scope
    count_without_scope = await db["document_chunks"].count_documents({"scope": {"$exists": False}})
    if count_without_scope > 0:
        print(f"⚠️  Attention: {count_without_scope} chunks n'ont toujours pas de scope")
    else:
        print("✅ Tous les chunks ont maintenant un scope")


if __name__ == "__main__":
    asyncio.run(migrate_existing_chunks())

