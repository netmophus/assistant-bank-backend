# 🔐 Explication : Permissions des Menus vs Affectation du Contenu

## 📋 TABLE DES MATIÈRES

1. [Vue d'ensemble](#vue-densemble)
2. [Système 1 : Permissions des Menus (tab_permissions)](#système-1-permissions-des-menus-tab_permissions)
3. [Système 2 : Affectation du Contenu des Menus](#système-2-affectation-du-contenu-des-menus)
4. [Différences et Complémentarité](#différences-et-complémentarité)
5. [Exemples Concrets](#exemples-concrets)

---

## 🎯 VUE D'ENSEMBLE

Il existe **DEUX SYSTÈMES DISTINCTS** qui fonctionnent ensemble pour contrôler l'accès dans l'application :

### 1. **Permissions des Menus** (`tab_permissions`)
- **Objectif** : Contrôler quels **menus/onglets** sont **visibles** pour quels utilisateurs
- **Exemple** : L'utilisateur voit-il le menu "Ressources" dans la navigation ?
- **Niveau** : Visibilité des modules entiers

### 2. **Affectation du Contenu** (`ressource_department_assignments`, etc.)
- **Objectif** : Contrôler quel **contenu** est **accessible** dans chaque menu
- **Exemple** : Quelles ressources spécifiques l'utilisateur voit-il dans le menu "Ressources" ?
- **Niveau** : Contenu à l'intérieur d'un module

---

## 🔐 SYSTÈME 1 : PERMISSIONS DES MENUS (tab_permissions)

### 📍 Ce qu'on a fait récemment

**Fichiers concernés :**
- `app/models/tab_permissions.py`
- `app/routers/tab_permissions.py`
- `app/schemas/tab_permissions.py`
- Frontend : `src/permissions/permissionService.js`, `src/permissions/PermissionContext.jsx`

### 🎯 Objectif

Contrôler la **visibilité des menus/onglets** dans l'interface utilisateur selon :
- **Organisation** : Tous les utilisateurs de l'organisation
- **Département** : Utilisateurs d'un département spécifique
- **Service** : Utilisateurs d'un service spécifique
- **Rôle départemental** : `agent`, `chef_service`, `directeur`
- **Utilisateur spécifique** : Un utilisateur précis (`user_id`)

### 📊 Structure des données

**Collection MongoDB :** `tab_permissions`

```json
{
  "_id": ObjectId("..."),
  "organization_id": ObjectId("..."),
  "tabs": [
    {
      "tab_id": "ressources",
      "enabled": true,
      "rules": [
        {
          "rule_type": "SEGMENT",
          "department_id": ObjectId("..."),
          "service_id": null,
          "role_departement": null
        },
        {
          "rule_type": "USER",
          "user_id": ObjectId("...")
        }
      ]
    }
  ]
}
```

### 🔍 Fonctionnement

1. **Admin configure les permissions** :
   - Active/désactive un onglet (`enabled: true/false`)
   - Définit des règles d'accès (SEGMENT ou USER)

2. **Backend calcule les onglets autorisés** :
   - Endpoint : `GET /tab-permissions/user/allowed-tabs`
   - Fonction : `get_user_allowed_tabs()`
   - Retourne : Liste des `tab_id` autorisés (ex: `["questions", "formations", "dashboard"]`)

3. **Frontend filtre les menus** :
   - Utilise `usePermissions()` hook
   - Filtre les menus selon `allowedTabs`
   - Cache les menus non autorisés

### ✅ Exemple

**Configuration :**
- Onglet "Ressources" activé (`enabled: true`)
- Règle : Accessible uniquement au département "RH" (`department_id: "dept_rh"`)

**Résultat :**
- ✅ User du département RH → Voit le menu "Ressources"
- ❌ User du département Finance → Ne voit PAS le menu "Ressources"

---

## 📦 SYSTÈME 2 : AFFECTATION DU CONTENU DES MENUS

### 📍 Ce qui existe déjà

**Fichiers concernés :**
- `app/models/ressource.py` (fonctions d'affectation)
- `app/routers/ressource.py` (endpoints d'affectation)
- Collection MongoDB : `ressource_department_assignments`

### 🎯 Objectif

Contrôler quel **contenu spécifique** est accessible dans un menu donné selon :
- **Département** : Ressources assignées à un département
- **Service** : (Peut être étendu)
- **Organisation** : Toutes les ressources de l'organisation (pour les admins)

### 📊 Structure des données

**Collection MongoDB :** `ressource_department_assignments`

```json
{
  "_id": ObjectId("..."),
  "ressource_id": ObjectId("..."),
  "department_id": ObjectId("..."),
  "created_at": ISODate("...")
}
```

### 🔍 Fonctionnement

1. **Admin assigne une ressource à des départements** :
   - Endpoint : `POST /ressources/{ressource_id}/assign`
   - Fonction : `assign_ressource_to_departments()`
   - Paramètres : Liste de `department_ids`

2. **User consulte les ressources** :
   - Endpoint : `GET /ressources/user/my-ressources`
   - Fonction : `get_ressources_for_department()`
   - Retourne : Liste des ressources assignées au département de l'utilisateur

3. **Filtrage automatique** :
   - Le backend filtre automatiquement selon `department_id` de l'utilisateur
   - L'utilisateur ne voit que les ressources assignées à son département

### ✅ Exemple

**Configuration :**
- Ressource "Guide RH 2024" assignée au département "RH"
- Ressource "Guide Finance 2024" assignée au département "Finance"

**Résultat :**
- ✅ User du département RH → Voit "Guide RH 2024" (mais pas "Guide Finance 2024")
- ✅ User du département Finance → Voit "Guide Finance 2024" (mais pas "Guide RH 2024")
- ✅ Admin → Voit toutes les ressources de l'organisation

---

## 🔄 DIFFÉRENCES ET COMPLÉMENTARITÉ

### 📊 Tableau Comparatif

| Aspect | Permissions Menus | Affectation Contenu |
|--------|-------------------|---------------------|
| **Niveau** | Module/Menu entier | Contenu à l'intérieur |
| **Question** | "L'utilisateur voit-il le menu ?" | "Quel contenu voit-il dans le menu ?" |
| **Collection** | `tab_permissions` | `ressource_department_assignments` |
| **Granularité** | Par menu (ressources, formations, etc.) | Par élément (ressource spécifique) |
| **Règles** | SEGMENT (dept/service/rôle) ou USER | Par département uniquement |
| **Mode** | OPT-IN (doit être activé) | OPT-IN (doit être assigné) |

### 🎯 Fonctionnement Combiné

**Exemple complet :**

1. **Permissions Menus** :
   - User A (Département RH) → Voit le menu "Ressources" ✅
   - User B (Département Finance) → Ne voit PAS le menu "Ressources" ❌

2. **Affectation Contenu** :
   - User A (Département RH) → Voit uniquement les ressources assignées au département RH
   - User B (Département Finance) → Ne voit rien (car menu caché)

**Résultat final :**
- User A → Voit le menu "Ressources" avec uniquement les ressources du département RH
- User B → Ne voit pas le menu "Ressources" du tout

---

## 📝 EXEMPLES CONCRETS

### Exemple 1 : Menu "Ressources"

#### Étape 1 : Permissions Menus
```json
{
  "tab_id": "ressources",
  "enabled": true,
  "rules": [
    {
      "rule_type": "SEGMENT",
      "department_id": "dept_rh",
      "service_id": null,
      "role_departement": null
    }
  ]
}
```
**Résultat :** Seuls les users du département RH voient le menu "Ressources"

#### Étape 2 : Affectation Contenu
```json
// Ressource 1 assignée au département RH
{
  "ressource_id": "ressource_1",
  "department_id": "dept_rh"
}

// Ressource 2 assignée au département RH
{
  "ressource_id": "ressource_2",
  "department_id": "dept_rh"
}
```
**Résultat :** Les users du département RH voient uniquement "Ressource 1" et "Ressource 2"

### Exemple 2 : Menu "Formations"

#### Étape 1 : Permissions Menus
```json
{
  "tab_id": "formations",
  "enabled": true,
  "rules": [
    {
      "rule_type": "SEGMENT",
      "department_id": null,
      "service_id": null,
      "role_departement": "directeur"
    }
  ]
}
```
**Résultat :** Seuls les directeurs voient le menu "Formations"

#### Étape 2 : Affectation Contenu
```json
// Formation 1 assignée au département RH
{
  "formation_id": "formation_1",
  "department_id": "dept_rh"
}

// Formation 2 assignée au département Finance
{
  "formation_id": "formation_2",
  "department_id": "dept_finance"
}
```
**Résultat :** 
- Directeur du département RH → Voit uniquement "Formation 1"
- Directeur du département Finance → Voit uniquement "Formation 2"

---

## 🎯 RÉSUMÉ

### Permissions Menus (tab_permissions)
- ✅ **Contrôle la visibilité des menus**
- ✅ **Granularité** : Par menu/onglet
- ✅ **Règles** : SEGMENT (dept/service/rôle) ou USER (utilisateur spécifique)
- ✅ **Mode** : OPT-IN strict (doit être activé explicitement)
- ✅ **Collection** : `tab_permissions`

### Affectation Contenu
- ✅ **Contrôle le contenu accessible dans chaque menu**
- ✅ **Granularité** : Par élément (ressource, formation, etc.)
- ✅ **Règles** : Par département (peut être étendu)
- ✅ **Mode** : OPT-IN (doit être assigné explicitement)
- ✅ **Collections** : `ressource_department_assignments`, `formation_department_assignments`, etc.

### Fonctionnement Combiné
1. **Permissions Menus** → Détermine si l'utilisateur voit le menu
2. **Affectation Contenu** → Détermine quel contenu il voit dans le menu

**Les deux systèmes fonctionnent ensemble pour un contrôle granulaire de l'accès !**

---

## 📁 FICHIERS CLÉS

### Permissions Menus
- `app/models/tab_permissions.py` : Logique de calcul des permissions
- `app/routers/tab_permissions.py` : Endpoints API
- `app/schemas/tab_permissions.py` : Schémas Pydantic
- `src/permissions/permissionService.js` : Service frontend
- `src/permissions/PermissionContext.jsx` : Context React

### Affectation Contenu
- `app/models/ressource.py` : Fonctions d'affectation ressources
- `app/routers/ressource.py` : Endpoints ressources
- `app/models/formation_assignment.py` : Fonctions d'affectation formations
- `app/routers/formation.py` : Endpoints formations

---

**Document créé le :** 2025-12-18  
**Dernière mise à jour :** 2025-12-18

