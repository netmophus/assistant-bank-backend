from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import time


class TrancheRetard(BaseModel):
    """Configuration d'une tranche de retard"""
    min_jours: int = Field(..., description="Nombre minimum de jours de retard")
    max_jours: Optional[int] = Field(None, description="Nombre maximum de jours de retard (None = infini)")
    libelle: str = Field(..., description="Libellé de la tranche (ex: 'Retard léger')")
    statut: str = Field(..., description="Statut associé (ex: 'Retard léger', 'Retard significatif', etc.)")


class ModeleSMS(BaseModel):
    """Modèle de SMS pour une tranche de retard"""
    tranche_id: str = Field(..., description="ID de la tranche de retard associée")
    libelle: str = Field(..., description="Libellé du modèle (ex: 'SMS retard léger')")
    texte: str = Field(..., description="Texte du SMS avec variables {NOM_CLIENT}, {MONTANT}, etc.")
    variables_disponibles: List[str] = Field(
        default_factory=lambda: [
            "NOM_CLIENT", "MONTANT", "DATE_ECHEANCE", "AGENCE", "CANAL_PAIEMENT",
            "REF_CREDIT", "MONTANT_IMPAYE", "JOURS_RETARD", "NUMERO_AGENCE",
            "CONSEILLER_TEL", "ENCOURS", "NB_ECHEANCES_IMPAYEES"
        ],
        description="Liste des variables disponibles dans le modèle"
    )
    actif: bool = Field(default=True, description="Le modèle est-il actif ?")


class RegleRestructuration(BaseModel):
    """Règle de détection de candidat à restructuration"""
    jours_retard_min: int = Field(default=60, description="Nombre minimum de jours de retard")
    pourcentage_impaye_min: float = Field(default=30.0, description="Pourcentage minimum d'impayé par rapport à l'encours")
    libelle: str = Field(default="Candidat à restructuration", description="Libellé du statut")


class ParametresTechniques(BaseModel):
    """Paramètres techniques pour l'envoi de SMS"""
    sender_id: str = Field(default="Softlink", description="Nom de l'expéditeur SMS")
    fuseau_horaire: str = Field(default="Africa/Niamey", description="Fuseau horaire (ex: Africa/Niamey)")
    heure_debut: str = Field(default="08:00", description="Heure de début autorisée (format HH:MM)")
    heure_fin: str = Field(default="20:00", description="Heure de fin autorisée (format HH:MM)")
    respecter_opt_out: bool = Field(default=True, description="Respecter le consentement client (opt-out)")


class ImpayesConfig(BaseModel):
    """Configuration complète des impayés"""
    organization_id: str
    tranches_retard: List[TrancheRetard] = Field(
        default_factory=lambda: [
            TrancheRetard(min_jours=1, max_jours=29, libelle="Retard léger", statut="Retard léger"),
            TrancheRetard(min_jours=30, max_jours=59, libelle="Retard significatif", statut="Retard significatif"),
            TrancheRetard(min_jours=60, max_jours=89, libelle="Zone critique / à restructurer", statut="Zone critique"),
            TrancheRetard(min_jours=90, max_jours=None, libelle="Douteux / NPL", statut="Douteux / NPL"),
        ],
        description="Tranches de jours de retard"
    )
    regle_restructuration: RegleRestructuration = Field(
        default_factory=lambda: RegleRestructuration(),
        description="Règle de détection de candidat à restructuration"
    )
    modeles_sms: List[ModeleSMS] = Field(default_factory=lambda: _get_default_modeles_sms(), description="Modèles de SMS par tranche")


def _get_default_modeles_sms() -> List[ModeleSMS]:
    """Retourne les modèles SMS par défaut pour chaque tranche"""
    return [
        ModeleSMS(
            tranche_id="0",
            libelle="SMS Retard léger",
            texte="Bonjour {NOM_CLIENT}, votre crédit {REF_CREDIT} présente un retard de {JOURS_RETARD} jours. Montant impayé: {MONTANT} FCFA. Merci de régulariser rapidement. Contactez {AGENCE} pour plus d'infos.",
            actif=True
        ),
        ModeleSMS(
            tranche_id="1",
            libelle="SMS Retard significatif",
            texte="Bonjour {NOM_CLIENT}, votre crédit {REF_CREDIT} présente un retard de {JOURS_RETARD} jours. Montant impayé: {MONTANT} FCFA. Veuillez régulariser URGENTEMENT. Contactez {AGENCE} au plus vite.",
            actif=True
        ),
        ModeleSMS(
            tranche_id="2",
            libelle="SMS Zone critique",
            texte="Bonjour {NOM_CLIENT}, votre crédit {REF_CREDIT} est en zone critique avec {JOURS_RETARD} jours de retard. Montant impayé: {MONTANT} FCFA. Contactez URGAMMENT {AGENCE} pour discuter d'une solution de restructuration.",
            actif=True
        ),
        ModeleSMS(
            tranche_id="3",
            libelle="SMS Douteux/NPL",
            texte="Bonjour {NOM_CLIENT}, votre crédit {REF_CREDIT} présente {JOURS_RETARD} jours de retard. Montant impayé: {MONTANT} FCFA. Situation critique. Contactez IMMÉDIATEMENT {AGENCE} pour éviter des mesures de recouvrement.",
            actif=True
        ),
    ]
    parametres_techniques: ParametresTechniques = Field(
        default_factory=lambda: ParametresTechniques(),
        description="Paramètres techniques d'envoi"
    )


class ImpayesConfigPublic(BaseModel):
    """Configuration publique des impayés"""
    id: str
    organization_id: str
    tranches_retard: List[TrancheRetard]
    regle_restructuration: RegleRestructuration
    modeles_sms: List[ModeleSMS]
    parametres_techniques: ParametresTechniques
    created_at: str
    updated_at: str

