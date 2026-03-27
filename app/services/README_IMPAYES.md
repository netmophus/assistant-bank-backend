# Services de gestion des impayés - Documentation

## Vue d'ensemble

Le module de suivi des impayés est organisé en plusieurs services spécialisés pour une meilleure maintenabilité et clarté du code.

## Architecture

### Modèle de données

Le système utilise deux collections MongoDB principales :

1. **`arrears_snapshots`** : Contient les snapshots (instantanés) des crédits impayés
   - `snapshot_id` : Identifiant unique du batch/fichier importé (UUID)
   - `date_situation` : Date économique de la situation (format YYYY-MM-DD)
   - `ref_credit` : Référence unique du crédit
   - Tous les autres champs du crédit (montants, indicateurs, etc.)

2. **`outbound_messages`** : Contient les SMS générés pour chaque snapshot
   - `snapshot_id` : Référence au batch (même UUID que les snapshots)
   - `linked_credit` : Référence au crédit (`ref_credit`)

### Principe de fonctionnement

**À chaque import de fichier :**
- Un nouveau `snapshot_id` (UUID) est généré
- Tous les snapshots de ce fichier partagent le même `snapshot_id`
- La `date_situation` est fournie par l'utilisateur lors de l'import
- Les snapshots précédents ne sont jamais modifiés ni écrasés

**Pour comparer deux dates :**
- On compare les snapshots entre deux `date_situation` différentes
- La comparaison se fait par `ref_credit` (identifiant du crédit)
- Détection automatique des régularisations (complètes et partielles)

## Services disponibles

### 1. `impayes_service.py` - Service d'import et traitement

**Responsabilités :**
- Validation des fichiers importés
- Calcul des indicateurs pour chaque ligne (montant total, tranche de retard, ratio, candidat restructuration)
- Génération des SMS selon la configuration
- Traitement complet d'un import

**Fonctions principales :**

```python
async def traiter_import_impayes(
    lignes: List[LigneImpayeImport],
    date_situation: str,
    organization_id: str,
    created_by: str
) -> Tuple[List[ArrearsSnapshot], List[OutboundMessage]]
```

**Utilisation :**
Cette fonction est appelée automatiquement lors de l'import d'un fichier via l'endpoint `/impayes/import/confirm`.

---

### 2. `impayes_snapshot_service.py` - Service de gestion des snapshots

**Responsabilités :**
- Récupération des snapshots par date
- Navigation dans l'historique (dernière date, date précédente)
- Comparaison entre deux dates de situation
- Résumé d'un snapshot (batch)

**Fonctions principales :**

#### `get_available_situation_dates(organization_id: str) -> List[str]`
Récupère toutes les dates de situation disponibles, triées du plus récent au plus ancien.

#### `get_latest_situation_date(organization_id: str) -> Optional[str]`
Récupère la date de situation la plus récente.

#### `get_previous_situation_date(organization_id: str, current_date: str) -> Optional[str]`
Récupère la date de situation précédente par rapport à une date donnée.

#### `get_snapshots_by_date(organization_id: str, date_situation: str, limit: int = 10000, skip: int = 0) -> List[dict]`
Récupère tous les snapshots pour une date de situation donnée.

#### `compare_snapshots(organization_id: str, date_ancienne: str, date_recente: str) -> Dict`
Compare les snapshots entre deux dates et détecte :
- Régularisations complètes
- Régularisations partielles
- Nouveaux crédits impayés
- Crédits stables
- Crédits aggravés

Retourne un dictionnaire avec les listes de crédits et les statistiques de comparaison.

#### `get_snapshot_summary(organization_id: str, date_situation: str) -> Optional[Dict]`
Récupère un résumé d'un snapshot (batch) avec :
- Le `snapshot_id`
- Le nombre de crédits
- Les statistiques agrégées (montants, répartitions par tranche, segment, agence)

**Exemple d'utilisation :**

```python
from app.services.impayes_snapshot_service import (
    get_available_situation_dates,
    get_latest_situation_date,
    compare_snapshots,
    get_snapshot_summary
)

# Récupérer toutes les dates disponibles
dates = await get_available_situation_dates(org_id)
# ['2025-12-15', '2025-11-30', '2025-10-31']

# Récupérer la date la plus récente
latest = await get_latest_situation_date(org_id)
# '2025-12-15'

# Comparer deux dates
comparaison = await compare_snapshots(org_id, '2025-11-30', '2025-12-15')
# {
#   "regularisations_completes": [...],
#   "regularisations_partielles": [...],
#   "statistiques": {
#     "montant_recupere_total": 5000000,
#     "variation_montant": -5000000,
#     ...
#   }
# }

# Récupérer un résumé
summary = await get_snapshot_summary(org_id, '2025-12-15')
# {
#   "snapshot_id": "abc-123-...",
#   "date_situation": "2025-12-15",
#   "nombre_snapshots": 145,
#   "statistiques": {...}
# }
```

---

### 3. `impayes_recouvrement_service.py` - Service d'indicateurs de recouvrement

**Responsabilités :**
- Détection automatique des régularisations
- Calcul des indicateurs de performance de recouvrement
- Analyse de l'efficacité par tranche de retard
- Calcul du taux de réponse aux SMS

**Fonctions principales :**

#### `detecter_regularisations_automatiques(organization_id: str, date_situation_debut: Optional[str] = None, date_situation_fin: Optional[str] = None) -> List[dict]`
Détecte automatiquement les régularisations en comparant les snapshots entre différentes dates.

