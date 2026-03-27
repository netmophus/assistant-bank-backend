from typing import Optional
from pydantic import BaseModel, Field


class PMEFieldConfig(BaseModel):
    """Configuration d'un champ pour le crédit PME"""
    enabled: bool = Field(default=True, description="Le champ est activé")
    required: bool = Field(default=False, description="Le champ est obligatoire")


class CreditPMEFieldConfig(BaseModel):
    """Configuration complète des champs pour le crédit PME"""
    # Profil entreprise
    raison_sociale: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    secteur_activite: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    taille: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    nombre_employes: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))
    annee_creation: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    forme_juridique: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    positionnement: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))
    
    # Données financières
    donnees_financieres: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    
    # Crédit demandé
    montant: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    objet: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    duree_mois: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    type_remboursement: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    garanties: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))
    valeur_garanties: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))
    source_remboursement: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=True))
    
    # Contexte risque
    concentration_clients: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))
    dependance_fournisseur: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))
    historique_incidents: PMEFieldConfig = Field(default_factory=lambda: PMEFieldConfig(enabled=True, required=False))


class CreditPMEConfigPublic(BaseModel):
    """Configuration publique du crédit PME"""
    id: str
    organization_id: str
    field_config: CreditPMEFieldConfig
    created_at: str
    updated_at: str

