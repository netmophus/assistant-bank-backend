# 📋 Explication du Système de Licence Actuel

## 🗄️ 1. STOCKAGE DE LA LICENCE

### Collection MongoDB : `licenses`

**Fichier :** `app/models/license.py`

**Structure d'un document :**
```javascript
{
  "_id": ObjectId("..."),
  "organization_id": ObjectId("..."),  // ID de l'organisation (banque)
  "plan": "Standard",                   // Plan de licence (Standard, Pro, etc.)
  "max_users": 50,                      // Nombre maximum d'utilisateurs autorisés
  "start_date": ISODate("..."),         // Date de début de la licence
  "end_date": ISODate("..."),           // Date de fin de la licence
  "status": "active",                   // Statut : "active", "expired", "suspended"
  "features": ["bank_qa", "letters", "training_modules"],  // Liste des features activées
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

**Schéma Pydantic :** `app/schemas/license.py`
- `LicenseBase` : Champs de base
- `LicenseCreate` : Pour la création
- `LicenseUpdate` : Pour la mise à jour
- `LicensePublic` : Pour la réponse publique

---

## 🔍 2. VÉRIFICATION DE LA LICENCE

### Fonction principale : `get_active_license_for_org(org_id)`

**Fichier :** `app/models/license.py` (ligne 88)

**Logique de vérification :**
```python
async def get_active_license_for_org(org_id: str) -> Optional[dict]:
    """
    Récupère une licence 'active' pour une organisation,
    en vérifiant aussi que la date actuelle est dans [start_date, end_date].
    """
    # Vérifie :
    # 1. organization_id correspond
    # 2. status == "active"
    # 3. start_date <= aujourd'hui <= end_date
```

**Critères d'une licence active :**
- ✅ `status` = `"active"`
- ✅ `start_date` <= date du jour
- ✅ `end_date` >= date du jour
- ✅ `organization_id` correspond

---

## 🛡️ 3. OÙ LA LICENCE EST VÉRIFIÉE ACTUELLEMENT

### A. Au moment du LOGIN (`app/routers/auth.py`)

**Fichier :** `app/routers/auth.py` (lignes 64-72)

**Endpoint :** `POST /auth/login`

**Logique :**
```python
# Si ce n'est pas un super admin, vérifier la licence active
if not is_super_admin:
    org_id = str(user["organization_id"])
    license_doc = await get_active_license_for_org(org_id)
    if not license_doc:
        raise HTTPException(
            status_code=403,
            detail="Aucune licence active pour cette banque..."
        )
```

**Impact :** 
- ❌ **Bloque la connexion** si pas de licence active
- ✅ Les superadmins peuvent toujours se connecter (pas de vérification)

---

### B. Lors de la CRÉATION D'UTILISATEUR (`app/models/user.py`)

**Fichier :** `app/models/user.py` (lignes 305-329)

**Fonction :** `create_org_user(org_id, user_in)`

**Logique :**
```python
# 1. Vérifier la licence active
license_doc = await get_active_license_for_org(org_id)
if not license_doc:
    raise ValueError("Aucune licence active pour cette organisation.")

# 2. Vérifier le quota d'utilisateurs
current_count = await count_users_by_org(org_id)
if current_count >= license_doc["max_users"]:
    raise ValueError(f"Limite d'utilisateurs atteinte ({license_doc['max_users']} max)")
```

**Impact :**
- ❌ **Bloque la création d'utilisateur** si pas de licence active
- ❌ **Bloque la création** si quota d'utilisateurs dépassé

---

## 🚫 4. ACTIONS BLOQUÉES ACTUELLEMENT

### Actions protégées par licence :

1. **Connexion** (`/auth/login`)
   - ❌ Impossible de se connecter sans licence active
   - ✅ Exception : superadmins

2. **Création d'utilisateurs** (`create_org_user`)
   - ❌ Impossible de créer un utilisateur sans licence active
   - ❌ Impossible si quota d'utilisateurs dépassé

### Actions NON protégées actuellement :

- ❌ **Accès à la base de connaissances globale** (GLOBAL chunks) dans l'IA
- ❌ **Consultation des ressources globales** côté UI
- ❌ **Autres fonctionnalités** (formations, documents org, etc.)

---

## 📍 5. POINTS D'ENTRÉE ACTUELS

### Routes protégées par licence :

**Aucune route n'utilise actuellement de dépendance FastAPI pour vérifier la licence** (sauf le login qui le fait manuellement).

**Les vérifications sont faites :**
- ✅ Dans le login (`auth.py`)
- ✅ Dans la création d'utilisateur (`user.py`)

**Pas de middleware ou de dépendance réutilisable** pour vérifier la licence sur d'autres routes.

---

## 🎯 6. CE QUI MANQUE ACTUELLEMENT

### Pour implémenter la restriction GLOBAL :

1. **Fonction réutilisable** : `org_has_active_license(org_id)` 
   - ✅ Existe déjà : `get_active_license_for_org(org_id)` retourne `None` si pas de licence
   - ✅ Peut être utilisée directement

2. **Dans `generate_question_answer`** :
   - ❌ Actuellement : Recherche GLOBAL toujours effectuée (lignes 517-542)
   - ✅ À modifier : Ne rechercher GLOBAL que si licence active

3. **Côté UI (optionnel)** :
   - ❌ Pas de vérification côté frontend actuellement
   - ✅ À ajouter : Masquer/bloquer l'accès aux ressources globales

---

## 📝 RÉSUMÉ EN TERRE À TERRE

**Comment ça marche aujourd'hui :**

1. **Stockage** : Les licences sont dans la collection `licenses` avec :
   - Organisation concernée
   - Dates de validité (start_date → end_date)
   - Statut (active/expired/suspended)
   - Quota d'utilisateurs (max_users)
   - Features activées

2. **Vérification** : La fonction `get_active_license_for_org()` vérifie :
   - Que la licence existe
   - Que le statut est "active"
   - Que la date du jour est entre start_date et end_date

3. **Utilisation actuelle** :
   - ✅ **Login** : Bloque la connexion si pas de licence
   - ✅ **Création utilisateur** : Bloque si pas de licence ou quota dépassé
   - ❌ **Base de connaissances globale** : **PAS DE VÉRIFICATION** (c'est ce qu'on va ajouter)

4. **Important** : 
   - La licence est au niveau **ORGANISATION**
   - Si l'org a une licence active, **tous ses utilisateurs** (admin + users) en bénéficient
   - Les **superadmins** n'ont pas besoin de licence (ils gèrent le système)

---

## 🔧 FICHIERS CONCERNÉS

### Backend :
- ✅ `app/models/license.py` : Modèle et fonctions de licence
- ✅ `app/schemas/license.py` : Schémas Pydantic
- ✅ `app/routers/license.py` : Endpoints CRUD licences
- ✅ `app/routers/auth.py` : Vérification licence au login
- ✅ `app/models/user.py` : Vérification licence création utilisateur
- ✅ `app/services/ai_service.py` : **À MODIFIER** - Recherche GLOBAL
- ✅ `app/models/documents.py` : Fonction `search_document_chunks` (déjà OK)

### Frontend (optionnel) :
- ❌ Pas de vérification actuellement
- ✅ À ajouter : Vérification licence pour masquer ressources globales

