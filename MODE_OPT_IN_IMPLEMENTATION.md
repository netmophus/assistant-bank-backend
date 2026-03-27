# Implémentation du Mode OPT-IN pour les Permissions

## Problème Identifié

Pour un user (`role=user`), l'API `/user/allowed-tabs` renvoie tous les onglets même quand aucune permission n'a été définie.

## Solution : Mode OPT-IN Strict

### Backend (`app/models/tab_permissions.py`)

#### Fonction `get_user_allowed_tabs`

**Logique actuelle (CORRIGÉE)** :

1. **Vérification du rôle** :
   ```python
   is_admin = user_role is not None and str(user_role).strip().lower() == "admin"
   ```

2. **Mode OPT-IN pour TOUS** (admin et user) :
   - Récupération des permissions : `permissions = await get_tab_permissions(organization_id)`
   - Si `configured_tabs = []` → retourner `[]` immédiatement
   - Sinon, parcourir uniquement les onglets configurés (pas tous les `AVAILABLE_TABS`)

3. **Pour chaque onglet configuré** :
   - Si `enabled=False` → ignorer
   - Si `enabled=True` et `rules=[]` → ajouter à `allowed_tabs`
   - Si `enabled=True` et `rules` non vide → vérifier les règles SEGMENT/USER

**IMPORTANT** : Plus de retour automatique de tous les `AVAILABLE_TABS` pour les admins dans cette fonction.

#### Fonction `get_tab_permissions`

**Logique OPT-IN** :
- Si aucune config n'existe → retourner `{"tabs": []}` (pas de fallback)
- Si config existe → retourner uniquement les onglets configurés avec `enabled=False` par défaut

### Endpoint (`app/routers/tab_permissions.py`)

#### `/user/allowed-tabs`

**Bootstrap pour les admins** :

```python
if user_role == "admin":
    if len(allowed_tabs) == 0:
        # Aucune config → bootstrap minimal
        bootstrap_tabs = ["tab-permissions", "departments", "services", "users"]
        allowed_tabs = bootstrap_tabs
    elif "tab-permissions" not in allowed_tabs:
        # Config existe mais "tab-permissions" pas activé → l'ajouter
        allowed_tabs.append("tab-permissions")
```

**Résultat** :
- User sans config → `allowed_tabs = []`
- Admin sans config → `allowed_tabs = ["tab-permissions", "departments", "services", "users"]`
- Admin avec config → `allowed_tabs` selon config + "tab-permissions" si absent

### Frontend

#### `permissionService.js`

**Logique fail-closed pour les users** :
```javascript
// Pour les USERS : MODE OPT-IN (fail-closed)
if (!allowedTabs || allowedTabs.length === 0) {
    return false; // Pas d'accès si liste vide
}
```

**Logique pour les admins** :
```javascript
// Les admins ont toujours accès (sauf global knowledge sans licence)
if (user?.role === "admin") {
    if (permissionKey === PERMISSIONS.MODULE_GLOBAL_KNOWLEDGE && !hasActiveLicense) {
        return false;
    }
    return true; // Accès à tout le reste
}
```

#### `TabPermissionsTab.jsx`

**`getTabConfig()` par défaut** :
```javascript
return tabConfig || { enabled: false, rules: [] }; // enabled=false par défaut
```

## Vérifications à Faire

1. **Redémarrer le backend** pour appliquer les changements
2. **Vérifier les logs backend** lors d'un appel `/user/allowed-tabs` avec un user :
   - `[get_user_allowed_tabs] User détecté: application du mode opt-in strict`
   - `[get_user_allowed_tabs] Aucune configuration trouvée: allowed_tabs = []`
   - `[get_user_allowed_tabs_endpoint] Résultat final: 0 onglets autorisés: []`

3. **Vérifier les logs frontend** :
   - `[UserDashboardPage] allowedTabs reçus: []`
   - `[UserDashboardPage] Nombre d'onglets autorisés: 0`

4. **Tester avec un admin** :
   - Sans config → devrait voir `["tab-permissions", "departments", "services", "users"]`
   - Avec config → devrait voir les onglets selon config + "tab-permissions"

## Points Critiques

1. **Plus de fallback automatique** : `AVAILABLE_TABS` n'est plus retourné automatiquement
2. **Mode opt-in strict** : Si aucune config → `[]` pour les users
3. **Bootstrap admin** : Permet aux admins de configurer même sans config initiale
4. **Frontend fail-closed** : Si `allowedTabs` vide → `false` pour les users

