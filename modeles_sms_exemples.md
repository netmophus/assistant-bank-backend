# Modèles SMS pour les Impayés - Exemples de Configuration

## Variables disponibles dans les modèles SMS

- `{NOM_CLIENT}` : Nom du client
- `{MONTANT_IMPAYE}` : Montant total impayé (formaté)
- `{MONTANT}` : Alias de MONTANT_IMPAYE
- `{REF_CREDIT}` : Référence du crédit
- `{JOURS_RETARD}` : Nombre de jours de retard
- `{AGENCE}` : Code de l'agence
- `{NUMERO_AGENCE}` : Alias de AGENCE
- `{DATE_ECHEANCE}` : Date de la dernière échéance impayée
- `{ENCOURS}` : Encours principal du crédit
- `{NB_ECHEANCES_IMPAYEES}` : Nombre d'échéances impayées
- `{CANAL_PAIEMENT}` : Canal de paiement (par défaut: "votre agence")
- `{CONSEILLER_TEL}` : Téléphone du conseiller (par défaut: "votre conseiller")

---

## 1. RETARD LÉGER (1-29 jours)

### Modèle SMS 1 - Courtois et informatif
```
Bonjour {NOM_CLIENT},

Nous vous informons que votre crédit {REF_CREDIT} présente un retard de {JOURS_RETARD} jours.

Montant impayé : {MONTANT_IMPAYE} FCFA.

Veuillez régulariser votre situation auprès de l'agence {AGENCE}.

Merci de votre compréhension.
```

### Modèle SMS 2 - Court et direct
```
Bonjour {NOM_CLIENT}, votre crédit {REF_CREDIT} a {JOURS_RETARD} jours de retard. Montant : {MONTANT_IMPAYE} FCFA. Contactez l'agence {AGENCE}. Merci.
```

### Modèle SMS 3 - Avec rappel de paiement
```
Bonjour {NOM_CLIENT},

Rappel : Votre crédit {REF_CREDIT} présente un retard de {JOURS_RETARD} jours.

Montant à régulariser : {MONTANT_IMPAYE} FCFA.

Agence {AGENCE} - Date échéance : {DATE_ECHEANCE}

Merci de régulariser rapidement.
```

---

## 2. RETARD SIGNIFICATIF (30-59 jours)

### Modèle SMS 1 - Urgent mais courtois
```
Bonjour {NOM_CLIENT},

URGENT : Votre crédit {REF_CREDIT} présente un retard de {JOURS_RETARD} jours.

Montant impayé : {MONTANT_IMPAYE} FCFA sur un encours de {ENCOURS} FCFA.

Nous vous invitons à contacter URGAMMENT l'agence {AGENCE} pour régulariser votre situation.

Merci.
```

### Modèle SMS 2 - Avec conséquences
```
Bonjour {NOM_CLIENT},

Votre crédit {REF_CREDIT} présente un retard significatif de {JOURS_RETARD} jours.

Montant impayé : {MONTANT_IMPAYE} FCFA ({NB_ECHEANCES_IMPAYEES} échéance(s)).

Il est important de régulariser votre situation auprès de l'agence {AGENCE} pour éviter toute procédure.

Contactez-nous rapidement.
```

### Modèle SMS 3 - Avec proposition de solution
```
Bonjour {NOM_CLIENT},

Votre crédit {REF_CREDIT} a {JOURS_RETARD} jours de retard. Montant : {MONTANT_IMPAYE} FCFA.

Nous vous proposons de discuter d'une solution adaptée. Contactez l'agence {AGENCE} au plus vite.

Merci.
```

---

## 3. ZONE CRITIQUE / À RESTRUCTURER (60-89 jours)

### Modèle SMS 1 - Alerte critique
```
Bonjour {NOM_CLIENT},

ALERTE : Votre crédit {REF_CREDIT} est en situation critique avec {JOURS_RETARD} jours de retard.

Montant impayé : {MONTANT_IMPAYE} FCFA.

Votre dossier est éligible à une restructuration. Contactez URGAMMENT l'agence {AGENCE} pour discuter d'une solution.

Ne tardez pas.
```

### Modèle SMS 2 - Avec menace de procédure
```
Bonjour {NOM_CLIENT},

SITUATION CRITIQUE : Votre crédit {REF_CREDIT} présente {JOURS_RETARD} jours de retard.

Montant impayé : {MONTANT_IMPAYE} FCFA.

Sans régularisation rapide, votre dossier sera transmis au service recouvrement.

Contactez immédiatement l'agence {AGENCE} pour éviter toute procédure.
```

