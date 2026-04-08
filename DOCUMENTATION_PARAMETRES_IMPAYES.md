# Documentation — Paramètres des Impayés
**Page :** `/org/settings/impayes`  
**Accès :** Administrateur uniquement  
**API :** `/api/impayes/config`, `/api/impayes/escalade/config`, `/api/impayes/scoring/config`

---

## Vue d'ensemble

La page de configuration des impayés est divisée en **3 onglets** :

| Onglet | Description |
|--------|-------------|
| **Escalade** | Définit les niveaux et règles d'escalade automatique des dossiers impayés |
| **Scoring** | Configure le moteur de calcul du score de risque des dossiers impayés |
| *(Tranches / SMS / Restructuration)* | Géré via l'onglet principal de configuration |

---

## 1. Onglet Escalade

L'escalade automatique permet de faire progresser un dossier impayé vers des niveaux de recouvrement de plus en plus sévères selon l'ancienneté du retard.

### 1.1 Options générales

| Paramètre | Type | Description |
|-----------|------|-------------|
| **Escalade automatique** | Booléen | Active/désactive le passage automatique d'un dossier au niveau d'escalade supérieur quand le seuil de jours est atteint. Si désactivé, l'escalade doit être faite manuellement. |
| **Notifier le gestionnaire** | Booléen | Envoie une notification interne au gestionnaire du dossier chaque fois qu'un niveau d'escalade est atteint. |
| **Autoriser le forçage manuel** | Booléen | Permet à un agent de forcer manuellement un dossier vers un niveau d'escalade sans attendre le seuil de jours. |
| **Justification de forçage obligatoire** | Booléen | Si le forçage manuel est autorisé, oblige l'agent à saisir un motif écrit avant de forcer l'escalade. |

### 1.2 Niveaux d'escalade

Chaque niveau représente une étape dans le processus de recouvrement. Par défaut 4 niveaux sont configurés, mais vous pouvez en ajouter.

| Paramètre | Description | Exemple par défaut |
|-----------|-------------|-------------------|
| **Identifiant (niveau)** | Code interne unique du niveau (sans espaces) | `relance_1`, `mise_en_demeure` |
| **Libellé** | Nom affiché dans l'interface | `Première relance`, `Contentieux` |
| **Description** | Explication courte de ce qui se passe à ce niveau | `Premier rappel amiable par SMS` |
| **Jours de déclenchement** | Nombre de jours de retard à partir duquel ce niveau s'active automatiquement | 7 / 30 / 60 / 90 |
| **Couleur** | Code couleur hexadécimal pour l'affichage visuel dans les tableaux | `#f59e0b` (orange), `#ef4444` (rouge) |
| **Actions automatiques** | Actions déclenchées automatiquement à l'atteinte du niveau | `SMS`, `Courrier`, `Email`, `Appel`, `Notification App` |
| **Responsable d'escalade** | Nom ou rôle de la personne responsable à ce niveau | `Agent Recouvrement 1`, `Responsable Juridique` |
| **Actif** | Activer ou désactiver ce niveau sans le supprimer | Oui / Non |

#### Niveaux par défaut

| # | Identifiant | Libellé | Déclenchement | Actions |
|---|-------------|---------|---------------|---------|
| 1 | `relance_1` | Première relance | 7 jours | SMS |
| 2 | `relance_2` | Deuxième relance | 30 jours | SMS |
| 3 | `mise_en_demeure` | Mise en demeure | 60 jours | SMS + Courrier |
| 4 | `contentieux` | Contentieux | 90 jours | Courrier |

---

## 2. Onglet Scoring

Le scoring calcule automatiquement un **score de 0 à 100** pour chaque dossier impayé. Plus le score est bas, plus le risque de non-recouvrement est élevé.

### 2.1 Poids des critères

Définit l'importance relative (en %) de chaque critère dans le calcul du score final. **La somme des poids doit être égale à 1 (100%).**

| Critère | Poids par défaut | Description |
|---------|-----------------|-------------|
| **Jours de retard** | 30% | Ancienneté du retard — facteur le plus important |
| **Ratio impayé/encours** | 20% | Proportion du capital impayé par rapport au capital restant dû |
| **Garanties** | 15% | Présence ou non d'une garantie sur le crédit |
| **Joignabilité** | 10% | Le client a-t-il un numéro de téléphone enregistré ? |
| **Historique des promesses** | 15% | Fiabilité du client à tenir ses promesses de paiement passées |
| **Échéances impayées** | 10% | Nombre d'échéances consécutives non honorées |

### 2.2 Seuils — Jours de retard

Définit le score partiel attribué selon le nombre de jours de retard :

