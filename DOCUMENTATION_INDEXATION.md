# 📄 Documentation : Stockage et Indexation des Documents

## 📁 1. Stockage Physique des Fichiers

### Emplacement
Les fichiers uploadés sont stockés dans le système de fichiers local :

```
assistant-banque-backend/
└── uploads/
    └── documents/
        └── {organization_id}/
            └── {user_id}_{nom_fichier_original}
```

**Exemple concret :**
```
C:\PROGPYTHON\assistant-banque-backend\uploads\documents\
└── 6931301e7a67fa5e359a5189\
    └── 693130717a67fa5e359a518b_PARTIE 01 DISPOSITIF DE GESTION DU RISQUE DE CREDIT.pdf
```

### Structure
- **Dossier racine** : `uploads/documents/` (créé automatiquement)
- **Sous-dossier par organisation** : `{organization_id}/` (isole les fichiers par organisation)
- **Nom du fichier** : `{user_id}_{nom_fichier_original}` (évite les conflits de noms)

### Formats supportés
- **PDF** : `.pdf`
- **Word** : `.docx`, `.doc`
- **Excel** : `.xlsx`, `.xls`

### Taille maximale
- **50 MB** par fichier

---

## 🗄️ 2. Stockage dans MongoDB

### Collections utilisées

#### Collection `documents`
Stocke les métadonnées des documents :

```javascript
{
  "_id": ObjectId("..."),
  "organization_id": ObjectId("..."),
  "uploaded_by": ObjectId("..."),
  "filename": "693130717a67fa5e359a518b_document.pdf",
  "original_filename": "document.pdf",
  "file_type": "pdf",
  "file_path": "uploads/documents/6931301e7a67fa5e359a5189/693130717a67fa5e359a518b_document.pdf",
  "file_size": 1024000,
  "category": "procedures",
  "subcategory": "credit",
  "tags": ["procedure", "credit", "risque"],
  "description": "Document sur la gestion du risque de crédit",
  "upload_date": ISODate("2025-12-16T12:00:00Z"),
  "status": "processed",  // pending, processing, processed, error
  "total_chunks": 25,
  "extracted_text": "Texte complet extrait du document..."
}
```

#### Collection `document_chunks`
Stocke les morceaux (chunks) du document avec leurs embeddings :

```javascript
{
  "_id": ObjectId("..."),
  "document_id": ObjectId("..."),
  "organization_id": ObjectId("..."),
  "category": "procedures",
  "chunk_index": 0,
  "content": "Texte du chunk...",
  "embedding": [0.123, -0.456, 0.789, ...],  // Vecteur de 1536 dimensions (OpenAI)
  "page_number": 1,  // Pour PDF
  "section": "Introduction"  // Pour Word
}
```

---

## 🔄 3. Processus d'Indexation

### Étape 1 : Upload du fichier
1. **Validation** : Type de fichier, taille
2. **Sauvegarde physique** : Fichier copié dans `uploads/documents/{org_id}/`
3. **Création en MongoDB** : Enregistrement dans `documents` avec statut `pending`

### Étape 2 : Extraction du contenu
Selon le type de fichier :

#### PDF (PyPDF2)
- Lecture page par page
- Extraction du texte de chaque page
- Découpage en paragraphes (chunks naturels)
- Conservation du numéro de page

#### Word (python-docx)
- Lecture des paragraphes
- Détection des titres (sections)
- Groupement par section
- Conservation de la structure hiérarchique

#### Excel (pandas + openpyxl)
- Lecture de toutes les feuilles
- Conversion en texte structuré
- Un chunk par feuille
- Conservation du nom de la feuille

### Étape 3 : Découpage intelligent (Chunking)
- **Taille maximale** : 1000 caractères par chunk
- **Overlap** : 200 caractères entre chunks (pour préserver le contexte)
- **Découpage intelligent** : Coupe aux espaces/retours à la ligne pour éviter de couper les mots

### Étape 4 : Génération des Embeddings
- **Modèle** : `text-embedding-3-small` (OpenAI)
- **Dimensions** : 1536
- **Limite** : 8000 caractères par texte
- **Batch** : Traitement en lot pour plusieurs chunks

### Étape 5 : Sauvegarde dans MongoDB
- **Chunks** : Enregistrés dans `document_chunks` avec :
  - Contenu textuel
  - Embedding vectoriel
  - Métadonnées (page, section, index)
  - Référence au document parent

### Étape 6 : Mise à jour du statut
- **Statut** : `pending` → `processing` → `processed`
- **Compteur** : `total_chunks` mis à jour
- **Texte complet** : `extracted_text` sauvegardé

---

## 🔍 4. Recherche et Utilisation

### Recherche sémantique
Les chunks avec embeddings permettent une recherche sémantique :

1. **Question utilisateur** → Génération d'embedding
2. **Comparaison** : Calcul de similarité cosinus avec tous les chunks
3. **Résultats** : Retour des chunks les plus pertinents
4. **Contexte** : Utilisation par l'IA pour répondre aux questions

### Utilisation par l'IA
Lorsqu'un utilisateur pose une question :
1. L'IA génère un embedding de la question
2. Recherche les chunks les plus similaires dans `document_chunks`
3. Utilise ces chunks comme contexte pour générer la réponse
4. Cite les sources (document, page, section)

---

## 📊 5. Statistiques et Monitoring

### Métriques disponibles
- **Total de documents** : Par organisation
- **Total de chunks** : Nombre de morceaux indexés
- **Par catégorie** : Répartition des documents
- **Par statut** : pending, processing, processed, error

### Endpoints de monitoring
- `GET /documents/stats` : Statistiques globales
- `GET /documents` : Liste des documents avec filtres
- `GET /documents/{id}` : Détails d'un document

---

## ⚙️ 6. Configuration

### Variables d'environnement
```env
OPENAI_API_KEY=votre_cle_api  # Pour les embeddings
```

### Paramètres configurables
- **Taille max fichier** : 50 MB (dans `documents.py`)
- **Taille max chunk** : 1000 caractères
- **Overlap** : 200 caractères
- **Modèle embedding** : `text-embedding-3-small`

---

## 🔧 7. Maintenance

### Re-indexation
Si un document doit être re-indexé :
```bash
POST /documents/{document_id}/reindex
```

### Suppression
La suppression d'un document :
1. Supprime le fichier physique
2. Supprime les métadonnées dans `documents`
3. Supprime tous les chunks associés dans `document_chunks`

---

## 📝 Exemple de Flux Complet

```
1. Upload PDF (2 MB, 10 pages)
   ↓
2. Fichier sauvegardé : uploads/documents/org123/user456_doc.pdf
   ↓
3. Document créé dans MongoDB (status: pending)
   ↓
4. Extraction : 10 pages → 25 paragraphes
   ↓
5. Découpage : 25 paragraphes → 30 chunks (avec overlap)
   ↓
6. Embeddings : 30 chunks → 30 vecteurs (1536 dimensions chacun)
   ↓
7. Sauvegarde : 30 documents dans document_chunks
   ↓
8. Mise à jour : Document status = processed, total_chunks = 30
   ↓
9. ✅ Document prêt pour la recherche sémantique
```

---

## 🚀 Améliorations Futures

- [ ] Recherche vectorielle native MongoDB Atlas
- [ ] Indexation asynchrone (background tasks)
- [ ] Support de plus de formats (PowerPoint, images OCR)
- [ ] Compression des embeddings
- [ ] Cache des résultats de recherche
- [ ] Versioning des documents

