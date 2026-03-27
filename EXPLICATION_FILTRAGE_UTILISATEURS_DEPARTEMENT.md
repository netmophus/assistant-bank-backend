# Explication : Filtrage des Utilisateurs par Département dans TabPermissionsTab

## 📋 Vue d'ensemble

Cette fonctionnalité permet de filtrer la liste des utilisateurs selon le département sélectionné dans les règles de permissions des onglets. Chaque organisation ne voit que ses propres utilisateurs et départements.

---

## 🔧 Modifications apportées

### 1. **Backend - Endpoint `/auth/users/org/simple`**

**Fichier :** `app/routers/auth.py`

**Fonctionnalité :** Retourne une liste simplifiée des utilisateurs de l'organisation avec les champs nécessaires pour le select.

**Code :**
```python
@router.get("/users/org/simple")
async def get_users_for_organization_simple(current_user: dict = Depends(get_current_user)):
    """
    Liste simplifiée des utilisateurs de l'organisation pour les permissions.
    Retourne uniquement les champs nécessaires pour le select dans TabPermissionsTab.
    """
    user_role = current_user.get("role", "user")
    user_org_id = current_user.get("organization_id")

    # Vérifier que l'utilisateur est un admin d'organisation
    if user_role != "admin" or not user_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seuls les administrateurs d'organisation peuvent voir les utilisateurs.",
        )

    try:
        users = await list_users_by_org(str(user_org_id))
        
        # Retourner uniquement les champs nécessaires
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des utilisateurs: {str(e)}",
        )
```

**Points importants :**
- ✅ Filtre automatiquement par `organization_id` (isolation des données)
- ✅ Retourne uniquement les champs nécessaires (`id`, `full_name`, `email`, `department_id`, `service_id`, `role_departement`)
- ✅ Accessible uniquement aux admins d'organisation

---

### 2. **Frontend - Chargement des utilisateurs**

**Fichier :** `src/components/orgAdmin/TabPermissionsTab.jsx`

**Ajout de l'état et du chargement :**
```javascript
const [users, setUsers] = useState([]); // Liste des utilisateurs de l'organisation

const loadUsers = async () => {
  try {
    const response = await api.get("/auth/users/org/simple");
    setUsers(response.data || []);
  } catch (err) {
    console.error("Erreur lors du chargement des utilisateurs:", err);
  }
};

useEffect(() => {
  loadData();
  loadDepartments();
  loadUsers(); // Charger les utilisateurs au montage
}, []);
```

**Points importants :**
- ✅ Charge les utilisateurs au montage du composant
- ✅ Stocke la liste complète dans `users`
- ✅ Gère les erreurs silencieusement

---

### 3. **Frontend - Fonction de filtrage**

**Fichier :** `src/components/orgAdmin/TabPermissionsTab.jsx`

**Fonction de filtrage :**
```javascript
// Filtrer les utilisateurs selon le département sélectionné dans la règle
const getFilteredUsers = (rule) => {
  if (!rule.department_id) {
    return users; // Afficher tous les utilisateurs si aucun département sélectionné
  }
  return users.filter(user => user.department_id === rule.department_id);
};
```

**Logique :**
- Si **aucun département** n'est sélectionné → retourne **tous les utilisateurs**
- Si un **département est sélectionné** → retourne uniquement les utilisateurs dont `department_id` correspond

---

### 4. **Frontend - Réorganisation de l'ordre des champs**

**Avant :**
```
1. Utilisateur (tous les utilisateurs)
2. Département
3. Service
4. Rôle département
```

**Après :**
```
1. Département (filtre principal)
2. Utilisateur (filtré par département)
3. Service
4. Rôle département
```

**Raison :** Permet de sélectionner d'abord le département, puis de voir uniquement les utilisateurs de ce département.

---

### 5. **Frontend - Modification du select Utilisateur**

**Code modifié :**
```javascript
<div>
  <label>Utilisateur</label>
  <select
    value={rule.user_id || ""}
    onChange={(e) => {
      const value = e.target.value || null;
      handleRuleChange(tab.id, ruleIndex, "user_id", value);
    }}
    disabled={!!rule.user_id && !rule.department_id}
    style={{
      background: (!!rule.user_id && !rule.department_id) ? "#f5f5f5" : "#fff",
    }}
  >
    <option value="">
      Tous les utilisateurs{rule.department_id ? ` (${departments.find(d => d.id === rule.department_id)?.name || ""})` : ""}
    </option>
    {getFilteredUsers(rule).map((user) => (
      <option key={user.id} value={user.id}>
        {user.full_name} ({user.email})
      </option>
    ))}
  </select>
  {rule.department_id && getFilteredUsers(rule).length === 0 && (
    <div style={{ fontSize: "0.75rem", color: "#999", marginTop: "4px" }}>
      Aucun utilisateur dans ce département
    </div>
  )}
</div>
```

**Points importants :**
- ✅ Utilise `getFilteredUsers(rule)` pour filtrer la liste
- ✅ Affiche le nom du département dans l'option par défaut si un département est sélectionné
- ✅ Affiche un message si aucun utilisateur n'est trouvé dans le département sélectionné
- ✅ Désactive le select si un utilisateur est déjà sélectionné sans département

---

### 6. **Frontend - Logique de réinitialisation**

