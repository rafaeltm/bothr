# Bothr

## Project overview

Bothr automates daily clock-in and clock-out actions with Playwright and exposes a Bootstrap-based Flask dashboard for operational control. The bot and dashboard run in the same Python process: the scheduler stays in the main thread and the dashboard runs in a daemon thread.

## Quick start with docker-compose

1. Create a `.env` file with the required variables.
2. Build and start the service:

```bash
docker-compose up --build -d
```

3. Open the dashboard at `http://localhost:5000`.
4. Authenticate with username `admin` and the password defined in `DASHBOARD_PASSWORD` (defaults to `admin`).

## Environment variables

| Name | Required | Description |
| --- | --- | --- |
| `USERNAME` | Yes | Username used by the external fichaje platform. |
| `PASSWORD` | Yes | Password used by the external fichaje platform. |
| `CHAT_ID` | Yes | Telegram chat ID that receives bot notifications. |
| `BOT_TOKEN` | Yes | Telegram bot token used for alerts and tests. |
| `ENABLE` | No | Enables real clock actions when set to `true`. Default: `false`. |
| `LATITUDE` | Yes | Latitude sent to Playwright geolocation. |
| `LONGITUDE` | Yes | Longitude sent to Playwright geolocation. |
| `LOGIN_URL` | Yes | Login URL for the fichaje platform. |
| `FICHAJE_FILE` | No | Path to the fichaje history JSON file. Default: `data/fichaje.json`. |
| `FESTIVOS_FILE` | No | Path to the holidays JSON file. Default: `data/festivos.json`. |
| `JORNADA_REDUCIDA_FILE` | No | Path to the reduced-workday JSON file. Default: `data/jornada_reducida.json`. |
| `DASHBOARD_PASSWORD` | No | HTTP Basic Auth password for the dashboard. Default: `admin`. |
| `DASHBOARD_PORT` | No | Flask dashboard port. Default: `5000`. |

## Dashboard features

- **Dashboard**: live view of the next action, countdown, and today's clock-in/clock-out state.
- **Settings**: update environment-backed configuration, preserve masked secrets, and test Telegram delivery.
- **Calendar**: maintain holidays and reduced-workdays with a clickable month grid plus JSON import/export.
- **Logs**: inspect the latest scheduler logs and current fichaje state with auto-refresh.

## API endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/settings` | Returns the current configuration with secret fields masked. |
| `POST` | `/api/settings` | Saves configuration values to `.env` and reloads them. |
| `POST` | `/api/test-telegram` | Sends a Telegram test message. |
| `GET` | `/api/festivos` | Returns the configured holidays. |
| `POST` | `/api/festivos` | Replaces the configured holidays list. |
| `GET` | `/api/jornada_reducida` | Returns reduced-workday dates. |
| `POST` | `/api/jornada_reducida` | Replaces reduced-workday dates. |
| `GET` | `/api/status` | Returns the next scheduler action and today's fichaje status. |
| `GET` | `/api/logs` | Returns the last 100 lines of `logs/general.log`. |

## Development setup

1. Install Python 3.11+.
2. Install dependencies:

```bash
pip install -r requirements.txt
python -m playwright install
```

3. Create a `.env` file.
4. Run the combined service locally:

```bash
python main.py
```

The root `fichaje.py` file is intentionally kept for history, while the maintained implementation lives in `bot/` and `dashboard/`.

## License

This project is distributed under the MIT License.
