# 🎯 Plan d'Implémentation - Restriction Base de Connaissances Globale par Licence

## 📋 OBJECTIF

**Seules les organisations ayant une licence active doivent pouvoir accéder à la base de connaissances globale (chunks GLOBAL) dans l'IA.**

**Principe :** La licence est au niveau ORGANISATION, donc si l'org est licenciée, tous ses users (admin + users) bénéficient de GLOBAL dans l'IA.

---

## 🔍 ANALYSE DU CODE ACTUEL

### Point d'entrée : `generate_question_answer()`

**Fichier :** `app/services/ai_service.py` (lignes 444-612)

**Flux actuel :**
1. Génère l'embedding de la question
2. Recherche dans documents ORG (si `organization_id` fourni)
3. **Recherche dans documents GLOBAL** (toujours effectuée, lignes 517-542)
4. Combine les contextes et génère la réponse

**Problème :** La recherche GLOBAL est **toujours effectuée**, même si l'organisation n'a pas de licence active.

---

## ✅ SOLUTION PROPOSÉE

### 1. Créer une fonction helper réutilisable

**Fichier :** `app/models/license.py`

**Fonction à ajouter :**
```python
async def org_has_active_license(org_id: Optional[str]) -> bool:
    """
    Vérifie si une organisation a une licence active.
    Retourne True si licence active, False sinon.
    Si org_id est None (superadmin), retourne True.
    """
    if not org_id:
        return True  # Superadmins ont toujours accès
    
    license_doc = await get_active_license_for_org(org_id)
    return license_doc is not None
```

**Avantages :**
- ✅ Réutilisable partout
- ✅ Gère le cas superadmin (None)
- ✅ Simple et clair

---

### 2. Modifier `generate_question_answer()`

**Fichier :** `app/services/ai_service.py` (lignes 516-542)

**Modification :**
```python
# AVANT (lignes 516-542)
# 2. Recherche dans base de connaissances globale (limit 3)
global_chunks = await search_document_chunks(
    organization_id=None,
    query_embedding=question_embedding,
    scope="GLOBAL",
    limit=3
)

# APRÈS
# 2. Recherche dans base de connaissances globale (limit 3)
# UNIQUEMENT si l'organisation a une licence active
global_chunks = []
if organization_id:
    from app.models.license import org_has_active_license
    has_license = await org_has_active_license(organization_id)
    if has_license:
        global_chunks = await search_document_chunks(
            organization_id=None,
            query_embedding=question_embedding,
            scope="GLOBAL",
            limit=3
        )
else:
    # Superadmin : toujours accès à GLOBAL
    global_chunks = await search_document_chunks(
        organization_id=None,
        query_embedding=question_embedding,
        scope="GLOBAL",
        limit=3
    )
```

**Logique :**
- ✅ Si `organization_id` fourni → Vérifier licence → Rechercher GLOBAL seulement si licence active
- ✅ Si `organization_id` est None (superadmin) → Toujours rechercher GLOBAL
- ✅ Si pas de licence → `global_chunks = []` → Seule la recherche ORG est utilisée

---

### 3. Vérifier où `generate_question_answer()` est appelé

**Fichier :** `app/models/question.py` (ligne 140)

**Appel actuel :**
```python
answer = await generate_question_answer(
    question=question_text,
    context=context,
    user_department=department_name,
    user_service=service_name,
    organization_id=organization_id  # ✅ Déjà passé !
)
```

**✅ Bonne nouvelle :** `organization_id` est **déjà passé** à la fonction !

**Vérification :** S'assurer que `organization_id` vient bien de l'utilisateur connecté.

**Fichier :** `app/models/question.py` (ligne ~120)
```python
# Récupérer l'utilisateur pour obtenir organization_id
user = await get_user_by_id(user_id)
organization_id = str(user["organization_id"]) if user.get("organization_id") else None
```

**✅ Parfait :** `organization_id` est bien récupéré depuis l'utilisateur.

---

## 📝 MODIFICATIONS À APPORTER

### Backend

#### 1. Ajouter fonction helper (`app/models/license.py`)

**Ajout après ligne 113 :**
```python
async def org_has_active_license(org_id: Optional[str]) -> bool:
    """
    Vérifie si une organisation a une licence active.
    
    Args:
        org_id: ID de l'organisation (None pour superadmin)
    
    Returns:
        True si licence active, False sinon.
        Retourne True si org_id est None (superadmin).
    """
    if not org_id:
        return True  # Superadmins ont toujours accès
    
    license_doc = await get_active_license_for_org(org_id)
    return license_doc is not None
```

---

#### 2. Modifier `generate_question_answer()` (`app/services/ai_service.py`)

**Lignes à modifier :** 516-542

**Remplacement :**
```python
# 2. Recherche dans base de connaissances globale (limit 3)
# UNIQUEMENT si l'organisation a une licence active
global_chunks = []

if organization_id:
    # Vérifier si l'organisation a une licence active
    from app.models.license import org_has_active_license
    has_license = await org_has_active_license(organization_id)
    
    if has_license:
        global_chunks = await search_document_chunks(
            organization_id=None,  # Pas nécessaire pour GLOBAL
            query_embedding=question_embedding,
            scope="GLOBAL",
            limit=3
        )
    # Sinon, global_chunks reste [] (pas de recherche GLOBAL)
else:
    # Superadmin : toujours accès à GLOBAL
    global_chunks = await search_document_chunks(
        organization_id=None,
        query_embedding=question_embedding,
        scope="GLOBAL",
        limit=3
    )
```

