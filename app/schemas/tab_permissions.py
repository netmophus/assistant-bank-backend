from typing import Optional, List, Literal
from pydantic import BaseModel, Field, model_validator


class TabPermissionRule(BaseModel):
    """Règle de permission pour un onglet"""
    rule_type: Optional[Literal["SEGMENT", "USER"]] = Field(
        None, 
        description="Type de règle: SEGMENT (par département/service/rôle) ou USER (par utilisateur spécifique). None = SEGMENT par défaut (rétrocompatibilité)"
    )
    department_id: Optional[str] = Field(None, description="ID du département (None = tous les départements). Utilisé uniquement si rule_type=SEGMENT")
    service_id: Optional[str] = Field(None, description="ID du service (None = tous les services du département). Utilisé uniquement si rule_type=SEGMENT")
    role_departement: Optional[str] = Field(None, description="Rôle dans le département (None = tous les rôles). Utilisé uniquement si rule_type=SEGMENT")
    user_id: Optional[str] = Field(None, description="ID de l'utilisateur spécifique. Utilisé uniquement si rule_type=USER")
    
    @model_validator(mode='after')
    def validate_rule_exclusivity(self):
        """Valider que les règles sont exclusives selon le type"""
        rule_type = self.rule_type or 'SEGMENT'  # Par défaut SEGMENT si non défini
        
        if rule_type == "USER":
            # Pour USER : si user_id est défini, les autres doivent être None
            # (on permet user_id=None pendant la création progressive)
            if self.user_id:
                if self.department_id or self.service_id or self.role_departement:
                    # Nettoyer les champs SEGMENT si user_id est défini
                    self.department_id = None
                    self.service_id = None
                    self.role_departement = None
        
        elif rule_type == "SEGMENT":
            # Pour SEGMENT : user_id doit être None
            if self.user_id:
                self.user_id = None  # Nettoyer user_id si SEGMENT
        
        return self


class TabPermissionsConfig(BaseModel):
    """Configuration des permissions pour un onglet"""
    tab_id: str = Field(..., description="ID de l'onglet (questions, formations, dashboard, etc.)")
    enabled: bool = Field(default=True, description="L'onglet est-il activé par défaut?")
    rules: List[TabPermissionRule] = Field(default_factory=list, description="Règles spécifiques de permission")


class OrganizationTabPermissions(BaseModel):
    """Permissions des onglets pour une organisation"""
    organization_id: str
    tabs: List[TabPermissionsConfig] = Field(default_factory=list)


class TabPermissionsConfigUpdate(BaseModel):
    """Mise à jour des permissions d'un onglet"""
    enabled: Optional[bool] = None
    rules: Optional[List[TabPermissionRule]] = None


class UserTabPermissions(BaseModel):
    """Permissions d'onglets pour un utilisateur"""
    allowed_tabs: List[str] = Field(default_factory=list, description="Liste des IDs d'onglets autorisés")

