import os

from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI_REMOTE")
DB_NAME = os.getenv("DB_NAME", "opdle_db")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

personajes = db["personajes"]
usuarios = db["usuarios"]

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