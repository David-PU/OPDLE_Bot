import logging
import os
import random
import re
import uuid
from datetime import datetime

from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError
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
from database import db
from database import init_db
from database import personajes, usuarios

load_dotenv()

# ===== CONFIGURACIÓN =====
TOKEN = os.getenv("BOT_TOKEN_DEV")
ADMIN_IDS = os.getenv("ADMIN_ID")
MONGO_URI = os.getenv("MONGO_URI_REMOTE")
DB_NAME = os.getenv("DB_NAME", "opdle_db")
logger = logging.getLogger(__name__)

# =====================
# FUNCIONES DE JUEGO
# =====================

def elegir_personaje(fixed_name=""):
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

    field_map = {
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

        elif key == "DevilFruitType":
            if val_secreto == val_intento:
                emoji = "🟩"
            else:
                emoji = "🟥"

            if val_intento in ["None", "Unknown"]:
                display = "Sin Fruta"
            else:
                display = val_intento

        elif val_secreto == val_intento:
            emoji = "🟩"
            display = formatted_bounty_i if key == "Bounty" else (val_intento or "None")

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
                emoji = "🟩"
            display = formatted_bounty_i if key == "Bounty" else (val_intento or "None")

        else:
            emoji = "🟥"
            display = formatted_bounty_i if key == "Bounty" else (val_intento or "None")

        if key == "Height":
            if val_intento in ["Unknown", "None"]:
                display = "Desconocida"
            else:
                display = f"{val_intento} cm"


        display_key = field_map.get(key, key)
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

async def formatear_personaje_acertado(personaje, update, context):

    # Lógica para BBDD
    telegram_id = update.effective_user.id
    intentos_usados = context.user_data.get("intentos_usados", 1) # Ya deberías tener el conteo

    # Llama a la función de actualización de DB para la victoria
    await actualizar_victoria(telegram_id, intentos_usados)

    # Marca la partida como terminada para que el próximo /play no la cuente como derrota.
    # context.user_data["juego_activo"] = False # o context.user_data["partida_ganada"] = True
    context.user_data.clear()

    field_map = {
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
        display_key = field_map.get(c, c)
        emoji = "🟩"

        if c == "Bounty":
            display = format_bounty(val)
        elif c == "Height":
            display = (val or "None") + " cm"
        elif c == "Appears":
            display = "Chapter " + (val or "None")
        elif c == "Haki":
            display = haki_visual(val)
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
        return "❌"
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
    if s.upper() == "UNKNOWN":
        return "Desconocida"
    elif s.upper() == "NONE" or s == "0":
        return "Sin Recompensa"
    digits = re.sub(r"[^\d]", "", s)
    if digits == "":
        return s

    try:
        n = int(digits)
    except ValueError:
        return s

    if n > 1_000_000 and n < 100_000_000:
        return f"{BERRIE_SYMBOL}{n // 1_000_000} M"
    elif 100_000_000 <= n <= 999_999_999:
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
# FUNCIONES DE BBDD
# =====================

async def asegurar_usuario_existe(telegram_id: int, user_info) -> None:
    # Se verifica si el usuario existe y si no lo crea
    usuario = await usuarios.find_one({"_id": telegram_id})

    if usuario is None:
        alias = user_info.username if user_info.username else user_info.first_name

        usuario_inicial = {
            "_id": telegram_id,
            "telegramId": telegram_id,
            "alias": alias,
            "totalGamesPlayed": 0,
            "totalGamesWon": 0,
            "totalGuesses": 0,
            "currentStreak": 0,
            "maxStreak": 0,
            "firstPlayed": datetime.now(),
            "lastPlayed": datetime.now()
        }

        try:
            await usuarios.insert_one(usuario_inicial)
            logger.info(f"Nuevo usuario creado: {telegram_id}")
        except DuplicateKeyError:
            pass

async def actualizar_derrota(telegram_id: int, intentos_usados: int) -> None:
    # Si el usuario abandona (vuelve a darle al /play) se actualizan los stats de la partida que tenía en juego
    await usuarios.update_one(
        {"_id": telegram_id},
        {
            "$inc": {
                "totalGamesPlayed": 1,
                "totalGuesses": intentos_usados
            },
            "$set": {
                "currentStreak": 0,
                "lastPlayed": datetime.now()
            }
        }
    )
    logger.info(f"Estadísticas de derrota (abandono) actualizadas para {telegram_id}")

async def actualizar_victoria(telegram_id: int, intentos_usados: int) -> None:
    # Actualiza los stats de un jugador tras la victoria
    # Usamos $inc para incrementar contadores de forma atómica
    # Usamos $max para actualizar la racha máxima solo si el valor es mayor
    await usuarios.update_one(
        {"_id": telegram_id},
        {
            "$inc": {
                "totalGamesPlayed": 1,
                "totalGamesWon": 1,
                "totalGuesses": intentos_usados,
                "currentStreak": 1
            },
            "$set": {
                "lastPlayed": datetime.now()
            }
        }
    )

    # 2. SEGUNDA OPERACIÓN: Actualizar maxStreak
    # Aquí usamos un $max para asegurarse de que maxStreak siempre sea el valor más alto.
    # El valor de currentStreak ya se habrá incrementado en la DB.
    await usuarios.update_one(
        {"_id": telegram_id},
        {
            "$max": {
                "maxStreak": "$currentStreak" # Usa el valor actual de currentStreak en la DB
            }
        }
    )
    logger.info(f"Estadísticas de victoria actualizadas para {telegram_id}")

# =====================
# COMANDOS DEL BOT
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Bienvenido a OPDle! Un Wordle de One Piece.\nUsa /play para comenzar.",
                                    parse_mode="HTML")
    usuario_inicial = {
        "_id": update.effective_user.id,
        "telegramId": update.effective_user.id,
        "alias": update.effective_user.username or update.effective_user.first_name,
        "totalGamesPlayed": 0,
        "totalGamesWon": 0,
        "totalGuesses": 0,
        "currentStreak": 0,
        "maxStreak": 0,
        "firstPlayed": datetime.now(),
        "lastPlayed": datetime.now()
    }
    db.usuarios.insert_one(usuario_inicial)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    # Lógica de abandono sin terminar partida
    # Revisamos si el usuario tiene una partida activa
    if context.user_data.get("juego_activo", False):
        # El juego anterior se considera una DERROTA por abandono
        intentos_usados = context.user_data.get("intentos_usados", 0) # Debe ser el total de intentos que llevaba
        # Llama a la función de actualización de DB para la derrota
        await actualizar_derrota(telegram_id, intentos_usados)
        # Informa al usuario (opcional)
        await update.message.reply_text("❌ Partida anterior abandonada. ¡Iniciando una nueva!")

        # Limpiamos los datos del juego anterior ANTES de empezar el nuevo
        context.user_data.clear()
        # ----------------------------------------------

        # 2. --- INSERCIÓN INICIAL (Si es la primera vez que juega) ---
        # La función debe buscar si el usuario existe y, si no, lo inserta.
        await asegurar_usuario_existe(telegram_id, update.effective_user)
        # -----------------------------------------------------------

        # 3. --- LÓGICA PARA INICIAR EL NUEVO JUEGO ---
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
        detalles = formatear_personaje_acertado(secreto, update, context)
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

async def guia_comando(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la guía, las reglas y el significado de los iconos del juego."""
    logger.info(f"🔵 Comando /guia recibido por User ID: {update.effective_user.id}")

    guia_text = (
        "📜 **GUÍA DE JUEGO Y SÍMBOLOS**\n\n"
        "¡Adivina el personaje secreto de One Piece 🏴‍☠️!\n"
        "Cada intento te mostrará qué has acertado y qué no del personaje secreto.\n\n"

        "--- **ICONOGRAFÍA DE ATRIBUTOS** ---\n"

        "🟩 **VERDE** (Coincidencia Perfecta):\n"
        "   El atributo del personaje que has introducido coincide **exactamente** con el "
        "   del personaje secreto (Ej: Género, Tipo de Fruta, Haki, Origen, etc.).\n\n"

        "🟥 **ROJO** (Sin Coincidencia):\n"
        "   El atributo no coincide en absoluto o no tiene relación directa.\n\n"

        "🟨 **AMARILLO** (Similitud/Parcialidad):\n"
        "   Sólo se usa en el atributo **Haki**. Significa que has adivinado "
        "   correctamente **al menos un tipo** de Haki (Observación, Armamento o Conquistador), "
        "   pero no todos los que posee el personaje secreto.\n\n"

        "--- **ICONOGRAFÍA DE VALORES NUMÉRICOS** ---\n"

        "🔺 **TRIÁNGULO ARRIBA**:\n"
        "   El valor del personaje secreto es **SUPERIOR** al que has introducido. "
        "   (Aplica a: *1ra Aparición*, *Altura*, *Recompensa*).\n\n"

        "🔻 **TRIÁNGULO ABAJO**:\n"
        "   El valor del personaje secreto es **INFERIOR** al que has introducido. "
        "   (Aplica a: *1ra Aparición*, *Altura*, *Recompensa*).\n\n"

        "--- **ADVERTENCIA DE SPOILERS** ---\n"
        "⚠️ **¡CUIDADO!** La base de datos contiene personajes, habilidades, recompensas "
        "y afiliaciones actualizadas **hasta el último capítulo del manga**. "
        "Juega bajo tu propio riesgo de **SPOILERS**.\n\n"

        "Para empezar, usa el comando `/play` o escribe `@OPDLE_Dev_Bot` en cualquier chat."
    )

    await update.message.reply_text(
        guia_text,
        parse_mode='Markdown' # Usamos Markdown para los títulos en negrita (**)
    )
    logger.info("🟢 Guía enviada al usuario.")

# =====================
# INICIO DEL BOT
# =====================

def main():

    db_connection = init_db(MONGO_URI, DB_NAME)
    if db_connection is None:
        logger.critical("🚨 La conexión a la base de datos es NULA. El bot NO puede iniciarse sin DB.")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    #app.add_handler(CommandHandler("play", lambda u, c: play(u, c, db_connection)))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("guia", guia_comando))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, intento))
    app.add_handler(InlineQueryHandler(inline_query_handler))




    print("🤖 Bot OPDle en marcha...")
    app.run_polling()

if __name__ == "__main__":
    main()
