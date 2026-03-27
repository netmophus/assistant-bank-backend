# 🔐 Système de Permissions - Administrateur d'Organisation

## 📋 TABLE DES MATIÈRES

1. [Vue d'ensemble](#vue-densemble)
2. [Hiérarchie des rôles](#hiérarchie-des-rôles)
3. [Mécanisme de vérification](#mécanisme-de-vérification)
4. [Fonctionnalités réservées aux admins d'organisation](#fonctionnalités-réservées-aux-admins-dorganisation)
5. [Endpoints protégés](#endpoints-protégés)
6. [Isolation des données](#isolation-des-données)
7. [Différences avec les autres rôles](#différences-avec-les-autres-rôles)

---

## 🎯 VUE D'ENSEMBLE

Le système de permissions de l'application utilise un modèle basé sur les **rôles** et les **organisations**. Les administrateurs d'organisation (`role="admin"`) ont des privilèges étendus pour gérer leur organisation et ses utilisateurs, mais leurs actions sont **strictement limitées à leur propre organisation**.

### Principe fondamental

**Un admin d'organisation ne peut gérer QUE sa propre organisation et ses utilisateurs.**

---

## 👥 HIÉRARCHIE DES RÔLES

### 1. **Superadmin** (`role="superadmin"`)
- **`organization_id`** : `None` (pas d'organisation)
- **Accès** : Toutes les organisations et toutes les fonctionnalités
- **Gestion** : Création d'organisations, gestion globale, base de connaissances globale

### 2. **Admin d'Organisation** (`role="admin"`)
- **`organization_id`** : ID de l'organisation (OBLIGATOIRE)
- **Accès** : Uniquement sa propre organisation
- **Gestion** : Utilisateurs, documents, configurations de son organisation

### 3. **User** (`role="user"`)
- **`organization_id`** : ID de l'organisation
- **Accès** : Consultation et actions limitées dans son organisation
- **Gestion** : Aucune gestion administrative

### 4. **Rôles spécialisés**
- `gestionnaire_stock` : Gestion du stock
- `agent_stock_drh` : Agent DRH pour le stock
- `role_departement` : Rôles au niveau département (`agent`, `chef_service`, `directeur`)

---

## 🔍 MÉCANISME DE VÉRIFICATION

### 1. **Dependency `get_org_admin()`**

**Fichier :** `app/core/deps.py` (lignes 39-52)

```python
async def get_org_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Vérifie que l'utilisateur est un administrateur d'organisation.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")
    
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs d'organisation.",
        )
    
    return current_user
```

**Conditions de validation :**
- ✅ `role == "admin"` (exactement "admin")
- ✅ `organization_id` doit être présent (pas `None`)
- ❌ Si `role != "admin"` → **403 Forbidden**
- ❌ Si `organization_id` est `None` → **403 Forbidden** (superadmin exclu)

### 2. **Vérification manuelle dans certains endpoints**

Certains endpoints vérifient manuellement le rôle admin au lieu d'utiliser `get_org_admin()` :

```python
user_role = current_user.get("role", "user")
user_org_id = current_user.get("organization_id")

if user_role != "admin" or not user_org_id:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Accès réservé aux administrateurs d'organisation.",
    )
```

**Fichiers concernés :**
- `app/routers/pcb.py` (tous les endpoints PCB)
- `app/routers/auth.py` (création/liste utilisateurs)
- `app/routers/question.py` (liste questions org)
- `app/routers/department.py` (gestion départements)
- `app/routers/formation.py` (publication formations)

---

## 🛡️ FONCTIONNALITÉS RÉSERVÉES AUX ADMINS D'ORGANISATION

### 1. **Gestion des Utilisateurs**

#### Créer un utilisateur
- **Endpoint :** `POST /auth/users`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)
- **Contraintes :**
  - L'utilisateur créé doit appartenir à la même organisation que l'admin
  - Vérification des limites de licence
- **Fichier :** `app/routers/auth.py` (lignes 200-230)

#### Lister les utilisateurs de l'organisation
- **Endpoint :** `GET /auth/users/org`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)
- **Fichier :** `app/routers/auth.py` (lignes 233-248)

#### Modifier/Supprimer un utilisateur
- **Endpoints :** `PUT /auth/users/{user_id}`, `DELETE /auth/users/{user_id}`
- **Contraintes :** L'utilisateur modifié doit appartenir à la même organisation

---

### 2. **Gestion des Documents**

#### Upload de documents
- **Endpoint :** `POST /documents/upload`
- **Dependency :** `get_org_admin`
- **Fonctionnalités :**
  - Upload PDF, Word, Excel
  - Extraction de texte
  - Découpage en chunks
  - Génération d'embeddings
  - Indexation dans la base de connaissances organisationnelle
- **Fichier :** `app/routers/documents.py` (ligne 52)

#### Mise à jour des métadonnées
- **Endpoint :** `PUT /documents/{document_id}`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/documents.py` (ligne 240)

#### Suppression de documents
- **Endpoint :** `DELETE /documents/{document_id}`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/documents.py` (ligne 256)

#### Statistiques des documents
- **Endpoint :** `GET /documents/stats`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/documents.py` (ligne 256)

#### Réindexation de documents
- **Endpoint :** `POST /documents/{document_id}/reindex`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/documents.py` (ligne 329)

#### Publication/Archivage
- **Endpoints :** `POST /documents/{document_id}/publish`, `POST /documents/{document_id}/archive`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/documents.py` (lignes 357, 375)

---

### 3. **Configuration des Impayés**

#### Récupérer la configuration complète
- **Endpoint :** `GET /impayes/config`
- **Dependency :** `get_org_admin`
- **Note :** Les utilisateurs normaux peuvent uniquement voir les tranches (`GET /impayes/config/tranches`)
- **Fichier :** `app/routers/impayes_config.py` (ligne 49)

#### Mettre à jour la configuration
- **Endpoint :** `PUT /impayes/config`
- **Dependency :** `get_org_admin`
- **Fonctionnalités :**
  - Tranches de retard
  - Modèles SMS
  - Règles de restructuration
  - Paramètres techniques
- **Fichier :** `app/routers/impayes_config.py` (ligne 71)

#### Initialiser les modèles SMS par défaut
- **Endpoint :** `POST /impayes/config/init-modeles-sms`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/impayes_config.py` (ligne 90)

---

### 4. **Gestion des Permissions d'Onglets**

#### Récupérer les permissions de l'organisation
- **Endpoint :** `GET /tab-permissions/organization`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/tab_permissions.py` (ligne 26)

#### Mettre à jour les permissions d'un onglet
- **Endpoint :** `PUT /tab-permissions/organization/tab/{tab_id}`
- **Dependency :** `get_org_admin`
- **Fonctionnalités :**
  - Activer/désactiver des onglets
  - Définir des règles par département/service/rôle
- **Fichier :** `app/routers/tab_permissions.py` (ligne 43)

---

### 5. **Configuration des Crédits**

#### Configuration PME
- **Endpoint :** `PUT /credit-pme/config`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/credit_pme.py` (ligne 59)

#### Configuration Particulier
- **Endpoint :** `PUT /credit-particulier/config`
- **Dependency :** `get_org_admin`
- **Fichier :** `app/routers/credit_particulier.py` (ligne 139)

---

### 6. **Gestion des Départements et Services**

#### Créer un département
- **Endpoint :** `POST /departments`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)
- **Contraintes :** Le département doit être créé pour la même organisation
- **Fichier :** `app/routers/department.py` (ligne 19)

#### Créer un service
- **Endpoint :** `POST /departments/{department_id}/services`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)
- **Fichier :** `app/routers/department.py`

#### Modifier un département/service
- **Endpoints :** `PUT /departments/{department_id}`, `PUT /departments/{department_id}/services/{service_id}`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)

---

### 7. **Gestion des Formations**

#### Publier une formation
- **Endpoint :** `POST /formations/{formation_id}/publish`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)
- **Fonctionnalités :**
  - Génération automatique de contenu avec IA
  - Génération automatique de QCM avec IA
- **Fichier :** `app/routers/formation.py` (ligne 200)

---

### 8. **Gestion des Questions**

#### Lister toutes les questions de l'organisation
- **Endpoint :** `GET /questions/org`
- **Dependency :** Vérification manuelle (`role="admin"` + `organization_id`)
- **Note :** Les utilisateurs normaux voient uniquement leurs propres questions
- **Fichier :** `app/routers/question.py` (ligne 71)

---

### 9. **Gestion PCB (Plan Comptable Bancaire)**

**Tous les endpoints PCB sont réservés aux admins d'organisation.**

**Fichier :** `app/routers/pcb.py`

**Endpoints protégés :**
- `POST /pcb/import` : Import du plan comptable
- `GET /pcb/accounts` : Liste des comptes
- `POST /pcb/accounts` : Créer un compte
- `PUT /pcb/accounts/{account_id}` : Modifier un compte
- `DELETE /pcb/accounts/{account_id}` : Supprimer un compte
- `GET /pcb/accounts/{account_id}` : Détails d'un compte
- `GET /pcb/accounts/search` : Recherche de comptes
- `GET /pcb/accounts/export` : Export Excel
- `GET /pcb/stats` : Statistiques
- Et tous les autres endpoints PCB...

**Vérification :** Tous utilisent une vérification manuelle (`role="admin"` + `organization_id`)

---

## 📍 ENDPOINTS PROTÉGÉS

### Endpoints utilisant `get_org_admin` :

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/documents/upload` | POST | Upload document |
| `/documents/{id}` | PUT | Mettre à jour métadonnées |
| `/documents/{id}` | DELETE | Supprimer document |
| `/documents/stats` | GET | Statistiques documents |
| `/documents/{id}/reindex` | POST | Réindexer document |
| `/documents/{id}/publish` | POST | Publier document |
| `/documents/{id}/archive` | POST | Archiver document |
| `/impayes/config` | GET | Configuration impayés (complète) |
| `/impayes/config` | PUT | Mettre à jour configuration |
| `/impayes/config/init-modeles-sms` | POST | Initialiser modèles SMS |
| `/tab-permissions/organization` | GET | Permissions onglets |
| `/tab-permissions/organization/tab/{id}` | PUT | Mettre à jour permissions onglet |
| `/credit-pme/config` | PUT | Configuration crédit PME |
| `/credit-particulier/config` | PUT | Configuration crédit particulier |

### Endpoints avec vérification manuelle :

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/auth/users` | POST | Créer utilisateur |
| `/auth/users/org` | GET | Lister utilisateurs org |
| `/departments` | POST | Créer département |
| `/departments/{id}` | PUT | Modifier département |
| `/departments/{id}/services` | POST | Créer service |
| `/departments/{id}/services/{id}` | PUT | Modifier service |
| `/questions/org` | GET | Lister questions org |
| `/formations/{id}/publish` | POST | Publier formation |
| `/pcb/*` | * | Tous les endpoints PCB |

---

## 🔒 ISOLATION DES DONNÉES

### Principe d'isolation

**Toutes les actions d'un admin d'organisation sont automatiquement filtrées par `organization_id`.**

### Exemples d'isolation :

#### 1. Documents
```python
# Dans upload_document()
organization_id = str(current_user["organization_id"])
# Le document est créé avec organization_id
# Les recherches ne retournent que les documents de cette organisation
```

#### 2. Utilisateurs
```python
# Dans create_user()
if str(user_org_id) != user_in.organization_id:
    raise HTTPException(403, "Vous ne pouvez créer des utilisateurs que pour votre propre organisation.")
```

#### 3. Configuration Impayés
```python
# Dans update_impayes_config()
config.organization_id = org_id  # Forcé à l'org de l'admin
```

#### 4. Permissions d'onglets
```python
# Dans get_organization_tab_permissions()
org_id = current_user.get("organization_id")
permissions = await get_tab_permissions(org_id)  # Uniquement pour cette org
```

---

## 🔄 DIFFÉRENCES AVEC LES AUTRES RÔLES

### Admin d'Organisation vs User

| Fonctionnalité | Admin | User |
|----------------|-------|------|
| Créer des utilisateurs | ✅ | ❌ |
| Uploader des documents | ✅ | ❌ |
| Modifier la configuration | ✅ | ❌ |
| Voir toutes les questions | ✅ | ❌ (uniquement les siennes) |
| Publier des formations | ✅ | ❌ |
| Gérer les permissions d'onglets | ✅ | ❌ |
| Voir la config complète impayés | ✅ | ❌ (uniquement tranches) |
| Analyser des crédits | ✅ | ✅ |
| Poser des questions à l'IA | ✅ | ✅ |
| Consulter les documents | ✅ | ✅ |

### Admin d'Organisation vs Superadmin

| Fonctionnalité | Admin Org | Superadmin |
|----------------|-----------|------------|
| Gérer sa propre organisation | ✅ | ✅ |
| Gérer d'autres organisations | ❌ | ✅ |
| Créer des organisations | ❌ | ✅ |
| Gérer la base de connaissances globale | ❌ | ✅ |
| Gérer les licences | ❌ | ✅ |
| Accès à toutes les données | ❌ | ✅ |

---

## 🛠️ IMPLÉMENTATION TECHNIQUE

### Schéma User

**Fichier :** `app/schemas/user.py`

```python
class UserPublic(BaseModel):
    id: str
    organization_id: Optional[str] = None  # None pour superadmin
    role: Optional[str] = None  # "user", "admin", "superadmin"
    role_departement: Optional[str] = None  # "agent", "chef_service", "directeur"
    is_active: Optional[bool] = True
```

### Vérification dans les modèles

**Fichier :** `app/models/user.py`

- Lors de la création d'un utilisateur, le `role` par défaut est `"user"`
- Seul un superadmin peut créer un `admin` ou modifier le rôle en `admin`
- Un `admin` ne peut pas créer un `superadmin`

---

## 📝 NOTES IMPORTANTES

### 1. **Sécurité**
- ✅ Toutes les vérifications sont effectuées côté serveur
- ✅ Les `organization_id` sont toujours validés avant toute action
- ✅ Les superadmins sont explicitement exclus des endpoints admin d'org

### 2. **Isolation stricte**
- ✅ Un admin ne peut jamais accéder aux données d'une autre organisation
- ✅ Les requêtes MongoDB filtrent toujours par `organization_id`
- ✅ Les validations empêchent la création/modification hors organisation

### 3. **Licences**
- ✅ Les admins d'organisation sont soumis aux limites de leur licence
- ✅ La création d'utilisateurs vérifie les quotas de la licence
- ✅ Les fonctionnalités peuvent être limitées selon le plan de licence

### 4. **Rôles départementaux**
- ✅ Les admins d'organisation peuvent avoir un `role_departement`
- ✅ Ce rôle départemental peut influencer les permissions d'onglets
- ✅ Mais le rôle système `role="admin"` reste le principal pour les permissions admin

---

## 🎯 RÉSUMÉ

**Un administrateur d'organisation (`role="admin"` avec `organization_id` défini) peut :**

✅ Gérer les utilisateurs de son organisation  
✅ Uploader et gérer les documents de son organisation  
✅ Configurer les paramètres de son organisation (impayés, crédits, permissions)  
✅ Gérer les départements et services de son organisation  
✅ Publier des formations pour son organisation  
✅ Voir toutes les questions de son organisation  
✅ Gérer le plan comptable bancaire de son organisation  

**Mais il ne peut PAS :**

❌ Accéder aux données d'autres organisations  
❌ Créer des organisations  
❌ Gérer la base de connaissances globale  
❌ Gérer les licences  
❌ Créer des superadmins  

**Toutes ses actions sont automatiquement isolées à son `organization_id`.**

---

## 📁 FICHIERS CLÉS

- **`app/core/deps.py`** : Définitions `get_current_user`, `get_org_admin`, `get_superadmin`
- **`app/models/user.py`** : Modèles et fonctions de gestion des utilisateurs
- **`app/schemas/user.py`** : Schémas Pydantic pour les utilisateurs
- **`app/routers/documents.py`** : Endpoints documents (utilise `get_org_admin`)
- **`app/routers/auth.py`** : Endpoints authentification et utilisateurs
- **`app/routers/impayes_config.py`** : Configuration impayés
- **`app/routers/tab_permissions.py`** : Permissions d'onglets
- **`app/routers/pcb.py`** : Plan comptable bancaire (vérification manuelle)
- **`app/routers/department.py`** : Gestion départements/services
- **`app/routers/formation.py`** : Gestion formations
- **`app/routers/question.py`** : Gestion questions

---

**Document créé le :** 2025-01-18  
**Dernière mise à jour :** 2025-01-18

