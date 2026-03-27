# 📊 Structure MongoDB pour les Embeddings/Chunks

## 🗄️ Collection MongoDB : `document_chunks`

### Nom de la Collection
```python
DOCUMENT_CHUNKS_COLLECTION = "document_chunks"
```

### Structure d'un Document Chunk

```javascript
{
  "_id": ObjectId("507f1f77bcf86cd799439011"),  // ID unique du chunk
  "document_id": ObjectId("507f1f77bcf86cd799439012"),  // Référence au document parent
  "organization_id": ObjectId("507f1f77bcf86cd799439013") | null,  // Organisation propriétaire (null pour GLOBAL)
  "scope": "ORG" | "GLOBAL",  // ⚠️ NOUVEAU : Portée du chunk
  "category": "procedures" | "plan_comptable" | "commission_bancaire" | "lb_ft" | "general",  // Catégorie
  "chunk_index": 0,  // Index du chunk dans le document (0, 1, 2, ...)
  "content": "Texte complet du chunk extrait du document...",  // Contenu textuel
  "embedding": [0.123, -0.456, 0.789, ...],  // Vecteur d'embedding (1536 dimensions pour text-embedding-3-small)
  "page_number": 1,  // Numéro de page (pour PDF) - Optionnel
  "section": "Introduction",  // Section/titre (pour Word) - Optionnel
  "status": "published" | "draft" | "archived"  // ⚠️ NOUVEAU : Pour chunks GLOBAL uniquement
}
```

**Règles :**
- `scope="ORG"` → `organization_id` obligatoire (ObjectId)
- `scope="GLOBAL"` → `organization_id=null` obligatoire
- `status` : utilisé uniquement pour `scope="GLOBAL"` (peut être null pour ORG)

### Schéma TypeScript/Python

```typescript
interface DocumentChunk {
  _id: ObjectId;
  document_id: ObjectId;
  organization_id: ObjectId;
  category: string;
  chunk_index: number;
  content: string;
  embedding: number[];  // Array de 1536 floats
  page_number?: number;
  section?: string;
}
```

---

## 🔍 Fonction `search_document_chunks` - Détails Techniques

### Signature de la Fonction

```python
async def search_document_chunks(
    organization_id: Optional[str] = None,  # ⚠️ MODIFIÉ : optionnel
    query_embedding: List[float],
    category: Optional[str] = None,
    scope: Optional[str] = None,  # ⚠️ NOUVEAU : "ORG" | "GLOBAL" | None (les deux)
    limit: int = 5,
) -> List[dict]:
```

### Paramètres

| Paramètre | Type | Description | Requis |
|-----------|------|-------------|--------|
| `organization_id` | `str` | ID de l'organisation | ✅ Oui |
| `query_embedding` | `List[float]` | Vecteur d'embedding de la question (1536 dimensions) | ✅ Oui |
| `category` | `Optional[str]` | Filtrer par catégorie (ex: "procedures") | ❌ Non |
| `limit` | `int` | Nombre maximum de résultats (défaut: 5) | ❌ Non (défaut: 5) |

### Requête MongoDB Exacte

#### Étape 1 : Construction du Filtre

```python
# Construction du filtre selon le scope
query = {
    "embedding": {"$exists": True, "$ne": []}  # Seulement les chunks avec embeddings
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
    pass

if category:
    query["category"] = category
```

**Filtres appliqués selon scope :**
- **scope="ORG"** :
  - ✅ `organization_id` : Chunks de l'organisation spécifiée
  - ✅ `scope` : "ORG"
  - ✅ `embedding` existe ET n'est pas vide
  - ✅ `category` (optionnel)
- **scope="GLOBAL"** :
  - ✅ `organization_id` : null
  - ✅ `scope` : "GLOBAL"
  - ✅ `status` : "published" (seulement documents publiés)
  - ✅ `embedding` existe ET n'est pas vide
  - ✅ `category` (optionnel)

#### Étape 2 : Récupération des Chunks

```python
cursor = db[DOCUMENT_CHUNKS_COLLECTION].find(query)
all_chunks = await cursor.to_list(length=None)  # Récupérer TOUS les chunks
```

**Note importante :** 
- ❌ **Pas de tri MongoDB** : La requête récupère tous les chunks sans tri
- ❌ **Pas de limit MongoDB** : Tous les chunks sont récupérés en mémoire
- ⚠️ **Performance** : Le tri se fait en Python après récupération

#### Étape 3 : Calcul de Similarité Cosinus (en Python)

```python
scored_chunks = []
for chunk in all_chunks:
    chunk_embedding = chunk.get("embedding", [])
    
    # Vérifier que l'embedding existe et a la bonne dimension
    if not chunk_embedding or len(chunk_embedding) != len(query_embedding):
        continue
    
    # Calculer la similarité cosinus
    similarity = cosine_similarity(query_embedding, chunk_embedding)
    
    scored_chunks.append({
        "chunk": chunk,
        "similarity": similarity
    })
```

**Fonction `cosine_similarity` :**
```python
def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)
```

