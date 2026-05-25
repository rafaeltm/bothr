from __future__ import annotations

from flask import Flask, redirect, render_template, send_from_directory, url_for

import config

app = Flask(__name__)

from dashboard.routes.calendar import calendar_bp  # noqa: E402
from dashboard.routes.settings import settings_bp  # noqa: E402

app.register_blueprint(settings_bp)
app.register_blueprint(calendar_bp)


@app.get('/')
def root():
    return redirect(url_for('dashboard'))


@app.get('/dashboard')
def dashboard():
    return render_template('index.html')


@app.get('/offline')
def offline():
    return render_template('offline.html'), 200


@app.get('/sw.js')
def service_worker():
    response = send_from_directory(app.static_folder, 'js/sw.js')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@app.get('/manifest.json')
def web_manifest():
    response = send_from_directory(app.static_folder, 'manifest.json')
    response.headers['Cache-Control'] = 'no-cache'
    return response



def run_dashboard() -> None:
    app.run(host='0.0.0.0', port=config.DASHBOARD_PORT, threaded=True, use_reloader=False)


if __name__ == '__main__':
    run_dashboard()
