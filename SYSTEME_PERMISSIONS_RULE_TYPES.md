# Système de Permissions avec Types de Règles (SEGMENT / USER)

## 📋 Vue d'ensemble

Le système de permissions des onglets permet maintenant de créer deux types de règles exclusives :
- **SEGMENT** : Permissions par département/service/rôle (règle existante)
- **USER** : Permission pour un utilisateur spécifique (nouveau)

Chaque règle est exclusive : si `rule_type="USER"`, seuls les champs `user_id` sont utilisés. Si `rule_type="SEGMENT"`, seuls `department_id`, `service_id`, `role_departement` sont utilisés.

---

## 🔧 Modifications Backend

### 1. **Schéma Pydantic** (`app/schemas/tab_permissions.py`)

**Ajout du champ `rule_type` :**
```python
class TabPermissionRule(BaseModel):
    rule_type: Optional[Literal["SEGMENT", "USER"]] = Field(
        None, 
        description="Type de règle: SEGMENT ou USER. None = SEGMENT par défaut (rétrocompatibilité)"
    )
    department_id: Optional[str] = Field(None, ...)
    service_id: Optional[str] = Field(None, ...)
    role_departement: Optional[str] = Field(None, ...)
    user_id: Optional[str] = Field(None, ...)
```

**Validation automatique :**
- Si `rule_type="USER"` et `user_id` est défini → nettoie automatiquement `department_id`, `service_id`, `role_departement`
- Si `rule_type="SEGMENT"` → nettoie automatiquement `user_id`
- Permet la création progressive (pas d'erreur si `user_id=None` pendant la création d'une règle USER)

**Rétrocompatibilité :**
- Si `rule_type` est `None` ou absent → considéré comme `"SEGMENT"` par défaut
- Les règles existantes sans `rule_type` continuent de fonctionner

---

### 2. **Logique de Matching** (`app/models/tab_permissions.py`)

**Fonction `get_user_allowed_tabs()` modifiée :**

```python
for rule in rules:
    rule_type = rule.get("rule_type", "SEGMENT")  # Rétrocompatibilité
    
    if rule_type == "USER":
        # Règle USER : match uniquement si user_id correspond
        rule_user_id = rule.get("user_id")
        if rule_user_id and user_id and rule_user_id == user_id:
            allowed_tabs.append(tab_id)
            break
    
    elif rule_type == "SEGMENT":
        # Règle SEGMENT : logique classique (department/service/role)
        # ... vérification department/service/role ...
```

**Points importants :**
- ✅ Rétrocompatibilité : si `rule_type` absent, traité comme `"SEGMENT"`
- ✅ Logique exclusive : USER vérifie uniquement `user_id`, SEGMENT vérifie uniquement `department/service/role`
- ✅ Si aucune règle ne match → onglet non autorisé (sauf si `enabled=True` et aucune règle définie)

---

### 3. **Endpoint `/auth/users/org/simple`** (`app/routers/auth.py`)

**Retourne une liste simplifiée des utilisateurs :**
```python
@router.get("/auth/users/org/simple")
async def get_users_for_organization_simple(...):
    users = await list_users_by_org(str(user_org_id))
    return [
        {
            "id": user.get("id", ""),
            "full_name": user.get("full_name", ""),
            "email": user.get("email", ""),
            "department_id": user.get("department_id"),
            "service_id": user.get("service_id"),
            "role_departement": user.get("role_departement"),
        }
        for user in users
    ]
```

**Isolation des données :**
- ✅ Filtre automatiquement par `organization_id`
- ✅ Accessible uniquement aux admins d'organisation

---

## 🎨 Modifications Frontend

### 1. **Chargement des utilisateurs** (`TabPermissionsTab.jsx`)

```javascript
const [users, setUsers] = useState([]);
const [userFilterDept, setUserFilterDept] = useState({}); // Filtre UX pour règles USER

const loadUsers = async () => {
  const response = await api.get("/auth/users/org/simple");
  setUsers(response.data || []);
};
```

---

### 2. **Select "Type de règle"**

**Ajout d'un select en premier dans chaque règle :**
```javascript
<select value={rule.rule_type || "SEGMENT"} onChange={...}>
  <option value="SEGMENT">📊 SEGMENT (par département/service/rôle)</option>
  <option value="USER">👤 USER (par utilisateur spécifique)</option>
</select>
```

---

### 3. **UI Conditionnelle selon le Type**

**Si `rule_type="USER"` :**
- Affiche uniquement le select **Utilisateur**
- Filtre UX par département (non sauvegardé, stocké dans `userFilterDept`)
- Message d'avertissement si aucun utilisateur sélectionné

**Si `rule_type="SEGMENT"` :**
- Affiche **Département**, **Service**, **Rôle département**
- Comportement identique à l'ancien système

---

### 4. **Logique de Réinitialisation**

**Fonction `handleRuleChange()` :**
```javascript
// Si changement de rule_type
if (field === "rule_type") {
  if (value === "USER") {
    // Réinitialiser département/service/rôle
    updatedRule.department_id = null;
    updatedRule.service_id = null;
    updatedRule.role_departement = null;
  } else if (value === "SEGMENT") {
    // Réinitialiser user_id
    updatedRule.user_id = null;
  }
}

// Si changement de user_id (pour USER)
if (field === "user_id" && ruleType === "USER") {
  updatedRule.department_id = null;
  updatedRule.service_id = null;
  updatedRule.role_departement = null;
}
```

---

### 5. **Filtrage des Utilisateurs**

