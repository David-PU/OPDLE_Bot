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

from database import (
    obtener_estadisticas_usuario, buscar_personajes_por_nombre,
    actualizar_estadisticas_usuario_win_loss, registrar_inicio_partida,
    registrar_intento_fallido
)
from database import personajes, usuarios

load_dotenv()

# ===== CONFIGURACIÓN =====
TOKEN = os.getenv("BOT_TOKEN_DEV")
ADMIN_IDS = os.getenv("ADMIN_ID")

logger = logging.getLogger(__name__)

# =====================
# FUNCIONES DE JUEGO
# =====================

def elegir_personaje(fixed_name="Nami"):
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

def formatear_personaje_acertado(personaje, update, context):
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

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    logger.debug(f"Inline query: '{query}'")

    # Llamada SÍNCRONA a la función de DB
    resultados = buscar_personajes_por_nombre(query)

    articulos = []
    for nombre in resultados:
        articulos.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=nombre,
                input_message_content=InputTextMessageContent(f"{nombre}")
            )
        )
    # Llamada SÍNCRONA a la API de Telegram
    await update.inline_query.answer(articulos, cache_time=5)

# =====================
# FUNCIONES DE BBDD
# =====================

def asegurar_usuario_existe(telegram_id: int, user_info) -> None:
    if usuarios is None:
        logger.error("Colección 'usuarios' es None. Fallo de conexión a DB.")
        return

    usuario = usuarios.find_one({"_id": telegram_id})

    if usuario is None:
        alias = user_info.username if user_info.username else user_info.first_name
        usuario_inicial = {
            "_id": telegram_id, "telegramId": telegram_id, "alias": alias,
            "totalGamesPlayed": 0, "totalGamesWon": 0, "totalGuesses": 0,
            "currentStreak": 0, "maxStreak": 0,
            "firstPlayed": datetime.now(), "lastPlayed": datetime.now()
        }
        try:
            usuarios.insert_one(usuario_inicial)
            logger.info(f"Nuevo usuario creado: {telegram_id}")
        except DuplicateKeyError:
            pass

