"""
Script de migration pour créer les catégories initiales de la base de connaissances globale.
À exécuter une seule fois après le déploiement.
"""
import asyncio
from app.core.db import get_database
from app.models.global_knowledge_category import create_category, list_categories


async def init_default_categories():
    """Crée les catégories par défaut si elles n'existent pas."""
    categories_to_create = [
        {
            "name": "Plan Comptable UEMOA",
            "slug": "plan_comptable",
            "description": "Plan comptable officiel de l'UEMOA",
        },
        {
            "name": "Commission Bancaire",
            "slug": "commission_bancaire",
            "description": "Instructions et circulaires de la Commission Bancaire",
        },
        {
            "name": "Lutte contre le Blanchiment (LBC/FT)",
            "slug": "lb_ft",
            "description": "Documents généraux de lutte contre le blanchiment des capitaux et le financement du terrorisme",
        },
        {
            "name": "Base de Connaissances Générale",
            "slug": "general",
            "description": "Base de connaissances générale pour répondre aux utilisateurs",
        },
    ]

    existing_categories = await list_categories(include_inactive=True)
    existing_slugs = {cat["slug"] for cat in existing_categories}

    created_count = 0
    for cat_data in categories_to_create:
        if cat_data["slug"] not in existing_slugs:
            try:
                await create_category(
                    name=cat_data["name"],
                    slug=cat_data["slug"],
                    description=cat_data["description"],
                )
                created_count += 1
                print(f"✅ Catégorie créée: {cat_data['name']}")
            except Exception as e:
                print(f"❌ Erreur lors de la création de '{cat_data['name']}': {e}")
        else:
            print(f"⏭️  Catégorie déjà existante: {cat_data['name']}")

    print(f"\n✅ Migration terminée: {created_count} catégorie(s) créée(s)")


if __name__ == "__main__":
    asyncio.run(init_default_categories())

