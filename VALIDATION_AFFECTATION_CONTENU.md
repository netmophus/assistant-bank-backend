# ✅ Validation et Implémentation : Affectation du Contenu par Département

## 📋 RÉSUMÉ DES MODIFICATIONS

### ✅ Module Ressources

**Fichiers modifiés :**
- `app/models/ressource.py`
- `app/routers/ressource.py`

**Modifications :**

1. **`assign_ressource_to_departments()`** :
   - ✅ Ajout du paramètre `org_id`
   - ✅ Validation que la ressource appartient à l'organisation
   - ✅ Validation que tous les départements appartiennent à la même organisation
   - ✅ Lève `ValueError` si validation échoue

2. **`GET /ressources/user/my-ressources`** :
   - ✅ Filtre uniquement avec `current_user.organization_id` + `current_user.department_id`
   - ✅ Pas de paramètre `department_id` accepté
   - ✅ Filtre supplémentaire par `organization_id` pour sécurité

3. **`POST /ressources/{id}/assign-departments`** :
   - ✅ Admin-only (vérification `role="admin"`)
   - ✅ Valide que ressource + départements appartiennent à la même organisation
   - ✅ Gestion des erreurs `ValueError` avec messages explicites

4. **`GET /ressources/{id}`** :
   - ✅ Admin : peut voir toutes les ressources de son org
   - ✅ User : peut voir uniquement si ressource assignée à son département ET de son organisation
   - ✅ Protection 403 si ressource non assignée au département

5. **`GET /ressources/{id}/download`** :
   - ✅ Même logique de protection que `GET /{id}`
   - ✅ Vérification `organization_id` avant vérification affectation

---

### ✅ Module Formations

**Fichiers modifiés :**
- `app/models/formation_assignment.py`
- `app/routers/formation.py`

**Modifications :**

1. **`assign_formation_to_departments()`** :
   - ✅ Validation que tous les départements appartiennent à la même organisation (ajoutée)
   - ✅ Validation que la formation est publiée (déjà existante)

2. **`get_formations_for_department()`** :
   - ✅ Ajout du paramètre optionnel `organization_id`
   - ✅ Filtre par organisation si fourni

3. **`GET /formations/user/my-formations`** :
   - ✅ Passe `organization_id` à `get_formations_for_department()`
   - ✅ Filtre par organisation + département

4. **Tous les endpoints utilisant `get_formations_for_department()`** :
   - ✅ Mis à jour pour passer `organization_id`
   - ✅ Protection contre l'accès aux formations d'autres organisations

---

### ✅ Module Documents ORG (NOUVEAU)

**Fichiers créés :**
- `app/models/document_assignment.py` (NOUVEAU)
- `app/schemas/documents.py` (ajout `DocumentDepartmentAssignment`)

**Fichiers modifiés :**
- `app/routers/documents.py`
- `app/models/documents.py` (ajout suppression affectations dans `delete_document`)

**Nouveaux endpoints :**

1. **`GET /documents/user/my-documents`** (NOUVEAU) :
   - ✅ Filtre uniquement avec `current_user.organization_id` + `current_user.department_id`
   - ✅ Pas de paramètre accepté
   - ✅ Retourne uniquement les documents ORG assignés au département

2. **`POST /documents/{id}/assign-departments`** (NOUVEAU) :
   - ✅ Admin-only (utilise `get_org_admin`)
   - ✅ Valide que document + départements appartiennent à la même organisation
   - ✅ Valide que le document est de scope "ORG" (pas GLOBAL)

3. **`GET /documents/{id}`** (MODIFIÉ) :
   - ✅ Changé de `get_org_admin` à `get_current_user`
   - ✅ Admin : peut voir tous les documents ORG de son org
   - ✅ User : peut voir uniquement si document assigné à son département ET de son organisation
   - ✅ Protection 403 si document non assigné au département
   - ✅ Vérifie que `scope="ORG"` (pas GLOBAL)

4. **`GET /documents/{id}/download`** (MODIFIÉ) :
   - ✅ Changé de `get_org_admin` à `get_current_user`
   - ✅ Même logique de protection que `GET /{id}`
   - ✅ Vérification `organization_id` + affectation département

5. **`GET /documents`** (MODIFIÉ) :
   - ✅ Ajoute les départements assignés pour chaque document (pour admin)

6. **`DELETE /documents/{id}`** (MODIFIÉ) :
   - ✅ Supprime les affectations aux départements lors de la suppression

**Nouvelles fonctions dans `document_assignment.py` :**

- ✅ `assign_document_to_departments()` : Affecte un document à des départements avec validation
- ✅ `get_departments_for_document()` : Récupère les départements assignés à un document
- ✅ `get_documents_for_department()` : Récupère les documents assignés à un département (avec filtre org)

**Collection MongoDB :**
- ✅ `document_department_assignments` (nouvelle collection)

---

## 🔒 RÈGLES DE SÉCURITÉ APPLIQUÉES

### Pour tous les modules (Ressources, Formations, Documents)

1. **Endpoint `/user/my-*`** :
   - ✅ Filtre uniquement avec `current_user.organization_id` + `current_user.department_id`
   - ✅ Pas de paramètre `department_id` accepté
   - ✅ Retourne liste vide si pas d'organisation ou pas de département

2. **Endpoint `POST /{id}/assign-departments`** :
   - ✅ Admin-only (vérification `role="admin"` + `organization_id`)
   - ✅ Valide que l'élément (ressource/formation/document) appartient à l'organisation
   - ✅ Valide que tous les départements appartiennent à la même organisation
   - ✅ Lève `ValueError` avec message explicite si validation échoue

