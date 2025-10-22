import os
from pymongo import MongoClient

# Leer variables de entorno (si no están, usa valores por defecto para desarrollo local)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "opdle_db")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

personajes = db["personajes"]
usuarios = db["usuarios"]

def close_connection():
    client.close()