**Fichier :** `src/components/orgAdmin/TabPermissionsTab.jsx`

**Fonction `handleRuleChange` modifiée :**
```javascript
const handleRuleChange = (tabId, ruleIndex, field, value) => {
  const currentConfig = getTabConfig(tabId);
  const rule = currentConfig.rules[ruleIndex];
  const updatedRule = { ...rule, [field]: value || null };
  
  // Si on change le département, réinitialiser le service et l'utilisateur
  if (field === "department_id") {
    updatedRule.service_id = null;
    updatedRule.user_id = null;
  }
  
  // Si on change l'utilisateur, réinitialiser département/service/rôle
  if (field === "user_id") {
    if (value) {
      // Si un utilisateur est sélectionné, réinitialiser les autres critères
      updatedRule.department_id = null;
      updatedRule.service_id = null;
      updatedRule.role_departement = null;
    }
  }
  
  updateRule(tabId, ruleIndex, updatedRule);
};
```

**Logique de réinitialisation :**

| Action | Réinitialise |
|--------|--------------|
| Sélectionner un **département** | `service_id` et `user_id` |
| Sélectionner un **utilisateur** | `department_id`, `service_id`, `role_departement` |

**Raison :** Évite les conflits entre les critères. Si on sélectionne un utilisateur spécifique, les critères généraux (département/service/rôle) sont réinitialisés car l'utilisateur est déjà ciblé.

---

## 🔄 Flux de données

```
1. Chargement initial
   └─> loadUsers() → GET /auth/users/org/simple
       └─> Backend filtre par organization_id
           └─> Retourne liste complète des utilisateurs
               └─> Stockée dans `users` state

2. Sélection d'un département
   └─> handleRuleChange("department_id", deptId)
       └─> Réinitialise service_id et user_id
           └─> getFilteredUsers(rule) filtre users par department_id
               └─> Select utilisateur se met à jour automatiquement

3. Sélection d'un utilisateur
   └─> handleRuleChange("user_id", userId)
       └─> Réinitialise department_id, service_id, role_departement
           └─> Règle sauvegardée avec uniquement user_id
```

---

## 🎯 Cas d'usage

### Cas 1 : Sélectionner tous les utilisateurs d'un département
1. Sélectionner un **département** → `department_id = "dept123"`
2. Laisser **Utilisateur** sur "Tous les utilisateurs" → `user_id = null`
3. Résultat : Tous les utilisateurs du département `dept123` ont accès

### Cas 2 : Sélectionner un utilisateur spécifique
1. Sélectionner un **département** → `department_id = "dept123"`
2. Sélectionner un **utilisateur** dans la liste filtrée → `user_id = "user456"`
3. Résultat : Seul l'utilisateur `user456` a accès (département/service/rôle sont réinitialisés)

### Cas 3 : Sélectionner par rôle sans département
1. Laisser **Département** sur "Tous les départements" → `department_id = null`
2. Sélectionner un **Rôle département** → `role_departement = "directeur"`
3. Résultat : Tous les directeurs de tous les départements ont accès

---

## 🔒 Isolation des données par organisation

### Backend
- ✅ `list_users_by_org(org_id)` filtre automatiquement par `organization_id`
- ✅ Seuls les utilisateurs de l'organisation de l'admin connecté sont retournés

### Frontend
- ✅ `loadDepartments()` charge uniquement les départements de l'organisation
- ✅ `loadUsers()` charge uniquement les utilisateurs de l'organisation
- ✅ Chaque organisation ne voit que ses propres données

---

## 📝 Résumé des modifications

| Fichier | Modification | Description |
|---------|--------------|-------------|
| `app/routers/auth.py` | Nouvel endpoint `/users/org/simple` | Retourne liste simplifiée des utilisateurs |
| `TabPermissionsTab.jsx` | Ajout `loadUsers()` | Charge les utilisateurs au montage |
| `TabPermissionsTab.jsx` | Ajout `getFilteredUsers(rule)` | Filtre les utilisateurs par département |
| `TabPermissionsTab.jsx` | Réorganisation des champs | Département avant Utilisateur |
| `TabPermissionsTab.jsx` | Modification `handleRuleChange` | Logique de réinitialisation améliorée |
| `TabPermissionsTab.jsx` | Modification select Utilisateur | Utilise `getFilteredUsers()` pour filtrer |

---

## ✅ Avantages

1. **UX améliorée** : Sélection progressive (département → utilisateur)
2. **Performance** : Filtrage côté client (pas de requête supplémentaire)
3. **Isolation** : Chaque organisation ne voit que ses données
4. **Flexibilité** : Possibilité de sélectionner par département OU par utilisateur spécifique
5. **Cohérence** : Réinitialisation automatique des critères conflictuels

---

## 🧪 Tests recommandés

1. ✅ Sélectionner un département → vérifier que seuls les utilisateurs de ce département apparaissent
2. ✅ Sélectionner un utilisateur → vérifier que département/service/rôle sont réinitialisés
3. ✅ Changer de département → vérifier que l'utilisateur sélectionné est réinitialisé
4. ✅ Vérifier que chaque organisation ne voit que ses propres utilisateurs
5. ✅ Vérifier le message "Aucun utilisateur dans ce département" si aucun utilisateur n'est trouvé

