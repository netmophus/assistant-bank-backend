# 📚 Base de Connaissances Globale - IMPLÉMENTATION COMPLÈTE

## ✅ Statut : IMPLÉMENTÉ

Cette fonctionnalité a été implémentée selon le plan corrigé qui réutilise les collections existantes avec un système de `scope`.

## 🎯 Objectif

Créer une **base de connaissances globale** accessible depuis le dashboard superadmin qui servira de référence pour toutes les organisations. Cette base de connaissances sera utilisée par l'IA pour répondre aux questions des utilisateurs avec des informations fiables et standardisées.

## ✅ Ce qui a été fait

### 1. Modification des Collections MongoDB

**Collection `document_chunks` :**
- ✅ Ajout du champ `scope` : "ORG" ou "GLOBAL"
- ✅ `organization_id` rendu nullable (null pour GLOBAL)
- ✅ Ajout du champ `status` pour les chunks GLOBAL (published/draft/archived)

**Collection `documents` :**
- ✅ `organization_id` rendu nullable (null pour GLOBAL)
- ✅ Ajout du champ `scope` : "ORG" ou "GLOBAL"
- ✅ Ajout des champs pour documents globaux : `titre`, `authority`, `reference`, `version`, `effective_date`, `published_date`

### 2. Modifications Backend

**`app/models/documents.py` :**
- ✅ `create_document()` : Support des documents globaux avec champs supplémentaires
- ✅ `save_document_chunks()` : Support du scope et status
- ✅ `search_document_chunks()` : Recherche par scope (ORG/GLOBAL)
- ✅ `get_global_document_by_id()` : Nouvelle fonction pour récupérer documents globaux
- ✅ `list_global_documents()` : Liste des documents globaux
- ✅ `update_global_document_status()` : Mise à jour statut + chunks associés
- ✅ `delete_document()` : Support des documents globaux (organization_id nullable)

**`app/services/ai_service.py` :**
- ✅ `generate_question_answer()` : Recherche hybride implémentée
  - Recherche dans documents ORG (limit 5)
  - Recherche dans base GLOBAL published (limit 3)
  - Contexte construit en deux sections avec citations

**`app/core/deps.py` :**
- ✅ `get_superadmin()` : Nouvelle dépendance pour vérifier role="superadmin"

**`app/routers/global_knowledge.py` :**
- ✅ Router complet pour gestion documents globaux
- ✅ Endpoints :
  - `POST /admin/global-knowledge/upload` : Upload document (draft)
  - `GET /admin/global-knowledge` : Liste documents globaux
  - `GET /admin/global-knowledge/{id}` : Détails document
  - `PUT /admin/global-knowledge/{id}` : Modifier métadonnées
  - `POST /admin/global-knowledge/{id}/publish` : Publier (indexe automatiquement)
  - `POST /admin/global-knowledge/{id}/archive` : Archiver
  - `POST /admin/global-knowledge/{id}/reindex` : Re-indexer
  - `DELETE /admin/global-knowledge/{id}` : Supprimer
  - `GET /admin/global-knowledge/{id}/download` : Télécharger fichier

**`app/schemas/global_knowledge.py` :**
- ✅ Schémas Pydantic pour documents globaux

**`app/main.py` :**
- ✅ Router `global_knowledge` enregistré

**`app/routers/documents.py` :**
- ✅ `process_document()` : Utilise scope="ORG" pour documents organisationnels

### 3. Migration

**`migration_add_scope.py` :**
- ✅ Script de migration pour ajouter scope="ORG" aux chunks existants

## 📋 Structure des Données

### Document Chunk

```javascript
{
  "_id": ObjectId("..."),
  "document_id": ObjectId("..."),
  "organization_id": ObjectId("...") | null,  // null pour GLOBAL
  "scope": "ORG" | "GLOBAL",                  // ⚠️ NOUVEAU
  "category": "procedures" | "plan_comptable" | "commission_bancaire" | "lb_ft" | "general",
  "chunk_index": 0,
  "content": "...",
  "embedding": [...],
  "page_number": 1,
  "section": "Introduction",
  "status": "published" | "draft" | "archived"  // Pour GLOBAL uniquement
}
```

