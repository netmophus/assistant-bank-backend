"""
Script pour corriger le statut d'un document global qui reste en "draft" alors que les chunks sont "published".
"""
import asyncio
from bson import ObjectId
from app.core.db import get_database
from app.models.documents import get_global_document_by_id, update_global_document_status

async def fix_document_status(document_id: str):
    """Corrige le statut d'un document global."""
    db = get_database()
    
    # Récupérer le document
    doc = await get_global_document_by_id(document_id)
    if not doc:
        print(f"❌ Document {document_id} non trouvé")
        return
    
    print(f"📄 Document trouvé: {doc.get('titre', doc.get('filename'))}")
    print(f"   Statut actuel: {doc.get('status')}")
    print(f"   Scope: {doc.get('scope')}")
    print(f"   Total chunks: {doc.get('total_chunks', 0)}")
    
    # Vérifier le statut des chunks
    chunks = await db["document_chunks"].find({
        "document_id": ObjectId(document_id),
        "scope": "GLOBAL"
    }).limit(5).to_list(length=5)
    
    if chunks:
        print(f"\n📊 Statut des chunks (échantillon de {len(chunks)}):")
        for chunk in chunks:
            print(f"   Chunk {chunk.get('chunk_index')}: status={chunk.get('status')}")
    
    # Si les chunks sont "published" mais le document est "draft" ou "processed", corriger
    if chunks and chunks[0].get("status") == "published":
        current_status = doc.get("status")
        if current_status in ["draft", "processed"]:
            print(f"\n🔧 Correction du statut du document de '{current_status}' en 'published'...")
            await update_global_document_status(document_id, "published")
            
            # Vérifier après correction
            updated_doc = await get_global_document_by_id(document_id)
            if updated_doc:
                print(f"✅ Statut après correction: {updated_doc.get('status')}")
            else:
                print(f"❌ Erreur: document non trouvé après correction")
        else:
            print(f"\nℹ️  Statut actuel '{current_status}' est déjà correct")
    else:
        print(f"\nℹ️  Aucune correction nécessaire (chunks non publiés)")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python fix_document_status.py <document_id>")
        print("Exemple: python fix_document_status.py 6943da39294d1b535c6297c4")
        sys.exit(1)
    
    document_id = sys.argv[1]
    asyncio.run(fix_document_status(document_id))

