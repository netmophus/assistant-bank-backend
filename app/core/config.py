import os
import sys
from dotenv import load_dotenv

# Charge les variables du fichier .env
load_dotenv()


class Settings:
    PROJECT_NAME: str = "Assistant Banque Backend"
    PROJECT_VERSION: str = "0.1.0"

    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "assistant_banque_db")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

    def __init__(self):
        if not self.JWT_SECRET or self.JWT_SECRET in ("CHANGE_ME", "change_ceci_par_une_chaine_longue_et_secrete"):
            print("[SECURITY ERROR] JWT_SECRET n'est pas défini ou utilise la valeur par défaut. Arrêt du serveur.", file=sys.stderr)
            sys.exit(1)
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Anthropic Configuration (utilisé par pcb_ai_service pour l'analyse PCB)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    
    # Limites d'utilisation IA par défaut
    AI_DAILY_LIMIT_PER_ORG: int = int(os.getenv("AI_DAILY_LIMIT_PER_ORG", "50"))
    
    # Configuration L'Africa Mobile SMS (https://developers.lafricamobile.com)
    LAM_ACCOUNT_ID: str = os.getenv("LAM_ACCOUNT_ID", "")
    LAM_PASSWORD: str = os.getenv("LAM_PASSWORD", "")
    LAM_SENDER: str = os.getenv("LAM_SENDER", "SOFTLINK")

    # Email de notification pour nouvelles demandes d'abonnement.
    # Si vide, fallback sur SMTP_USER (l'admin lui-meme).
    SUBSCRIPTION_NOTIFY_EMAIL: str = os.getenv(
        "SUBSCRIPTION_NOTIFY_EMAIL",
        os.getenv("SMTP_USER", ""),
    )


settings = Settings()
