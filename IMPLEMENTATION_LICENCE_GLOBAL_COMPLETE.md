# ✅ Implémentation Complète - Restriction Base de Connaissances Globale par Licence

## 🎯 OBJECTIF ATTEINT

**Seules les organisations ayant une licence active peuvent accéder à la base de connaissances globale (chunks GLOBAL) dans l'IA.**

**Principe respecté :** La licence est au niveau ORGANISATION, donc si l'org est licenciée, tous ses users (admin + users) bénéficient de GLOBAL dans l'IA.

---

## 📝 MODIFICATIONS APPORTÉES

### 1. ✅ Fonction helper ajoutée : `org_has_active_license()`

**Fichier :** `app/models/license.py` (lignes 117-139)

**Code ajouté :**
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
        logger.debug("org_has_active_license: org_id=None (superadmin) → True")
        return True  # Superadmins ont toujours accès
    
    license_doc = await get_active_license_for_org(org_id)
    has_license = license_doc is not None
    
    if has_license:
        logger.debug(f"org_has_active_license: org_id={org_id} → True (licence active trouvée)")
    else:
        logger.debug(f"org_has_active_license: org_id={org_id} → False (pas de licence active)")
    
    return has_license
```

**Fonctionnalités :**
- ✅ Retourne `True` si `org_id` est `None` (superadmin)
- ✅ Vérifie la licence active via `get_active_license_for_org()`
- ✅ Logs de debug pour faciliter le test
- ✅ Réutilisable partout dans le code

---

### 2. ✅ Modification de `generate_question_answer()`

**Fichier :** `app/services/ai_service.py` (lignes 516-546)

**Code modifié :**
```python
# 2. Recherche dans base de connaissances globale (limit 3)
# UNIQUEMENT si l'organisation a une licence active
global_chunks = []
GLOBAL_INCLUDED = False

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
        GLOBAL_INCLUDED = True
        print(f"[DEBUG] GLOBAL_INCLUDED=True pour org_id={organization_id} ({len(global_chunks)} chunks trouvés)")
    else:
        print(f"[DEBUG] GLOBAL_INCLUDED=False pour org_id={organization_id} (pas de licence active)")
else:
    # Superadmin : toujours accès à GLOBAL
    global_chunks = await search_document_chunks(
        organization_id=None,
        query_embedding=question_embedding,
        scope="GLOBAL",
        limit=3
    )
    GLOBAL_INCLUDED = True
    print(f"[DEBUG] GLOBAL_INCLUDED=True pour superadmin ({len(global_chunks)} chunks trouvés)")
```

**Logique implémentée :**
- ✅ Si `organization_id` fourni → Vérifie la licence → Recherche GLOBAL seulement si licence active
- ✅ Si `organization_id` est `None` (superadmin) → Toujours recherche GLOBAL
- ✅ Si pas de licence → `global_chunks = []` → Seule la recherche ORG est utilisée
- ✅ Logs de debug avec `GLOBAL_INCLUDED=True/False` pour faciliter les tests

---

## 🧪 TESTS À EFFECTUER

### Test 1 : Organisation AVEC licence active

**Prérequis :**
- Créer une organisation avec une licence active (status="active", dates valides)
- Créer un utilisateur pour cette organisation
- Uploader des documents globaux dans la base de connaissances

**Étapes :**
1. Se connecter avec un utilisateur de cette organisation
2. Poser une question via `POST /questions`
3. Vérifier les logs backend : `[DEBUG] GLOBAL_INCLUDED=True pour org_id=...`
4. Vérifier la réponse IA : doit contenir les deux sections :
   - `## 📁 Contexte de votre organisation:`
   - `## 🌐 Base de Connaissances Globale (Références Officielles):`

**Résultat attendu :**
- ✅ `GLOBAL_INCLUDED=True` dans les logs
- ✅ Réponse contient les deux contextes (ORG + GLOBAL)

---

### Test 2 : Organisation SANS licence active

**Prérequis :**
- Créer une organisation SANS licence (ou avec licence expirée/suspended)
- Créer un utilisateur pour cette organisation
- Uploader des documents globaux dans la base de connaissances

**Étapes :**
1. Se connecter avec un utilisateur de cette organisation
2. Poser une question via `POST /questions`
3. Vérifier les logs backend : `[DEBUG] GLOBAL_INCLUDED=False pour org_id=...`
4. Vérifier la réponse IA : doit contenir UNIQUEMENT :
   - `## 📁 Contexte de votre organisation:`
   - ❌ PAS de section "Base de Connaissances Globale"

**Résultat attendu :**
- ✅ `GLOBAL_INCLUDED=False` dans les logs
- ✅ Réponse contient UNIQUEMENT le contexte ORG (pas de GLOBAL)

---

### Test 3 : Superadmin

**Prérequis :**
- Avoir un compte superadmin
- Uploader des documents globaux dans la base de connaissances

