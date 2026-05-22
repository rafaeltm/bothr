from __future__ import annotations

import logging

from playwright.async_api import TimeoutError

import config
from bot import telegram

logger = logging.getLogger('bothr')


def _missing_login_config() -> list[str]:
    """Return required login config keys that are currently missing."""
    missing: list[str] = []
    required_values = {
        'USERNAME': config.USERNAME,
        'PASSWORD': config.PASSWORD,
        'LOGIN_URL': config.LOGIN_URL,
        'LATITUDE': config.LATITUDE,
        'LONGITUDE': config.LONGITUDE,
    }
    for key, value in required_values.items():
        if value in (None, ''):
            missing.append(key)
    return missing


async def login(playwright):
    missing = _missing_login_config()
    if missing:
        logger.error('No se puede iniciar sesión por configuración incompleta.')
        await telegram.send_message(config.CHAT_ID, 'No se puede iniciar sesión por configuración incompleta.')
        return None, None

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        geolocation={'latitude': config.LATITUDE, 'longitude': config.LONGITUDE},
        permissions=['geolocation'],
    )
    page = await context.new_page()

    try:
        logger.info('Iniciando sesión en la plataforma...')
        await page.goto(config.LOGIN_URL, wait_until='networkidle')
        await page.fill('input[name="FrmEntrada[usuario]"]', config.USERNAME)
        await page.fill('input[name="FrmEntrada[clave]"]', config.PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state('networkidle')
        logger.info('Login exitoso.')
        return page, browser
    except TimeoutError:
        message = 'Error: tiempo de espera agotado en el login.'
    except Exception as exc:
        message = f'Error inesperado durante el login: {exc}'

    logger.exception(message) if 'inesperado' in message else logger.error(message)
    await telegram.send_message(config.CHAT_ID, message)
    await browser.close()
    return None, None


async def fichar(page, tipo: str = 'entrada') -> bool:
    if not config.ENABLE:
        logger.info('Fichaje de %s deshabilitado por configuración.', tipo)
        return False

    try:
        await page.wait_for_selector('a[data-bs-target="#ModalPicada"]', timeout=10000)
        await page.click('a[data-bs-target="#ModalPicada"]')
        await page.wait_for_selector('#ModalPicada .modal-content', timeout=10000)
        await page.wait_for_selector('#btnFrmFichar', timeout=10000)
        await page.click('#btnFrmFichar')
        logger.info('Fichaje de %s realizado.', tipo)
        return True
    except TimeoutError:
        message = f'Error: timeout al intentar realizar el fichaje de {tipo}.'
    except Exception as exc:
        message = f'Error inesperado al intentar fichar {tipo}: {exc}'

    logger.exception(message) if 'inesperado' in message else logger.error(message)
    await telegram.send_message(config.CHAT_ID, message)
    return False
