# Système d'archivage des impayés

## Vue d'ensemble

Le système d'archivage permet de :
1. **Archiver** les données actuelles (snapshots, messages, historique SMS) avant de réinitialiser
2. **Réinitialiser** les tables pour recommencer avec une base vide
3. **Consulter** les archives sans les restaurer
4. **Restaurer** une archive si nécessaire

## Architecture

### Collections MongoDB créées

1. **`impayes_archives`** : Métadonnées des archives
2. **`impayes_archived_snapshots`** : Snapshots archivés
3. **`impayes_archived_messages`** : Messages archivés
4. **`impayes_archived_sms_history`** : Historique SMS archivé

### Collections actuelles (non modifiées)

- `arrears_snapshots` : Snapshots actuels
- `outbound_messages` : Messages actuels
- `sms_history` : Historique SMS actuel

## Workflow d'utilisation

### 1. Archiver les données actuelles

**Endpoint:** `POST /impayes/archive`

```json
{
  "archive_name": "Archive Q4 2025",
  "archive_description": "Archive des données avant réinitialisation",
  "include_snapshots": true,
  "include_messages": true,
  "include_sms_history": true
}
```

**Ce que fait cette opération :**
- Copie tous les snapshots dans `impayes_archived_snapshots`
- Copie tous les messages dans `impayes_archived_messages`
- Copie l'historique SMS dans `impayes_archived_sms_history`
- Crée une entrée de métadonnées dans `impayes_archives`
- **Les données actuelles restent intactes** (elles ne sont pas supprimées)

**Réponse :**
```json
{
  "success": true,
  "message": "Archive créée avec succès: abc-123-...",
  "archive": {
    "archive_id": "abc-123-...",
    "archived_at": "2025-12-17T10:30:00",
    "total_snapshots": 150,
    "total_messages": 100,
    "montant_total_impaye": 50000000,
    ...
  }
}
```

### 2. Vider les données actuelles (réinitialiser)

**Endpoint:** `POST /impayes/archive/clear?confirm=true`

⚠️ **ATTENTION:** Cette opération est **IRRÉVERSIBLE**. Assurez-vous d'avoir archivé vos données avant.

**Ce que fait cette opération :**
- Supprime tous les snapshots de `arrears_snapshots`
- Supprime tous les messages de `outbound_messages`
- Supprime tout l'historique SMS de `sms_history`
- **Les archives ne sont pas affectées**

**Réponse :**
```json
{
  "success": true,
  "message": "Données supprimées avec succès",
  "result": {
    "deleted_snapshots": 150,
    "deleted_messages": 100,
    "deleted_sms_history": 50,
    "cleared_at": "2025-12-17T10:35:00"
  }
}
```

### 3. Consulter les archives

#### Lister toutes les archives

**Endpoint:** `GET /impayes/archives?limit=100&skip=0`

**Réponse :**
```json
{
  "data": [
    {
      "archive_id": "abc-123-...",
      "archive_name": "Archive Q4 2025",
      "archived_at": "2025-12-17T10:30:00",
      "total_snapshots": 150,
      "montant_total_impaye": 50000000,
      ...
    },
    ...
  ],
  "total": 5
}
```

#### Récupérer une archive spécifique

**Endpoint:** `GET /impayes/archives/{archive_id}`

#### Consulter les snapshots d'une archive

**Endpoint:** `GET /impayes/archives/{archive_id}/snapshots?limit=1000&skip=0`

Permet de consulter les données archivées **sans les restaurer**.

### 4. Restaurer une archive

**Endpoint:** `POST /impayes/archives/{archive_id}/restore`

```json
{
  "restore_snapshots": true,
  "restore_messages": true,
  "restore_sms_history": true,
  "clear_existing": false
}
```

**Ce que fait cette opération :**
- Copie les snapshots archivés vers `arrears_snapshots`
- Copie les messages archivés vers `outbound_messages`
- Copie l'historique SMS archivé vers `sms_history`
- Si `clear_existing: true`, vide les données actuelles avant restauration

