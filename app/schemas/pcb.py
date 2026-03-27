"""
Schémas Pydantic pour le système PCB UEMOA
"""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ========== COMPTES GL ==========

class GLCodeMapping(BaseModel):
    """Mapping d'un code GL avec son signe et sa base de calcul"""
    code: str = Field(..., description="Code GL ou pattern (ex: 411*, Classe 4, 4111-4119)")
    signe: str = Field(..., description="Signe: + ou -")
    basis: Literal["NET", "DEBIT", "CREDIT"] = Field("NET", description="Base de calcul: NET (Crédit-Débit), DEBIT (Débit brut), CREDIT (Crédit brut)")
    
    @field_validator('signe')
    @classmethod
    def validate_signe(cls, v):
        """Valide que le signe est + ou -"""
        if v not in ['+', '-']:
            raise ValueError("Le signe doit être '+' ou '-'")
        return v
    
    @field_validator('basis')
    @classmethod
    def validate_basis(cls, v):
        """Valide que basis est NET, DEBIT ou CREDIT"""
        if v not in ['NET', 'DEBIT', 'CREDIT']:
            raise ValueError("La base doit être 'NET', 'DEBIT' ou 'CREDIT'")
        return v


class GLCreate(BaseModel):
    """Schéma pour créer/mettre à jour un compte GL"""
    code: str = Field(..., description="Code GL selon PCB UEMOA")
    libelle: str = Field(..., description="Libellé du compte")
    classe: int = Field(..., description="Classe PCB UEMOA: 1-7 (bilan) ou 9 (hors bilan). La classe 8 n'existe pas.")
    sous_classe: Optional[str] = Field(None, description="Sous-classe ou groupe")
    type: Optional[str] = Field(None, description="actif, passif, charge, produit")
    nature: Optional[str] = Field("compte_detail", description="compte_synthese ou compte_detail")
    solde_debit: Optional[float] = Field(0, description="Montant débiteur")
    solde_credit: Optional[float] = Field(0, description="Montant créditeur")
    solde_net: Optional[float] = Field(None, description="Solde net (prioritaire si fourni)")
    date_solde: datetime = Field(..., description="Date de clôture du solde")
    devise: Optional[str] = Field("XOF", description="Devise")
    is_active: Optional[bool] = Field(True, description="Compte actif")
    
    @field_validator('classe')
    @classmethod
    def validate_classe(cls, v):
        """Valide que la classe est 1-7 ou 9 (pas 8)"""
        valid_classes = [1, 2, 3, 4, 5, 6, 7, 9]
        if v not in valid_classes:
            raise ValueError(f"Classe invalide: {v}. Les classes valides sont 1-7 (bilan) et 9 (hors bilan). La classe 8 n'existe pas dans le PCB UEMOA.")
        return v


class GLPublic(BaseModel):
    """Schéma public pour un compte GL"""
    id: str
    code: str
    libelle: str
    classe: Optional[int]
    sous_classe: Optional[str]
    type: Optional[str]
    nature: Optional[str]
    organization_id: Optional[str]
    solde: float
    solde_debit: float
    solde_credit: float
    date_solde: Optional[datetime]
    devise: str
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# ========== VALEURS POSTE PAR EXERCICE (N-1 / BUDGET) ==========

class PosteExerciceValueUpsert(BaseModel):
    """Payload pour créer/mettre à jour N-1 et Budget d'un poste sur un exercice"""
    n_1: Optional[float] = Field(None, description="Valeur N-1 (saisie manuelle)")
    budget: Optional[float] = Field(None, description="Valeur Budget (saisie manuelle)")


class PosteExerciceValuePublic(BaseModel):
    """Schéma public pour une valeur N-1/Budget par poste/exercice"""
    id: str
    organization_id: Optional[str]
    poste_id: str
    exercice: str
    n_1: Optional[float] = None
    budget: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ========== CATALOGUE VARIABLES RATIOS (PAR ORGANISATION) + VALEURS PAR DATE ==========


class RatioVariableCatalogBase(BaseModel):
    key: str = Field(..., description="Code variable unique dans l'organisation (ex: FONDS_PROPRES, ACTIF_PONDERE)")
    label: str = Field(..., description="Libellé")
    unit: str = Field("", description="Unité (XOF, %, etc.)")
    description: Optional[str] = Field(None, description="Description")
    is_active: bool = Field(True, description="Variable active")


class RatioVariableCatalogCreate(RatioVariableCatalogBase):
    pass


class RatioVariableCatalogUpdate(BaseModel):
    key: Optional[str] = None
    label: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class RatioVariableCatalogPublic(RatioVariableCatalogBase):
    id: str
    organization_id: Optional[str]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RatioVariableValueUpsert(BaseModel):
    key: str = Field(..., description="Code variable")
    value: float = Field(..., description="Valeur numérique")


class RatioVariableValuePublic(BaseModel):
    id: str
    organization_id: Optional[str]
    date_solde: Optional[datetime] = None
    key: str
    value: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ========== POSTES RÉGLEMENTAIRES ==========

