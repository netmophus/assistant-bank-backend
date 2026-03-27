# 📋 Workflow Complet - Gestion des Consommables

## 🔄 Workflow d'Introduction de Stock

### **Étape 1 : Introduction de Stock par le Gestionnaire**
- **Acteur** : Gestionnaire de stock (`role = "gestionnaire_stock"` ou `"admin"`)
- **Note** : Le gestionnaire de stock est un rôle distinct, séparé de l'agent DRH
- **Action** : Crée une demande d'introduction via `POST /stock/introductions` ou `PUT /stock/consommables/{id}/stock`
- **Données requises** :
  - `consommable_id` : ID du consommable
  - `quantite` : Quantité à introduire
  - `operation` : "set", "add", ou "subtract"
  - `motif` : Motif de l'introduction (optionnel)
- **Statut initial** : `en_attente`
- **Champs créés** :
  - `gestionnaire_id` : ID du gestionnaire
  - `organization_id` : ID de l'organisation
  - `validation_drh.statut` : "en_attente"
- **Important** : Le stock n'est **PAS** mis à jour immédiatement

---

### **Étape 2 : Validation par l'Agent DRH**
- **Acteur** : Agent stock DRH (`role = "agent_stock_drh"` ou `"admin"`)
- **Note** : L'agent DRH est différent du gestionnaire de stock. Seul l'agent DRH peut valider.
- **Action** : Valide ou rejette via :
  - `POST /stock/introductions/{id}/valider`
  - `POST /stock/introductions/{id}/rejeter`
- **Vérifications** :
  - L'utilisateur doit avoir `role = "admin"` ou `"agent_stock_drh"`
  - La demande doit appartenir à l'organisation
  - La demande doit être en statut `en_attente`
- **Résultat si validé** :
  - `statut` → `valide`
  - `validation_drh.statut` → `"valide"`
  - `validation_drh.agent_drh_id` : ID de l'agent DRH
  - `validation_drh.date` : Date de validation
  - **Stock mis à jour automatiquement** selon l'opération demandée
- **Résultat si rejeté** :
  - `statut` → `rejete`
  - `validation_drh.statut` → `"rejete"`
  - Fin du workflow (stock non modifié)

---

## 🔄 Workflow de Demande de Consommables (Modifié)

### **Étape 1 : Création de la Demande**
- **Acteur** : Agent du département
- **Action** : Crée une demande via `POST /stock/demandes`
- **Données requises** :
  - `consommable_id` : ID du consommable demandé
  - `quantite_demandee` : Quantité demandée
  - `motif` : Motif de la demande
  - `type_selection` : "conteneur" ou "unite"
- **Statut initial** : `en_attente`
- **Champs créés** :
  - `user_id` : ID de l'agent demandeur
  - `department_id` : ID du département
  - `approbation_directeur.statut` : "en_attente"
  - `traitement_stock` : vide (pas encore traité)

---

### **Étape 2 : Validation par le Directeur de Département**
- **Acteur** : Directeur de département
- **Action** : Approuve ou rejette via :
  - `POST /stock/demandes/{id}/approuver`
  - `POST /stock/demandes/{id}/rejeter`
- **Vérifications** :
  - L'utilisateur doit avoir `role_departement = "directeur"`
  - La demande doit appartenir au département du directeur
  - La demande doit être en statut `en_attente`
- **Résultat si approuvé** :
  - `statut` → `approuve_directeur`
  - `approbation_directeur.statut` → `"approuve"`
  - `approbation_directeur.directeur_id` : ID du directeur
  - `approbation_directeur.date` : Date d'approbation
  - `approbation_directeur.commentaire` : Commentaire optionnel
- **Résultat si rejeté** :
  - `statut` → `rejete_directeur`
  - `approbation_directeur.statut` → `"rejete"`
  - Fin du workflow (pas de traitement stock)

---

### **Étape 3 : Approbation par le Directeur DRH**
- **Acteur** : Directeur DRH (`role_departement = "directeur"` avec accès organisationnel)
- **Action** : Approuve ou rejette via :
  - `POST /stock/demandes/{id}/approuver-drh`
  - `POST /stock/demandes/{id}/rejeter-drh`
