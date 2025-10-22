import json
from pathlib import Path
from database import personajes, close_connection

def load_json_path():
    # Path al archivo data/characters.json relativo a la raíz del proyecto
    # __file__ está en src/, así que parent.parent -> raíz del proyecto
    root = Path(__file__).resolve().parent.parent
    return root / "data" / "characters.json"

def main():
    json_path = load_json_path()
    if not json_path.exists():
        print(f"❌ No se encuentra {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("❌ El JSON debe contener una lista de objetos (personajes).")
        return

    count = 0
    for personaje in data:
        # Suponemos que cada objeto contiene un campo "Name" que es único
        nombre = personaje.get("Name")
        if not nombre:
            print("⚠️ Personaje sin Name, se ignora:", personaje)
            continue

        # Upsert: reemplaza si existe o inserta si no
        personajes.replace_one({"Name": nombre}, personaje, upsert=True)
        count += 1

    print(f"✅ {count} personajes insertados/actualizados en la colección 'personajes'.")
    close_connection()

if __name__ == "__main__":
    main()
