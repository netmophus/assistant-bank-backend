import os
from dotenv import load_dotenv

# Charge les variables du fichier .env
load_dotenv()


class Settings:
    PROJECT_NAME: str = "Assistant Banque Backend"
    PROJECT_VERSION: str = "0.1.0"

    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "assistant_banque_db")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "CHANGE_ME")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Limites d'utilisation IA par défaut
    AI_DAILY_LIMIT_PER_ORG: int = int(os.getenv("AI_DAILY_LIMIT_PER_ORG", "50"))


settings = Settings()
