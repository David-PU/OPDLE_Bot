def comparar_personajes(secreto, intento):
    """
    Compara campo a campo el personaje secreto con el intento del jugador.
    - Verde 🟩 si coincide totalmente.
    - Rojo 🟥 si no coincide.
    - Flecha ⬆️ / ⬇️ si el valor secreto es mayor o menor (en campos numéricos).
    - En 'Haki': 🟥🟨 si hay coincidencia parcial de letras.
    """
    campos = [
        "Name", "Sex", "DevilFruitType", "Devilfruit",
        "Org", "Origin", "Appears", "Height", "Haki", "Bounty"
    ]

    resultado = []

    for key in campos:
        val_secreto = str(secreto.get(key, "")).strip()
        val_intento = str(intento.get(key, "")).strip()

        # Intentar convertir a número
        def to_number(val):
            try:
                return float(str(val).replace(",", "").replace(" ", ""))
            except ValueError:
                return None

        num_secreto = to_number(val_secreto)
        num_intento = to_number(val_intento)

        # 🔹 CASO 1: HAKI (comparación especial)
        if key == "Haki":
            set_secreto = set(val_secreto.upper())
            set_intento = set(val_intento.upper())
            coincidencias = set_secreto.intersection(set_intento)

            if len(coincidencias) == 3:
                emoji = "🟩"
            elif len(coincidencias) == 0:
                emoji = "🟥"
            else:
                emoji = "🟨"

            texto = f"**{val_intento or 'None'}**"

        # 🔹 CASO 2: Coincidencia exacta
        elif val_secreto == val_intento:
            emoji = "🟩"
            texto = f"**{val_intento}**"

        # 🔹 CASO 3: Números comparables
        elif num_secreto is not None and num_intento is not None:
            if num_secreto > num_intento:
                emoji = "🟥⬆️"
            elif num_secreto < num_intento:
                emoji = "🟥⬇️"
            else:
                emoji = "🟥"
            texto = f"**{val_intento}**"

        # 🔹 CASO 4: Diferente texto
        else:
            emoji = "🟥"
            texto = f"**{val_intento or 'None'}**"

        resultado.append(f"{key}: {emoji} {texto}")

    return "\n".join(resultado)
