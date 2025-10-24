import random

from database import personajes


def elegir_personaje():
    lista = list(personajes.find())
    return random.choice(lista)

def comparar_personajes(personaje_secreto, intento):
    resultado = {}
    for clave in personaje_secreto:
        if clave in intento:
            resultado[clave] = (
                "🟩" if personaje_secreto[clave] == intento[clave] else "🟥"
            )
    return resultado
