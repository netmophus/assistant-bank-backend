from typing import Optional



from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase



from .config import settings



_client: Optional[AsyncIOMotorClient] = None





def get_client() -> AsyncIOMotorClient:

    """

    Retourne le client MongoDB global.

    """

    global _client

    if _client is None:
        _client = AsyncIOMotorClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=10000,
            socketTimeoutMS=45000,
        )

    return _client





def get_database() -> AsyncIOMotorDatabase:

    """

    Retourne la base de données MongoDB à utiliser.

    """

    client = get_client()

    return client[settings.MONGO_DB_NAME]