- **Vérifications** :
  - L'utilisateur doit avoir `role_departement = "directeur"`
  - La demande doit être en statut `approuve_directeur`
- **Résultat si approuvé** :
  - `statut` → `approuve_drh`
  - `approbation_drh.statut` → `"approuve"`
  - `approbation_drh.directeur_drh_id` : ID du directeur DRH
  - `approbation_drh.date` : Date d'approbation
  - `approbation_drh.commentaire` : Commentaire optionnel
- **Résultat si rejeté** :
  - `statut` → `rejete_drh`
  - `approbation_drh.statut` → `"rejete"`
  - Fin du workflow (pas de traitement stock)

---

### **Étape 4 : Traitement par le Gestionnaire de Stock (Débit)**
- **Acteur** : Gestionnaire de stock (`role = "gestionnaire_stock"`) ou Administrateur (`role = "admin"`)
- **Action** : Traite la demande approuvée par le directeur DRH via `POST /stock/demandes/{id}/traiter`
- **Vérifications** :
  - L'utilisateur doit avoir `role = "admin"` ou `"gestionnaire_stock"`
  - La demande doit être en statut `approuve_drh`
  - La demande doit avoir été approuvée par le directeur DRH (`approbation_drh.statut = "approuve"`)
  - La demande doit appartenir à l'organisation du gestionnaire
- **Action effectuée** :
  - Vérifie le stock disponible
  - Débite le stock (utilise la quantité validée)
  - Met à jour la demande
- **Résultat** :
  - `statut` → `traite`
  - `traitement_stock.gestionnaire_id` : ID du gestionnaire/admin
  - `traitement_stock.date` : Date de traitement
  - `traitement_stock.quantite_accordee` : Quantité réellement débitée
  - `traitement_stock.commentaire` : Commentaire optionnel
  - **Stock débité automatiquement**

---

## 📊 États (Statuts) des Demandes de Consommables

1. **`en_attente`** : Demande créée, en attente de validation directeur département
2. **`approuve_directeur`** : Validée par le directeur département, en attente d'approbation directeur DRH
3. **`rejete_directeur`** : Rejetée par le directeur département (fin du workflow)
4. **`approuve_drh`** : Approuvée par le directeur DRH, en attente de traitement par le gestionnaire de stock
5. **`rejete_drh`** : Rejetée par le directeur DRH (fin du workflow)
6. **`traite`** : Traitée par le gestionnaire, stock débité

## 📊 États (Statuts) des Introductions de Stock

1. **`en_attente`** : Introduction créée, en attente de validation DRH
2. **`valide`** : Validée par le DRH, stock mis à jour
3. **`rejete`** : Rejetée par le DRH (fin du workflow)

---

## 🔍 Endpoints Disponibles

### Introduction de Stock

#### Pour les Gestionnaires de Stock
- `POST /stock/introductions` : Créer une demande d'introduction de stock
- `PUT /stock/consommables/{id}/stock` : Créer une demande d'introduction (ancien endpoint modifié)
- `GET /stock/introductions/gestionnaire/mes-introductions` : Voir ses introductions
- `GET /stock/introductions/{id}` : Voir une introduction spécifique

#### Pour les Agents DRH
- `GET /stock/introductions/drh/a-valider` : Voir les introductions en attente
- `POST /stock/introductions/{id}/valider` : Valider une introduction (met à jour le stock)
- `POST /stock/introductions/{id}/rejeter` : Rejeter une introduction

### Demandes de Consommables

#### Pour les Agents
- `POST /stock/demandes` : Créer une demande
- `GET /stock/demandes/user/mes-demandes` : Voir ses demandes
- `GET /stock/demandes/{id}` : Voir une demande spécifique

#### Pour les Directeurs
- `GET /stock/demandes/directeur/a-valider` : Voir les demandes en attente
- `POST /stock/demandes/{id}/approuver` : Approuver une demande
- `POST /stock/demandes/{id}/rejeter` : Rejeter une demande

#### Pour les Agents DRH
- `GET /stock/demandes/drh/a-formaliser` : Voir les demandes approuvées en attente de formalisation
- `POST /stock/demandes/{id}/formaliser` : Formaliser une demande approuvée

