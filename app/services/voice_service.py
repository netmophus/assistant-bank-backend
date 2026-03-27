"""
Service pour la gestion des sessions vocales avec OpenAI Realtime API.
"""
import json
import asyncio
from datetime import datetime
from typing import Dict, Any
from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.voice_chat import VoiceSessionRequest, VoiceSessionResponse


class VoiceService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.active_sessions: Dict[str, Dict] = {}
    
    def build_dossier_context(self, request: VoiceSessionRequest) -> str:
        """Construit le contexte du dossier de crédit pour l'agent vocal."""
        dossier_context = f"""
DOSSIER DE CRÉDIT PARTICULIER - CONTEXTE POUR DISCUSSION VOCALE:

INFORMATIONS CLIENT:
- Nom: {request.request_data.get('clientName', 'Non renseigné')}
- Statut professionnel: {request.request_data.get('employmentStatus', 'Non renseigné')}
- Employeur: {request.request_data.get('employerName', 'Non renseigné')}
- Secteur: {request.request_data.get('employerSector', 'Non renseigné')}
- Contrat: {request.request_data.get('contractType', 'Non renseigné')}
- Poste: {request.request_data.get('position', 'Non renseigné')}

SITUATION FINANCIÈRE:
- Salaire net mensuel: {request.request_data.get('netMonthlySalary', 0)} XOF
- Autres revenus: {request.request_data.get('otherMonthlyIncome', 0)} XOF
- Revenu total mensuel: {request.calculated_metrics.get('totalMonthlyIncome', 0)} XOF
- Charges mensuelles actuelles: {request.calculated_metrics.get('totalMonthlyCharges', 0)} XOF
- Nouveau taux d'endettement: {request.calculated_metrics.get('newDebtToIncomeRatio', 0)}%
- Reste à vivre: {request.calculated_metrics.get('resteAVivre', 0)} XOF

CRÉDIT DEMANDÉ:
- Montant: {request.request_data.get('loanAmount', 0)} XOF
- Durée: {request.request_data.get('loanDurationMonths', 0)} mois
- Type: {request.request_data.get('loanType', 'Non renseigné')}
- Mensualité: {request.calculated_metrics.get('newLoanMonthlyPayment', 0)} XOF
- Taux d'intérêt: {request.calculated_metrics.get('annualInterestRate', 'N/A')}%

ANALYSE PRÉCÉDENTE:
- Décision: {request.ai_decision or 'Non disponible'}
- Analyse: {request.ai_analysis or 'Non disponible'}

INSTRUCTIONS POUR L'AGENT VOCAL:
- Tu es un expert-conseil bancaire spécialisé en crédit particulier
- Tu parles français de manière naturelle et professionnelle
- Tu te bases exclusivement sur les chiffres et informations fournis
- Tu es pédagogue et précis dans tes explications
- Tu n'utilises jamais de markdown ni de formatage spécial
- Tu adaptes ton ton au contexte (approbation, refus, ou conditionnel)
- Tu peux poser des questions pour clarifier la situation si nécessaire
"""
        return dossier_context
    
    def build_system_prompt(self) -> str:
        """Construit le prompt système pour l'agent vocal."""
        return """Tu es un expert-conseil bancaire spécialisé dans l'analyse et l'octroi de crédits particuliers. 

Ton rôle est d'assister le client dans la compréhension de son dossier de crédit, en te basant exclusivement sur les informations financières et les métriques fournies.

Directives importantes:
- Parle français de manière naturelle, professionnelle et accessible
- Explique les concepts financiers complexes de façon simple
- Base toutes tes réponses sur les chiffres réels du dossier
- Sois empathique mais objectif dans tes conseils
- N'invente aucune information non présente dans le dossier
- Pose des questions pertinentes si tu as besoin de clarifications
- Adapte ton discours selon la décision (APPROUVÉ/REFUSÉ/CONDITIONNEL)
- Ne mentionne jamais que tu es une IA

Ton expertise couvre:
- Analyse de la capacité de remboursement
- Compréhension du taux d'endettement
- Explication du reste à vivre
- Justification des décisions de crédit
- Conseils sur la gestion financière

Sois concis mais complet dans tes réponses vocales."""
    
    async def create_realtime_session(self, request: VoiceSessionRequest) -> VoiceSessionResponse:
        """
        Crée une session OpenAI Realtime API pour la discussion vocale.
        
        Args:
            request: Données du dossier de crédit
            
        Returns:
            VoiceSessionResponse: Informations pour la connexion WebSocket
        """
        try:
            # Construire le contexte du dossier
            dossier_context = self.build_dossier_context(request)
            system_prompt = self.build_system_prompt()
            
            # Générer un ID de session unique
            session_id = f"voice_session_{datetime.utcnow().timestamp()}"
            
            # Stocker la session active avec toutes les données
            session_info = {
                "session_id": session_id,
                "created_at": datetime.utcnow(),
                "request_data": request.request_data,
                "calculated_metrics": request.calculated_metrics,
                "ai_decision": request.ai_decision,
                "ai_analysis": request.ai_analysis,
                "dossier_context": dossier_context,
                "system_prompt": system_prompt,
                "status": "active"
            }
            self.active_sessions[session_id] = session_info
            
            # Pour l'implémentation WebSocket directe, nous n'avons pas besoin de clé éphémère
            # Le frontend se connectera directement avec la clé API du backend
            return VoiceSessionResponse(
                session_id=session_id,
                client_secret="",  # Pas utilisé pour WebSocket direct
                ephemeral_key=settings.OPENAI_API_KEY,  # Clé API pour le frontend
                websocket_url="wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
                system_prompt=system_prompt,
                dossier_context=dossier_context
            )
            
        except Exception as e:
            raise Exception(f"Erreur lors de la création de la session vocale: {str(e)}")
    
    async def end_session(self, session_id: str) -> bool:
        """
        Termine une session vocale active.
        
        Args:
            session_id: ID de la session à terminer
            
        Returns:
            bool: True si la session a été terminée avec succès
        """
        try:
            if session_id in self.active_sessions:
                # Marquer la session comme terminée
                self.active_sessions[session_id]["status"] = "ended"
                self.active_sessions[session_id]["ended_at"] = datetime.utcnow()
                
                # Nettoyer la session (optionnel, peut être gardée pour l'historique)
                del self.active_sessions[session_id]
                
                return True
            return False
            
        except Exception as e:
            raise Exception(f"Erreur lors de la terminaison de la session: {str(e)}")
    
    async def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Récupère le statut d'une session vocale.
        
        Args:
            session_id: ID de la session
            
        Returns:
            Dict: Informations sur la session
        """
        if session_id in self.active_sessions:
            session_info = self.active_sessions[session_id].copy()
            return {
                "session_id": session_id,
                "status": session_info["status"],
                "created_at": session_info["created_at"],
                "duration_seconds": (datetime.utcnow() - session_info["created_at"]).total_seconds() if session_info["status"] == "active" else None
            }
        else:
            return {"session_id": session_id, "status": "not_found"}


# Instance globale du service
voice_service = VoiceService()
