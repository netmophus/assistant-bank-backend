# Exemple de création d'un poste réglementaire

## 1. Via l'interface utilisateur (Frontend)

Dans l'interface Next.js, allez dans **Paramètres > PCB UEMOA > Postes Réglementaires** et cliquez sur **"Ajouter un poste"**.

### Exemple 1 : Poste feuille avec GL codes

**Champs à remplir :**
- **Code** : `ACTIF_001`
- **Libellé** : `Trésorerie et équivalents de trésorerie`
- **Type** : `bilan_actif`
- **Niveau** : `2`
- **Parent** : (sélectionner un poste parent si nécessaire)
- **Ordre** : `10`
- **GL Codes** :
  - Code GL : `101*` (pattern wildcard)
  - Signe : `+`
  - Base : `NET` (ou `DEBIT` ou `CREDIT`)
- **Formule** : `somme`
- **Actif** : ✓

### Exemple 2 : Poste parent (sans GL codes, somme des enfants)

**Champs à remplir :**
- **Code** : `ACTIF_000`
- **Libellé** : `ACTIF TOTAL`
- **Type** : `bilan_actif`
- **Niveau** : `1`
- **Parent** : (aucun)
- **Ordre** : `1`
- **GL Codes** : (vide - sera calculé comme somme des enfants)
- **Formule** : `somme`
- **Actif** : ✓

---

## 2. Via l'API (Backend)

### Endpoint
```
POST /api/pcb/postes
```

### Headers
```
Authorization: Bearer <token>
Content-Type: application/json
```

### Exemple 1 : Poste feuille avec un GL code simple

```json
{
  "code": "ACTIF_001",
  "libelle": "Trésorerie et équivalents de trésorerie",
  "type": "bilan_actif",
  "niveau": 2,
  "parent_id": null,
  "parent_code": null,
  "ordre": 10,
  "gl_codes": [
    {
      "code": "101011",
      "signe": "+",
      "basis": "NET"
    }
  ],
  "formule": "somme",
  "formule_custom": null,
  "is_active": true
}
```

### Exemple 2 : Poste avec pattern wildcard

```json
{
  "code": "ACTIF_002",
  "libelle": "Créances clients",
  "type": "bilan_actif",
  "niveau": 2,
  "ordre": 20,
  "gl_codes": [
    {
      "code": "411*",
      "signe": "+",
      "basis": "DEBIT"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 3 : Poste avec plusieurs GL codes et patterns

```json
{
  "code": "ACTIF_003",
  "libelle": "Immobilisations",
  "type": "bilan_actif",
  "niveau": 2,
  "ordre": 30,
  "gl_codes": [
    {
      "code": "211*",
      "signe": "+",
      "basis": "NET"
    },
    {
      "code": "213*",
      "signe": "+",
      "basis": "NET"
    },
    {
      "code": "2181-2189",
      "signe": "+",
      "basis": "DEBIT"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 4 : Poste parent (sans GL codes)

```json
{
  "code": "ACTIF_000",
  "libelle": "ACTIF TOTAL",
  "type": "bilan_actif",
  "niveau": 1,
  "ordre": 1,
  "gl_codes": [],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 5 : Poste avec classe de comptes

```json
{
  "code": "PASSIF_001",
  "libelle": "Capitaux propres",
  "type": "bilan_passif",
  "niveau": 2,
  "ordre": 10,
  "gl_codes": [
    {
      "code": "Classe 1",
      "signe": "+",
      "basis": "CREDIT"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 6 : Poste compte de résultat (Produit)

```json
{
  "code": "CR_PROD_001",
  "libelle": "Produits d'exploitation",
  "type": "cr_produit",
  "niveau": 1,
  "ordre": 10,
  "gl_codes": [
    {
      "code": "701*",
      "signe": "+",
      "basis": "CREDIT"
    },
    {
      "code": "702*",
      "signe": "+",
      "basis": "CREDIT"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 7 : Poste compte de résultat (Charge)

```json
{
  "code": "CR_CHG_001",
  "libelle": "Charges d'exploitation",
  "type": "cr_charge",
  "niveau": 1,
  "ordre": 10,
  "gl_codes": [
    {
      "code": "601*",
      "signe": "+",
      "basis": "DEBIT"
    },
    {
      "code": "602*",
      "signe": "+",
      "basis": "DEBIT"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 8 : Poste avec liste CSV de codes GL

```json
{
  "code": "ACTIF_004",
  "libelle": "Divers actifs",
  "type": "bilan_actif",
  "niveau": 2,
  "ordre": 40,
  "gl_codes": [
    {
      "code": "471,472,473",
      "signe": "+",
      "basis": "NET"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

### Exemple 9 : Poste hiérarchique (avec parent)

```json
{
  "code": "ACTIF_001_001",
  "libelle": "Caisse",
  "type": "bilan_actif",
  "niveau": 3,
  "parent_id": "507f1f77bcf86cd799439011",
  "parent_code": "ACTIF_001",
  "ordre": 1,
  "gl_codes": [
    {
      "code": "101011",
      "signe": "+",
      "basis": "DEBIT"
    }
  ],
  "formule": "somme",
  "is_active": true
}
```

---

## 3. Types de postes disponibles

- `bilan_actif` : Poste d'actif du bilan
- `bilan_passif` : Poste de passif du bilan
- `hors_bilan` : Poste hors bilan
- `cr_produit` : Produit du compte de résultat
- `cr_charge` : Charge du compte de résultat

## 4. Patterns supportés pour les codes GL

- **Code exact** : `101011`
- **Wildcard** : `101*` (tous les codes commençant par 101)
- **Plage** : `4111-4119` (codes de 4111 à 4119)
- **Classe** : `Classe 4` (tous les comptes de la classe 4)
- **Liste CSV** : `471,472,473` (plusieurs codes séparés par des virgules)

## 5. Bases de calcul (basis)

- `NET` : Solde net (Crédit - Débit) - **Par défaut**
- `DEBIT` : Débit brut
- `CREDIT` : Crédit brut

## 6. Signes

- `+` : Ajouter la valeur
- `-` : Soustraire la valeur

## 7. Formules

- `somme` : Somme des GL codes (ou des enfants si pas de GL codes)
- `difference` : Différence entre deux valeurs
- `ratio` : Calcul de ratio
- `custom` : Formule personnalisée (nécessite `formule_custom`)

---

## 8. Exemple avec cURL

```bash
curl -X POST "http://localhost:8000/api/pcb/postes" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "ACTIF_001",
    "libelle": "Trésorerie",
    "type": "bilan_actif",
    "niveau": 2,
    "ordre": 10,
    "gl_codes": [
      {
        "code": "101*",
        "signe": "+",
        "basis": "NET"
      }
    ],
    "formule": "somme",
    "is_active": true
  }'
```

---

## 9. Réponse de l'API

```json
{
  "id": "507f1f77bcf86cd799439011",
  "code": "ACTIF_001",
  "libelle": "Trésorerie et équivalents de trésorerie",
  "type": "bilan_actif",
  "niveau": 2,
  "parent_id": null,
  "parent_code": null,
  "organization_id": "507f1f77bcf86cd799439012",
  "ordre": 10,
  "gl_codes": [
    {
      "code": "101*",
      "signe": "+",
      "basis": "NET"
    }
  ],
  "formule": "somme",
  "formule_custom": null,
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

