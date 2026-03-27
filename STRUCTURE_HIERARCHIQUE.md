# 🏢 Structure Hiérarchique de l'Application

## 📋 TABLE DES MATIÈRES

1. [Vue d'ensemble](#vue-densemble)
2. [Hiérarchie complète](#hiérarchie-complète)
3. [Détails de chaque niveau](#détails-de-chaque-niveau)
4. [Rôles et permissions](#rôles-et-permissions)
5. [Structure des données](#structure-des-données)
6. [Exemples concrets](#exemples-concrets)

---

## 🎯 VUE D'ENSEMBLE

Oui, vous avez bien la structure suivante :

```
ORGANISATION
    └── DÉPARTEMENTS
        └── SERVICES
            └── AGENTS (Utilisateurs)
```

**Chaque niveau peut contenir plusieurs éléments du niveau inférieur.**

---

## 📊 HIÉRARCHIE COMPLÈTE

```
┌─────────────────────────────────────┐
│     ORGANISATION                    │
│  (Banque, Institution, etc.)         │
│  - name, code, country, status      │
└──────────────┬──────────────────────┘
               │
               ├──────────────────────────────┐
               │                              │
    ┌──────────▼──────────┐      ┌───────────▼──────────┐
    │   DÉPARTEMENT 1     │      │   DÉPARTEMENT 2      │
    │  (ex: RH, Finance)  │      │  (ex: Commercial)    │
    │  - name, code       │      │  - name, code        │
    └──────────┬──────────┘      └───────────┬──────────┘
               │                              │
    ┌──────────┼──────────┐      ┌───────────┼──────────┐
    │          │          │      │           │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌──▼───┐ ┌───▼───┐ ┌───▼───┐
│SERVICE│ │SERVICE│ │SERVICE│ │SERVICE│ │SERVICE│ │SERVICE│
│   1   │ │   2   │ │   3   │ │   4   │ │   5   │ │   6   │
│(ex:   │ │(ex:   │ │(ex:   │ │(ex:   │ │(ex:   │ │(ex:   │
│Recrut)│ │Form.) │ │Paie)  │ │Vente) │ │Credit)│ │...)   │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
    │         │         │         │         │         │
    └─────────┴─────────┴─────────┴─────────┴─────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│ AGENT │ │ AGENT │ │ AGENT │
│   1   │ │   2   │ │   3   │
│(User) │ │(User) │ │(User) │
└───────┘ └───────┘ └───────┘
```

---

## 📁 DÉTAILS DE CHAQUE NIVEAU

### 1. **ORGANISATION** (Niveau 1)

**Collection MongoDB :** `organizations`

**Champs :**
- `_id` : ObjectId unique
- `name` : Nom de l'organisation (ex: "Banque ABC")
- `code` : Code unique (ex: "BANK_ABC")
- `country` : Pays (ex: "Niger")
- `status` : Statut ("active", "inactive", etc.)
- `created_at` : Date de création

**Caractéristiques :**
- ✅ Une organisation peut avoir plusieurs départements
- ✅ Une organisation peut avoir plusieurs utilisateurs (directement ou via départements/services)
- ✅ Isolation stricte : toutes les données sont filtrées par `organization_id`

**Exemple :**
```json
{
  "_id": ObjectId("..."),
  "name": "Banque ABC",
  "code": "BANK_ABC",
  "country": "Niger",
  "status": "active",
  "created_at": ISODate("2024-01-01T00:00:00Z")
}
```

---

### 2. **DÉPARTEMENT** (Niveau 2)

**Collection MongoDB :** `departments`

**Champs :**
- `_id` : ObjectId unique
- `name` : Nom du département (ex: "Ressources Humaines")
- `code` : Code unique dans l'organisation (ex: "RH")
- `description` : Description optionnelle
- `organization_id` : ObjectId de l'organisation parente (OBLIGATOIRE)
- `status` : Statut ("active", "inactive")
- `created_at` : Date de création

**Caractéristiques :**
- ✅ Un département appartient à UNE organisation
- ✅ Un département peut avoir plusieurs services
- ✅ Un département peut avoir des agents directement (sans service)
- ✅ Le code doit être unique dans l'organisation

**Exemple :**
```json
{
  "_id": ObjectId("..."),
  "name": "Ressources Humaines",
  "code": "RH",
  "description": "Gestion des ressources humaines",
  "organization_id": ObjectId("..."), // Référence à l'organisation
  "status": "active",
  "created_at": ISODate("2024-01-01T00:00:00Z")
}
```

**Note importante :** Un utilisateur peut être dans un département **sans service** (agent direct du département).

---

### 3. **SERVICE** (Niveau 3)

**Collection MongoDB :** `services`

**Champs :**
- `_id` : ObjectId unique
- `name` : Nom du service (ex: "Recrutement")
- `code` : Code unique dans le département (ex: "REC")
- `description` : Description optionnelle
- `department_id` : ObjectId du département parent (OBLIGATOIRE)
- `status` : Statut ("active", "inactive")
- `created_at` : Date de création

**Caractéristiques :**
- ✅ Un service appartient à UN département
- ✅ Un service peut avoir plusieurs agents
- ✅ Le code doit être unique dans le département
- ⚠️ Un service ne peut pas exister sans département

**Exemple :**
```json
{
  "_id": ObjectId("..."),
  "name": "Recrutement",
  "code": "REC",
  "description": "Service de recrutement",
  "department_id": ObjectId("..."), // Référence au département RH
  "status": "active",
  "created_at": ISODate("2024-01-01T00:00:00Z")
}
```

---

### 4. **AGENT / UTILISATEUR** (Niveau 4)

**Collection MongoDB :** `users`

**Champs :**
- `_id` : ObjectId unique
- `email` : Email unique
- `full_name` : Nom complet
- `password_hash` : Hash du mot de passe
- `organization_id` : ObjectId de l'organisation (OBLIGATOIRE)
- `department_id` : ObjectId du département (OPTIONNEL)
- `service_id` : ObjectId du service (OPTIONNEL, mais nécessite `department_id`)
- `role` : Rôle système ("user", "admin", "superadmin")
- `role_departement` : Rôle dans le département ("agent", "chef_service", "directeur")
- `is_active` : Statut actif/inactif
- `created_at` : Date de création

**Caractéristiques :**
- ✅ Un utilisateur appartient à UNE organisation (obligatoire)
- ✅ Un utilisateur peut être dans un département (optionnel)
- ✅ Un utilisateur peut être dans un service (optionnel, mais nécessite un département)
- ✅ Un utilisateur peut être directement dans l'organisation (sans département ni service)
- ✅ Un utilisateur peut être dans un département sans service (agent direct du département)

**Rôles système (`role`) :**
- `"user"` : Utilisateur standard
- `"admin"` : Administrateur d'organisation
- `"superadmin"` : Super administrateur (pas d'organisation)

**Rôles départementaux (`role_departement`) :**
- `"agent"` : Agent standard (par défaut)
- `"chef_service"` : Chef de service
- `"directeur"` : Directeur de département

**Exemple 1 : Agent dans un service**
```json
{
  "_id": ObjectId("..."),
  "email": "jean.dupont@bank.com",
  "full_name": "Jean Dupont",
  "organization_id": ObjectId("..."), // Banque ABC
  "department_id": ObjectId("..."),  // RH
  "service_id": ObjectId("..."),      // Recrutement
  "role": "user",
  "role_departement": "agent",
  "is_active": true
}
```

**Exemple 2 : Agent direct d'un département (sans service)**
```json
{
  "_id": ObjectId("..."),
  "email": "marie.martin@bank.com",
  "full_name": "Marie Martin",
  "organization_id": ObjectId("..."), // Banque ABC
  "department_id": ObjectId("..."),  // RH
  "service_id": null,                 // Pas de service
  "role": "user",
  "role_departement": "agent",
  "is_active": true
}
```

**Exemple 3 : Chef de service**
```json
{
  "_id": ObjectId("..."),
  "email": "pierre.durand@bank.com",
  "full_name": "Pierre Durand",
  "organization_id": ObjectId("..."), // Banque ABC
  "department_id": ObjectId("..."),  // RH
  "service_id": ObjectId("..."),     // Recrutement
  "role": "admin",                    // Admin d'organisation
  "role_departement": "chef_service", // Chef de service
  "is_active": true
}
```

**Exemple 4 : Utilisateur sans département/service**
```json
{
  "_id": ObjectId("..."),
  "email": "admin@bank.com",
  "full_name": "Admin Principal",
  "organization_id": ObjectId("..."), // Banque ABC
  "department_id": null,              // Pas de département
  "service_id": null,                 // Pas de service
  "role": "admin",                     // Admin d'organisation
  "role_departement": null,
  "is_active": true
}
```

---

## 🔐 RÔLES ET PERMISSIONS

### Rôles Système (`role`)

| Rôle | Description | `organization_id` | Accès |
|------|-------------|-------------------|-------|
| `superadmin` | Super administrateur | `None` | Toutes les organisations |
| `admin` | Admin d'organisation | Obligatoire | Uniquement son organisation |
| `user` | Utilisateur standard | Obligatoire | Uniquement son organisation |

### Rôles Départementaux (`role_departement`)

| Rôle | Description | Hiérarchie |
|------|-------------|------------|
| `directeur` | Directeur de département | Niveau le plus élevé |
| `chef_service` | Chef de service | Niveau intermédiaire |
| `agent` | Agent standard | Niveau de base (par défaut) |

**Note :** Les rôles départementaux sont utilisés pour :
- Les permissions d'onglets (filtrage par département/service/rôle)
- L'affichage dans les interfaces
- La hiérarchie organisationnelle

---

## 📊 STRUCTURE DES DONNÉES

### Relations MongoDB

```
organizations (1) ──→ (N) departments
departments (1) ──→ (N) services
departments (1) ──→ (N) users (directement)
services (1) ──→ (N) users
organizations (1) ──→ (N) users (directement)
```

### Contraintes

1. **Un département doit appartenir à une organisation**
   ```python
   department.organization_id → organizations._id
   ```

2. **Un service doit appartenir à un département**
   ```python
   service.department_id → departments._id
   ```

3. **Un utilisateur doit appartenir à une organisation**
   ```python
   user.organization_id → organizations._id (OBLIGATOIRE)
   ```

4. **Un utilisateur peut appartenir à un département**
   ```python
   user.department_id → departments._id (OPTIONNEL)
   ```

5. **Un utilisateur peut appartenir à un service**
   ```python
   user.service_id → services._id (OPTIONNEL)
   # MAIS nécessite user.department_id
   ```

6. **Validation lors de la création**
   - Si `service_id` est fourni → `department_id` doit être fourni
   - Si `department_id` est fourni → doit appartenir à la même organisation
   - Si `service_id` est fourni → doit appartenir au `department_id` fourni

---

## 💡 EXEMPLES CONCRETS

### Exemple 1 : Structure complète

```
ORGANISATION: Banque ABC
│
├── DÉPARTEMENT: Ressources Humaines (RH)
│   │
│   ├── SERVICE: Recrutement (REC)
│   │   ├── AGENT: Jean Dupont (agent)
│   │   └── AGENT: Marie Martin (chef_service)
│   │
│   ├── SERVICE: Formation (FOR)
│   │   └── AGENT: Pierre Durand (agent)
│   │
│   └── AGENT DIRECT: Sophie Bernard (directeur) [sans service]
│
├── DÉPARTEMENT: Finance (FIN)
│   │
│   ├── SERVICE: Comptabilité (COMP)
│   │   └── AGENT: Luc Petit (agent)
│   │
│   └── SERVICE: Trésorerie (TRES)
│       └── AGENT: Anne Moreau (agent)
│
└── ADMIN DIRECT: Admin Principal (admin) [sans département ni service]
```

### Exemple 2 : Requêtes MongoDB

**Lister tous les départements d'une organisation :**
```python
departments = await db["departments"].find({
    "organization_id": ObjectId(org_id)
})
```

**Lister tous les services d'un département :**
```python
services = await db["services"].find({
    "department_id": ObjectId(dept_id)
})
```

**Lister tous les agents d'un service :**
```python
agents = await db["users"].find({
    "service_id": ObjectId(service_id),
    "is_active": True
})
```

**Lister tous les agents directs d'un département (sans service) :**
```python
agents = await db["users"].find({
    "department_id": ObjectId(dept_id),
    "service_id": None,
    "is_active": True
})
```

**Lister tous les utilisateurs d'une organisation :**
```python
users = await db["users"].find({
    "organization_id": ObjectId(org_id),
    "is_active": True
})
```

---

## 🎯 CAS D'USAGE

### Cas 1 : Agent dans un service
- **Utilisation :** Agent spécialisé dans une fonction précise
- **Exemple :** Agent de recrutement dans le service Recrutement du département RH
- **Structure :** `organization_id` → `department_id` → `service_id`

### Cas 2 : Agent direct d'un département
- **Utilisation :** Agent qui travaille pour le département mais pas dans un service spécifique
- **Exemple :** Directeur RH qui supervise tous les services
- **Structure :** `organization_id` → `department_id` → `service_id: null`

### Cas 3 : Admin sans département/service
- **Utilisation :** Administrateur principal de l'organisation
- **Exemple :** Admin général qui gère toute l'organisation
- **Structure :** `organization_id` → `department_id: null` → `service_id: null`

### Cas 4 : Permissions d'onglets par hiérarchie
- **Utilisation :** Restreindre l'accès à certains onglets selon le département/service/rôle
- **Exemple :** Seuls les agents du service "Recrutement" peuvent voir l'onglet "Formations"
- **Structure :** Utilise `department_id`, `service_id`, `role_departement` pour filtrer

---

## 📝 NOTES IMPORTANTES

### 1. **Flexibilité de la structure**
- ✅ Un utilisateur peut être directement dans l'organisation (sans département/service)
- ✅ Un utilisateur peut être dans un département sans service
- ✅ Un utilisateur peut être dans un service (nécessite un département)

### 2. **Validation stricte**
- ✅ Un service ne peut pas exister sans département
- ✅ Un utilisateur avec `service_id` doit avoir un `department_id`
- ✅ Tous les niveaux doivent appartenir à la même organisation

### 3. **Isolation des données**
- ✅ Toutes les requêtes filtrent par `organization_id`
- ✅ Un utilisateur ne peut voir que les données de son organisation
- ✅ Un admin ne peut gérer que son organisation

### 4. **Compteurs automatiques**
- ✅ Les départements affichent le nombre de services et d'utilisateurs
- ✅ Les services affichent le nombre d'utilisateurs
- ✅ Calculés dynamiquement lors de la récupération

---

## 📁 FICHIERS CLÉS

- **`app/models/organization.py`** : Modèles et fonctions pour les organisations
- **`app/models/department.py`** : Modèles et fonctions pour les départements et services
- **`app/models/user.py`** : Modèles et fonctions pour les utilisateurs
- **`app/schemas/organization.py`** : Schémas Pydantic pour les organisations
- **`app/schemas/department.py`** : Schémas Pydantic pour les départements/services
- **`app/schemas/user.py`** : Schémas Pydantic pour les utilisateurs
- **`app/routers/department.py`** : Endpoints API pour gérer départements/services
- **`app/models/tab_permissions.py`** : Permissions d'onglets basées sur la hiérarchie

---

## 🎯 RÉSUMÉ

**Oui, vous avez bien la structure suivante :**

```
ORGANISATION
    └── DÉPARTEMENTS
        └── SERVICES
            └── AGENTS (Utilisateurs)
```

**Avec les caractéristiques suivantes :**
- ✅ Une organisation peut avoir plusieurs départements
- ✅ Un département peut avoir plusieurs services
- ✅ Un service peut avoir plusieurs agents
- ✅ Un département peut avoir des agents directement (sans service)
- ✅ Un utilisateur peut être directement dans l'organisation (sans département/service)
- ✅ Tous les niveaux sont isolés par `organization_id`
- ✅ Les rôles départementaux (`agent`, `chef_service`, `directeur`) permettent une hiérarchie fine

**Cette structure permet une gestion flexible et granulaire des permissions et de l'organisation des utilisateurs.**

---

**Document créé le :** 2025-01-18  
**Dernière mise à jour :** 2025-01-18

