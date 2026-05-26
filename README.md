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

## Multi-architecture Docker image

The `Build and Push Docker Image` GitHub Actions workflow now publishes a manifest image for:

- `linux/amd64`
- `linux/arm64`

This allows `docker pull ghcr.io/<owner>/cactushr_bot:latest` to work on both standard x86_64 hosts and ARM64 devices (replace `<owner>` with your GitHub user or org, for example `rafaeltm`).

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
| `PREFERRED_CLOCK_IN` | No | Preferred reference time used to calculate planned exit time; planned entry applies a daily ±15 minute margin around it. Default: `08:00`. |
| `DASHBOARD_PASSWORD` | No | HTTP Basic Auth password for the dashboard. Default: `admin`. |
| `DASHBOARD_PORT` | No | Flask dashboard port. Default: `5000`. |

## Dashboard features

- **Dashboard**: live view of the next action, countdown, today's clock-in/clock-out state, the preferred clock-in reference, and the planned schedule.
- **Settings**: update environment-backed configuration, preserve masked secrets, and test Telegram delivery.
- **Calendar**: maintain holidays and reduced-workdays with a clickable month grid plus JSON import/export.
- **Logs**: inspect the latest scheduler logs and current fichaje state with auto-refresh.
- **PWA installable app**: install the dashboard on iPhone/Android home screen with offline shell and dedicated standalone mode.

## Install as a PWA (without App Store)

The dashboard supports Progressive Web App (PWA) installation, so it can be used like an app icon on the home screen.

### iPhone (Safari)

1. Open the dashboard URL in Safari.
2. Tap **Share**.
3. Tap **Add to Home Screen**.
4. Open Bothr from the new home-screen icon.

### Android (Chrome/Edge)

1. Open the dashboard URL in the browser.
2. Use **Install app** / **Add to Home screen** from the browser menu (or the install prompt).
3. Launch Bothr from the installed icon.

### Important limitations

- This is a **PWA**, not a native iOS app distributed via App Store.
- Installing does **not** require App Store publication.
- Live scheduler data and API-backed views still require internet connectivity.
- Offline mode keeps the app shell available and provides an offline fallback page.

## Telegram commands

The bot still sends scheduler notifications to `CHAT_ID`, and it now also answers read-only commands in that same configured chat:

- `/help` — lists the available commands.
- `/status` — shows the current summary, including next action and today's fichajes.
- `/today` — shows today's planned schedule plus recorded entry/exit times.
- `/next` — shows the next scheduled action and the remaining time.
- `/calendar` — shows the next configured holidays and reduced-workday dates.

For safety, command responses are restricted to the configured `CHAT_ID`.

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

The root `fichaje.py` file is **deprecated** and kept only for history/compatibility; it is not maintained as runtime logic. The maintained implementation lives in `bot/` and `dashboard/`, and the supported entrypoint is `python main.py`.

## License

This project is distributed under the MIT License.
