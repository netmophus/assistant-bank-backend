# 📚 Explication : Base de Connaissances Interne (ORG) et Globale (GLOBAL)

## 🎯 Vue d'ensemble

Le système utilise **deux types de bases de connaissances** pour alimenter l'IA :

1. **Base de Connaissances Organisationnelle (ORG)** : Documents propres à chaque organisation
2. **Base de Connaissances Globale (GLOBAL)** : Documents de référence partagés par toutes les organisations (plan comptable UEMOA, instructions commission bancaire, etc.)

---

## 📊 Architecture de Stockage

### Collections MongoDB

#### 1. Collection `documents`
Stocke les métadonnées des documents (ORG et GLOBAL).

**Champs communs :**
- `_id` : ObjectId du document
- `filename` : Nom du fichier stocké
- `original_filename` : Nom original du fichier
- `file_type` : Type de fichier (pdf, docx, etc.)
- `file_size` : Taille du fichier
- `category` : Catégorie du document
- `subcategory` : Sous-catégorie (optionnel)
- `status` : Statut (pending, processing, processed, published, draft, archived, error)
- `total_chunks` : Nombre de chunks générés
- `extracted_text` : Texte complet extrait
- `scope` : **"ORG"** ou **"GLOBAL"**

**Champs spécifiques ORG :**
- `organization_id` : ObjectId de l'organisation propriétaire
- `uploaded_by` : ObjectId de l'utilisateur qui a uploadé
- `upload_date` : Date d'upload

