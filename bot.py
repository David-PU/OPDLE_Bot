import os
import random
import re
import uuid

from dotenv import load_dotenv
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.ext import InlineQueryHandler

from database import buscar_personajes_por_nombre
from database import personajes

load_dotenv()

# ===== CONFIGURACIÓN =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_ID")
MONGO_URI_CLUSTER = os.getenv("MONGO_URI_CLUSTER")
MONGO_URI_LOCAL = os.getenv("MONGO_URI_LOCAL")
DB_NAME = os.getenv("DB_NAME")

# =====================
# FUNCIONES DE JUEGO
# =====================

def elegir_personaje(fixed_name=""):
    # Si se solicita un personaje concreto, buscarlo (case-insensitive)
    if fixed_name:
        query = {"Name": {"$regex": f"^{re.escape(fixed_name)}$", "$options": "i"}}
        encontrado = personajes.find_one(query)
        if encontrado:
            return encontrado

    # Si no hay nombre forzado o no se encontró, elegir aleatorio
    lista = list(personajes.find())
    if not lista:
        return None
    return random.choice(lista)

def comparar_personajes(secreto, intento):

    FIELD_MAP = {
        "Sex": "Género",
        "Height": "Altura",
        "Appears": "1ra Aparición",
        "Bounty": "Recompensa",
        "Org": "Afiliación",
        "Origin": "Origen",
        "DevilFruitType": "Tipo de Fruta",
        "Haki": "Haki"
    }

    campos = [
        "Name", "Sex", "DevilFruitType",
        "Org", "Origin", "Appears", "Height", "Haki", "Bounty"
    ]

    rows = []

    def to_number(val):
        try:
            return float(str(val).replace(",", "").replace(" ", ""))
        except ValueError:
            return None

    for key in campos:
        val_secreto = str(secreto.get(key, "")).strip()
        val_intento = str(intento.get(key, "")).strip()

        formatted_bounty_i = format_bounty(val_intento)

        num_secreto = to_number(val_secreto)
        num_intento = to_number(val_intento)

        visual_intento = haki_visual(val_intento)

        # Determinar emoji y texto mostrable
        if key == "Haki":
            val_s = val_secreto.upper().strip()
            val_i = val_intento.upper().strip()

            is_none_s = val_s == "" or val_s == "NONE"
            is_none_i = val_i == "" or val_i == "NONE"

            if is_none_s and is_none_i:
                emoji = "🟩"
            elif is_none_s and not is_none_i:
                emoji = "🟥"
            elif not is_none_s and is_none_i:
                emoji = "🟥"
            else:
                letras_s = set(ch for ch in val_s if ch in {"O", "A", "C"})
                letras_i = set(ch for ch in val_i if ch in {"O", "A", "C"})
                coincidencias = letras_s.intersection(letras_i)
                if len(coincidencias) == 3:
                    emoji = "🟩"
                elif len(coincidencias) == 0:
                    emoji = "🟥"
                elif len(coincidencias) == 1 and val_s == val_i:
                    emoji = "🟩"
                elif len(coincidencias) == 2 and val_s == val_i:
                    emoji = "🟩"
                else:
                    emoji = "🟨"
            display = visual_intento or "None"

        elif val_secreto == val_intento:
            emoji = "🟩"
            display = formatted_bounty_i if key == "Bounty" else (val_intento or "None")

        elif key == "DevilFruitType" and val_intento == "None":
            display = "Sin Fruta"

        elif key == "Appears" and num_secreto is not None and num_intento is not None:
            if num_secreto == num_intento:
                emoji = "🟩"
            elif num_secreto > num_intento:
                emoji = "🔺"
            elif num_secreto < num_intento:
                emoji = "🔻"
            display = "Capítulo " + val_intento

        elif num_secreto is not None and num_intento is not None:
            if num_secreto > num_intento:
                emoji = "🔺"
            elif num_secreto < num_intento:
                emoji = "🔻"
            else:
                emoji = "🟩" # Debería ser verde si los números son iguales
            display = formatted_bounty_i if key == "Bounty" else (val_intento or "None")

        else:
            emoji = "🟥"
            display = formatted_bounty_i if key == "Bounty" else (val_intento or "None")

        if key == "Height" and display != "None":
            display = display + " cm"


        display_key = FIELD_MAP.get(key, key)
        rows.append((display_key, emoji, str(display)))

    # Calcular anchos para alineado
    key_w = max(len(r[0]) for r in rows)
    # El ancho máximo de la columna de emoji es 2 (por "🟥⬆️")
    emoji_w = max(len(r[1]) for r in rows) # Esto será 2
    val_w = max(len(r[2]) for r in rows)

    # Construir líneas alineadas (monoespaciado dentro de <pre>)
    lines = []
    for key, emoji, val in rows:
        if key == "Name":
            continue
        lines.append(f"{key.ljust(key_w)} | {emoji.ljust(emoji_w)} | {val.ljust(val_w)}")

    return "<code>" + "\n".join(lines) + "</code>"