**Réponse :**
```json
{
  "success": true,
  "message": "Archive abc-123-... restaurée avec succès",
  "result": {
    "restored_snapshots": 150,
    "restored_messages": 100,
    "restored_sms_history": 50,
    "restored_at": "2025-12-17T11:00:00"
  }
}
```

## Cas d'usage

### Scénario 1 : Réinitialisation complète pour une nouvelle période

```bash
# 1. Archiver les données actuelles
POST /impayes/archive
{
  "archive_name": "Archive avant réinitialisation Q1 2026",
  "archive_description": "Données complètes avant nouveau départ"
}

# 2. Vider les données actuelles
POST /impayes/archive/clear?confirm=true

# 3. Vous pouvez maintenant importer de nouveaux fichiers
# Les données actuelles sont vides, prêtes pour de nouveaux imports
```

### Scénario 2 : Consulter une archive sans la restaurer

```bash
# 1. Lister les archives disponibles
GET /impayes/archives

# 2. Consulter les snapshots d'une archive
GET /impayes/archives/{archive_id}/snapshots

# Les données actuelles ne sont pas modifiées
```

### Scénario 3 : Restaurer une archive pour analyse

```bash
# 1. Restaurer une archive spécifique
POST /impayes/archives/{archive_id}/restore
{
  "restore_snapshots": true,
  "restore_messages": false,
  "restore_sms_history": false,
  "clear_existing": true
}

# Les snapshots de l'archive sont maintenant dans les données actuelles
# Vous pouvez les analyser avec les outils habituels
```

## Points importants

1. **Les archives sont permanentes** : Une fois créées, elles ne sont jamais supprimées automatiquement
2. **Les données actuelles restent intactes après archivage** : L'archivage ne supprime pas les données actuelles
3. **La réinitialisation est irréversible** : Assurez-vous d'avoir archivé avant de vider
4. **Les archives sont isolées** : Chaque organisation ne voit que ses propres archives
5. **La restauration peut être sélective** : Vous pouvez restaurer seulement les snapshots, ou seulement les messages, etc.

## Sécurité

- Seuls les utilisateurs authentifiés peuvent créer/consulter/restaurer des archives
- Chaque organisation ne peut accéder qu'à ses propres archives
- La suppression nécessite une confirmation explicite (`confirm=true`)

## Métadonnées stockées

Chaque archive contient :
- `archive_id` : Identifiant unique (UUID)
- `archived_at` : Date de création
- `archive_name` : Nom descriptif (optionnel)
- `archive_description` : Description (optionnel)
- `total_snapshots` : Nombre de snapshots archivés
- `total_messages` : Nombre de messages archivés
- `total_sms_history` : Nombre d'entrées SMS archivées
- `date_situation_debut` : Première date de situation
- `date_situation_fin` : Dernière date de situation
- `dates_situation` : Liste de toutes les dates de situation
- `montant_total_impaye` : Montant total impayé
- `nombre_total_credits` : Nombre total de crédits
- `candidats_restructuration` : Nombre de candidats à restructuration

## Exemple complet

```python
# 1. Archiver les données actuelles
import requests

response = requests.post(
    "http://localhost:8000/impayes/archive",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={
        "archive_name": "Archive fin d'année 2025",
        "archive_description": "Archive complète avant réinitialisation",
        "include_snapshots": True,
        "include_messages": True,
        "include_sms_history": True
    }
)
archive_id = response.json()["archive"]["archive_id"]
print(f"Archive créée: {archive_id}")

# 2. Vider les données actuelles
response = requests.post(
    "http://localhost:8000/impayes/archive/clear?confirm=true",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
print("Données supprimées")

# 3. Consulter les archives disponibles
response = requests.get(
    "http://localhost:8000/impayes/archives",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
archives = response.json()["data"]
print(f"{len(archives)} archives disponibles")

# 4. Consulter les snapshots d'une archive
response = requests.get(
    f"http://localhost:8000/impayes/archives/{archive_id}/snapshots",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
snapshots = response.json()["data"]
print(f"{len(snapshots)} snapshots dans l'archive")
```


