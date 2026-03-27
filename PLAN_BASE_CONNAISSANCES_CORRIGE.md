# 📚 Plan d'Implémentation Corrigé : Base de Connaissances Globale

## 🎯 Objectif

Ajouter une base de connaissances globale gérée par le superadmin, utilisée par l'IA en complément de la base organisationnelle existante, **sans créer de nouvelle collection**.

---

## 📋 1. Schéma Minimal - Champs à Ajouter

### Collection `document_chunks` (modification)

**Champs à ajouter/modifier :**

```javascript
{
  "_id": ObjectId("..."),
  "document_id": ObjectId("..."),
  "organization_id": ObjectId("...") | null,  // ⚠️ MODIFIÉ : nullable pour GLOBAL
  "scope": "ORG" | "GLOBAL",                    // ⚠️ NOUVEAU : champ obligatoire
  "category": "procedures" | "plan_comptable" | "commission_bancaire" | "lb_ft" | "general",
  "chunk_index": 0,
  "content": "...",
  "embedding": [...],
  "page_number": 1,
  "section": "Introduction",
  "status": "published" | "draft" | "archived"  // ⚠️ NOUVEAU : pour GLOBAL uniquement
}
```

**Règles :**
- `scope="ORG"` → `organization_id` obligatoire (ObjectId)
- `scope="GLOBAL"` → `organization_id=null` obligatoire
- `status` : utilisé uniquement pour `scope="GLOBAL"` (peut être null pour ORG)

### Collection `documents` (nouvelle collection pour documents globaux)

**Structure proposée :**

```javascript
{
  "_id": ObjectId("..."),
  "scope": "GLOBAL",                           // Toujours "GLOBAL" pour cette collection
  "titre": "Plan Comptable UEMOA 2024",
  "description": "Plan comptable officiel de l'UEMOA",
  "category": "plan_comptable" | "commission_bancaire" | "lb_ft" | "general",
  "authority": "Commission Bancaire UEMOA",    // Autorité émettrice
  "reference": "CB-UEMOA-2024-001",            // Référence officielle
  "version": "1.0",
  "effective_date": ISODate("2024-01-01"),    // Date d'entrée en vigueur
  "status": "draft" | "published" | "archived",
  "filename": "...",
  "original_filename": "...",
  "file_type": "pdf" | "word" | "excel",
  "file_path": "uploads/global_knowledge/...",
  "file_size": 1024000,
  "uploaded_by": ObjectId("..."),              // ID du superadmin
  "upload_date": ISODate("..."),
  "published_date": ISODate("..."),            // Date de publication
  "total_chunks": 25,
  "extracted_text": "..."
}
```

**Alternative : Réutiliser `documents` existante**

Si on veut réutiliser la collection `documents` existante :

```javascript
{
  "_id": ObjectId("..."),
  "organization_id": null,                    // ⚠️ MODIFIÉ : null pour GLOBAL
  "scope": "GLOBAL",                           // ⚠️ NOUVEAU
  "titre": "Plan Comptable UEMOA 2024",        // ⚠️ NOUVEAU
  "description": "...",
  "category": "plan_comptable",
  "authority": "Commission Bancaire UEMOA",    // ⚠️ NOUVEAU
  "reference": "CB-UEMOA-2024-001",            // ⚠️ NOUVEAU
  "version": "1.0",                            // ⚠️ NOUVEAU
  "effective_date": ISODate("..."),            // ⚠️ NOUVEAU
  "status": "published",                       // ⚠️ MODIFIÉ : utilisé pour GLOBAL
  "filename": "...",
  "original_filename": "...",
  "file_type": "pdf",
  "file_path": "...",
  "file_size": 1024000,
  "uploaded_by": ObjectId("..."),
  "upload_date": ISODate("..."),
  "published_date": ISODate("..."),            // ⚠️ NOUVEAU
  "total_chunks": 25,
  "extracted_text": "..."
}
```

**Recommandation : Réutiliser `documents` avec `scope` et `organization_id` nullable**

---

## 🔧 2. Patch sur `search_document_chunks`

### Fonction Modifiée