| Palier | Jours de retard | Score attribué |
|--------|----------------|----------------|
| Palier 1 | ≤ 15 jours | 90 |
| Palier 2 | ≤ 30 jours | 75 |
| Palier 3 | ≤ 60 jours | 50 |
| Palier 4 | ≤ 90 jours | 30 |
| Palier 5 | ≤ 180 jours | 15 |
| Palier 6 | > 180 jours | 5 |

### 2.3 Seuils — Ratio impayé / encours

Définit le score partiel selon le pourcentage du montant impayé sur l'encours :

| Palier | Ratio impayé | Score attribué |
|--------|-------------|----------------|
| Palier 1 | ≤ 10% | 90 |
| Palier 2 | ≤ 25% | 70 |
| Palier 3 | ≤ 50% | 45 |
| Palier 4 | ≤ 75% | 20 |
| Palier 5 | > 75% | 5 |

### 2.4 Seuils — Nombre d'échéances impayées

| Palier | Nb échéances | Score attribué |
|--------|-------------|----------------|
| Palier 1 | 1 échéance | 90 |
| Palier 2 | ≤ 3 échéances | 65 |
| Palier 3 | ≤ 6 échéances | 35 |
| Palier 4 | > 6 échéances | 10 |

### 2.5 Scores — Garanties

| Situation | Score attribué |
|-----------|----------------|
| Crédit avec garantie | 80 |
| Crédit sans garantie | 20 |

### 2.6 Scores — Joignabilité

| Situation | Score attribué |
|-----------|----------------|
| Client avec numéro de téléphone | 80 |
| Client sans numéro de téléphone | 20 |

### 2.7 Interprétation du score final (niveaux de risque)

| Niveau | Seuil | Couleur | Recommandation par défaut |
|--------|-------|---------|--------------------------|
| **Faible risque** | Score ≥ 70 | Vert | Relance amiable par SMS, forte probabilité de régularisation |
| **Risque moyen** | Score ≥ 50 | Orange | Relance téléphonique recommandée, négocier un échéancier |
| **Risque élevé** | Score ≥ 30 | Rouge | Mise en demeure à envisager, visite terrain si possible |
| **Risque critique** | Score < 30 | Rouge foncé | Risque de perte élevé, envisager contentieux ou passage en perte |

> Les seuils et recommandations sont entièrement personnalisables.

---

## 3. Configuration principale des Impayés

Gérée via l'API `/api/impayes/config`.

### 3.1 Tranches de retard

Permet de classifier chaque dossier dans une tranche selon son nombre de jours de retard.

| Paramètre | Description |
|-----------|-------------|
| **Jours min** | Nombre de jours de retard minimum pour entrer dans cette tranche |
| **Jours max** | Nombre de jours de retard maximum (vide = sans limite) |
| **Libellé** | Nom affiché dans les tableaux et rapports |
| **Statut** | Statut interne associé à cette tranche |

#### Tranches par défaut

| Tranche | Jours de retard | Libellé |
|---------|----------------|---------|
| 0 | 1 – 29 jours | Retard léger |
| 1 | 30 – 59 jours | Retard significatif |
| 2 | 60 – 89 jours | Zone critique / à restructurer |
| 3 | ≥ 90 jours | Douteux / NPL |

### 3.2 Règle de restructuration

Définit les critères pour qu'un dossier soit automatiquement marqué comme **"Candidat à restructuration"**.

| Paramètre | Valeur par défaut | Description |
|-----------|-------------------|-------------|
| **Jours de retard minimum** | 60 jours | Le dossier doit avoir au moins ce nombre de jours de retard |
| **Ratio impayé minimum** | 30% | Le montant impayé doit représenter au moins ce % de l'encours |
| **Libellé** | `Candidat à restructuration` | Étiquette affichée sur le dossier |

> Un dossier est candidat à restructuration si **les deux conditions sont réunies simultanément**.

### 3.3 Modèles SMS

Un modèle SMS est configuré par tranche de retard. Ces SMS sont générés automatiquement lors de l'import des impayés.

| Paramètre | Description |
|-----------|-------------|
| **Tranche associée** | À quelle tranche de retard ce modèle correspond (0 à 3) |
| **Libellé** | Nom interne du modèle |
| **Texte du SMS** | Corps du message avec variables dynamiques |
| **Actif** | Activer/désactiver ce modèle sans le supprimer |

#### Variables disponibles dans le texte SMS

