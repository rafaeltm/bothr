from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from telegram import Bot, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

import config

_bot_token: str | None = None
bot: Bot | None = None
logger = logging.getLogger('bothr')


def refresh_bot() -> Bot | None:
    global bot, _bot_token
    if config.BOT_TOKEN != _bot_token:
        _bot_token = config.BOT_TOKEN
        bot = Bot(token=_bot_token) if _bot_token else None
    return bot


async def send_message(chat_id: str | None, text: str) -> None:
    current_bot = refresh_bot()
    if not current_bot or not chat_id:
        return
    await current_bot.send_message(chat_id=chat_id, text=text)


def _is_authorized_chat(update: Update) -> bool:
    chat = update.effective_chat
    if chat is None or not config.CHAT_ID:
        return False
    return str(chat.id) == str(config.CHAT_ID).strip()


async def _reply_if_authorized(update: Update, text: str) -> None:
    if not _is_authorized_chat(update):
        logger.warning('Ignoring Telegram command from unauthorized chat.')
        return
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(text)


def _format_timestamp(value: str | None) -> str:
    if not value:
        return 'pendiente'
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return value
    return parsed.strftime('%d/%m/%Y %H:%M')


def _format_action(action: str) -> str:
    return {
        'entrada': 'Entrada',
        'salida': 'Salida',
        'ninguna': 'Ninguna',
    }.get(action, action.capitalize())


def _format_help_text() -> str:
    return '\n'.join(
        [
            'Comandos disponibles:',
            '/help - Muestra esta ayuda',
            '/status - Resumen del estado actual',
            '/today - Estado de fichajes de hoy',
            '/next - Próxima acción programada',
            '/calendar - Resumen de festivos y jornadas reducidas',
        ]
    )


def _format_status_text() -> str:
    from bot import scheduler

    payload = scheduler.get_status_payload()
    return '\n'.join(
        [
            'Estado actual:',
            f"Próxima acción: {_format_action(str(payload['next_action']))}",
            f"Programada para: {_format_timestamp(payload.get('next_action_at'))}",
            f"Tiempo restante: {payload['time_remaining']}",
            f"Entrada de hoy: {_format_timestamp(payload.get('today_clocked_in_at'))}",
            f"Salida de hoy: {_format_timestamp(payload.get('today_clocked_out_at'))}",
        ]
    )


def _format_today_text() -> str:
    from bot import scheduler

    now = datetime.now(config.TZ)
    hours = scheduler.get_fichaje_hours(now)
    if hours is None:
        schedule_text = 'Hoy no es laborable.'
    else:
        schedule_text = f"Horario previsto: {hours['clock_in'].strftime('%H:%M')} - {hours['clock_out'].strftime('%H:%M')}"

    payload = scheduler.get_status_payload()
    return '\n'.join(
        [
            f"Hoy ({now.strftime('%d/%m/%Y')}):",
            schedule_text,
            f"Entrada registrada: {_format_timestamp(payload.get('today_clocked_in_at'))}",
            f"Salida registrada: {_format_timestamp(payload.get('today_clocked_out_at'))}",
        ]
    )


def _format_next_text() -> str:
    from bot import scheduler

    payload = scheduler.get_status_payload()
    return '\n'.join(
        [
            'Próxima acción:',
            f"Tipo: {_format_action(str(payload['next_action']))}",
            f"Momento: {_format_timestamp(payload.get('next_action_at'))}",
            f"Tiempo restante: {payload['time_remaining']}",
        ]
    )


def _format_calendar_entries(title: str, values: list[str]) -> list[str]:
    lines = [title]
    if not values:
        lines.append('- Ninguna')
        return lines
    for value in values:
        lines.append(f'- {value}')
    return lines


def _format_calendar_text() -> str:
    today = datetime.now(config.TZ).strftime('%Y-%m-%d')
    festivos = sorted(day for day in config.load_festivos() if day >= today)[:5]
    jornada_reducida = sorted(day for day in config.load_jornada_reducida() if day >= today)[:5]

    lines = ['Calendario:']
    lines.extend(_format_calendar_entries('Próximos festivos configurados:', festivos))
    lines.extend(_format_calendar_entries('Próximas jornadas reducidas configuradas:', jornada_reducida))
    lines.append('Nota: los viernes se consideran jornada reducida automáticamente.')
    return '\n'.join(lines)


async def _help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_if_authorized(update, _format_help_text())


async def _status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_if_authorized(update, _format_status_text())


async def _today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_if_authorized(update, _format_today_text())


async def _next_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_if_authorized(update, _format_next_text())


async def _calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    await _reply_if_authorized(update, _format_calendar_text())


def _build_application() -> Application:
    if not config.BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN no configurado para el listener de Telegram.')

    application = ApplicationBuilder().token(config.BOT_TOKEN).build()
    application.add_handler(CommandHandler('help', _help_command))
    application.add_handler(CommandHandler('status', _status_command))
    application.add_handler(CommandHandler('today', _today_command))
    application.add_handler(CommandHandler('next', _next_command))
    application.add_handler(CommandHandler('calendar', _calendar_command))
    return application


async def _start_application(application: Application) -> None:
    await application.initialize()
    await application.start()
    if application.updater is None:
        raise RuntimeError('Telegram updater no disponible.')
    await application.updater.start_polling()


async def _stop_application(application: Application) -> None:
    if application.updater is not None:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()


async def run_command_listener() -> None:
    application: Application | None = None
    current_token: str | None = None
    waiting_for_token = False

    while True:
        try:
            if not config.BOT_TOKEN:
                if application is not None:
                    await _stop_application(application)
                    application = None
                    current_token = None
                if not waiting_for_token:
                    logger.info('Listener de comandos de Telegram en espera de BOT_TOKEN.')
                    waiting_for_token = True
                await asyncio.sleep(30)
                continue

            waiting_for_token = False
            if config.BOT_TOKEN != current_token:
                if application is not None:
                    await _stop_application(application)
                application = _build_application()
                await _start_application(application)
                current_token = config.BOT_TOKEN
                logger.info('Listener de comandos de Telegram iniciado.')
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            if application is not None:
                await _stop_application(application)
            raise
        except Exception:
            logger.exception('Fallo en el listener de comandos de Telegram.')
            if application is not None:
                try:
                    await _stop_application(application)
                except Exception:
                    logger.exception('No se pudo detener limpiamente el listener de Telegram.')
            application = None
            current_token = None
            await asyncio.sleep(60)


refresh_bot()
