from __future__ import annotations

import asyncio
import json
import threading

import config
from bot import scheduler, telegram
from dashboard.app import run_dashboard



def ensure_runtime_files() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    defaults = {
        config.FESTIVOS_FILE: {'festivos': ['2025-04-17', '2025-04-18']},
        config.JORNADA_REDUCIDA_FILE: {'dias': ['2025-04-14', '2025-04-15', '2025-04-16']},
        config.FICHAJE_FILE: [],
    }

    for path, payload in defaults.items():
        if path.exists():
            continue
        config.ensure_parent(path)
        with path.open('w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    ensure_runtime_files()
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True, name='dashboard-thread')
    dashboard_thread.start()

    async def run_services() -> None:
        await asyncio.gather(
            scheduler.run(),
            telegram.run_command_listener(),
        )

    asyncio.run(run_services())
