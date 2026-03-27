"""
Schémas pour l'archivage des données d'impayés
"""
from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field


class ArchiveMetadata(BaseModel):
    """Métadonnées d'une archive"""
    archive_id: str = Field(..., description="Identifiant unique de l'archive")
    organization_id: str = Field(..., description="ID de l'organisation")
    archived_by: str = Field(..., description="ID de l'utilisateur qui a créé l'archive")
    archived_at: datetime = Field(default_factory=datetime.utcnow, description="Date de création de l'archive")
    archive_name: Optional[str] = Field(None, description="Nom descriptif de l'archive")
    archive_description: Optional[str] = Field(None, description="Description de l'archive")
    
    # Statistiques de l'archive
    total_snapshots: int = Field(0, description="Nombre total de snapshots archivés")
    total_messages: int = Field(0, description="Nombre total de messages archivés")
    total_sms_history: int = Field(0, description="Nombre total d'entrées dans l'historique SMS")
    
    # Dates de situation couvertes
    date_situation_debut: Optional[str] = Field(None, description="Première date de situation")
    date_situation_fin: Optional[str] = Field(None, description="Dernière date de situation")
    dates_situation: List[str] = Field(default_factory=list, description="Liste de toutes les dates de situation")
    
    # Statistiques agrégées
    montant_total_impaye: float = Field(0.0, description="Montant total impayé dans l'archive")
    nombre_total_credits: int = Field(0, description="Nombre total de crédits")
    candidats_restructuration: int = Field(0, description="Nombre de candidats à restructuration")
    
    # Métadonnées supplémentaires
    metadata: Optional[Dict] = Field(default_factory=dict, description="Métadonnées supplémentaires")


class ArchiveCreate(BaseModel):
    """Schéma pour créer une archive"""
    archive_name: Optional[str] = Field(None, description="Nom descriptif de l'archive")
    archive_description: Optional[str] = Field(None, description="Description de l'archive")
    include_snapshots: bool = Field(True, description="Inclure les snapshots dans l'archive")
    include_messages: bool = Field(True, description="Inclure les messages dans l'archive")
    include_sms_history: bool = Field(True, description="Inclure l'historique SMS dans l'archive")


class ArchivePublic(BaseModel):
    """Schéma public pour une archive"""
    archive_id: str
    organization_id: str
    archived_by: str
    archived_at: str
    archive_name: Optional[str]
    archive_description: Optional[str]
    total_snapshots: int
    total_messages: int
    total_sms_history: int
    date_situation_debut: Optional[str]
    date_situation_fin: Optional[str]
    dates_situation: List[str]
    montant_total_impaye: float
    nombre_total_credits: int
    candidats_restructuration: int
    metadata: Dict


class ArchiveRestoreRequest(BaseModel):
    """Schéma pour restaurer une archive"""
    archive_id: str = Field(..., description="ID de l'archive à restaurer")
    restore_snapshots: bool = Field(True, description="Restaurer les snapshots")
    restore_messages: bool = Field(True, description="Restaurer les messages")
    restore_sms_history: bool = Field(True, description="Restaurer l'historique SMS")
    clear_existing: bool = Field(False, description="Vider les données existantes avant restauration")


