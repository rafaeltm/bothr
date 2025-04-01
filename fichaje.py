import os
import time
import random
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright, TimeoutError
import asyncio
from telegram import Bot

load_dotenv()

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
CHAT_ID = os.getenv("CHAT_ID")  
BOT_TOKEN = os.getenv("BOT_TOKEN")
ENABLE = os.getenv("ENABLE") 

LATITUDE = float(os.getenv("LATITUDE"))
LONGITUDE = float(os.getenv("LONGITUDE"))

FICHAJE_FILE = "/usr/src/app/data/fichajes.log"

if not USERNAME or not PASSWORD or not CHAT_ID or not BOT_TOKEN:
    raise ValueError("Faltan variables de entorno necesarias")

LOGIN_URL = os.getenv("LOGIN_URL")

def cargar_fechas(nombre_archivo):
    with open(nombre_archivo, "r", encoding="utf-8") as f:
        return set(json.load(f)["dias" if "jornada" in nombre_archivo else "festivos"])

FESTIVOS = cargar_fechas("/usr/src/app/data/festivos.json")
JORNADA_REDUCIDA = cargar_fechas("/usr/src/app/data/jornada_reducida.json")

bot = Bot(token=BOT_TOKEN)

async def enviar_mensaje_telegram(mensaje):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=mensaje)
    except Exception as e:
        print(f"Error al enviar mensaje por Telegram: {str(e)}")

async def log_event(message):
    timestamp = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"{timestamp} - {message}"
    print(log_message)
    await enviar_mensaje_telegram(log_message)

def es_festivo():
    return datetime.today().strftime("%Y-%m-%d") in FESTIVOS or datetime.today().weekday() >= 5

def get_fichaje_hours():
    today = datetime.now(ZoneInfo("Europe/Madrid"))
    if today.weekday() >= 5 or es_festivo():
        return None

    base_entry_time = datetime.strptime("08:00", "%H:%M").replace(tzinfo=ZoneInfo("Europe/Madrid"))
    margin = timedelta(minutes=random.randint(-15, 15))
    adjusted_entry_time = (base_entry_time + margin).time()

    today_str = today.strftime("%Y-%m-%d")
    if today_str in JORNADA_REDUCIDA:
        work_hours = 7
    else:
        work_hours = 7 if (6 <= today.month <= 9 or today.weekday() == 4) else 9

    exit_time = (datetime.combine(today, adjusted_entry_time).replace(tzinfo=ZoneInfo("Europe/Madrid")) + timedelta(hours=work_hours)).time()
    
    return {"clock_in": adjusted_entry_time, "clock_out": exit_time}