**Champs spécifiques GLOBAL :**
- `organization_id` : **null** (pas d'organisation)
- `titre` : Titre du document
- `authority` : Autorité émettrice (ex: "Commission Bancaire UEMOA")
- `reference` : Référence officielle
- `version` : Version du document
- `effective_date` : Date d'entrée en vigueur
- `published_date` : Date de publication

#### 2. Collection `document_chunks`
Stocke les chunks (morceaux) de texte avec leurs embeddings pour la recherche sémantique.

**Champs :**
- `_id` : ObjectId du chunk
- `document_id` : ObjectId du document parent
- `organization_id` : ObjectId de l'organisation (pour ORG) ou **null** (pour GLOBAL)
- `scope` : **"ORG"** ou **"GLOBAL"**
- `chunk_index` : Index du chunk dans le document
- `content` : Texte du chunk
- `embedding` : Vecteur d'embedding (liste de floats) pour la recherche sémantique
- `page_number` : Numéro de page (si disponible)
- `section` : Section du document (si disponible)
- `category` : Catégorie du document
- `status` : Statut (pour GLOBAL : published, draft, archived)

---

## 🔄 Processus de Création des Chunks

### Pour les Documents ORG

**Endpoint :** `POST /documents/upload` (admin organisation uniquement)

**Processus :**
1. **Upload du fichier** → Sauvegarde physique du fichier
2. **Création du document** → Insertion dans `documents` avec `scope="ORG"` et `status="pending"`
3. **Traitement asynchrone** (`process_document`) :
   - **Extraction du texte** : Extraction du contenu selon le type de fichier (PDF, DOCX, etc.)
   - **Découpage en chunks** :
     - Chunks de taille max 1000 caractères
     - Overlap de 200 caractères entre chunks
     - Préservation des numéros de page et sections
   - **Génération des embeddings** : Création d'un vecteur d'embedding pour chaque chunk (via OpenAI)
   - **Sauvegarde des chunks** : Insertion dans `document_chunks` avec :
     - `scope="ORG"`
     - `organization_id` = ID de l'organisation
     - `embedding` = vecteur d'embedding
   - **Mise à jour du document** : `status="processed"`, `total_chunks` = nombre de chunks

### Pour les Documents GLOBAL

**Endpoint :** `POST /admin/global-knowledge/upload` (superadmin uniquement)

**Processus :**
1. **Upload du fichier** → Sauvegarde physique du fichier
2. **Création du document** → Insertion dans `documents` avec :
   - `scope="GLOBAL"`
   - `organization_id` = **null**
   - `status="draft"`
   - Métadonnées : `titre`, `authority`, `reference`, `version`, `effective_date`
3. **Traitement asynchrone** (`process_global_document`) :
   - Même processus que pour ORG (extraction, découpage, embeddings)
   - **Sauvegarde des chunks** avec :
     - `scope="GLOBAL"`
     - `organization_id` = **null**
     - `status` = statut du document (published, draft, archived)
4. **Publication** : `POST /admin/global-knowledge/{document_id}/publish`
   - Met à jour `status="published"` sur le document ET tous ses chunks
   - Seuls les documents/chunks avec `status="published"` sont utilisés par l'IA

---

## 🔍 Recherche Sémantique (RAG - Retrieval Augmented Generation)

### Fonction `search_document_chunks`

**Localisation :** `app/models/documents.py`

**Paramètres :**
- `organization_id` : ID de l'organisation (requis pour `scope="ORG"`)
- `query_embedding` : Vecteur d'embedding de la question de l'utilisateur
- `scope` : **"ORG"** | **"GLOBAL"** | None
- `limit` : Nombre maximum de résultats

**Processus :**
1. **Construction du filtre MongoDB** selon le `scope` :
   - **ORG** : `organization_id` = ID de l'org ET `scope="ORG"`
   - **GLOBAL** : `organization_id` = **null** ET `scope="GLOBAL"` ET `status="published"`
2. **Récupération de tous les chunks** correspondants avec leurs embeddings
3. **Calcul de la similarité cosinus** entre l'embedding de la question et chaque chunk
4. **Tri par similarité décroissante** et sélection des `limit` meilleurs résultats
5. **Enrichissement** : Ajout des métadonnées du document parent (nom, autorité, référence, etc.)

---

## 🤖 Utilisation par l'IA (`generate_question_answer`)

**Localisation :** `app/services/ai_service.py`

### Processus de Recherche Hybride

Quand un utilisateur pose une question :

1. **Génération de l'embedding de la question** :
   - La question est convertie en vecteur d'embedding via OpenAI

2. **Recherche dans les documents ORG** (limit 5) :
   - Appel à `search_document_chunks()` avec :
     - `scope="ORG"`
     - `organization_id` = ID de l'organisation de l'utilisateur
   - Résultats formatés avec citations (document, page, section)

3. **Recherche dans les documents GLOBAL** (limit 3) :
   - **Vérification de la licence** :
     - Appel à `org_has_active_license(organization_id)`
     - Vérifie si l'organisation a une licence active (status="active", dates valides)
   - **Si licence active** :
     - Appel à `search_document_chunks()` avec :
       - `scope="GLOBAL"`
       - `organization_id` = **null**
       - Filtre automatique sur `status="published"`
   - **Si pas de licence** : Aucune recherche GLOBAL (seulement ORG)
   - **Superadmin** : Toujours accès GLOBAL (même sans organisation)

4. **Construction du contexte pour l'IA** :
   ```
   ## 📁 Contexte de votre organisation:
   [Extraits des documents ORG avec citations]
   
   ## 🌐 Base de Connaissances Globale (Références Officielles):
   [Extraits des documents GLOBAL avec métadonnées : autorité, référence, version]
   ```

5. **Génération de la réponse** :
   - L'IA (GPT-4) reçoit :
     - La question de l'utilisateur
     - Le contexte ORG (si disponible)
     - Le contexte GLOBAL (si licence active)
     - Le département/service de l'utilisateur (contexte)
   - Génération d'une réponse basée sur ces informations

---

## 🔐 Contrôle d'Accès

### Documents ORG
- **Upload** : Admin organisation uniquement
- **Consultation** : Utilisateurs de l'organisation (avec filtrage par département si affectation)
- **Recherche IA** : Tous les utilisateurs de l'organisation

### Documents GLOBAL
- **Upload/Gestion** : Superadmin uniquement
- **Consultation** : Org admins (via `/admin/global-knowledge/published`)
- **Recherche IA** : 
  - **Avec licence active** : Tous les utilisateurs de l'organisation
  - **Sans licence** : Aucun accès (seulement ORG)
  - **Superadmin** : Toujours accès

### Vérification de Licence

**Fonction :** `org_has_active_license(organization_id)` dans `app/models/license.py`

**Vérifications :**
1. Récupération de la licence de l'organisation
2. Vérification que `status="active"`
3. Vérification que `start_date <= aujourd'hui <= end_date`
4. Retourne `True` si toutes les conditions sont remplies, sinon `False`
5. **Superadmin** (`organization_id=None`) : Retourne toujours `True`

---

## 📈 Statistiques et Métriques

### Pour les Documents ORG
- Nombre total de documents
- Nombre total de chunks
- Taille totale des fichiers
- Répartition par catégorie

### Pour les Documents GLOBAL
- Nombre total de documents publiés
- Nombre total de chunks publiés
- Taille totale des fichiers
- Répartition par catégorie (plan_comptable, commission_bancaire, lb_ft, general)

---

## 🔄 Cycle de Vie des Documents

### Documents ORG
1. **Upload** → `status="pending"`
2. **Traitement** → `status="processing"`
3. **Terminé** → `status="processed"`
4. **Erreur** → `status="error"`

### Documents GLOBAL
1. **Upload** → `status="draft"`
2. **Traitement** → `status="processing"`
3. **Publication** → `status="published"` (disponible pour l'IA)
4. **Archivage** → `status="archived"` (non disponible pour l'IA)
5. **Erreur** → `status="error"`

**Important :** Seuls les documents GLOBAL avec `status="published"` sont utilisés par l'IA.

---

## 🎯 Cas d'Usage

### Scénario 1 : Utilisateur avec licence active
1. Pose une question sur "les ratios de solvabilité"
2. L'IA recherche dans :
   - Documents ORG de son organisation (5 meilleurs extraits)
   - Documents GLOBAL publiés (3 meilleurs extraits) ← **Grâce à la licence**
3. Génère une réponse combinant les deux sources

### Scénario 2 : Utilisateur sans licence
1. Pose une question sur "les ratios de solvabilité"
2. L'IA recherche dans :
   - Documents ORG de son organisation (5 meilleurs extraits)
   - **Aucun document GLOBAL** ← Pas de licence
3. Génère une réponse basée uniquement sur les documents ORG

### Scénario 3 : Superadmin
1. Pose une question
2. L'IA recherche dans :
   - Documents ORG (si organisation associée)
   - Documents GLOBAL publiés (toujours) ← **Superadmin a toujours accès**

---

## 🔧 Endpoints Clés

### Documents ORG
- `POST /documents/upload` : Upload d'un document (admin org)
- `GET /documents` : Liste des documents (admin org)
- `GET /documents/user/my-documents` : Documents assignés à l'utilisateur
- `GET /documents/{id}` : Détails d'un document
- `POST /documents/{id}/assign-departments` : Assigner à des départements (admin)

### Documents GLOBAL
- `POST /admin/global-knowledge/upload` : Upload (superadmin)
- `GET /admin/global-knowledge` : Liste (superadmin)
- `GET /admin/global-knowledge/published` : Liste publiés (org admin)
- `POST /admin/global-knowledge/{id}/publish` : Publier (superadmin)
- `POST /admin/global-knowledge/{id}/archive` : Archiver (superadmin)
- `POST /admin/global-knowledge/{id}/reindex` : Réindexer (superadmin)

### Recherche IA
- `POST /questions/ask` : Poser une question (utilise automatiquement ORG + GLOBAL si licence)

---

## 📝 Notes Importantes

1. **Séparation stricte** : Les documents ORG et GLOBAL sont stockés dans la même collection mais différenciés par le champ `scope` et `organization_id`.

2. **Performance** : La recherche sémantique calcule la similarité cosinus pour tous les chunks correspondants. Pour de grandes bases, envisager un index vectoriel (ex: Pinecone, Weaviate).

3. **Licence** : Le contrôle de licence est au niveau **organisation**, donc si une organisation a une licence active, **tous ses utilisateurs** (admin + users) bénéficient de l'accès GLOBAL.

4. **Publication** : Les documents GLOBAL doivent être explicitement publiés pour être utilisés par l'IA. Le statut "draft" n'est pas utilisé par l'IA.

5. **Embeddings** : Les embeddings sont générés via OpenAI (modèle text-embedding-ada-002 ou équivalent). Le coût dépend du nombre de chunks.