| Variable | Valeur remplacée |
|----------|-----------------|
| `{NOM_CLIENT}` | Nom complet du client |
| `{REF_CREDIT}` | Référence du crédit |
| `{MONTANT}` | Montant impayé total (FCFA) |
| `{MONTANT_IMPAYE}` | Montant impayé détaillé |
| `{ENCOURS}` | Capital restant dû |
| `{JOURS_RETARD}` | Nombre de jours de retard |
| `{NB_ECHEANCES_IMPAYEES}` | Nombre d'échéances non payées |
| `{DATE_ECHEANCE}` | Date de la dernière échéance impayée |
| `{AGENCE}` | Nom de l'agence |
| `{NUMERO_AGENCE}` | Numéro de téléphone de l'agence |
| `{CONSEILLER_TEL}` | Téléphone du conseiller |
| `{CANAL_PAIEMENT}` | Canal de paiement recommandé |

### 3.4 Paramètres techniques d'envoi SMS

| Paramètre | Valeur par défaut | Description |
|-----------|-------------------|-------------|
| **Sender ID** | `Softlink` | Nom de l'expéditeur affiché sur le téléphone du client (max 11 caractères) |
| **Fuseau horaire** | `Africa/Niamey` | Fuseau horaire pour le calcul des plages d'envoi autorisées |
| **Heure de début** | `08:00` | Heure la plus tôt à laquelle un SMS peut être envoyé |
| **Heure de fin** | `20:00` | Heure limite après laquelle aucun SMS n'est envoyé |
| **Respecter l'opt-out** | `Oui` | Si activé, les clients ayant refusé les SMS ne recevront aucun message |

---

## 4. Colonnes du fichier Excel d'import

Pour importer des impayés, le fichier Excel doit contenir les colonnes suivantes (dans cet ordre) :

| Colonne | Obligatoire | Format | Description |
|---------|-------------|--------|-------------|
| `dateSituation` | Oui | `YYYY-MM-DD` | Date de la situation des impayés |
| `refCredit` | Oui | Texte | Référence unique du crédit |
| `idClient` | Oui | Texte | Identifiant unique du client |
| `nomClient` | Oui | Texte | Nom complet du client |
| `telephoneClient` | Non | Numéro | Téléphone du client (pour les SMS) |
| `segment` | Oui | `PARTICULIER` / `PME` / `PMI` | Segment du client |
| `agence` | Oui | Texte | Code ou nom de l'agence |
| `gestionnaire` | Non | Texte | Nom du gestionnaire du dossier |
| `produit` | Oui | `Conso` / `Immo` / `Trésorerie` / `Autre` | Type de crédit |
| `montantInitial` | Oui | Nombre | Montant initial du crédit accordé (FCFA) |
| `encoursPrincipal` | Oui | Nombre | Capital restant dû (FCFA) |
| `principalImpayé` | Oui | Nombre | Capital impayé (FCFA) |
| `interetsImpayés` | Oui | Nombre | Intérêts impayés (FCFA) |
| `penalitesImpayées` | Oui | Nombre | Pénalités de retard impayées (FCFA) |
| `nbEcheancesImpayées` | Oui | Entier | Nombre d'échéances non honorées |
| `joursRetard` | Oui | Entier | Nombre de jours de retard |
| `dateDerniereEcheanceImpayee` | Non | `YYYY-MM-DD` | Date de la dernière échéance impayée |
| `statutInterne` | Oui | `Normal` / `Impayé` / `Douteux` / `Compromis` | Statut interne du crédit |
| `garanties` | Non | Texte | Description des garanties (ex: Hypothèque) |
| `revenuMensuel` | Non | Nombre | Revenu mensuel du client (FCFA) |
| `commentaire` | Non | Texte | Commentaire libre |

> Un modèle Excel pré-rempli est téléchargeable via le bouton **"Modèle Excel"** dans l'onglet Import.

---

## 5. Champs calculés automatiquement

Ces champs sont calculés par le système lors de l'import — ils ne peuvent pas être saisis manuellement.

| Champ | Formule / Logique |
|-------|------------------|
| `montant_total_impaye` | `principalImpaye + interetsImpayes + penalitesImpayees` |
| `bucket_retard` | Tranche déterminée selon `joursRetard` et la configuration des tranches |
| `ratio_impaye_encours` | `montant_total_impaye / encoursPrincipal × 100` |
| `statut_reglementaire` | Statut calculé selon la réglementation bancaire |
| `candidat_restructuration` | `true` si `joursRetard ≥ jours_retard_min` ET `ratio_impaye_encours ≥ pourcentage_impaye_min` |
| `score_recouvrement` | Score 0–100 calculé par le moteur de scoring |
| `niveau_escalade` | Niveau d'escalade actif selon les jours de retard |
| `periode_suivi` | Période mensuelle `YYYY-MM` générée automatiquement |

---

*Documentation générée le 2026-04-08 — Assistant Banque Backend*