```python
async def search_document_chunks(
    organization_id: Optional[str] = None,  # ⚠️ MODIFIÉ : optionnel
    query_embedding: List[float],
    category: Optional[str] = None,
    scope: Optional[str] = None,  # ⚠️ NOUVEAU : "ORG" | "GLOBAL" | None (les deux)
    limit: int = 5,
) -> List[dict]:
    """
    Recherche sémantique dans les chunks par similarité cosinus.
    
    Args:
        organization_id: ID de l'organisation (requis si scope="ORG")
        query_embedding: Vecteur d'embedding de la question
        category: Filtrer par catégorie (optionnel)
        scope: "ORG" | "GLOBAL" | None (recherche dans les deux)
        limit: Nombre maximum de résultats
    
    Returns:
        Liste des chunks les plus pertinents
    """
    if not query_embedding:
        return []
    
    db = get_database()
    
    # Construction du filtre selon le scope
    query = {
        "embedding": {"$exists": True, "$ne": []}
    }
    
    if scope == "ORG":
        # Chunks organisationnels
        if not organization_id:
            raise ValueError("organization_id requis pour scope='ORG'")
        query["organization_id"] = ObjectId(organization_id)
        query["scope"] = "ORG"
    
    elif scope == "GLOBAL":
        # Chunks globaux publiés uniquement
        query["organization_id"] = None
        query["scope"] = "GLOBAL"
        query["status"] = "published"  # Seulement les documents publiés
    
    elif scope is None:
        # Recherche dans les deux (pour compatibilité)
        # On ne filtre pas par organization_id ni scope
        pass
    
    if category:
        query["category"] = category
    
    # Récupérer tous les chunks avec embeddings
    cursor = db[DOCUMENT_CHUNKS_COLLECTION].find(query)
    all_chunks = await cursor.to_list(length=None)
    
    if not all_chunks:
        return []
    
    # Calculer la similarité cosinus pour chaque chunk
    scored_chunks = []
    for chunk in all_chunks:
        chunk_embedding = chunk.get("embedding", [])
        if not chunk_embedding or len(chunk_embedding) != len(query_embedding):
            continue
        
        similarity = cosine_similarity(query_embedding, chunk_embedding)
        scored_chunks.append({
            "chunk": chunk,
            "similarity": similarity
        })
    
    # Trier par similarité décroissante
    scored_chunks.sort(key=lambda x: x["similarity"], reverse=True)
    top_chunks = scored_chunks[:limit]
    
    # Filtrer les chunks invalides
    error_messages = [
        "Document PDF vide ou non lisible",
        "Aucun texte n'a pu être extrait",
        "Document vide ou non lisible",
    ]
    
    results = []
    for item in top_chunks:
        chunk = item["chunk"]
        content = chunk.get("content", "").strip()
        
        if any(error_msg.lower() in content.lower() for error_msg in error_messages):
            continue
        
        if not content or len(content) < 20:
            continue
        
        document_id = str(chunk["document_id"])
        
        # Récupérer le nom du document
        doc = await db[DOCUMENTS_COLLECTION].find_one({"_id": chunk["document_id"]})
        document_filename = doc.get("original_filename", doc.get("filename", "Document")) if doc else "Document"
        
        # Pour GLOBAL, ajouter les métadonnées supplémentaires
        result = {
            "id": str(chunk["_id"]),
            "document_id": document_id,
            "document_filename": document_filename,
            "content": content,
            "chunk_index": chunk["chunk_index"],
            "page_number": chunk.get("page_number"),
            "section": chunk.get("section"),
            "similarity": item["similarity"],
            "scope": chunk.get("scope", "ORG"),  # ⚠️ NOUVEAU
        }
        
        # Ajouter métadonnées pour GLOBAL
        if chunk.get("scope") == "GLOBAL" and doc:
            result["authority"] = doc.get("authority")
            result["reference"] = doc.get("reference")
            result["version"] = doc.get("version")
        
        results.append(result)
    
    return results
```

---

## 🤖 3. Patch sur `generate_question_answer`

### Fonction Modifiée