---

### Frontend (Optionnel - Consultation ressources globales)

**Si vous voulez masquer/bloquer l'accès aux ressources globales côté UI :**

#### Endpoint à créer (optionnel) :
```python
# app/routers/license.py
@router.get("/check-active")
async def check_active_license(
    current_user: dict = Depends(get_current_user)
):
    """Vérifie si l'organisation de l'utilisateur a une licence active."""
    org_id = current_user.get("organization_id")
    if not org_id:
        return {"has_active_license": True}  # Superadmin
    
    from app.models.license import org_has_active_license
    has_license = await org_has_active_license(str(org_id))
    return {"has_active_license": has_license}
```

#### Côté frontend :
- Appeler `/licenses/check-active` au chargement
- Masquer les sections "Ressources Globales" si `has_active_license: false`
- Afficher un message : "Accès réservé aux organisations avec licence active"

---

## 🎯 ENDPOINTS IMPACTÉS

### Directement impactés :

1. **`POST /questions`** (via `generate_question_answer`)
   - ✅ Impact : Les réponses IA n'incluront plus GLOBAL si pas de licence
   - ✅ Pas de changement d'API, comportement interne

### Non impactés (pas de changement d'API) :

- ✅ Tous les autres endpoints restent inchangés
- ✅ Les superadmins continuent d'avoir accès à GLOBAL
- ✅ Les organisations avec licence continuent d'avoir accès à GLOBAL

---

## ✅ CHECKLIST D'IMPLÉMENTATION

### Backend :
- [ ] Ajouter `org_has_active_license()` dans `app/models/license.py`
- [ ] Modifier `generate_question_answer()` dans `app/services/ai_service.py`
- [ ] Tester avec organisation SANS licence → GLOBAL ne doit pas être recherché
- [ ] Tester avec organisation AVEC licence → GLOBAL doit être recherché
- [ ] Tester avec superadmin → GLOBAL doit toujours être recherché

### Frontend (optionnel) :
- [ ] Créer endpoint `/licenses/check-active` (si besoin)
- [ ] Appeler l'endpoint au chargement
- [ ] Masquer sections "Ressources Globales" si pas de licence
- [ ] Afficher message informatif

---

## 🧪 TESTS À EFFECTUER

### Test 1 : Organisation SANS licence active
1. Créer une organisation sans licence (ou avec licence expirée)
2. Créer un utilisateur pour cette organisation
3. Poser une question via `/questions`
4. **Vérifier :** La réponse ne doit contenir QUE le contexte ORG (pas de section "Base de Connaissances Globale")

### Test 2 : Organisation AVEC licence active
1. Créer une organisation avec licence active
2. Créer un utilisateur pour cette organisation
3. Poser une question via `/questions`
4. **Vérifier :** La réponse doit contenir les deux contextes (ORG + GLOBAL)

### Test 3 : Superadmin
1. Se connecter en tant que superadmin
2. Poser une question (si possible, sinon via endpoint direct)
3. **Vérifier :** La réponse doit contenir GLOBAL (superadmin a toujours accès)

---

## 📊 RÉSUMÉ DES CHANGEMENTS

### Fichiers modifiés :
1. ✅ `app/models/license.py` : Ajout fonction `org_has_active_license()`
2. ✅ `app/services/ai_service.py` : Modification `generate_question_answer()` (lignes 516-542)

### Fichiers créés :
- Aucun (modifications uniquement)

### Fichiers non modifiés :
- ✅ `app/routers/question.py` : Pas de changement (déjà passe `organization_id`)
- ✅ `app/models/question.py` : Pas de changement (déjà récupère `organization_id`)
- ✅ `app/models/documents.py` : Pas de changement (`search_document_chunks` déjà OK)

---

## 🚀 ORDRE D'IMPLÉMENTATION

1. **Étape 1** : Ajouter `org_has_active_license()` dans `license.py`
2. **Étape 2** : Modifier `generate_question_answer()` pour vérifier la licence avant recherche GLOBAL
3. **Étape 3** : Tester avec organisation sans licence
4. **Étape 4** : Tester avec organisation avec licence
5. **Étape 5** : (Optionnel) Ajouter vérification côté frontend

---

## 💡 NOTES IMPORTANTES

1. **Pas de breaking change** : Les endpoints restent identiques, seul le comportement interne change
2. **Superadmins** : Toujours accès à GLOBAL (pas de vérification)
3. **Rétrocompatibilité** : Les organisations existantes avec licence continuent de fonctionner
4. **Performance** : Si pas de licence, on évite une recherche inutile (gain de performance)

---

## ❓ QUESTIONS À CLARIFIER

1. **Superadmins** : Doivent-ils avoir accès à GLOBAL même sans licence ? → **OUI** (déjà géré)
2. **Messages d'erreur** : Faut-il informer l'utilisateur qu'il n'a pas accès à GLOBAL ? → **NON** (silencieux, juste pas de résultats GLOBAL)
3. **Frontend** : Faut-il masquer les ressources globales ? → **OPTIONNEL** (souhaité mais pas obligatoire)