**Fonction `getFilteredUsers(rule, ruleIndex)` :**
```javascript
const getFilteredUsers = (rule, ruleIndex) => {
  const ruleType = rule.rule_type || "SEGMENT";
  let deptId = null;
  
  if (ruleType === "USER") {
    // Utiliser le filtre UX (non sauvegardé)
    deptId = userFilterDept[ruleIndex] || null;
  } else {
    // Utiliser le département de la règle
    deptId = rule.department_id || null;
  }
  
  if (deptId) {
    return users.filter(user => user.department_id === deptId);
  }
  return users;
};
```

**Points importants :**
- Pour les règles **USER** : le filtre département est uniquement pour l'UX (non sauvegardé)
- Pour les règles **SEGMENT** : le filtre département fait partie de la règle (sauvegardé)

---

### 6. **Résumé de Règle**

**Affichage conditionnel :**
```javascript
{(rule.rule_type || "SEGMENT") === "USER" ? (
  rule.user_id ? (
    `👤 Utilisateur: ${user.full_name} (${user.email})`
  ) : (
    <span style={{ color: "#f44336" }}>⚠️ Aucun utilisateur sélectionné</span>
  )
) : (
  // Résumé SEGMENT (département/service/rôle)
)}
```

---

## 🔄 Flux de Données

```
┌─────────────────────────────────────────────────────────────┐
│                    CRÉATION D'UNE RÈGLE                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
        1. Sélectionner le Type (SEGMENT ou USER)
                          ↓
        ┌─────────────────┴─────────────────┐
        │                                   │
   SEGMENT                              USER
        │                                   │
        ↓                                   ↓
  2. Sélectionner                   2. Filtrer par dept (UX)
     Département                          ↓
        ↓                           3. Sélectionner Utilisateur
  3. Sélectionner                        ↓
     Service (optionnel)           4. Sauvegarder avec
        ↓                              rule_type="USER"
  4. Sélectionner                        user_id="user123"
     Rôle (optionnel)                    department_id=null
        ↓                              service_id=null
  5. Sauvegarder avec                  role_departement=null
     rule_type="SEGMENT"
     department_id="dept123"
     service_id="service456"
     role_departement="directeur"
     user_id=null

┌─────────────────────────────────────────────────────────────┐
│              VÉRIFICATION DES PERMISSIONS                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
    get_user_allowed_tabs(org_id, dept_id, service_id, role, user_id)
                          ↓
    Pour chaque onglet :
        ├─> Si enabled=False → refusé
        ├─> Si pas de règles → autorisé
        └─> Si règles existent :
                ├─> Règle USER : match si rule.user_id == current_user.id
                └─> Règle SEGMENT : match si dept/service/role correspondent
                          ↓
    Retourne liste des onglets autorisés
```

---

## ✅ Rétrocompatibilité

### Backend
- ✅ Les règles existantes sans `rule_type` sont traitées comme `"SEGMENT"`
- ✅ Les règles existantes avec `user_id` mais sans `rule_type` continuent de fonctionner (logique actuelle)
- ✅ Le validator nettoie automatiquement les champs conflictuels

### Frontend
- ✅ Les règles existantes s'affichent comme `"SEGMENT"` par défaut
- ✅ L'UI s'adapte automatiquement selon la présence/absence de `rule_type`

---

## 🧪 Cas d'Usage

### Cas 1 : Règle SEGMENT (comportement existant)
```json
{
  "rule_type": "SEGMENT",
  "department_id": "dept123",
  "service_id": null,
  "role_departement": "directeur",
  "user_id": null
}
```
**Résultat :** Tous les directeurs du département `dept123` ont accès.

### Cas 2 : Règle USER (nouveau)
```json
{
  "rule_type": "USER",
  "department_id": null,
  "service_id": null,
  "role_departement": null,
  "user_id": "user456"
}
```
**Résultat :** Seul l'utilisateur `user456` a accès.

### Cas 3 : Règle existante (sans rule_type)
```json
{
  "department_id": "dept123",
  "service_id": null,
  "role_departement": null,
  "user_id": null
}
```
**Résultat :** Traitée comme `"SEGMENT"` → tous les utilisateurs du département `dept123` ont accès.

---

## 📝 Résumé des Fichiers Modifiés

| Fichier | Modification | Description |
|---------|--------------|-------------|
| `app/schemas/tab_permissions.py` | Ajout `rule_type` + validator | Validation automatique de l'exclusivité |
| `app/models/tab_permissions.py` | Modification `get_user_allowed_tabs()` | Logique de matching selon le type |
| `app/routers/auth.py` | Nouvel endpoint `/users/org/simple` | Liste simplifiée des utilisateurs |
| `TabPermissionsTab.jsx` | Select Type + UI conditionnelle | Interface adaptée selon le type |
| `TabPermissionsTab.jsx` | `getFilteredUsers()` améliorée | Filtrage avec support UX pour USER |
| `TabPermissionsTab.jsx` | `handleRuleChange()` améliorée | Réinitialisation automatique |

---

## 🎯 Avantages

1. **Clarté** : Types explicites (SEGMENT vs USER) évitent les ambiguïtés
2. **Flexibilité** : Permissions granulaires jusqu'au niveau utilisateur
3. **Rétrocompatibilité** : Aucune régression sur les règles existantes
4. **UX améliorée** : Interface adaptée selon le type de règle
5. **Validation automatique** : Le backend nettoie les champs conflictuels

---

## 🔒 Sécurité

- ✅ Backend reste la source de vérité (validation Pydantic)
- ✅ Frontend ne fait que masquer/afficher (UX)
- ✅ Isolation des données par organisation
- ✅ Validation des règles exclusives côté backend

