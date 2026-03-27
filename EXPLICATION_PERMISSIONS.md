# Explication du Système de Permissions

## Comportement Actuel (Opt-Out)

### Logique d'Application des Permissions

Le système fonctionne actuellement en mode **"opt-out"** (exclusion par défaut) :

1. **Si un onglet n'a PAS de règles définies** → **Il est accessible à TOUS les utilisateurs**
2. **Si un onglet a des règles définies** → L'utilisateur doit correspondre à **au moins une règle** pour y accéder

### Exemple Concret

```
Onglet "impayes" :
- Pas de règles → Accessible à tous ✅
- Règle 1: département="Dépt A" → Seuls les users du Dépt A y accèdent
- Règle 2: user_id="User123" → User123 y accède même s'il n'est pas dans Dépt A
```

### Pourquoi un Nouvel Utilisateur a Tous les Menus ?

**Réponse** : Parce que la plupart des onglets n'ont probablement **pas de règles définies**.

Quand vous créez un utilisateur dans un nouveau département :
- Si aucun onglet n'a de règles → Tous les onglets sont accessibles (comportement par défaut)
- Si certains onglets ont des règles → Seuls ces onglets sont filtrés

## Types de Règles

### 1. Règle SEGMENT (par département/service/rôle)

```python
{
    "rule_type": "SEGMENT",
    "department_id": "69313c6ecf39bb50c288d798",  # Optionnel
    "service_id": "69313c9ccf39bb50c288d799",      # Optionnel
    "role_departement": "directeur"                # Optionnel
}
```

**Logique de correspondance** :
- Si `department_id` est défini → L'utilisateur doit être dans ce département
- Si `service_id` est défini → L'utilisateur doit être dans ce service (ET ce département)
- Si `role_departement` est défini → L'utilisateur doit avoir ce rôle
- Si un champ est `None` → Il accepte toutes les valeurs pour ce champ

**Exemple** :
```python
# Règle : département="Dépt A", service=None, rôle=None
# → Tous les utilisateurs du Dépt A y accèdent (peu importe le service/rôle)

# Règle : département="Dépt A", service="Service B", rôle="directeur"
# → Seuls les directeurs du Service B du Dépt A y accèdent
```

### 2. Règle USER (par utilisateur spécifique)

```python
{
    "rule_type": "USER",
    "user_id": "693130717a67fa5e359a518b"
}
```

**Logique de correspondance** :
- L'utilisateur doit avoir exactement cet `user_id`
- Les champs `department_id`, `service_id`, `role_departement` sont ignorés

## Problème Identifié

### Comportement Actuel (Ligne 182-185)

```python
rules = tab_config.get("rules", [])

# Si pas de règles, l'onglet est accessible à tous
if not rules:
    allowed_tabs.append(tab_id)
    continue
```

**Conséquence** : Un nouvel utilisateur dans un nouveau département a accès à tous les onglets qui n'ont pas de règles restrictives.

## Solutions Possibles

### Option 1 : Mode Opt-In (Recommandé pour la Sécurité)

Changer le comportement par défaut : **Rien n'est accessible sauf si explicitement autorisé**.

```python
# Si pas de règles, l'onglet n'est PAS accessible
if not rules:
    continue  # Ne pas ajouter l'onglet
```

**Avantages** :
- Plus sécurisé (principe du moindre privilège)
- Contrôle explicite des accès
- Nouveaux utilisateurs/départements n'ont rien par défaut

**Inconvénients** :
- Nécessite de définir des règles pour chaque onglet
- Peut casser le comportement existant si des organisations comptent sur le comportement par défaut

### Option 2 : Mode Hybride (Configuration par Organisation)

Ajouter un champ `default_behavior` dans la configuration de l'organisation :

```python
{
    "organization_id": "...",
    "default_behavior": "opt-in",  # ou "opt-out"
    "tabs": [...]
}
```

**Avantages** :
- Flexibilité par organisation
- Rétrocompatibilité (organisations existantes gardent "opt-out")

### Option 3 : Garder Opt-Out mais Documenter

Garder le comportement actuel mais améliorer la documentation et l'UI pour que les admins comprennent qu'ils doivent définir des règles restrictives.

## Recommandation

**Pour une meilleure sécurité**, je recommande **Option 1 (Opt-In)** avec une migration progressive :

1. Ajouter un paramètre de configuration `restrictive_mode` (par défaut `False` pour rétrocompatibilité)
2. Si `restrictive_mode=True` → Comportement opt-in (pas de règles = pas d'accès)
3. Si `restrictive_mode=False` → Comportement actuel (pas de règles = accès à tous)

## Code à Modifier

### Fichier : `app/models/tab_permissions.py`

**Ligne 182-185** : Changer le comportement par défaut

```python
# AVANT (Opt-Out)
if not rules:
    allowed_tabs.append(tab_id)
    continue

# APRÈS (Opt-In)
if not rules:
    continue  # Pas d'accès si aucune règle
```

## Test de Vérification

Pour vérifier pourquoi un utilisateur a tous les menus :

1. **Vérifier les règles définies** :
   ```python
   # Dans MongoDB
   db.tab_permissions.find({"organization_id": ObjectId("...")})
   ```

2. **Vérifier les permissions calculées** :
   ```bash
   # Appel API
   GET /tab-permissions/user/allowed-tabs
   # Vérifier le header Authorization avec le token de l'utilisateur
   ```

3. **Logs du backend** :
   - Les logs ajoutés dans `get_user_allowed_tabs_endpoint` montrent les `allowed_tabs` calculés

## Conclusion

Le comportement actuel est **"tout est accessible sauf si des règles restrictives sont définies"**. 

Pour restreindre l'accès aux nouveaux utilisateurs/départements, vous devez :
1. **Définir des règles restrictives** pour chaque onglet que vous voulez contrôler
2. **OU** changer le comportement par défaut en mode "opt-in" (recommandé pour la sécurité)