def actualizar_derrota(telegram_id: int, intentos_usados: int) -> None:
    # Si el usuario abandona (vuelve a darle al /play) se actualizan los stats de la partida que tenía en juego
    usuarios.update_one(
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

# =====================
# COMANDOS DEL BOT
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Bienvenido a OPDle! Un Wordle de One Piece.\nUsa /play para comenzar.",
                                    parse_mode="HTML")

    telegram_id = update.effective_user.id
    if personajes is not None or usuarios is not None:
        print("PERSONAJES y USUARIOS OK")
    else:
        print("ERROR: La colección de PERSONAJES y USUARIOS no se inicializó. Fallo de conexión a DB.")

    if usuarios is not None:
        asegurar_usuario_existe(telegram_id, update.effective_user)
    else:
        print("ERROR: La colección de usuarios no se inicializó. Fallo de conexión a DB.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    user_data = context.user_data

    if user_data.get("juego_activo", False):
        # Necesitas el secreto para registrar la derrota correctamente (solo para la racha, el contador ya fue registrado)
        # Nota: La derrota resetea la racha, por lo que no hace falta pasar el secreto.
        # Pero necesitas obtener las estadísticas para saber la racha previa y resetearla
        # (Asumo que 'actualizar_derrota' es una función auxiliar que llama a la lógica DB)
        #intentos_usados = user_data.get("intentos_usados", 0) # Debe ser el total de intentos que llevaba
        #actualizar_derrota(telegram_id, intentos_usados)

        stats = obtener_estadisticas_usuario(telegram_id)
        racha_actual = stats.get("currentStreak", 0) if stats else 0
        actualizar_estadisticas_usuario_win_loss(telegram_id, es_victoria=False, racha_actual=racha_actual)

        await update.message.reply_text("❌ Partida anterior abandonada. ¡Iniciando una nueva!")
    # Limpiamos los datos del juego anterior ANTES de empezar el nuevo
    context.user_data.clear()

    # --- INSERCIÓN INICIAL (Si es la primera vez que juega) ---
    # La función debe buscar si el usuario existe y, si no, lo inserta.
    asegurar_usuario_existe(telegram_id, update.effective_user)
    # -----------------------------------------------------------

    # --- LÓGICA PARA INICIAR EL NUEVO JUEGO ---
    secreto = elegir_personaje()
    context.user_data["personaje_secreto"] = secreto
    user_data["juego_activo"] = True
    user_data["intentos_usados"] = 0
    await update.message.reply_text("🔍 He elegido un personaje de One Piece. ¡Adivina quién es escribiendo su nombre!")

    # Sumamos 1 a totalGamesPlayed del usuario
    registrar_inicio_partida(telegram_id)

async def intento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_data = context.user_data

    # --- VERIFICACIONES DE ESTADO DEL JUEGO ---
    if not user_data.get("juego_activo"):
        await update.message.reply_text("👋 ¡Bienvenido! Usa /play para comenzar una nueva partida.")
        return

    nombre = update.message.text.strip()
    secreto_data = user_data.get("personaje_secreto")

    # Lógica de obtención de intentos usados
    intentos_usados = user_data.get("intentos_usados", 0) + 1
    user_data["intentos_usados"] = intentos_usados

    # Control sobre el juego
    es_victoria = False
    juego_terminado = False

    intento_personaje = personajes.find_one({"Name": {"$regex": f"^{nombre}$", "$options": "i"}})

    # --- LÓGICA DE JUEGO ---
    # Si el personaje no está en la BBDD
    if intento_personaje is None:
        await update.message.reply_text(f"❌ El personaje '{nombre}' no se encuentra en la base de datos. Intenta con otro nombre.")
        return

    # Si el personaje es correcto (VICTORIA)
    if intento_personaje["Name"].lower() == secreto_data["Name"].lower():
        es_victoria = True
        juego_terminado = True

        detalles = formatear_personaje_acertado(secreto_data, update, context)
        await update.message.reply_text(
            f"🎉 ¡Correcto! El personaje era {secreto_data['Name']} 🏴‍☠️\n\n{detalles}",
            parse_mode="HTML"
        )
    # Lógica de Juego en Curso. Ha fallado el intento.
    else:
        # Registrar intento fallido en la base de datos
        registrar_intento_fallido(user_id)

        resultado = comparar_personajes(secreto_data, intento_personaje)
        await update.message.reply_text(f"❌ No es {nombre}...\n\n{resultado}", parse_mode="HTML")
        # PENSAR LÓGICA DE DERROTA

    # --- LÓGICA FINAL DE ESTADÍSTICAS Y LIMPIEZA ---
    if juego_terminado:
        # Obtener estadísticas para la racha
        stats = obtener_estadisticas_usuario(user_id)
        racha_actual = stats.get("currentStreak", 0) if stats else 0

        # Llamar a la función atómica de DB para la racha
        actualizar_estadisticas_usuario_win_loss(
            user_id=user_id,
            es_victoria=es_victoria,
            racha_actual=racha_actual
        )

        # Si perdió, hay que notificar la derrota (si no se hizo antes)
        if not es_victoria:
            await update.message.reply_text(
                f"💀 ¡Has perdido! El personaje era **{secreto_data['Name']}**.",
                parse_mode="Markdown"
            )

        # Limpieza de user_data
        user_data["juego_activo"] = False
        user_data.pop("personaje_secreto", None)
        user_data.pop("intentos_usados", None)

# async def intento(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     nombre = update.message.text.strip()
#     secreto = context.user_data.get("secreto")
#
#     if not secreto:
#         await update.message.reply_text("⚠️ Usa /play para comenzar una partida antes de intentar.")
#         return
#
#     intento_personaje = personajes.find_one({"Name": {"$regex": f"^{nombre}$", "$options": "i"}})
#
#     if not intento_personaje:
#         await update.message.reply_text("No encontré ese personaje en la base de datos. Intenta con otro nombre.")
#         return
#
#     if intento_personaje["Name"].lower() == secreto["Name"].lower():
#         detalles = formatear_personaje_acertado(secreto, update, context)
#         await update.message.reply_text(
#             f"🎉 ¡Correcto! El personaje era {secreto['Name']} 🏴‍☠️\n\n{detalles}",
#             parse_mode="HTML"
#         )
#         context.user_data.clear()
#     else:
#         resultado = comparar_personajes(secreto, intento_personaje)
#         await update.message.reply_text(f"❌ No es {nombre}...\n\n{resultado}", parse_mode="HTML")

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

    update.message.reply_text(
        guia_text,
        parse_mode='Markdown' # Usamos Markdown para los títulos en negrita (**)
    )
    logger.info("🟢 Guía enviada al usuario.")

# =====================
# INICIO DEL BOT
# =====================

def main():

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("guia", guia_comando))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, intento))
    app.add_handler(InlineQueryHandler(inline_query_handler))

    print("🤖 Bot OPDle en marcha...")
    app.run_polling()

if __name__ == "__main__":
    main()