**Étapes :**
1. Se connecter en tant que superadmin
2. Poser une question (si possible via endpoint direct, sinon via interface)
3. Vérifier les logs backend : `[DEBUG] GLOBAL_INCLUDED=True pour superadmin`
4. Vérifier la réponse IA : doit contenir GLOBAL

**Résultat attendu :**
- ✅ `GLOBAL_INCLUDED=True` dans les logs
- ✅ Réponse contient GLOBAL (superadmin a toujours accès)

---

## 📊 COMPORTEMENT ATTENDU

### Scénario 1 : Organisation avec licence active
```
User (org_id=X, licence active) pose question
  ↓
generate_question_answer(organization_id="X")
  ↓
org_has_active_license("X") → True
  ↓
Recherche ORG (5 chunks) + Recherche GLOBAL (3 chunks)
  ↓
Réponse IA = Contexte ORG + Contexte GLOBAL
```

### Scénario 2 : Organisation sans licence active
```
User (org_id=Y, pas de licence) pose question
  ↓
generate_question_answer(organization_id="Y")
  ↓
org_has_active_license("Y") → False
  ↓
Recherche ORG (5 chunks) + PAS de recherche GLOBAL
  ↓
Réponse IA = Contexte ORG uniquement
```

### Scénario 3 : Superadmin
```
Superadmin (org_id=None) pose question
  ↓
generate_question_answer(organization_id=None)
  ↓
org_has_active_license(None) → True (par défaut)
  ↓
Recherche ORG (si applicable) + Recherche GLOBAL (3 chunks)
  ↓
Réponse IA = Contexte GLOBAL (toujours)
```

---

## 🔍 LOGS DE DEBUG

Les logs suivants apparaîtront dans la console backend lors des appels à `generate_question_answer()` :

**Organisation avec licence :**
```
[DEBUG] GLOBAL_INCLUDED=True pour org_id=6943da39294d1b535c6297c4 (3 chunks trouvés)
```

**Organisation sans licence :**
```
[DEBUG] GLOBAL_INCLUDED=False pour org_id=6943da39294d1b535c6297c4 (pas de licence active)
```

**Superadmin :**
```
[DEBUG] GLOBAL_INCLUDED=True pour superadmin (3 chunks trouvés)
```

**Pour désactiver les logs :** Retirer les `print()` ou les remplacer par `logger.debug()` avec niveau DEBUG.

---

## ✅ CHECKLIST DE VALIDATION

### Backend :
- [x] Fonction `org_has_active_license()` ajoutée dans `app/models/license.py`
- [x] Modification de `generate_question_answer()` pour vérifier la licence
- [x] Gestion du cas superadmin (organization_id=None)
- [x] Logs de debug ajoutés (`GLOBAL_INCLUDED=True/False`)
- [x] Pas de breaking change (endpoints inchangés)
- [x] Contrôle appliqué à tous les users de l'organisation (admin + users)

### Tests à exécuter :
- [ ] Test 1 : Organisation avec licence → Vérifier GLOBAL_INCLUDED=True + réponse contient GLOBAL
- [ ] Test 2 : Organisation sans licence → Vérifier GLOBAL_INCLUDED=False + réponse ne contient PAS GLOBAL
- [ ] Test 3 : Superadmin → Vérifier GLOBAL_INCLUDED=True + réponse contient GLOBAL

---

## 📁 FICHIERS MODIFIÉS

1. ✅ `app/models/license.py`
   - Ajout import `logging`
   - Ajout fonction `org_has_active_license()` (lignes 117-139)

2. ✅ `app/services/ai_service.py`
   - Modification de `generate_question_answer()` (lignes 516-546)
   - Ajout vérification licence avant recherche GLOBAL
   - Ajout logs de debug

---

## 🚀 PROCHAINES ÉTAPES (Optionnel)

### Frontend (après validation backend) :
1. Créer endpoint `/licenses/check-active` dans `app/routers/license.py`
2. Appeler cet endpoint au chargement du dashboard
3. Masquer les sections "Ressources Globales" si `has_active_license: false`
4. Afficher message informatif : "Accès réservé aux organisations avec licence active"

---

## 💡 NOTES IMPORTANTES

1. **Pas de breaking change** : Les endpoints restent identiques, seul le comportement interne change
2. **Superadmins** : Toujours accès à GLOBAL (pas de vérification)
3. **Rétrocompatibilité** : Les organisations existantes avec licence continuent de fonctionner
4. **Performance** : Si pas de licence, on évite une recherche inutile (gain de performance)
5. **Logs** : Les logs de debug peuvent être désactivés en retirant les `print()` ou en utilisant `logger.debug()` avec niveau approprié

---

## 🎯 RÉSUMÉ

**Implémentation complète et fonctionnelle :**
- ✅ Fonction helper `org_has_active_license()` créée
- ✅ Vérification licence dans `generate_question_answer()`
- ✅ Gestion superadmin (toujours accès GLOBAL)
- ✅ Logs de debug pour faciliter les tests
- ✅ Pas de breaking change
- ✅ Contrôle au niveau organisation (tous les users bénéficient)

**Prêt pour les tests !** 🚀

