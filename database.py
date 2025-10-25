import logging
import os
from datetime import datetime
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)
load_dotenv()

db_name = os.getenv("DB_NAME_TEST")
usrdbenv = os.getenv("DB_USERNAME")
passdbenv = os.getenv("DB_PASSWORD")
cluster = os.getenv("CLUSTER_DB")
datadb = os.getenv("DATA_DB")

if not (usrdbenv and passdbenv and cluster and datadb and db_name):
    logger.critical("❌ ERROR CRÍTICO: Faltan variables de entorno para la DB. Revise .env.")

username = quote_plus(usrdbenv)
password = quote_plus(passdbenv)
uri = 'mongodb+srv://' + username + ':' + password + '@' + cluster.lower() + '.' + datadb + '.mongodb.net/?retryWrites=true&w=majority&appName=' + cluster

print("--- INICIO DEBUG ---")
print("DB_USERNAME:", usrdbenv)
print("DB_PASSWORD:", passdbenv) # OJO: Solo para debug temporal, luego ELIMÍNALO
print("URI COMPLETA:", uri)
print("--- FIN DEBUG ---")

try:
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client[db_name]
    personajes = db["personajes"]
    usuarios = db["usuarios"]
    client.admin.command('ping')
    logger.info("✅ Conexión a MongoDB establecida.")
except Exception as e:
    logger.critical(f"❌ FALLO CRÍTICO AL CONECTAR/PING MONGODB: {e}")
    client = None
    db = None
    personajes = None
    usuarios = None

# client = MongoClient(uri, server_api=ServerApi('1'))
# db = client[db_name]
#
# personajes = db["personajes"]
# usuarios = db["usuarios"]

def buscar_personajes_por_nombre(query, limit=10):
    global personajes

    if personajes is None:
        logger.error("❌ Colección 'personajes' no inicializada. No se puede buscar.")
        return []

    if not query:
        return []

    try:
        # Operación SÍNCRONA de PyMongo
        cursor = personajes.find(
            {"Name": {"$regex": query, "$options": "i"}},
            {"Name": 1, "_id": 0}
        ).limit(limit)

        # Iteramos el cursor síncronamente
        resultados = [doc['Name'] for doc in cursor]

        return resultados

    except Exception as e:
        logger.error(f"Error al buscar personajes: {e}")
        return []

def obtener_estadisticas_usuario(user_id: int):
    global usuarios
    if usuarios is None:
        return None
    try:
        return usuarios.find_one({"telegramId": user_id})
    except Exception as e:
        logger.error(f"Error al obtener estadísticas del usuario {user_id}: {e}")
        return None

def actualizar_estadisticas_usuario_win_loss(user_id: int, es_victoria: bool, racha_actual: int):
    global usuarios

    if usuarios is None:
        logger.error("Colección 'usuarios' no inicializada. No se puede actualizar.")
        return

    # Usamos $set para la racha y $inc para los contadores
    set_ops = {}
    inc_ops = {}
    max_ops = {}

    if es_victoria:
        # LÓGICA DE VICTORIA

        # 1. Incrementar totalGamesWon
        inc_ops["totalGamesWon"] = 1
        inc_ops["totalGuesses"] = 1

        # 2. Calcular y fijar la nueva racha
        nueva_racha = racha_actual + 1
        set_ops["currentStreak"] = nueva_racha
        max_ops["maxStreak"] = nueva_racha

    else: # LÓGICA DE DERROTA
        # Resetear racha actual a 0
        set_ops["currentStreak"] = 0

        # 3. Construir la operación final
    update_ops = {}
    if set_ops: update_ops["$set"] = set_ops
    if inc_ops: update_ops["$inc"] = inc_ops
    if max_ops: update_ops["$max"] = max_ops

    # Si la operación está vacía (no debería pasar), salimos
    if not update_ops:
        return

    try:
        usuarios.update_one(
            {"telegramId": user_id},
            update_ops,
            upsert=True
        )
        logger.info(f"Racha y victorias actualizadas para el usuario {user_id}. Victoria: {es_victoria}")
    except Exception as e:
        logger.error(f"Error al actualizar racha del usuario {user_id}: {e}")

def registrar_inicio_partida(user_id: int):
    """
    Incrementa totalGamesPlayed y actualiza la fecha de última partida al inicio de /play.
    """
    global usuarios
    if usuarios is None:
        logger.error("❌ Colección 'usuarios' no inicializada.")
        return

    try:
        usuarios.update_one(
            {"telegramId": user_id},
            {
                "$inc": {"totalGamesPlayed": 1},
                "$set": {"lastPlayed": datetime.utcnow()} # Usar UTC para consistencia
            },
            upsert=True
        )
        logger.info(f"Partida iniciada y totalGamesPlayed actualizado para {user_id}")
    except Exception as e:
        logger.error(f"Error al registrar inicio de partida para {user_id}: {e}")

def registrar_intento_fallido(user_id: int):
    global usuarios
    if usuarios is None:
        logger.error("❌ Colección 'usuarios' no inicializada.")
        return

    try:
        usuarios.update_one(
            {"telegramId": user_id},
            {
                # Usamos $inc para asegurar una actualización atómica
                "$inc": {"totalGuesses": 1}
            },
            upsert=True
        )
        logger.info(f"Intento registrado para {user_id}")
    except Exception as e:
        logger.error(f"Error al registrar intento para {user_id}: {e}")

def close_connection():
    global client
    if client:
        client.close()
        logger.info("Conexión a MongoDB cerrada.")