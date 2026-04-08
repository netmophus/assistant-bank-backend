from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class SegmentEnum(str, Enum):
    PARTICULIER = "PARTICULIER"
    PME = "PME"
    PMI = "PMI"


class ProduitEnum(str, Enum):
    CONSO = "Conso"
    IMMO = "Immo"
    TRESORERIE = "Trésorerie"
    AUTRE = "Autre"


class StatutInterneEnum(str, Enum):
    NORMAL = "Normal"
    IMPAYE = "Impayé"
    DOUTEUX = "Douteux"
    COMPROMIS = "Compromis"


class StatutMessageEnum(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


# ===================== Import Excel =====================

class LigneImpayeImport(BaseModel):
    """Une ligne du fichier Excel importé"""
    dateSituation: str
    refCredit: str
    idClient: str
    nomClient: str
    telephoneClient: Optional[str] = None
    segment: SegmentEnum
    agence: str
    gestionnaire: Optional[str] = None
    produit: ProduitEnum
    montantInitial: float
    encoursPrincipal: float
    principalImpaye: float
    interetsImpayes: float
    penalitesImpayees: float
    nbEcheancesImpayees: int
    joursRetard: int
    dateDerniereEcheanceImpayee: Optional[str] = None
    statutInterne: StatutInterneEnum
    garanties: Optional[str] = None
    revenuMensuel: Optional[float] = None
    commentaire: Optional[str] = None




class ImportImpayesRequest(BaseModel):
    """Requête d'import d'un fichier Excel"""
    dateSituation: str  # Format YYYY-MM-DD
    lignes: List[LigneImpayeImport]


class ErreurImport(BaseModel):
    """Erreur détectée lors de l'import"""
    ligne: int
    champ: str
    message: str


class ImportImpayesResponse(BaseModel):
    """Réponse après validation de l'import"""
    success: bool
    errors: List[ErreurImport] = []
    message: str
    snapshots_preview: List[dict] = []  # Prévisualisation des snapshots calculés
    messages_preview: List[dict] = []  # Prévisualisation des SMS générés
    stats_preview: dict = {}  # Statistiques prévisionnelles
    existing_import: Optional[dict] = None  # Information sur un import existant pour cette date




# ===================== Snapshot d'impayés =====================

class ArrearsSnapshot(BaseModel):
    """Snapshot d'impayés calculé et enregistré"""
    snapshot_id: str
    organization_id: str
    date_situation: str
    periode_suivi: str = Field(..., description="Période de suivi mensuel YYYY-MM")
    created_by: str
    created_at: datetime
    is_active: bool = True  # Indique si ce snapshot fait partie du batch actif
    
    # Données originales
    ref_credit: str
    id_client: str
    nom_client: str
    telephone_client: Optional[str]
    segment: str
    agence: str
    gestionnaire: Optional[str]
    produit: str
    montant_initial: float
    encours_principal: float
    principal_impaye: float
    interets_impayes: float
    penalites_impayees: float
    nb_echeances_impayees: int
    jours_retard: int
    date_derniere_echeance_impayee: Optional[str]
    statut_interne: str
    garanties: Optional[str]
    revenu_mensuel: Optional[float]
    commentaire: Optional[str]
    
    # Champs calculés
    montant_total_impaye: float
    bucket_retard: str  # Tranche de retard (ex: "Retard léger")
    ratio_impaye_encours: float
    statut_reglementaire: str
    candidat_restructuration: bool
    
    # Champs de restructuration
    statut_restructuration: Optional[str] = None  # "restructure", "refuse", "douteux", "en_cours", None
    date_restructuration: Optional[str] = None
    commentaire_restructuration: Optional[str] = None
    restructure_par: Optional[str] = None  # ID de l'utilisateur qui a pris la décision
    date_action_restructuration: Optional[datetime] = None


class ArrearsSnapshotPublic(BaseModel):
    """Snapshot public pour l'API"""
    id: str
    snapshot_id: str
    organization_id: str
    date_situation: str
    periode_suivi: str
    created_by: str
    created_at: str
    is_active: bool
    ref_credit: str
    nom_client: str
    telephone_client: Optional[str]
    segment: str
    agence: str
    gestionnaire: Optional[str]
    produit: str
    montant_initial: float
    encours_principal: float
    principal_impaye: float
    interets_impayes: float
    penalites_impayees: float
    montant_total_impaye: float
    nb_echeances_impayees: int
    jours_retard: int
    bucket_retard: str
    ratio_impaye_encours: float
    statut_reglementaire: str
    candidat_restructuration: bool
    garanties: Optional[str]
    revenu_mensuel: Optional[str]
    commentaire: Optional[str]
    # Champs de restructuration
    statut_restructuration: Optional[str] = None
    date_restructuration: Optional[str] = None
    commentaire_restructuration: Optional[str] = None
    restructure_par: Optional[str] = None
    date_action_restructuration: Optional[str] = None


# ===================== Messages SMS =====================

class OutboundMessage(BaseModel):
    """Message SMS généré"""
    message_id: str
    organization_id: str
    snapshot_id: str
    periode_suivi: str = Field(..., description="Période de suivi mensuel YYYY-MM")
    type: str = "SMS"
    to: str
    body: str
    status: StatutMessageEnum = StatutMessageEnum.PENDING
    linked_credit: str  # refCredit
    tranche_id: str  # ID de la tranche de retard
    created_at: datetime
    sent_at: Optional[datetime] = None
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None


class OutboundMessagePublic(BaseModel):
    """Message public pour l'API"""
    id: str
    message_id: str
    snapshot_id: str
    periode_suivi: str
    to: str
    body: str
    status: str
    linked_credit: str
    tranche_id: str
    created_at: str
    sent_at: Optional[str] = None
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None


# ===================== Tableau de bord =====================

class StatistiquesImpayes(BaseModel):
    """Statistiques globales des impayés"""
    total_montant_impaye: float
    total_credits: int
    total_encours: float = 0
    repartition_tranches: dict  # {tranche: count}
    repartition_segments: dict  # {segment: count}
    repartition_agences: dict  # {agence: count}
    repartition_produits: dict = {}  # {produit: count}
    candidats_restructuration: int
    ratio_impaye_encours_moyen: float = 0
    montant_moyen_par_credit: float = 0


class EvolutionIndicateur(BaseModel):
    """Évolution d'un indicateur entre deux dates"""
    valeur: float  # Différence absolue
    pourcentage: float  # Variation en pourcentage
    couleur: str = "neutral-dark"  # Couleurs foncées pour meilleure visibilité: "success-dark" (vert foncé), "danger-dark" (rouge foncé), "warning-dark" (orange foncé), "neutral-dark" (gris foncé)
    icone: str = "equal"  # "arrow-down" (baisse), "arrow-up" (hausse), "equal" (stable)
    couleur_hex: str = "#6c757d"  # Code couleur hexadécimal pour affichage direct
    couleur_bg: str = "#ffffff"  # Couleur de fond recommandée pour le contraste
    avec_fond: bool = True  # Indique qu'un fond doit être appliqué pour meilleure visibilité
    style_recommande: dict = {}  # Styles CSS recommandés pour l'affichage


class EvolutionStatistiques(BaseModel):
    """Évolution des statistiques entre deux dates"""
    montant_impaye: EvolutionIndicateur
    nombre_credits: EvolutionIndicateur
    candidats_restructuration: EvolutionIndicateur
    ratio_moyen: EvolutionIndicateur


class ComparaisonStatistiques(BaseModel):
    """Comparaison des statistiques entre deux dates"""
    stats_actuelles: StatistiquesImpayes
    stats_precedentes: Optional[StatistiquesImpayes] = None
    date_precedente: Optional[str] = None
    evolution: Optional[EvolutionStatistiques] = None
    tendance: str  # "hausse", "baisse", "stable", "pas_de_comparaison"
    couleur_tendance: str = "neutral"  # "success" (baisse/vert), "danger" (hausse/rouge), "warning" (orange), "neutral" (gris)
    icone_tendance: str = "equal"  # "arrow-down" (baisse), "arrow-up" (hausse), "equal" (stable)


class ComparaisonParallele(BaseModel):
    """Données en parallèle pour comparaison visuelle"""
    indicateur: str  # Nom de l'indicateur (ex: "montant_impaye")
    libelle: str  # Libellé affiché (ex: "Montant total impayé")
    valeur_actuelle: float
    valeur_precedente: float
    difference: float  # Différence absolue
    pourcentage: float  # Variation en pourcentage
    couleur: str = "neutral-dark"  # Couleurs foncées pour meilleure visibilité: "success-dark" (vert foncé), "danger-dark" (rouge foncé), "warning-dark" (orange foncé), "neutral-dark" (gris foncé)
    icone: str = "equal"  # "arrow-down" (baisse), "arrow-up" (hausse), "equal" (stable)
    couleur_hex: str = "#6c757d"  # Code couleur hexadécimal pour affichage direct
    couleur_bg: str = "#ffffff"  # Couleur de fond recommandée pour le contraste
    avec_fond: bool = True  # Indique qu'un fond doit être appliqué pour meilleure visibilité
    style_recommande: dict = {}  # Styles CSS recommandés pour l'affichage


class FiltresImpayes(BaseModel):
    """Filtres pour les requêtes sur les impayés"""
    agence: Optional[str] = None
    segment: Optional[str] = None
    bucket_retard: Optional[str] = None
    statut_reglementaire: Optional[str] = None
    candidat_restructuration: Optional[bool] = None
    date_situation: Optional[str] = None
    periode_suivi: Optional[str] = None  # Nouveau filtre pour la période de suivi mensuelle


# ===================== Restructuration =====================

class ActionRestructuration(BaseModel):
    """Action sur un candidat à restructuration"""
    snapshot_id: str
    action: str  # "restructure", "refuse", "douteux"
    date_restructuration: Optional[str] = None
    commentaire: Optional[str] = None




# ===================== Archive de Situation =====================

class ArchiveSituation(BaseModel):
    """Archive d'une situation complète (snapshots + messages)"""
    archive_id: str
    organization_id: str
    periode_suivi: str
    date_situation_fin: str  # Dernière date de situation archivée
    created_by: str
    created_at: datetime
    archived_at: datetime
    
    # Statistiques au moment de l'archive
    total_snapshots: int
    total_messages: int
    montant_total_impaye: float
    total_credits: int
    
    # Résumé des crédits archivés
    credits_impayes: List[str]  # Liste des ref_credit archivés
    periodes_couvertes: List[str]  # Périodes couvertes par cette archive
    
    # Métadonnées
    commentaire: Optional[str] = None
    statut: str = "archivee"  # "archivee", "restauree", "supprimee"


class CreateArchiveRequest(BaseModel):
    """Requête pour créer une archive avec collections datées"""
    date_archive: str = Field(..., description="Date de l'archive au format YYYY-MM-DD")
    commentaire: Optional[str] = None


class ArchiveResponse(BaseModel):
    """Réponse après création d'archive"""
    success: bool
    archive_id: str
    message: str
    statistiques: dict
    credits_archives: List[str]


# ===================== Indicateurs de Performance =====================

class IndicateursRecouvrement(BaseModel):
    """Indicateurs de performance de recouvrement (calculés automatiquement en comparant les snapshots)"""
    # Taux de recouvrement global
    taux_recouvrement: float  # montant récupéré / montant impayé (en %)
    montant_total_impaye: float
    montant_total_recupere: float
    
    # Délai moyen de recouvrement
    delai_moyen_recouvrement: Optional[float]  # en jours (None si aucune régularisation détectée)
    nombre_regularisations: int  # Nombre de régularisations détectées automatiquement
    
    # Taux de réponse aux SMS
    taux_reponse_sms: float  # en %
    nombre_sms_envoyes: int
    nombre_reponses_sms: int  # Basé sur les régularisations détectées après SMS
    
    # Efficacité par tranche de retard
    efficacite_par_tranche: dict  # {tranche: {"taux_recouvrement": float, "nombre": int, "montant_impaye": float, "montant_recupere": float}}
    
    # Taux de régularisation après SMS
    taux_regularisation_apres_sms: float  # en %
    nombre_regularisations_apres_sms: int
    nombre_sms_avec_regularisation: int  # SMS suivis d'une régularisation détectée
    
    # Période analysée
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None


# ===================== Tableau de bord détaillé =====================

class RepartitionDetaillee(BaseModel):
    """Répartition détaillée avec montants et pourcentages"""
    nombre: int
    montant_total: float
    pourcentage_nombre: float
    pourcentage_montant: float
    montant_moyen: float


class TopCredit(BaseModel):
    """Top crédit impayé"""
    ref_credit: str
    nom_client: str
    montant_total_impaye: float
    jours_retard: int
    bucket_retard: str
    agence: str
    segment: str


class EvolutionTemporelle(BaseModel):
    """Évolution d'un indicateur dans le temps"""
    date_situation: str
    valeur: float
    variation: Optional[float] = None  # Variation par rapport à la période précédente


class StatistiquesSMS(BaseModel):
    """Statistiques détaillées des SMS"""
    total_envoyes: int
    total_en_attente: int
    total_echoues: int
    taux_succes: float
    montant_impaye_couvert: float  # Montant total impayé des crédits avec SMS envoyés
    nombre_credits_avec_sms: int
    nombre_credits_sans_sms: int
    repartition_par_tranche: dict  # {tranche: {"envoyes": int, "en_attente": int, "echoues": int}}


class AlerteRisque(BaseModel):
    """Alerte ou risque détecté"""
    type: str  # "critique", "attention", "info"
    titre: str
    description: str
    nombre_credits_concernes: int
    montant_concerme: float
    action_recommandee: Optional[str] = None


class DashboardDetaille(BaseModel):
    """Tableau de bord détaillé avec toutes les métriques"""
    # Informations générales
    date_situation_actuelle: Optional[str] = None
    date_situation_precedente: Optional[str] = None
    nombre_dates_disponibles: int
    
    # KPIs principaux
    kpis: dict = Field(default_factory=lambda: {
        "total_montant_impaye": 0.0,
        "total_credits": 0,
        "total_encours": 0.0,
        "montant_moyen_par_credit": 0.0,
        "ratio_impaye_encours_moyen": 0.0,
        "candidats_restructuration": 0,
        "taux_impayes": 0.0,  # Montant impayé / Encours total
    })
    
    # Évolution par rapport à la période précédente
    evolution: Optional[EvolutionStatistiques] = None
    tendance: str = "stable"  # "hausse", "baisse", "stable", "pas_de_comparaison"
    couleur_tendance: str = "neutral"  # "success" (baisse/vert), "danger" (hausse/rouge), "warning" (orange), "neutral" (gris)
    icone_tendance: str = "equal"  # "arrow-down" (baisse), "arrow-up" (hausse), "equal" (stable)
    
    # Comparaisons en parallèle (données côte à côte)
    comparaisons_paralleles: List[ComparaisonParallele] = Field(default_factory=list)
    
    # Répartitions détaillées
    repartition_tranches: dict = Field(default_factory=dict)  # {tranche: RepartitionDetaillee}
    repartition_segments: dict = Field(default_factory=dict)  # {segment: RepartitionDetaillee}
    repartition_agences: dict = Field(default_factory=dict)  # {agence: RepartitionDetaillee}
    repartition_produits: dict = Field(default_factory=dict)  # {produit: RepartitionDetaillee}
    repartition_statuts: dict = Field(default_factory=dict)  # {statut: RepartitionDetaillee}
    
    # Top crédits
    top_10_credits_par_montant: List[TopCredit] = Field(default_factory=list)
    top_10_credits_par_jours_retard: List[TopCredit] = Field(default_factory=list)
    top_10_credits_par_ratio: List[TopCredit] = Field(default_factory=list)
    
    # Évolution temporelle (dernières 12 dates)
    evolution_montant: List[EvolutionTemporelle] = Field(default_factory=list)
    evolution_nombre_credits: List[EvolutionTemporelle] = Field(default_factory=list)
    evolution_candidats_restructuration: List[EvolutionTemporelle] = Field(default_factory=list)
    
    # Indicateurs de recouvrement
    indicateurs_recouvrement: Optional[IndicateursRecouvrement] = None
    
    # Statistiques SMS
    statistiques_sms: Optional[StatistiquesSMS] = None
    
    # Analyses approfondies
    analyses: dict = Field(default_factory=lambda: {
        "credits_avec_garanties": 0,
        "montant_avec_garanties": 0.0,
        "credits_sans_garanties": 0,
        "montant_sans_garanties": 0.0,
        "credits_avec_telephone": 0,
        "credits_sans_telephone": 0,
        "duree_moyenne_retard": 0.0,
        "echeances_impayees_moyennes": 0.0,
        "taux_penalites": 0.0,  # Pénalités / Montant total impayé
        "taux_interets": 0.0,  # Intérêts / Montant total impayé
    })
    
    # Alertes et risques
    alertes: List[AlerteRisque] = Field(default_factory=list)
    
    # Concentrations (risque de concentration)
    concentrations: dict = Field(default_factory=lambda: {
        "top_5_agences": {},  # % du montant total
        "top_5_segments": {},  # % du montant total
        "top_5_produits": {},  # % du montant total
    })
    
    # Métriques de qualité des données
    qualite_donnees: dict = Field(default_factory=lambda: {
        "credits_avec_telephone": 0,
        "credits_sans_telephone": 0,
        "taux_completude_telephone": 0.0,
        "credits_avec_garanties": 0,
        "taux_completude_garanties": 0.0,
    })


# ===================== Workflow d'Escalade =====================

class NiveauEscaladeEnum(str, Enum):
    RELANCE_1 = "relance_1"
    RELANCE_2 = "relance_2"
    MISE_EN_DEMEURE = "mise_en_demeure"
    CONTENTIEUX = "contentieux"


class EscaladeNiveau(BaseModel):
    """Définition d'un niveau d'escalade"""
    niveau: NiveauEscaladeEnum
    label: str
    description: str
    jours_declenchement: int = Field(..., description="Nb jours de retard pour déclencher ce niveau")
    actions_auto: List[str] = Field(default_factory=list, description="Actions automatiques: sms, email, courrier")
    template_sms: Optional[str] = None
    template_courrier: Optional[str] = None
    couleur: str = "#6b7280"


class EscaladeNiveauConfig(BaseModel):
    """Configuration d'un niveau d'escalade personnalisable"""
    niveau: str = Field(..., description="Identifiant unique du niveau")
    label: str = Field(..., description="Libellé affiché dans l'interface")
    description: Optional[str] = Field(None, description="Description du niveau")
    jours_declenchement: int = Field(..., gt=0, description="Nombre de jours de retard pour déclencher ce niveau")
    couleur: str = Field(..., description="Couleur d'affichage (format hex)")
    actions_auto: List[str] = Field(default_factory=list, description="Actions automatiques à ce niveau")
    responsable_escalade: Optional[str] = Field(None, description="Personne ou rôle responsable à ce niveau")
    agent_id: Optional[str] = Field(None, description="ID de l'utilisateur à qui attribuer automatiquement les dossiers à ce niveau")
    agent_nom: Optional[str] = Field(None, description="Nom de l'utilisateur attribué (cache)")
    actif: bool = Field(True, description="Ce niveau est-il actif ?")

    class Config:
        json_encoders = {
            # Pour garantir la cohérence des types
        }


class EscaladeConfig(BaseModel):
    """Configuration complète du workflow d'escalade pour une organisation"""
    # Paramètres globaux
    escalade_auto: bool = Field(True, description="Activer l'escalade automatique")
    notifier_gestionnaire: bool = Field(True, description="Notifier le gestionnaire lors des escalades")
    autoriser_forcage_manuel: bool = Field(True, description="Autoriser le forçage manuel d'escalade")
    justification_forcage_obligatoire: bool = Field(True, description="Justification obligatoire si forçage manuel")
    
    # Niveaux configurables
    niveaux: List[EscaladeNiveauConfig] = Field(default_factory=lambda: [
        EscaladeNiveauConfig(
            niveau="relance_1",
            label="Première relance",
            description="Premier rappel amiable par SMS",
            jours_declenchement=7,
            couleur="#f59e0b",
            actions_auto=["sms"],
            responsable_escalade="Agent Recouvrement 1",
            actif=True
        ),
        EscaladeNiveauConfig(
            niveau="relance_2",
            label="Deuxième relance",
            description="Deuxième rappel avec avertissement",
            jours_declenchement=30,
            couleur="#f97316",
            actions_auto=["sms"],
            responsable_escalade="Agent Recouvrement 2",
            actif=True
        ),
        EscaladeNiveauConfig(
            niveau="mise_en_demeure",
            label="Mise en demeure",
            description="Notification formelle de mise en demeure",
            jours_declenchement=60,
            couleur="#ef4444",
            actions_auto=["sms", "courrier"],
            responsable_escalade="Superviseur Recouvrement",
            actif=True
        ),
        EscaladeNiveauConfig(
            niveau="contentieux",
            label="Contentieux",
            description="Transfert au service contentieux / juridique",
            jours_declenchement=90,
            couleur="#7f1d1d",
            actions_auto=["courrier"],
            responsable_escalade="Responsable Juridique",
            actif=True
        ),
    ])


class EscaladeDossier(BaseModel):
    """État d'escalade d'un dossier (crédit impayé)"""
    ref_credit: str
    nom_client: str
    niveau_actuel: NiveauEscaladeEnum
    niveau_label: str
    date_escalade: str
    jours_retard: int
    montant_impaye: float
    agence: str
    agent_attribue: Optional[str] = None
    agent_nom: Optional[str] = None
    historique_escalade: List[dict] = Field(default_factory=list)
    prochaine_escalade: Optional[str] = None
    jours_avant_prochaine: Optional[int] = None


class SmsRappelEscaladeRequest(BaseModel):
    """Requête pour envoyer un SMS de rappel depuis l'onglet escalade"""
    ref_credit: str
    nom_client: str
    telephone: str
    message: str
    niveau_actuel: Optional[str] = None


class EscaladeActionRequest(BaseModel):
    """Requête pour escalader manuellement un dossier"""
    ref_credit: str
    nouveau_niveau: str
    commentaire: Optional[str] = None


class UpdateEscaladeConfigRequest(BaseModel):
    """Requête pour mettre à jour la configuration d'escalade"""
    escalade_auto: bool = Field(True, description="Activer l'escalade automatique")
    notifier_gestionnaire: bool = Field(True, description="Notifier le gestionnaire lors des escalades")
    autoriser_forcage_manuel: bool = Field(True, description="Autoriser le forçage manuel d'escalade")
    justification_forcage_obligatoire: bool = Field(True, description="Justification obligatoire si forçage manuel")
    niveaux: List[EscaladeNiveauConfig] = Field(..., description="Liste des niveaux d'escalade")


class ValidationEscaladeConfigRequest(BaseModel):
    """Requête pour valider une configuration d'escalade avant sauvegarde"""
    config: EscaladeConfig


# ===================== Promesses de Paiement =====================

class StatutPromesseEnum(str, Enum):
    EN_ATTENTE = "en_attente"
    TENUE = "tenue"
    NON_TENUE = "non_tenue"
    ANNULEE = "annulee"


class CreatePromesseRequest(BaseModel):
    """Requête pour créer une promesse de paiement"""
    ref_credit: str
    nom_client: str
    montant_promis: float
    date_promesse: str = Field(..., description="Date à laquelle le client promet de payer (YYYY-MM-DD)")
    commentaire: Optional[str] = None


class UpdatePromesseStatutRequest(BaseModel):
    """Requête pour mettre à jour le statut d'une promesse"""
    statut: StatutPromesseEnum
    montant_recu: Optional[float] = None
    commentaire: Optional[str] = None


class PromessePaiement(BaseModel):
    """Promesse de paiement d'un client"""
    id: str
    promesse_id: str
    organization_id: str
    ref_credit: str
    nom_client: str
    montant_promis: float
    montant_recu: Optional[float] = None
    date_promesse: str
    date_creation: str
    date_echeance: Optional[str] = None
    statut: StatutPromesseEnum = StatutPromesseEnum.EN_ATTENTE
    commentaire: Optional[str] = None
    created_by: str
    updated_at: Optional[str] = None


class PromesseStats(BaseModel):
    """Statistiques des promesses de paiement"""
    total: int = 0
    en_attente: int = 0
    tenues: int = 0
    non_tenues: int = 0
    annulees: int = 0
    montant_total_promis: float = 0
    montant_total_recu: float = 0
    taux_tenue: float = 0


# ===================== Scoring de Recouvrabilité =====================

class ScoringPoidsConfig(BaseModel):
    """Pondération de chaque facteur (doit totaliser 1.0)"""
    jours_retard: float = Field(0.30, ge=0, le=1, description="Poids jours de retard (défaut 30%)")
    ratio_impaye: float = Field(0.20, ge=0, le=1, description="Poids ratio impayé/encours (défaut 20%)")
    garanties: float = Field(0.15, ge=0, le=1, description="Poids présence de garanties (défaut 15%)")
    joignabilite: float = Field(0.10, ge=0, le=1, description="Poids joignabilité client (défaut 10%)")
    historique_promesses: float = Field(0.15, ge=0, le=1, description="Poids historique promesses tenues (défaut 15%)")
    echeances_impayees: float = Field(0.10, ge=0, le=1, description="Poids nombre d'échéances impayées (défaut 10%)")


class ScoringSeuilsJoursRetard(BaseModel):
    """Paliers en jours → score attribué (100 = excellent)"""
    palier_1_jours: int = Field(15, description="Seuil 1 (≤ X jours → score très bon)")
    palier_1_score: int = Field(90, ge=0, le=100)
    palier_2_jours: int = Field(30, description="Seuil 2")
    palier_2_score: int = Field(75, ge=0, le=100)
    palier_3_jours: int = Field(60, description="Seuil 3")
    palier_3_score: int = Field(50, ge=0, le=100)
    palier_4_jours: int = Field(90, description="Seuil 4")
    palier_4_score: int = Field(30, ge=0, le=100)
    palier_5_jours: int = Field(180, description="Seuil 5")
    palier_5_score: int = Field(15, ge=0, le=100)
    palier_6_score: int = Field(5, ge=0, le=100, description="Score si > seuil 5")


class ScoringSeuilsRatioImpaye(BaseModel):
    """Paliers ratio impayé/encours (%) → score"""
    palier_1_pct: int = Field(10, description="≤ X% → très bon")
    palier_1_score: int = Field(90, ge=0, le=100)
    palier_2_pct: int = Field(25)
    palier_2_score: int = Field(70, ge=0, le=100)
    palier_3_pct: int = Field(50)
    palier_3_score: int = Field(45, ge=0, le=100)
    palier_4_pct: int = Field(75)
    palier_4_score: int = Field(20, ge=0, le=100)
    palier_5_score: int = Field(5, ge=0, le=100, description="Score si > seuil 4")


class ScoringSeuilsEcheances(BaseModel):
    """Paliers nombre d'échéances impayées → score"""
    palier_1_nb: int = Field(1, description="≤ X échéances → très bon")
    palier_1_score: int = Field(90, ge=0, le=100)
    palier_2_nb: int = Field(3)
    palier_2_score: int = Field(65, ge=0, le=100)
    palier_3_nb: int = Field(6)
    palier_3_score: int = Field(35, ge=0, le=100)
    palier_4_score: int = Field(10, ge=0, le=100, description="Score si > seuil 3")


class ScoringScoresGaranties(BaseModel):
    """Scores attribués selon présence de garanties"""
    avec_garantie: int = Field(80, ge=0, le=100, description="Score si garantie présente")
    sans_garantie: int = Field(20, ge=0, le=100, description="Score si aucune garantie")


class ScoringScoresJoignabilite(BaseModel):
    """Scores attribués selon joignabilité"""
    avec_telephone: int = Field(80, ge=0, le=100, description="Score si téléphone renseigné")
    sans_telephone: int = Field(20, ge=0, le=100, description="Score si aucun téléphone")


class ScoringSeuilsNiveaux(BaseModel):
    """Seuils de score → niveau de risque"""
    faible: int = Field(70, ge=0, le=100, description="Score ≥ X → risque faible")
    moyen: int = Field(50, ge=0, le=100, description="Score ≥ X → risque moyen")
    eleve: int = Field(30, ge=0, le=100, description="Score ≥ X → risque élevé (en dessous = critique)")
    recommandation_faible: str = Field("Relance amiable par SMS, forte probabilité de régularisation")
    recommandation_moyen: str = Field("Relance téléphonique recommandée, négocier un échéancier")
    recommandation_eleve: str = Field("Mise en demeure à envisager, visite terrain si possible")
    recommandation_critique: str = Field("Risque de perte élevé, envisager contentieux ou passage en perte")


class ScoringConfig(BaseModel):
    """Configuration complète du moteur de scoring de recouvrabilité"""
    poids: ScoringPoidsConfig = Field(default_factory=ScoringPoidsConfig)
    seuils_jours_retard: ScoringSeuilsJoursRetard = Field(default_factory=ScoringSeuilsJoursRetard)
    seuils_ratio_impaye: ScoringSeuilsRatioImpaye = Field(default_factory=ScoringSeuilsRatioImpaye)
    seuils_echeances: ScoringSeuilsEcheances = Field(default_factory=ScoringSeuilsEcheances)
    scores_garanties: ScoringScoresGaranties = Field(default_factory=ScoringScoresGaranties)
    scores_joignabilite: ScoringScoresJoignabilite = Field(default_factory=ScoringScoresJoignabilite)
    seuils_niveaux: ScoringSeuilsNiveaux = Field(default_factory=ScoringSeuilsNiveaux)


class UpdateScoringConfigRequest(BaseModel):
    config: ScoringConfig


class ScoreRecouvrabilite(BaseModel):
    """Score de probabilité de recouvrement d'un dossier"""
    ref_credit: str
    nom_client: str
    score: float = Field(..., ge=0, le=100, description="Score de 0 à 100")
    niveau_risque: str  # "faible", "moyen", "eleve", "critique"
    couleur: str
    facteurs: Dict[str, float] = Field(default_factory=dict, description="Détail des facteurs du score")
    recommandation: str
    montant_impaye: float
    jours_retard: int
    agence: str


# ===================== Attribution Portefeuille Agent =====================

class AttributionAgentRequest(BaseModel):
    """Requête pour attribuer des crédits à un agent"""
    agent_id: str
    agent_nom: str
    ref_credits: List[str]
    department_id: Optional[str] = None
    service_id: Optional[str] = None


class PortefeuilleAgent(BaseModel):
    """Portefeuille d'un agent de recouvrement"""
    agent_id: str
    agent_nom: str
    nombre_dossiers: int = 0
    montant_total: float = 0
    dossiers: List[dict] = Field(default_factory=list)
    taux_recouvrement: float = 0
    promesses_en_cours: int = 0


class AgentPerformance(BaseModel):
    """Performance d'un agent de recouvrement"""
    agent_id: str
    agent_nom: str
    nombre_dossiers: int = 0
    montant_attribue: float = 0
    montant_recouvre: float = 0
    taux_recouvrement: float = 0
    promesses_tenues: int = 0
    promesses_non_tenues: int = 0
    actions_realisees: int = 0


# ===================== Journal d'Activité =====================

class TypeActionJournalEnum(str, Enum):
    APPEL = "appel"
    SMS_ENVOYE = "sms_envoye"
    VISITE = "visite"
    COURRIER = "courrier"
    PROMESSE = "promesse"
    PAIEMENT = "paiement"
    ESCALADE = "escalade"
    NOTE = "note"
    ATTRIBUTION = "attribution"
    RESTRUCTURATION = "restructuration"
    COMMENTAIRE = "commentaire"


class CreateActionJournalRequest(BaseModel):
    """Requête pour créer une entrée de journal"""
    ref_credit: str
    type_action: TypeActionJournalEnum
    description: str
    montant: Optional[float] = None
    resultat: Optional[str] = None


class ActionJournal(BaseModel):
    """Entrée du journal d'activité d'un dossier"""
    id: str
    action_id: str
    organization_id: str
    ref_credit: str
    nom_client: Optional[str] = None
    type_action: str
    description: str
    montant: Optional[float] = None
    resultat: Optional[str] = None
    created_by: str
    created_by_nom: Optional[str] = None
    created_at: str


# ===================== Dashboard Agence =====================

class AgenceRanking(BaseModel):
    """Ranking d'une agence"""
    agence: str
    rang: int
    total_credits: int = 0
    montant_total_impaye: float = 0
    montant_recouvre: float = 0
    taux_recouvrement: float = 0
    promesses_tenues: int = 0
    promesses_non_tenues: int = 0
    score_performance: float = 0
    evolution: Optional[str] = None  # "hausse", "baisse", "stable"


class DashboardAgence(BaseModel):
    """Dashboard par agence"""
    agence: str
    total_credits: int = 0
    montant_total_impaye: float = 0
    repartition_tranches: Dict[str, int] = Field(default_factory=dict)
    repartition_niveaux_escalade: Dict[str, int] = Field(default_factory=dict)
    agents: List[AgentPerformance] = Field(default_factory=list)
    promesses_stats: Optional[PromesseStats] = None
    evolution_montant: List[dict] = Field(default_factory=list)