```python
async def generate_question_answer(
    question: str,
    context: Optional[str] = None,
    user_department: Optional[str] = None,
    user_service: Optional[str] = None,
    organization_id: Optional[str] = None
) -> str:
    """
    Génère une réponse à une question posée par un utilisateur.
    Recherche hybride : documents ORG + base de connaissances GLOBAL.
    """
    if not client:
        return _generate_mock_question_answer(question)
    
    try:
        system_prompt = """Tu es Fahimta AI, un assistant expert en formation bancaire spécialisé dans la réglementation UEMOA.
Tu dois répondre aux questions des utilisateurs de manière claire, précise et pédagogique.
Tes réponses doivent être techniques, conformes à la réglementation UEMOA, et adaptées au contexte bancaire.
Utilise un langage professionnel mais accessible, avec des exemples concrets lorsque c'est pertinent.
Structure tes réponses de manière claire avec des titres si nécessaire.

IMPORTANT - Formules mathématiques:
- N'utilise JAMAIS de notation LaTeX (pas de \\[ \\], \\( \\), $$, ou commandes LaTeX)
- Écris toutes les formules en texte lisible et compréhensible
- Utilise des formats comme: "Ratio = Résultat Net / Capitaux Propres"
- Pour les fractions, utilise: "(numérateur) / (dénominateur)" ou "numérateur divisé par dénominateur"
- Pour les racines carrées, utilise: "√(valeur)" ou "racine carrée de valeur"
- Sois explicite et descriptif dans tes formules pour qu'elles soient facilement compréhensibles"""
        
        # Recherche hybride : ORG puis GLOBAL
        org_context = ""
        global_context = ""
        
        if organization_id:
            try:
                from app.services.embedding_service import generate_embedding
                from app.models.documents import search_document_chunks
                
                # Générer l'embedding de la question
                question_embedding = await generate_embedding(question)
                
                if question_embedding:
                    # 1. Recherche dans documents organisationnels (limit 5)
                    org_chunks = await search_document_chunks(
                        organization_id=organization_id,
                        query_embedding=question_embedding,
                        scope="ORG",
                        limit=5
                    )
                    
                    if org_chunks:
                        org_context = "\n\n## 📁 Contexte de votre organisation:\n\n"
                        for i, chunk in enumerate(org_chunks, 1):
                            source_info = []
                            if chunk.get("page_number"):
                                source_info.append(f"Page {chunk['page_number']}")
                            if chunk.get("section"):
                                source_info.append(f"Section: {chunk['section']}")
                            if chunk.get("document_filename"):
                                source_info.append(f"Document: {chunk['document_filename']}")
                            
                            source = f" ({', '.join(source_info)})" if source_info else ""
                            org_context += f"**Extrait {i}**{source}:\n{chunk.get('content', '')}\n\n"
                    
                    # 2. Recherche dans base de connaissances globale (limit 3)
                    global_chunks = await search_document_chunks(
                        organization_id=None,  # Pas nécessaire pour GLOBAL
                        query_embedding=question_embedding,
                        scope="GLOBAL",
                        limit=3
                    )
                    
                    if global_chunks:
                        global_context = "\n\n## 🌐 Base de Connaissances Globale (Références Officielles):\n\n"
                        for i, chunk in enumerate(global_chunks, 1):
                            source_info = []
                            if chunk.get("authority"):
                                source_info.append(f"Source: {chunk['authority']}")
                            if chunk.get("reference"):
                                source_info.append(f"Réf: {chunk['reference']}")
                            if chunk.get("version"):
                                source_info.append(f"v{chunk['version']}")
                            if chunk.get("page_number"):
                                source_info.append(f"Page {chunk['page_number']}")
                            if chunk.get("section"):
                                source_info.append(f"Section: {chunk['section']}")
                            if chunk.get("document_filename"):
                                source_info.append(f"Document: {chunk['document_filename']}")
                            
                            source = f" ({', '.join(source_info)})" if source_info else ""
                            global_context += f"**Référence {i}**{source}:\n{chunk.get('content', '')}\n\n"
            
            except Exception as e:
                print(f"Erreur lors de la recherche dans la base de connaissances: {e}")
                # Continuer sans la base de connaissances si erreur
        
        # Construire le prompt utilisateur
        user_prompt = f"""Question de l'utilisateur:
{question}
"""
        
        if context:
            user_prompt += f"""
Contexte fourni par l'utilisateur:
{context}
"""
        
        # Ajouter les contextes (ORG puis GLOBAL)
        if org_context:
            user_prompt += org_context
        
        if global_context:
            user_prompt += global_context
        
        if user_department:
            user_prompt += f"""
Département de l'utilisateur: {user_department}
"""
        
        if user_service:
            user_prompt += f"""
Service de l'utilisateur: {user_service}
"""
        
        user_prompt += """
Instructions:
- Réponds de manière complète et détaillée à la question
- Si des extraits de la base de connaissances sont fournis, utilise-les comme référence principale
- Priorise les informations de votre organisation si disponibles, puis complète avec les références officielles globales
- Cite les sources (document, page, référence officielle) quand tu utilises des informations de la base de connaissances
- Utilise des exemples concrets liés au secteur bancaire UEMOA si pertinent
- Structure ta réponse avec des titres (##) et des listes si nécessaire
- Assure-toi que la réponse est conforme à la réglementation UEMOA
- Sois précis et technique tout en restant accessible
"""
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"Erreur lors de la génération de la réponse avec OpenAI: {e}")
        return _generate_mock_question_answer(question)
```

---

## 🔐 4. Nouveau Router Superadmin

### Endpoints à Créer