### Document Global

```javascript
{
  "_id": ObjectId("..."),
  "organization_id": null,                    // null pour GLOBAL
  "scope": "GLOBAL",
  "titre": "Plan Comptable UEMOA 2024",
  "description": "...",
  "category": "plan_comptable",
  "authority": "Commission Bancaire UEMOA",
  "reference": "CB-UEMOA-2024-001",
  "version": "1.0",
  "effective_date": ISODate("..."),
  "status": "draft" | "published" | "archived",
  "published_date": ISODate("..."),
  "filename": "...",
  "file_path": "...",
  "total_chunks": 25,
  ...
}
```

## 🔍 Recherche Hybride

Lorsqu'un utilisateur pose une question :

1. **Recherche ORG** (limit 5) : Documents de l'organisation
2. **Recherche GLOBAL** (limit 3) : Base de connaissances globale (status="published")
3. **Contexte combiné** : Deux sections distinctes avec citations
4. **Réponse IA** : Priorise ORG puis complète avec GLOBAL

## 🚀 Utilisation

### Gestion des Catégories

Les catégories sont maintenant gérées dynamiquement depuis le dashboard superadmin.

**Endpoints disponibles :**
- `GET /admin/global-knowledge/categories` : Liste des catégories
- `POST /admin/global-knowledge/categories` : Créer une catégorie
- `PUT /admin/global-knowledge/categories/{id}` : Modifier une catégorie
- `DELETE /admin/global-knowledge/categories/{id}` : Supprimer une catégorie
- `POST /admin/global-knowledge/categories/{id}/toggle` : Activer/désactiver

**Structure d'une catégorie :**
```javascript
{
  "id": "...",
  "name": "Plan Comptable UEMOA",
  "slug": "plan_comptable",  // Unique, utilisé dans l'API
  "description": "...",
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

### Upload d'un Document Global

```bash
POST /admin/global-knowledge/upload
Content-Type: multipart/form-data