#### Pour la Validation Conjointe des Sorties
- `GET /stock/demandes/validation-sortie/a-valider` : Voir les demandes en attente de validation conjointe
- `POST /stock/demandes/{id}/valider-sortie-departement` : Valider la sortie (Agent département)
- `POST /stock/demandes/{id}/valider-sortie-stock` : Valider la sortie (Agent stock DRH)

#### Pour les Gestionnaires de Stock (Admin)
- `GET /stock/demandes/gestionnaire/a-traiter` : Voir les demandes avec validation conjointe complète
- `POST /stock/demandes/{id}/traiter` : Traiter une demande (débiter le stock)

### Endpoint Spécial (Tests/Démo)
- `POST /stock/demandes/direct` : Crée une demande et débite immédiatement le stock (bypass le workflow)

---

## ⚠️ Différences avec le Workflow Souhaité

### Workflow d'Introduction de Stock
```
Gestionnaire introduit stock → Agent DRH valide → Stock mis à jour
```

### Workflow de Demande de Consommables
```
Agent → Crée demande → Directeur valide → Agent DRH formalise → Agent département + Agent stock valident sorties → Admin débite stock
```

### Points à Corriger

1. **Formalisation par Agent DRH** :
   - ❌ Actuellement : Après validation directeur, la demande passe directement au gestionnaire (admin)
   - ✅ Souhaité : Après validation directeur, un agent DRH doit formaliser la demande

2. **Validation des Sorties** :
   - ❌ Actuellement : L'admin traite seul et débite automatiquement le stock
   - ✅ Souhaité : L'agent du département doit aller valider les sorties avec l'agent du stock (DRH)

3. **Rôle Gestionnaire de Stock** :
   - ❌ Actuellement : Rôle "admin" générique
   - ✅ Souhaité : Rôle spécifique "agent_stock_drh" ou similaire

4. **Processus de Sortie** :
   - ❌ Actuellement : Débit automatique lors du traitement
   - ✅ Souhaité : Validation conjointe agent département + agent stock avant débit

---

## 📝 Modifications Nécessaires

1. **Ajouter un statut intermédiaire** : `formalise_drh` entre `approuve_directeur` et `traite`
2. **Créer un rôle spécifique** : `agent_stock_drh` ou `gestionnaire_stock`
3. **Ajouter une étape de formalisation** : Endpoint pour l'agent DRH
4. **Modifier le traitement** : Requérir validation conjointe avant débit
5. **Séparer validation et débit** : La validation ne doit pas débitter automatiquement

---

## 🔐 Permissions et Rôles

### Rôles Définis

1. **`gestionnaire_stock`** : Gestionnaire de stock (rôle distinct)
   - **Peut** : Introduire du stock (créer des demandes d'introduction)
   - **Ne peut pas** : Valider les introductions, formaliser les demandes

2. **`agent_stock_drh`** : Agent stock DRH
   - **Peut** : Valider les introductions de stock, formaliser les demandes, valider les sorties
   - **Ne peut pas** : Introduire directement du stock (doit passer par le gestionnaire)

3. **`admin`** : Administrateur (peut tout faire)

### Introduction de Stock
- **Création** : `role = "admin"` ou `"gestionnaire_stock"` (gestionnaire de stock)
- **Validation DRH** : `role = "admin"` ou `"agent_stock_drh"` (agent DRH uniquement)

### Demandes de Consommables
- **Création** : Tous les utilisateurs avec `department_id`
- **Validation Directeur** : Utilisateurs avec `role_departement = "directeur"`
- **Formalisation DRH** : `role = "admin"` ou `"agent_stock_drh"` (agent DRH uniquement)
- **Validation Sortie Département** : Agents du département concerné
- **Validation Sortie Stock** : `role = "admin"` ou `"agent_stock_drh"` (agent DRH uniquement)
- **Traitement (Débit)** : `role = "admin"` (admin uniquement)

---

## 📦 Collections MongoDB

- **`demandes_consommables`** : Stocke toutes les demandes avec leur historique
- **`introductions_stock`** : Stocke toutes les demandes d'introduction de stock

---

## 🎯 Prochaines Étapes

1. Définir le nouveau workflow complet
2. Créer les nouveaux statuts
3. Ajouter les rôles nécessaires
4. Créer les nouveaux endpoints
5. Modifier le frontend pour refléter le nouveau workflow