```python
# app/routers/global_knowledge.py

POST   /admin/global-knowledge/upload          # Upload document (draft)
GET    /admin/global-knowledge                 # Liste tous les documents globaux
GET    /admin/global-knowledge/{id}            # Détails d'un document
PUT    /admin/global-knowledge/{id}           # Modifier métadonnées
POST   /admin/global-knowledge/{id}/publish   # Publier (indexe automatiquement)
POST   /admin/global-knowledge/{id}/archive    # Archiver
POST   /admin/global-knowledge/{id}/reindex   # Re-indexer
DELETE /admin/global-knowledge/{id}            # Supprimer
GET    /admin/global-knowledge/{id}/download  # Télécharger fichier
```

### Structure du Router

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from app.core.deps import get_superadmin  # ⚠️ Nouvelle dépendance à créer

router = APIRouter(
    prefix="/admin/global-knowledge",
    tags=["global-knowledge"],
)

@router.post("/upload")
async def upload_global_document(
    file: UploadFile = File(...),
    titre: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),  # plan_comptable | commission_bancaire | lb_ft | general
    authority: str = Form(""),
    reference: str = Form(""),
    version: str = Form("1.0"),
    effective_date: str = Form(None),
    current_user: dict = Depends(get_superadmin),  # ⚠️ Superadmin uniquement
):
    """Upload un document global (statut: draft)"""
    # ... implémentation
    
@router.post("/{document_id}/publish")
async def publish_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Publie un document global (indexe automatiquement)"""
    # 1. Mettre status="published"
    # 2. Appeler process_document() pour indexer
    # 3. Insérer chunks avec scope="GLOBAL", organization_id=null, status="published"
    
@router.post("/{document_id}/archive")
async def archive_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Archive un document global"""
    # 1. Mettre status="archived"
    # 2. Mettre à jour chunks: status="archived"
    
@router.post("/{document_id}/reindex")
async def reindex_global_document(
    document_id: str,
    current_user: dict = Depends(get_superadmin),
):
    """Re-indexe un document global"""
    # 1. Supprimer anciens chunks (scope="GLOBAL", document_id)
    # 2. Re-indexer avec process_document()
```

---

## 📝 5. Migration des Données Existantes

### Script de Migration

```python
# migration_add_scope.py

async def migrate_existing_chunks():
    """Ajoute scope="ORG" aux chunks existants"""
    db = get_database()
    
    # Mettre à jour tous les chunks existants
    result = await db["document_chunks"].update_many(
        {"scope": {"$exists": False}},  # Chunks sans scope
        {
            "$set": {
                "scope": "ORG"
            }
        }
    )
    
    print(f"Migration terminée: {result.modified_count} chunks mis à jour")
```

---

## ✅ Checklist d'Implémentation

### Backend

- [ ] Modifier `app/models/documents.py` :
  - [ ] Ajouter champ `scope` dans `save_document_chunks()`
  - [ ] Rendre `organization_id` nullable dans les chunks
  - [ ] Ajouter champ `status` pour chunks GLOBAL
  - [ ] Modifier `search_document_chunks()` avec support scope
  - [ ] Créer fonction `save_global_document_chunks()`

- [ ] Modifier `app/models/documents.py` pour documents :
  - [ ] Rendre `organization_id` nullable
  - [ ] Ajouter champs : `scope`, `titre`, `authority`, `reference`, `version`, `effective_date`, `published_date`
  - [ ] Modifier `create_document()` pour supporter GLOBAL

- [ ] Modifier `app/services/ai_service.py` :
  - [ ] Modifier `generate_question_answer()` pour recherche hybride

- [ ] Créer `app/routers/global_knowledge.py` :
  - [ ] Endpoints CRUD pour documents globaux
  - [ ] Endpoint publish
  - [ ] Endpoint archive
  - [ ] Endpoint reindex

- [ ] Créer `app/core/deps.py` :
  - [ ] Fonction `get_superadmin()` pour vérifier role="superadmin"

- [ ] Créer script de migration :
  - [ ] Ajouter `scope="ORG"` aux chunks existants

### Frontend

- [ ] Créer `src/components/admin/GlobalKnowledgeTab.jsx`
- [ ] Ajouter onglet dans `AdminDashboardPage.jsx`
- [ ] Interface upload avec champs métadonnées
- [ ] Liste avec filtres (category, status)
- [ ] Actions : publish, archive, reindex, delete

### Documentation

- [ ] Mettre à jour `REFLEXION_BASE_CONNAISSANCES.md`
- [ ] Mettre à jour `STRUCTURE_MONGODB_CHUNKS.md`
- [ ] Mettre à jour `DOCUMENTATION_INDEXATION.md`