file: [fichier PDF]
titre: "Plan Comptable UEMOA 2024"
category: "plan_comptable"  # Slug de la catégorie (dynamique)
subcategory: "Comptes de bilan"  # Optionnel
authority: "Commission Bancaire UEMOA"
reference: "CB-UEMOA-2024-001"
version: "1.0"
effective_date: "2024-01-01"
```

### Publication

```bash
POST /admin/global-knowledge/{id}/publish
```

Cela indexe automatiquement le document si pas encore fait, puis le publie.

## 📝 Migrations Requises

### 1. Migration Scope

Avant d'utiliser la fonctionnalité, exécuter :

```bash
python migration_add_scope.py
```

Cela ajoute `scope="ORG"` à tous les chunks existants.

### 2. Initialisation des Catégories

Pour créer les catégories par défaut :

```bash
python migration_init_categories.py
```

Cela crée les 4 catégories initiales :
- Plan Comptable UEMOA
- Commission Bancaire
- Lutte contre le Blanchiment (LBC/FT)
- Base de Connaissances Générale

**Note :** Les catégories peuvent aussi être créées manuellement depuis l'interface.

## 🔐 Sécurité

- ✅ Seul le superadmin peut gérer les documents globaux
- ✅ Les documents globaux sont accessibles en lecture par toutes les organisations via l'IA
- ✅ Seuls les documents avec `status="published"` sont utilisés par l'IA

## 📋 Contenu de la Base de Connaissances

La base de connaissances contiendra :

1. **Plan Comptable UEMOA**
   - Structure comptable standardisée
   - Comptes et leurs significations
   - Règles de comptabilisation

2. **Instructions de la Commission Bancaire**
   - Circulaires et instructions réglementaires
   - Normes prudentielles
   - Obligations bancaires

3. **Documents de Lutte contre le Blanchiment des Capitaux (LBC/FT)**
   - Procédures de vigilance
   - Obligations de déclaration
   - Cadre réglementaire

4. **Base de Connaissances Générale**
   - FAQ bancaire
   - Procédures standards
   - Bonnes pratiques

## 🏗️ Architecture Proposée

### 1. Séparation des Documents

**Documents Organisationnels** (existant) :
- Stockés avec `organization_id`
- Accessibles uniquement par l'organisation concernée
- Collection : `documents` et `document_chunks`

**Documents Globaux** (nouveau) :
- Stockés **sans** `organization_id` (ou avec `organization_id: null`)
- Accessibles par **toutes** les organisations
- Collection : `global_knowledge_documents` et `global_knowledge_chunks`
- Gérés uniquement par le superadmin

### 2. Structure de Données

#### Collection `global_knowledge_documents`
```javascript
{
  "_id": ObjectId("..."),
  "filename": "...",
  "original_filename": "...",
  "file_type": "pdf|word|excel",
  "file_path": "uploads/global_knowledge/...",
  "file_size": 1024000,
  "category": "plan_comptable|commission_bancaire|lb_ft|general",
  "subcategory": "...",
  "tags": ["uemoa", "comptabilité", ...],
  "description": "...",
  "upload_date": ISODate("..."),
  "uploaded_by": ObjectId("..."), // ID du superadmin
  "status": "processed",
  "total_chunks": 25,
  "extracted_text": "..."
}
```

#### Collection `global_knowledge_chunks`
```javascript
{
  "_id": ObjectId("..."),
  "document_id": ObjectId("..."),
  "category": "plan_comptable|commission_bancaire|lb_ft|general",
  "chunk_index": 0,
  "content": "...",
  "embedding": [0.123, -0.456, ...],
  "page_number": 1,
  "section": "..."
}
```

### 3. Recherche Hybride

Lorsqu'un utilisateur pose une question, l'IA recherche dans **deux sources** :

1. **Documents de l'organisation** (priorité haute)
   - Documents spécifiques à l'organisation
   - Contexte local et personnalisé

2. **Base de connaissances globale** (priorité basse mais toujours incluse)
   - Informations standardisées
   - Références réglementaires
   - Bonnes pratiques communes

**Algorithme de recherche** :
```
1. Rechercher dans documents organisationnels (top 3-5 chunks)
2. Rechercher dans base de connaissances globale (top 2-3 chunks)
3. Combiner les résultats avec priorité aux documents org
4. Envoyer à l'IA avec contexte complet
```

## 🔧 Implémentation Technique

### Backend

#### 1. Nouveaux Modèles (`app/models/global_knowledge.py`)
- `create_global_document()` : Créer un document global
- `list_global_documents()` : Lister les documents globaux
- `search_global_knowledge_chunks()` : Recherche sémantique dans la base globale
- `delete_global_document()` : Supprimer un document global

#### 2. Nouveau Router (`app/routers/global_knowledge.py`)
- `POST /admin/global-knowledge/upload` : Upload document (superadmin uniquement)
- `GET /admin/global-knowledge` : Liste des documents globaux
- `GET /admin/global-knowledge/{id}` : Détails d'un document
- `DELETE /admin/global-knowledge/{id}` : Supprimer un document
- `POST /admin/global-knowledge/{id}/reindex` : Re-indexer un document

#### 3. Modification du Service IA (`app/services/ai_service.py`)
Modifier `generate_question_answer()` pour :
1. Rechercher dans documents organisationnels
2. Rechercher dans base de connaissances globale
3. Combiner les résultats avec priorité

#### 4. Stockage Physique
```
uploads/
├── documents/          # Documents organisationnels (existant)
│   └── {organization_id}/
│       └── ...
└── global_knowledge/   # Nouveau dossier pour documents globaux
    └── {document_id}_{filename}
