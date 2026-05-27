# Bothr

## Project overview

Bothr automates daily clock-in and clock-out actions with Playwright and exposes a Bootstrap-based Flask dashboard for operational control. The bot and dashboard run in the same Python process: the scheduler stays in the main thread and the dashboard runs in a daemon thread.

## Quick start with docker-compose

1. Create a `.env` file with the required variables.
   - Runtime changes made from the dashboard are persisted to `data/runtime.env` (mounted volume) and survive container redeploys.
2. Generate TLS certificates for your server's IP address (run once):

```bash
./scripts/gen_certs.sh <YOUR_SERVER_IP>
# Example: ./scripts/gen_certs.sh 192.168.1.50
```

3. Build and start the service:

```bash
docker-compose up --build -d
```

4. Open the dashboard at `https://<YOUR_SERVER_IP>` or `https://<YOUR_SERVER_IP>:5822`.
5. Dashboard access is transparent at app level because deployment access is expected through VPN/network perimeter controls.

> **Note:** The first time you access the dashboard you will get a browser warning unless you install the generated CA root certificate (`certs/ca.crt`) on your device. See [HTTPS / TLS setup](#https--tls-setup) below for per-OS instructions.

## HTTPS / TLS setup

The stack uses a self-signed CA so that HTTPS works by IP address without any external domain or Let's Encrypt dependency. Nginx terminates TLS and proxies traffic to the Flask app internally. Externally, HTTPS is exposed on ports `443` and `5822` (both mapped to the same internal TLS endpoint). Port 80 redirects to HTTPS automatically.

### Generating certificates

```bash
# Replace with the actual IP of your server
./scripts/gen_certs.sh 192.168.1.50

# Or pass it via an env variable
SERVER_IP=192.168.1.50 ./scripts/gen_certs.sh
```

This creates three files in `certs/` (excluded from git):
- `ca.crt` — CA root certificate — **install this once on every client device**
- `server.crt` / `server.key` — used by nginx (no action needed)

### Installing the CA root certificate

Install `certs/ca.crt` on every device that will access the dashboard so the browser shows a valid padlock instead of a warning.

**macOS**
```bash
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain certs/ca.crt
```

**Linux (Ubuntu / Debian)**
```bash
sudo cp certs/ca.crt /usr/local/share/ca-certificates/bothr-ca.crt
sudo update-ca-certificates
```

**Linux (RHEL / Fedora)**
```bash
sudo cp certs/ca.crt /etc/pki/ca-trust/source/anchors/bothr-ca.crt
sudo update-ca-trust
```

**Windows**
1. Open `certlm.msc`
2. Go to **Trusted Root Certification Authorities → Certificates**
3. Right-click → **All Tasks → Import** → select `certs/ca.crt`

**Android (Chrome)**
Settings → Security → Install a certificate → CA certificate → select the file.

**iPhone / iPad (Safari)**
1. Transfer `ca.crt` to the device (AirDrop, email, etc.)
2. Settings → General → VPN & Device Management → Install Profile
3. Settings → General → About → Certificate Trust Settings → enable full trust for the bothr CA

### Regenerating certificates

Run `./scripts/gen_certs.sh` again with the new IP, then restart the stack (`docker-compose up -d --no-build`). The CA root certificate you already installed on client devices remains valid — only the server certificate changes, so no re-installation is needed on client devices.

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
| `TEAMLEADER_ENABLED` | No | Enables Teamleader integration. Default: `false`. |
| `TEAMLEADER_CLIENT_ID` | No | Teamleader OAuth client ID. Required to connect Teamleader. |
| `TEAMLEADER_CLIENT_SECRET` | No | Teamleader OAuth client secret. Required to connect Teamleader. |
| `TEAMLEADER_REDIRECT_URI` | No | OAuth callback URL (must point to `/api/integrations/teamleader/callback`). |
| `TEAMLEADER_AUTH_BASE_URL` | No | Teamleader OAuth base URL. Default: `https://focus.teamleader.eu`. |
| `TEAMLEADER_API_BASE_URL` | No | Teamleader API base URL. Default: `https://api.focus.teamleader.eu`. |
| `TEAMLEADER_ACCESS_TOKEN` | No | Teamleader OAuth access token (managed automatically after connect). |
| `TEAMLEADER_REFRESH_TOKEN` | No | Teamleader OAuth refresh token (managed automatically after connect). |
| `TEAMLEADER_TOKEN_EXPIRES_AT` | No | ISO timestamp for Teamleader token expiration (managed automatically). |
| `TEAMLEADER_ACCOUNT_ID` | No | Optional Teamleader account/organization identifier. |
| `TEAMLEADER_USER_ID` | No | Teamleader user UUID used to keep only entries from a specific user in listings/analysis/summary and when reusing yesterday's task for auto-entry. |
| `TEAMLEADER_TASK_ID` | No | Teamleader task UUID used in `timeTracking.list` as `filter.subject` with type `nextgenTask`. |
| `TEAMLEADER_TASK_TYPE` | No | Subject type used together with `TEAMLEADER_TASK_ID` in `timeTracking.list`. Default: `nextgenTask`. |
| `TEAMLEADER_PAGE_SIZE` | No | Page size (1-100) used to paginate and aggregate all `timeTracking.list` results. Default: `100`. |
| `TEAMLEADER_WORKDAY_START` | No | Exact start time (`HH:MM`) used for Teamleader hour analysis. Default: `08:00`. |
| `TEAMLEADER_WORKDAY_END` | No | Exact end time (`HH:MM`) used for Teamleader hour analysis. Default: `17:00`. |

> **Persistence note:** dashboard/API setting updates (including Teamleader tokens) are stored in both `.env` and `data/runtime.env`. On startup, `data/runtime.env` is loaded with priority so values survive container recreation when `data/` is persisted.

## Dashboard features

- **Dashboard**: live view of the next action, countdown, today's clock-in/clock-out state, the preferred clock-in reference, and the planned schedule.
- **Settings**: update environment-backed configuration, preserve masked secrets, test Telegram delivery, and manage Teamleader integration (OAuth connect, task selection, exact-hour analysis).
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
| `POST` | `/api/integrations/teamleader/connect` | Starts Teamleader OAuth flow and returns authorization URL. |
| `GET` | `/api/integrations/teamleader/callback` | OAuth callback endpoint that stores Teamleader tokens. |
| `POST` | `/api/integrations/teamleader/test` | Validates Teamleader connection (`users.me`) and refreshes token if needed. |
| `POST` | `/api/integrations/teamleader/disconnect` | Clears Teamleader token/session fields from `.env`. |
| `GET` | `/api/integrations/teamleader/entries` | Lists Teamleader fichajes/time entries for a date range. |
| `GET` | `/api/integrations/teamleader/analysis` | Returns expected vs clocked hours analysis for a date range. |
| `GET` | `/api/integrations/teamleader/dashboard-summary` | Returns Teamleader totals for the current day/week/month and whether today already has records. |
| `GET` | `/api/festivos` | Returns the configured holidays. |
| `POST` | `/api/festivos` | Replaces the configured holidays list. |
| `GET` | `/api/jornada_reducida` | Returns reduced-workday dates. |
| `POST` | `/api/jornada_reducida` | Replaces reduced-workday dates. |
| `GET` | `/api/status` | Returns the next scheduler action and today's fichaje status. |
| `GET` | `/api/logs` | Returns the last 100 lines of `logs/general.log`. |

## Teamleader setup notes

1. Register an OAuth app in Teamleader.
2. Configure `TEAMLEADER_CLIENT_ID`, `TEAMLEADER_CLIENT_SECRET` and `TEAMLEADER_REDIRECT_URI`.
3. Set redirect URI to this dashboard callback:
   - `https://<your-host>/api/integrations/teamleader/callback`
4. In Settings, define `TEAMLEADER_USER_ID` (your Teamleader user UUID) so only your fichajes are counted. Optionally define `TEAMLEADER_TASK_ID` (task UUID) and `TEAMLEADER_TASK_TYPE` (default `nextgenTask`) so requests also apply `subject: { type, id }`. You can tune `TEAMLEADER_PAGE_SIZE` (1-100) for `timeTracking.list` pagination. Configure exact hours (`TEAMLEADER_WORKDAY_START`, `TEAMLEADER_WORKDAY_END`) to analyze tracked time (for example `08:00` to `17:00`); Teamleader analysis uses the same working calendar as the scheduler (weekends/holidays excluded).
5. Use **Conectar Teamleader** in Settings to complete OAuth and persist tokens.

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