def formatear_personaje(personaje):

    FIELD_MAP = {
        "Sex": "Género",
        "Height": "Altura",
        "Appears": "1ra Aparición",
        "Bounty": "Recompensa",
        "Org": "Afiliación",
        "Origin": "Origen",
        "DevilFruitType": "Tipo de Fruta",
        "Haki": "Haki"
    }

    campos_db = ["Sex", "DevilFruitType", "Org", "Origin", "Appears", "Height", "Haki", "Bounty"]

    rows = []
    for c in campos_db:
        val = personaje.get(c, "")
        display_key = FIELD_MAP.get(c, c)
        emoji = "🟩"

        if c == "Bounty":
            # Asumimos que format_bounty ya está definida y aplica el símbolo (ej. 💰)
            display = format_bounty(val)
        elif c == "Height":
            display = (val or "None") + " cm"
        elif c == "Appears":
            display = "Chapter " + (val or "None")
        else:
            display = val or "None"

        # Añadir la fila con la clave traducida, el emoji fijo, y el valor formateado
        rows.append((display_key, emoji, str(display)))

    key_w = max(len(r[0]) for r in rows)
    val_w = max(len(r[2]) for r in rows)

    lines = []
    for key, emoji, val in rows:
        lines.append(f"{key.ljust(key_w)} | {emoji}  | {val.ljust(val_w)}")

    return "<code>" + "\n".join(lines) + "</code>"

def haki_visual(val):
    mapping = {"O": "👁️", "A": "🦾", "C": "👑"}
    if val is None:
        return "None"
    s = str(val).upper().strip()
    if s == "" or s == "NONE":
        return "None"
    seen = []
    for ch in s:
        if ch in mapping and mapping[ch] not in seen:
            seen.append(mapping[ch])
        elif ch not in mapping and ch not in seen:
            seen.append(ch)
    return "".join(seen) if seen else s

def format_bounty(val):
    BERRIE_SYMBOL = "💰"
    if val is None:
        return "None"
    s = str(val).strip()
    if s == "" or s.upper() == "NONE":
        return "None"

    digits = re.sub(r"[^\d]", "", s)
    if digits == "":
        return s

    try:
        n = int(digits)
    except ValueError:
        return s

    if 100_000_000 <= n <= 999_999_999:
        return f"{BERRIE_SYMBOL}{n // 1_000_000} M"
    elif n >= 1_000_000_000:
        return f"{BERRIE_SYMBOL}{n // 1_000_000} M"
    else:
        return f"{BERRIE_SYMBOL}{s}"

async def inline_query_handler(update, context):
    query = update.inline_query.query

    # 1. Búsqueda en la base de datos
    resultados = buscar_personajes_por_nombre(query)

    # 2. Construir la respuesta
    articulos = []
    for nombre in resultados:
        articulos.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=nombre,
                input_message_content=InputTextMessageContent(f"{nombre}")
            )
        )

    # 3. Enviar los resultados inline
    await update.inline_query.answer(articulos, cache_time=5)

# =====================
# COMANDOS DEL BOT
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Bienvenido a OPDle! Un Wordle de One Piece.\nUsa /play para comenzar.",
                                    parse_mode="HTML")

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
        detalles = formatear_personaje(secreto)
        await update.message.reply_text(
            f"🎉 ¡Correcto! El personaje era {secreto['Name']} 🏴‍☠️\n\n{detalles}",
            parse_mode="HTML"
        )
        context.user_data.clear()
    else:
        resultado = comparar_personajes(secreto, intento_personaje)
        await update.message.reply_text(f"❌ No es {nombre}...\n\n{resultado}", parse_mode="HTML")

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
    app.add_handler(InlineQueryHandler(inline_query_handler))

    print("🤖 Bot OPDle en marcha...")
    app.run_polling()

if __name__ == "__main__":
    main()