3. **Endpoint `GET /{id}`** :
   - ✅ Admin : peut voir tous les éléments de son organisation
   - ✅ User : peut voir uniquement si élément assigné à son département ET de son organisation
   - ✅ Protection 403 si élément non assigné au département
   - ✅ Vérification `organization_id` avant vérification affectation

4. **Endpoint `GET /{id}/download`** :
   - ✅ Même logique de protection que `GET /{id}`
   - ✅ Vérification `organization_id` + affectation département

---

## 📊 ARCHITECTURE UNIFIÉE

### Collections MongoDB

| Module | Collection Pivot | Structure |
|--------|------------------|-----------|
| **Ressources** | `ressource_department_assignments` | `{ressource_id, department_id, created_at}` |
| **Formations** | `formation_assignments` | `{formation_id, department_id, organization_id, assigned_at}` |
| **Documents ORG** | `document_department_assignments` | `{document_id, department_id, created_at}` |

### Endpoints Unifiés

| Action | Ressources | Formations | Documents |
|--------|------------|------------|-----------|
| **Liste user** | `GET /ressources/user/my-ressources` | `GET /formations/user/my-formations` | `GET /documents/user/my-documents` |
| **Liste admin** | `GET /ressources` | `GET /formations` | `GET /documents` |
| **Détails** | `GET /ressources/{id}` | `GET /formations/{id}` | `GET /documents/{id}` |
| **Télécharger** | `GET /ressources/{id}/download` | N/A | `GET /documents/{id}/download` |
| **Affecter** | `POST /ressources/{id}/assign-departments` | `POST /formations/{id}/assign-departments` | `POST /documents/{id}/assign-departments` |

### Fonctions Modèles Unifiées

| Fonction | Ressources | Formations | Documents |
|----------|------------|------------|-----------|
| **Assigner** | `assign_ressource_to_departments(resource_id, dept_ids, org_id)` | `assign_formation_to_departments(formation_id, dept_ids, org_id)` | `assign_document_to_departments(document_id, dept_ids, org_id)` |
| **Départements** | `get_departments_for_ressource(resource_id)` | `get_departments_for_formation(formation_id)` | `get_departments_for_document(document_id)` |
| **Pour département** | `get_ressources_for_department(dept_id)` | `get_formations_for_department(dept_id, org_id?)` | `get_documents_for_department(dept_id, org_id?)` |

---

## ✅ VALIDATIONS EFFECTUÉES

### Ressources
- ✅ `GET /ressources/user/my-ressources` filtre uniquement avec `current_user.department_id` (sans paramètre)
- ✅ `POST /ressources/{id}/assign-departments` valide ressource + départements appartiennent à la même organisation
- ✅ `GET /ressources/{id}` protège l'accès si ressource non assignée au département

### Formations
- ✅ `GET /formations/user/my-formations` filtre par organisation + département
- ✅ `POST /formations/{id}/assign-departments` valide formation + départements appartiennent à la même organisation
- ✅ Tous les endpoints utilisent `get_formations_for_department()` avec `organization_id`

### Documents ORG
- ✅ `GET /documents/user/my-documents` créé et filtre uniquement avec `current_user.department_id` (sans paramètre)
- ✅ `POST /documents/{id}/assign-departments` créé, admin-only, valide document + départements
- ✅ `GET /documents/{id}` modifié pour protéger l'accès si document non assigné au département
- ✅ `GET /documents/{id}/download` modifié pour protéger l'accès si document non assigné au département
- ✅ Collection `document_department_assignments` créée

---

## 🎯 TESTS À EFFECTUER

### Test 1 : Ressources
1. Admin assigne ressource R1 au département D1
2. User du département D1 → `GET /ressources/user/my-ressources` → doit voir R1
3. User du département D2 → `GET /ressources/user/my-ressources` → ne doit pas voir R1
4. User du département D1 → `GET /ressources/{R1_id}` → doit voir R1
5. User du département D2 → `GET /ressources/{R1_id}` → doit recevoir 403

### Test 2 : Formations
1. Admin assigne formation F1 au département D1
2. User du département D1 → `GET /formations/user/my-formations` → doit voir F1
3. User du département D2 → `GET /formations/user/my-formations` → ne doit pas voir F1
4. User du département D1 → `GET /formations/{F1_id}` → doit voir F1
5. User du département D2 → `GET /formations/{F1_id}` → doit recevoir 403

### Test 3 : Documents ORG
1. Admin assigne document DOC1 au département D1
2. User du département D1 → `GET /documents/user/my-documents` → doit voir DOC1
3. User du département D2 → `GET /documents/user/my-documents` → ne doit pas voir DOC1
4. User du département D1 → `GET /documents/{DOC1_id}` → doit voir DOC1
5. User du département D2 → `GET /documents/{DOC1_id}` → doit recevoir 403

### Test 4 : Validation Organisation
1. Admin Org1 essaie d'assigner ressource de Org2 → doit recevoir 403/400
2. Admin Org1 essaie d'assigner ressource à département de Org2 → doit recevoir 400 avec message explicite

---

## 📝 NOTES IMPORTANTES

1. **Isolation stricte** : Tous les filtres incluent `organization_id` pour garantir l'isolation entre organisations
2. **Mode OPT-IN** : Les éléments doivent être explicitement assignés pour être visibles par les users
3. **Admin toujours accès** : Les admins peuvent toujours voir tous les éléments de leur organisation
4. **Documents GLOBAL exclus** : Les documents de scope "GLOBAL" ne peuvent pas être affectés aux départements (réservés au superadmin)

---

**Document créé le :** 2025-12-18  
**Dernière mise à jour :** 2025-12-18