class PosteReglementaireCreate(BaseModel):
    """Schéma pour créer un poste réglementaire"""
    code: str = Field(..., description="Code du poste (ex: ACTIF_001, I.A.1)")
    libelle: str = Field(..., description="Libellé du poste")
    type: str = Field(..., description="bilan_actif, bilan_passif, hors_bilan, cr_produit, cr_exploitation, cr_charge")
    niveau: Optional[int] = Field(1, description="Niveau hiérarchique")
    parent_id: Optional[str] = Field(None, description="ID du poste parent")
    parent_code: Optional[str] = Field(None, description="Code du poste parent")
    contribution_signe: Optional[Literal["+", "-"]] = Field("+", description="Signe de contribution au parent: + ou -")
    ordre: Optional[int] = Field(0, description="Ordre d'affichage")
    gl_codes: Optional[List[GLCodeMapping]] = Field([], description="Liste des GL associés")
    calculation_mode: Optional[Literal["gl", "parents_formula"]] = Field("gl", description="Mode de calcul: gl ou parents_formula")
    parents_formula: Optional[List[dict]] = Field([], description="Formule +, -, *, / basée sur d'autres postes parents (niveau 1)")
    formule: Optional[str] = Field("somme", description="Type de formule: somme, difference, ratio, custom")
    formule_custom: Optional[str] = Field(None, description="Formule personnalisée")
    is_active: Optional[bool] = Field(True, description="Poste actif")


class PosteReglementaireUpdate(BaseModel):
    """Schéma pour mettre à jour un poste réglementaire"""
    code: Optional[str] = None
    libelle: Optional[str] = None
    type: Optional[str] = None
    niveau: Optional[int] = None
    parent_id: Optional[str] = None
    parent_code: Optional[str] = None
    contribution_signe: Optional[Literal["+", "-"]] = None
    ordre: Optional[int] = None
    gl_codes: Optional[List[GLCodeMapping]] = None
    calculation_mode: Optional[Literal["gl", "parents_formula"]] = None
    parents_formula: Optional[List[dict]] = None
    formule: Optional[str] = None
    formule_custom: Optional[str] = None
    is_active: Optional[bool] = None


class PosteReglementairePublic(BaseModel):
    """Schéma public pour un poste réglementaire"""
    id: str
    code: str
    libelle: str
    type: str
    niveau: int
    parent_id: Optional[str]
    parent_code: Optional[str]
    contribution_signe: Optional[str] = None
    organization_id: Optional[str]
    ordre: int
    gl_codes: List[GLCodeMapping]
    calculation_mode: Optional[str] = None
    parents_formula: Optional[List[dict]] = None
    formule: Optional[str]
    formule_custom: Optional[str]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


# ========== RAPPORTS ==========

class PosteCalcul(BaseModel):
    """Poste avec son solde calculé"""
    code: str
    libelle: str
    solde: float = Field(..., description="Solde affiché (toujours positif) - compatibilité")
    solde_brut: Optional[float] = Field(None, description="Solde brut (peut être négatif)")
    solde_affiche: Optional[float] = Field(None, description="Solde affiché (toujours positif)")
    warning_signe: Optional[bool] = Field(None, description="True si solde_brut < 0")
    gl_details: Optional[List[dict]] = Field(None, description="Détails des GL contribuant au solde")
    niveau: Optional[int] = Field(None, description="Niveau hiérarchique")
    parent_id: Optional[str] = Field(None, description="ID du poste parent")
    source: Optional[str] = Field(None, description="Source du calcul: gl_codes, somme_enfants, etc.")


class StructureRapport(BaseModel):
    """Structure d'un rapport (postes et totaux)"""
    postes: List[PosteCalcul]
    totaux: dict = Field({}, description="Totaux par catégorie")


class RatiosBancaires(BaseModel):
    """Ratios bancaires calculés"""
    ratio_solvabilite: Optional[float] = None
    ratio_liquidite: Optional[float] = None
    ratio_couverture_risque: Optional[float] = None
    ratio_endettement: Optional[float] = None
    roe: Optional[float] = None  # Return on Equity
    roa: Optional[float] = None  # Return on Assets
    marge_nette: Optional[float] = None
    ratio_efficacite: Optional[float] = None


class ReportCreate(BaseModel):
    """Schéma pour créer un rapport"""
    type: str = Field(..., description="bilan_reglementaire, hors_bilan, compte_resultat")
    section: Optional[str] = Field(None, description="Optionnel: actif/passif pour bilan, produits/charges pour compte de résultat")
    exercice: Optional[str] = Field(None, description="Exercice comptable")
    date_cloture: datetime = Field(..., description="Date de clôture")
    date_realisation: Optional[datetime] = Field(None, description="Date de réalisation de référence (comparaison)")
    date_debut: Optional[datetime] = Field(None, description="Date de début pour comparaison")
    modele_id: Optional[str] = Field(None, description="ID du modèle utilisé")
    structure: Optional[StructureRapport] = None
    ratios_bancaires: Optional[RatiosBancaires] = None
    interpretation_ia: Optional[str] = None
    statut: Optional[str] = Field("generated", description="generated, validated, error")


class ReportPublic(BaseModel):
    """Schéma public pour un rapport"""
    id: str
    organization_id: Optional[str]
    type: str
    section: Optional[str] = None
    exercice: Optional[str]
    date_cloture: Optional[datetime]
    date_realisation: Optional[datetime] = None
    date_debut: Optional[datetime]
    date_generation: Optional[datetime]
    modele_id: Optional[str]
    structure: Optional[dict]
    ratios_bancaires: Optional[dict]
    interpretation_ia: Optional[str]
    statut: str
    created_at: Optional[datetime]
    created_by: Optional[str]


# ========== IMPORT ==========

class GLImportResult(BaseModel):
    """Résultat d'un import de comptes GL"""
    total_lignes: int
    comptes_crees: int
    comptes_mis_a_jour: int
    erreurs: List[dict] = Field([], description="Liste des erreurs rencontrées")


class GLImportRequest(BaseModel):
    """Requête d'import de comptes GL"""
    date_solde: datetime = Field(..., description="Date de clôture des soldes")
    organization_id: str = Field(..., description="ID de l'organisation")

