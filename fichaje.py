"""Módulo legado (DEPRECATED).

Este archivo se conserva solo por historial y compatibilidad de ruta.
La implementación mantenida vive en `bot/` y `dashboard/`.

Si se ejecuta directamente, delega al entrypoint actual (`main.py`).
"""

from __future__ import annotations

import runpy
import warnings


if __name__ == '__main__':
    warnings.warn(
        'fichaje.py raíz está deprecado; usa `python main.py`.',
        DeprecationWarning,
        stacklevel=2,
    )
    runpy.run_module('main', run_name='__main__')