```

### Frontend

#### 1. Nouvel Onglet dans AdminDashboardPage
Ajouter un onglet **"Base de Connaissances"** avec :
- Liste des documents globaux
- Upload de nouveaux documents
- Catégories : Plan Comptable, Commission Bancaire, LBC/FT, Général
- Gestion (modifier, supprimer, re-indexer)

#### 2. Interface de Gestion
- Tableau avec filtres par catégorie
- Formulaire d'upload avec sélection de catégorie
- Indicateur de statut (pending, processing, processed, error)
- Statistiques (nombre de documents, chunks, taille totale)

## 🔐 Sécurité et Permissions

- **Superadmin uniquement** : Seul le superadmin peut gérer la base de connaissances globale
- **Lecture pour tous** : Tous les utilisateurs bénéficient automatiquement de cette base lors des questions
- **Validation** : Le superadmin peut marquer certains documents comme "validés" ou "officiels"

## 📊 Flux d'Utilisation

### 1. Upload par Superadmin
```
Superadmin → Dashboard → Base de Connaissances → Upload PDF
→ Extraction → Découpage → Embeddings → Stockage MongoDB
→ Statut: processed
```

### 2. Question Utilisateur
```
Utilisateur pose question
→ Recherche dans documents org (top 5)
→ Recherche dans base globale (top 3)
→ Combinaison avec priorité
→ Envoi à l'IA avec contexte complet
→ Réponse avec citations des sources
```

## 🎨 Catégories de Documents

1. **plan_comptable** : Plan comptable UEMOA
2. **commission_bancaire** : Instructions et circulaires
3. **lb_ft** : Lutte contre blanchiment et financement terrorisme
4. **general** : Base de connaissances générale

## 📈 Avantages

1. **Standardisation** : Informations cohérentes pour toutes les organisations
2. **Mise à jour centralisée** : Un seul endroit pour mettre à jour les références
3. **Conformité** : Garantit l'utilisation de documents officiels et à jour
4. **Efficacité** : Réduit la duplication de documents entre organisations
5. **Qualité** : Réponses plus précises grâce à une base de référence solide

## 🚀 Plan d'Implémentation

### Phase 1 : Backend - Modèles et Stockage
- [ ] Créer `app/models/global_knowledge.py`
- [ ] Créer collections MongoDB
- [ ] Implémenter fonctions CRUD
- [ ] Créer dossier `uploads/global_knowledge/`

### Phase 2 : Backend - Router et API
- [ ] Créer `app/routers/global_knowledge.py`
- [ ] Implémenter endpoints CRUD
- [ ] Ajouter protection superadmin
- [ ] Intégrer avec système d'indexation existant

### Phase 3 : Backend - Intégration IA
- [ ] Modifier `generate_question_answer()` pour recherche hybride
- [ ] Tester recherche combinée
- [ ] Optimiser performance

### Phase 4 : Frontend - Interface Admin
- [ ] Ajouter onglet "Base de Connaissances" dans AdminDashboardPage
- [ ] Créer composant de gestion des documents
- [ ] Implémenter upload avec catégories
- [ ] Ajouter statistiques

### Phase 5 : Tests et Validation
- [ ] Tester upload et indexation
- [ ] Tester recherche hybride
- [ ] Valider réponses IA avec contexte global
- [ ] Tests de performance

## 🔄 Évolutions Futures

1. **Versioning** : Gérer les versions des documents (plan comptable v1, v2, etc.)
2. **Validation** : Workflow de validation avant publication
3. **Notifications** : Notifier les organisations lors de mises à jour importantes
4. **Analytics** : Statistiques d'utilisation de la base de connaissances
5. **Import en masse** : Upload de plusieurs documents simultanément
6. **Recherche avancée** : Filtres par date, auteur, tags

## 📝 Notes Techniques

- **Réutilisation du code existant** : Utiliser les mêmes services d'extraction, découpage et embeddings
- **Compatibilité** : S'assurer que les documents globaux fonctionnent avec le système existant
- **Performance** : Optimiser les recherches pour ne pas ralentir les réponses
- **Scalabilité** : Prévoir l'augmentation du nombre de documents globaux

