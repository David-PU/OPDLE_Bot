import logging

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
client = None
db = None
personajes = None
usuarios = None

def init_db(uri: str, db_name: str):
    """Inicializa la conexión asíncrona a MongoDB Atlas."""
    global client, db, personajes, usuarios
    try:
        # 1. Usar AsyncIOMotorClient
        client = AsyncIOMotorClient(uri)
        db = client[db_name]
        personajes = db["personajes"]
        usuarios = db["usuarios"]

        # Opcional: Probar la conexión al arrancar el bot
        client.admin.command('ping')
        logger.info("Conexión a MongoDB Atlas (asíncrono) establecida con éxito.")

        # Devolvemos la base de datos para usarla en los handlers
        return db

    except Exception as e:
        logger.critical(f"❌ FALLO CRÍTICO AL CONECTAR CON MONGODB: {e}")
        # En un bot, es mejor dejar que el código siga si la DB falla,
        # pero con un log CRITICAL.
        return None

def close_connection():
    client.close()

def buscar_personajes_por_nombre(query, limit=10):
    if not query:
        return []

    resultados = personajes.find(
        {"Name": {"$regex": query, "$options": "i"}},
        {"Name": 1, "_id": 0}
    ).limit(limit)

    return [doc['Name'] for doc in resultados]