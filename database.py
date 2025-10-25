import logging

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)

client = None
db = None
personajes = None
usuarios = None

def init_db(uri: str, db_name: str):
    global client, db, personajes, usuarios

    logger.info(f"DEBUG: Intentando conectar a URI: {uri}")
    # Usar el cliente ASÍNCRONO
    client = AsyncIOMotorClient(uri, server_api=ServerApi('1'))
    db = client[db_name]

    # Asignar las colecciones a las variables globales
    personajes = db["personajes"]
    usuarios = db["usuarios"]

    if personajes is None or usuarios is None:
        print("personajes o usuarios NONE DB")
    else:
        print("personajes y usuarios INCIADOS DB")

    return db

async def verify_db_connection():
    global client, db, personajes, usuarios

    if client is None:
        return False

    try:
        await client.admin.command('ping')
        logger.info("VERIFICACIÓN DE CONEXIÓN A MONGODB EXITOSA.")
        return True
    except Exception as e:
        logger.critical(f"FALLO DE AUTENTICACIÓN/RED DURANTE EL PING ASÍNCRONO: {e}")
        client, db, personajes, usuarios = [None] * 4
        return False

async def close_connection():
    global client
    if client:
        client.close()
        logger.info("Conexión a MongoDB cerrada.")

async def buscar_personajes_por_nombre(query, limit=10):
    global personajes

    if personajes is None:
        logger.error("❌ Colección 'personajes' no inicializada. No se puede buscar.")
        return []

    if not query:
        return []

    try:
        cursor = personajes.find(
            {"Name": {"$regex": query, "$options": "i"}},
            {"Name": 1, "_id": 0}
        ).limit(limit)

        resultados = await cursor.to_list(length=limit)

        return [doc['Name'] for doc in resultados]

    except Exception as e:
        logger.error(f"Error al buscar personajes: {e}")
        return []