#### `calculer_indicateurs_recouvrement(organization_id: str, date_debut: Optional[str] = None, date_fin: Optional[str] = None, date_situation: Optional[str] = None) -> dict`
Calcule tous les indicateurs de performance de recouvrement :
- Taux de recouvrement (montant récupéré / montant impayé)
- Délai moyen de recouvrement (jours)
- Taux de réponse aux SMS
- Efficacité par tranche de retard
- Taux de régularisation après SMS

**Exemple d'utilisation :**

```python
from app.services.impayes_recouvrement_service import (
    detecter_regularisations_automatiques,
    calculer_indicateurs_recouvrement
)

# Détecter les régularisations
regularisations = await detecter_regularisations_automatiques(
    organization_id=org_id,
    date_situation_debut='2025-11-01',
    date_situation_fin='2025-12-31'
)

# Calculer les indicateurs
indicateurs = await calculer_indicateurs_recouvrement(
    organization_id=org_id,
    date_debut='2025-11-01',
    date_fin='2025-12-31'
)
# {
#   "taux_recouvrement": 10.5,
#   "montant_total_recupere": 5000000,
#   "delai_moyen_recouvrement": 15.2,
#   "taux_reponse_sms": 25.0,
#   "efficacite_par_tranche": {...}
# }
```

---

## Endpoints API disponibles

### Gestion des dates de situation

- `GET /impayes/dates-situation` : Liste toutes les dates disponibles
- `GET /impayes/dates-situation/latest` : Récupère la date la plus récente
- `GET /impayes/dates-situation/{current_date}/previous` : Récupère la date précédente

### Gestion des snapshots

- `GET /impayes/snapshots/by-date/{date_situation}` : Récupère les snapshots pour une date
- `GET /impayes/snapshots/by-date/{date_situation}/summary` : Récupère le résumé d'un snapshot
- `GET /impayes/snapshots/compare?date_ancienne=...&date_recente=...` : Compare deux dates

### Indicateurs de recouvrement

- `GET /impayes/indicateurs-recouvrement?date_debut=...&date_fin=...&date_situation=...` : Calcule les indicateurs

---

## Flux d'utilisation typique

### 1. Import d'un premier fichier (30/11/2025)

```python
# L'utilisateur importe un fichier via l'interface
# Le système appelle automatiquement :
snapshots, messages = await traiter_import_impayes(
    lignes=lignes_du_fichier,
    date_situation="2025-11-30",
    organization_id=org_id,
    created_by=user_id
)
# → Crée 150 snapshots avec snapshot_id = "abc-123-..."
# → Génère 100 SMS
```

### 2. Import d'un deuxième fichier (15/12/2025)

```python
# L'utilisateur importe un nouveau fichier
snapshots, messages = await traiter_import_impayes(
    lignes=lignes_du_fichier,
    date_situation="2025-12-15",
    organization_id=org_id,
    created_by=user_id
)
# → Crée 145 snapshots avec snapshot_id = "xyz-789-..." (nouveau UUID)
# → Les anciens snapshots (abc-123) ne sont pas modifiés
```

### 3. Comparaison entre les deux dates

```python
# Comparer les deux dates
comparaison = await compare_snapshots(
    organization_id=org_id,
    date_ancienne="2025-11-30",
    date_recente="2025-12-15"
)
# → Détecte automatiquement :
#   - 5 régularisations complètes
#   - 10 régularisations partielles
#   - 3 nouveaux crédits
#   - Statistiques de variation
```

### 4. Calcul des indicateurs de recouvrement

```python
# Calculer les indicateurs globaux
indicateurs = await calculer_indicateurs_recouvrement(
    organization_id=org_id,
    date_debut="2025-11-01",
    date_fin="2025-12-31"
)
# → Calcule :
#   - Taux de recouvrement : 10%
#   - Délai moyen : 15 jours
#   - Efficacité par tranche
#   - Taux de réponse SMS
```

---

## Bonnes pratiques

1. **Toujours utiliser les services plutôt que les modèles directement**
   - Les services encapsulent la logique métier
   - Facilite les tests et la maintenance

2. **Utiliser les fonctions utilitaires pour naviguer dans l'historique**
   - `get_latest_situation_date()` pour la date la plus récente
   - `get_previous_situation_date()` pour la date précédente
   - `get_available_situation_dates()` pour toutes les dates

3. **Comparer les dates dans l'ordre chronologique**
   - `date_ancienne` doit être antérieure à `date_recente`
   - Le système détecte automatiquement les régularisations

4. **Utiliser les résumés pour les dashboards**
   - `get_snapshot_summary()` pour un aperçu rapide d'un batch
   - `compare_snapshots()` pour les comparaisons détaillées

---

## Notes importantes

- **Pas de modification des snapshots existants** : Chaque import crée de nouveaux snapshots
- **Séparation par date** : Les snapshots sont strictement séparés par `date_situation`
- **Identifiant de batch** : Le `snapshot_id` identifie un fichier importé complet
- **Comparaison automatique** : Les régularisations sont détectées automatiquement lors des comparaisons

---

## Migration depuis l'ancien code

Les fonctions dans `app/models/impayes.py` (`detecter_regularisations_automatiques` et `calculer_indicateurs_recouvrement`) sont maintenant dépréciées mais toujours disponibles pour compatibilité.

**Recommandation :** Utiliser les nouveaux services :
- `app.services.impayes_snapshot_service` pour la gestion des snapshots
- `app.services.impayes_recouvrement_service` pour les indicateurs

Les endpoints API ont été mis à jour pour utiliser les nouveaux services.

