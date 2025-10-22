import os
import random
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
from database import personajes

load_dotenv()

# ===== CONFIGURACIÓN =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_ID")
MONGO_URI_CLUSTER = os.getenv("MONGO_URI_CLUSTER")
MONGO_URI_LOCAL = os.getenv("MONGO_URI_LOCAL")
DB_NAME = os.getenv("DB_NAME")

# ===== COMANDOS =====

# =====================
# FUNCIONES DE JUEGO
# =====================

def elegir_personaje():
    lista = list(personajes.find())
    return random.choice(lista)

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

# =====================
# COMANDOS DEL BOT
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Bienvenido a *OPDle*! Un Wordle de One Piece.\nUsa /play para comenzar.", parse_mode="Markdown")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secreto = elegir_personaje()
    context.user_data["secreto"] = secreto
    await update.message.reply_text("🔍 He elegido un personaje de One Piece. ¡Adivina quién es escribiendo su nombre!")

async def intento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.message.text.strip()
    secreto = context.user_data.get("secreto")

    if not secreto:
        await update.message.reply_text("⚠️ Usa /play para comenzar una partida antes de intentar.")
        return

    intento_personaje = personajes.find_one({"Name": {"$regex": f"^{nombre}$", "$options": "i"}})

    if not intento_personaje:
        await update.message.reply_text("❌ No encontré ese personaje en la base de datos. Intenta con otro nombre.")
        return

    if intento_personaje["Name"].lower() == secreto["Name"].lower():
        await update.message.reply_text(f"🎉 ¡Correcto! El personaje era *{secreto['Name']}* 🏴‍☠️", parse_mode="Markdown")
        context.user_data.clear()
    else:
        resultado = comparar_personajes(secreto, intento_personaje)
        await update.message.reply_text(f"❌ No es {nombre}...\n\n{resultado}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_IDS:
        await update.message.reply_text("🚫 No tienes permiso para usar este comando.")
        return

    context.user_data.clear()
    await update.message.reply_text("🔄 Juego reiniciado para este usuario.")

# =====================
# INICIO DEL BOT
# =====================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, intento))

    print("🤖 Bot OPDle en marcha...")
    app.run_polling()

if __name__ == "__main__":
    main()