async def login(playwright):
    await log_event("Iniciando sesión en la plataforma...")
    
    geolocation = {"latitude": LATITUDE, "longitude": LONGITUDE}
    permissions = ["geolocation"] 

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        geolocation=geolocation,
        permissions=permissions  
    )
    page = await context.new_page()

    await page.goto(LOGIN_URL)

    try:
        await page.fill('input[name="FrmEntrada[usuario]"]', USERNAME)
        await page.fill('input[name="FrmEntrada[clave]"]', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        await log_event("Login exitoso.")
        return page, browser
    except TimeoutError:
        await log_event("Error: Tiempo de espera agotado en el login.")
        await browser.close()
        return None, None

async def fichar(page, tipo="entrada"):
    # Si ENABLE es false, ejecutamos todo pero no fichamos
    if not ENABLE:
        await log_event(f"Fichaje de {tipo} deshabilitado por configuración.")
        return
    try:
        await page.wait_for_selector('a[data-bs-target="#ModalPicada"]', timeout=10000)
        await page.click('a[data-bs-target="#ModalPicada"]') 

        await page.wait_for_selector('#ModalPicada .modal-content', timeout=10000)
        
        await page.wait_for_selector('#btnFrmFichar', timeout=10000)

        await page.click('#btnFrmFichar')
        await log_event(f"Fichaje de {tipo} realizado.")
    except TimeoutError:
        error_message = f"Error: Timeout alcanzado al intentar realizar el fichaje de {tipo}."
        await log_event(error_message)
        await enviar_mensaje_telegram(error_message)  
    except Exception as e:
        error_message = f"Error inesperado al intentar fichar {tipo}: {str(e)}"
        await log_event(error_message)
        await enviar_mensaje_telegram(error_message)  

async def esperar_hora(fichaje_hora: time):
    now = datetime.now(ZoneInfo("Europe/Madrid"))
    target_time = datetime.combine(now.date(), fichaje_hora).replace(tzinfo=ZoneInfo("Europe/Madrid"))

    if now > target_time:
        target_time += timedelta(days=1)

    time_to_wait = (target_time - now).total_seconds()
    await log_event(f"Esperando hasta las {target_time.strftime('%H:%M:%S')} ({time_to_wait:.0f} segundos)")

    while time_to_wait > 0:
        sleep_time = min(time_to_wait, 300)

        if time_to_wait <= 600:
            await log_event(f"Quedan menos de 10 minutos ({time_to_wait:.0f} segundos)")

        await asyncio.sleep(sleep_time)
        time_to_wait -= sleep_time
    
def read_fichaje_log():
    # Leer los registros del archivo
    try:
        with open(FICHAJE_FILE, 'r', encoding='utf-8') as f:
            registros = json.load(f)
        return registros
    except FileNotFoundError:
        return []  # Si el archivo no existe, devolver una lista vacía
    except json.JSONDecodeError:
        return []  # Si el archivo está vacío o tiene un error de formato, devolver una lista vacía

def es_fichaje_realizado_hoy(tipo_fichaje):
    """Verifica si el fichaje de tipo entrada o salida se ha realizado hoy."""
    today = datetime.now().date()
    registros = read_fichaje_log()
    for registro in registros:
        if tipo_fichaje in registro:
            timestamp = registro[tipo_fichaje]
            fecha_fichaje = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").date()
            if fecha_fichaje == today:
                return True
    return False

def write_fichaje_log(tipo_fichaje, timestamp):
    # Crear el registro con tipo de fichaje y timestamp
    registro = {tipo_fichaje: timestamp}
    
    # Leer los registros existentes en el archivo (si existen)
    try:
        with open(FICHAJE_FILE, 'r', encoding='utf-8') as f:
            registros = json.load(f)
    except FileNotFoundError:
        registros = []
    
    # Agregar el nuevo registro
    registros.append(registro)
    
    # Escribir de nuevo el archivo con los registros actualizados
    with open(FICHAJE_FILE, 'w', encoding='utf-8') as f:
        json.dump(registros, f, indent=4)

async def main():
    while True:
        if es_festivo():
            await log_event("Hoy es festivo. No se fichará.")
            # Si es festivo o fin de semana, esperar hasta el próximo día laborable
            while es_festivo():
                await asyncio.sleep(3600)
            continue

        # Comprobar si ya se ha fichado hoy (entrada y salida)
        if es_fichaje_realizado_hoy("entrada") and es_fichaje_realizado_hoy("salida"):
            await log_event("Ya se ha fichado entrada y salida hoy. Esperando hasta mañana.")
            await asyncio.sleep(86400)  # Esperar un día completo
            continue
        elif es_fichaje_realizado_hoy("entrada"):
            await log_event("Ya se ha fichado entrada hoy. Esperando hasta la salida.")
            fichaje_horas = get_fichaje_hours()
            if fichaje_horas:
                await esperar_hora(fichaje_horas["clock_out"])
                async with async_playwright() as playwright:
                    page, browser = await login(playwright)
                    if page:
                        await fichar(page, "salida")
                        write_fichaje_log("salida", datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S"))
                        await browser.close()
            else:
                await log_event("No se requiere fichaje de salida hoy.")
        else:
            # Si no hay fichaje de entrada, proceder a fichar
            fichaje_horas = get_fichaje_hours()
            if fichaje_horas:
                await esperar_hora(fichaje_horas["clock_in"])
                async with async_playwright() as playwright:
                    page, browser = await login(playwright)
                    if page:
                        await fichar(page, "entrada")
                        write_fichaje_log("entrada", datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S"))
                        await browser.close()
            else:
                await log_event("No se requiere fichaje de entrada hoy.")
        
        await asyncio.sleep(3600)  # Esperar una hora antes de la próxima iteración

asyncio.run(main())