#### Étape 4 : Tri et Limitation

```python
# Trier par similarité décroissante
scored_chunks.sort(key=lambda x: x["similarity"], reverse=True)

# Prendre les N meilleurs résultats
top_chunks = scored_chunks[:limit]
```

**Tri :** Par similarité décroissante (du plus similaire au moins similaire)

#### Étape 5 : Filtrage des Chunks Invalides

```python
# Messages d'erreur à filtrer
error_messages = [
    "Document PDF vide ou non lisible",
    "Aucun texte n'a pu être extrait",
    "Document vide ou non lisible",
]

results = []
for item in top_chunks:
    chunk = item["chunk"]
    content = chunk.get("content", "").strip()
    
    # Filtrer les chunks d'erreur
    if any(error_msg.lower() in content.lower() for error_msg in error_messages):
        continue
    
    # Filtrer les chunks vides ou trop courts (< 20 caractères)
    if not content or len(content) < 20:
        continue
    
    # ... ajout au résultat
```

**Filtres appliqués :**
- ❌ Chunks contenant des messages d'erreur
- ❌ Chunks vides ou < 20 caractères

#### Étape 6 : Enrichissement avec Informations du Document

```python
# Récupérer le nom du document parent
doc = await db[DOCUMENTS_COLLECTION].find_one({"_id": chunk["document_id"]})
document_filename = doc.get("original_filename", doc.get("filename", "Document")) if doc else "Document"

results.append({
    "id": str(chunk["_id"]),
    "document_id": document_id,
    "document_filename": document_filename,
    "content": content,
    "chunk_index": chunk["chunk_index"],
    "page_number": chunk.get("page_number"),
    "section": chunk.get("section"),
    "similarity": item["similarity"],
})
```

---

## 📋 Résumé de la Requête Complète

### Requête MongoDB (Étape 1-2)

```javascript
db.document_chunks.find({
  organization_id: ObjectId("..."),
  embedding: { $exists: true, $ne: [] },
  category: "procedures"  // Optionnel
})
// Pas de .sort()
// Pas de .limit()
```

### Traitement Python (Étape 3-6)

1. **Calcul de similarité** : Pour chaque chunk, calculer `cosine_similarity(query_embedding, chunk_embedding)`
2. **Tri** : Trier par similarité décroissante
3. **Limitation** : Prendre les `limit` premiers résultats
4. **Filtrage** : Exclure les chunks d'erreur et trop courts
5. **Enrichissement** : Ajouter les métadonnées du document parent

### Format de Retour

```python
[
    {
        "id": "507f1f77bcf86cd799439011",
        "document_id": "507f1f77bcf86cd799439012",
        "document_filename": "document.pdf",
        "content": "Texte du chunk...",
        "chunk_index": 0,
        "page_number": 1,
        "section": "Introduction",
        "similarity": 0.856  // Score de similarité (0.0 à 1.0)
    },
    ...
]
```

---

## ⚠️ Points d'Attention Performance

### Problèmes Actuels

1. **Récupération complète en mémoire** : Tous les chunks sont récupérés avant le tri
2. **Calcul de similarité en Python** : Pas d'index vectoriel MongoDB
3. **Pas de limite MongoDB** : La limite est appliquée après récupération

### Impact

- ⚠️ **Lent avec beaucoup de chunks** : Si une organisation a 10,000+ chunks, tous sont récupérés
- ⚠️ **Consommation mémoire** : Tous les embeddings sont chargés en mémoire
- ⚠️ **Pas scalable** : Performance dégrade avec la croissance des données

### Solutions Futures Recommandées

1. **MongoDB Atlas Vector Search** : Utiliser l'index vectoriel natif
2. **Pinecone / Weaviate** : Base de données vectorielle dédiée
3. **Limite MongoDB** : Appliquer `.limit()` après tri (nécessite index vectoriel)

---

## 📝 Exemple d'Utilisation

```python
# Générer l'embedding de la question
from app.services.embedding_service import generate_embedding
question_embedding = await generate_embedding("Qu'est-ce que le ratio de solvabilité ?")

# Rechercher les chunks pertinents
from app.models.documents import search_document_chunks
results = await search_document_chunks(
    organization_id="507f1f77bcf86cd799439013",
    query_embedding=question_embedding,
    category="procedures",  # Optionnel
    limit=5
)

# Utiliser les résultats
for result in results:
    print(f"Document: {result['document_filename']}")
    print(f"Page: {result.get('page_number', 'N/A')}")
    print(f"Similarité: {result['similarity']:.2%}")
    print(f"Contenu: {result['content'][:200]}...")
```

---

## 🔗 Collections Liées

### Collection `documents`
```javascript
{
  "_id": ObjectId("507f1f77bcf86cd799439012"),
  "organization_id": ObjectId("507f1f77bcf86cd799439013"),
  "filename": "document.pdf",
  "original_filename": "document.pdf",
  "category": "procedures",
  "total_chunks": 25,
  ...
}
```

**Relation :** `document_chunks.document_id` → `documents._id`