### Modèle SMS 3 - Proposition de restructuration
```
Bonjour {NOM_CLIENT},

Votre crédit {REF_CREDIT} est en zone critique ({JOURS_RETARD} jours de retard, {MONTANT_IMPAYE} FCFA impayés).

Nous pouvons étudier une restructuration de votre crédit.

Contactez URGAMMENT l'agence {AGENCE} pour discuter d'une solution adaptée à votre situation.

Agence {AGENCE}
```

---

## 4. DOUTEUX / NPL (≥90 jours)

### Modèle SMS 1 - Dernier rappel avant procédure
```
Bonjour {NOM_CLIENT},

DERNIER RAPPEL : Votre crédit {REF_CREDIT} présente {JOURS_RETARD} jours de retard.

Montant impayé : {MONTANT_IMPAYE} FCFA.

Votre dossier est classé DOUTEUX. Sans régularisation immédiate, des procédures de recouvrement seront engagées.

Contactez URGAMMENT l'agence {AGENCE} - Dernière chance de régularisation.
```

### Modèle SMS 2 - Alerte procédure
```
Bonjour {NOM_CLIENT},

ALERTE PROCÉDURE : Votre crédit {REF_CREDIT} est classé DOUTEUX avec {JOURS_RETARD} jours de retard.

Montant impayé : {MONTANT_IMPAYE} FCFA.

Des procédures de recouvrement seront engagées sous 48h si aucun contact n'est établi.

Contactez IMMÉDIATEMENT l'agence {AGENCE}.
```

### Modèle SMS 3 - Dernière opportunité
```
Bonjour {NOM_CLIENT},

Votre crédit {REF_CREDIT} est en situation DOUTEUX ({JOURS_RETARD} jours de retard, {MONTANT_IMPAYE} FCFA impayés).

Dernière opportunité : Contactez l'agence {AGENCE} dans les 48h pour discuter d'une solution de régularisation.

Au-delà, votre dossier sera transmis au service contentieux.
```

---

## Configuration dans l'interface

### Pour chaque modèle SMS, configurez :

1. **Tranche ID** : 
   - "0" pour Retard léger (1ère tranche)
   - "1" pour Retard significatif (2ème tranche)
   - "2" pour Zone critique (3ème tranche)
   - "3" pour Douteux/NPL (4ème tranche)

2. **Libellé** : 
   - "SMS Retard léger"
   - "SMS Retard significatif"
   - "SMS Zone critique"
   - "SMS Douteux"

3. **Texte** : Copiez l'un des modèles ci-dessus

4. **Actif** : Cochez la case pour activer le modèle

---

## Exemple de configuration complète

### Tranche 0 - Retard léger
- Tranche ID: `0`
- Libellé: `SMS Retard léger`
- Texte: `Bonjour {NOM_CLIENT}, votre crédit {REF_CREDIT} a {JOURS_RETARD} jours de retard. Montant : {MONTANT_IMPAYE} FCFA. Contactez l'agence {AGENCE}. Merci.`
- Actif: ✅

### Tranche 1 - Retard significatif
- Tranche ID: `1`
- Libellé: `SMS Retard significatif`
- Texte: `Bonjour {NOM_CLIENT}, URGENT : Votre crédit {REF_CREDIT} présente un retard de {JOURS_RETARD} jours. Montant impayé : {MONTANT_IMPAYE} FCFA. Contactez URGAMMENT l'agence {AGENCE}. Merci.`
- Actif: ✅

### Tranche 2 - Zone critique
- Tranche ID: `2`
- Libellé: `SMS Zone critique`
- Texte: `Bonjour {NOM_CLIENT}, ALERTE : Votre crédit {REF_CREDIT} est en situation critique avec {JOURS_RETARD} jours de retard. Montant impayé : {MONTANT_IMPAYE} FCFA. Contactez URGAMMENT l'agence {AGENCE} pour discuter d'une solution.`
- Actif: ✅

### Tranche 3 - Douteux/NPL
- Tranche ID: `3`
- Libellé: `SMS Douteux`
- Texte: `Bonjour {NOM_CLIENT}, DERNIER RAPPEL : Votre crédit {REF_CREDIT} présente {JOURS_RETARD} jours de retard. Montant impayé : {MONTANT_IMPAYE} FCFA. Votre dossier est classé DOUTEUX. Contactez URGAMMENT l'agence {AGENCE} - Dernière chance.`
- Actif: ✅

---

## Notes importantes

- Les SMS sont limités à 160 caractères pour un SMS standard (certains opérateurs supportent jusqu'à 1600 caractères en mode concaténé)
- Adaptez le ton selon votre politique de communication
- Testez toujours les modèles avant de les activer en production
- Vérifiez que toutes les variables sont bien remplacées

