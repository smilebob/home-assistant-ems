"""FastAPI Web Server for Smart Residential EMS with native WebSockets & Ingress support."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config, EMSConfig
from .engine import EMSEngine
from .ha_client import HAClient
from .mqtt_client import EMSMQTTClient
from .storage import EMSStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_LOGGER = logging.getLogger("ems.main")

config = load_config()
storage = EMSStorage(config.data_dir)
ha_client = HAClient(config.ha_url, config.ha_token, config.ha_verify_ssl)

mqtt_client = None
if config.mqtt_enabled and config.mqtt_host:
    mqtt_client = EMSMQTTClient(
        host=config.mqtt_host,
        port=config.mqtt_port,
        username=config.mqtt_username,
        password=config.mqtt_password,
        topic_prefix=config.mqtt_topic_prefix,
        discovery_prefix=config.mqtt_discovery_prefix,
    )

engine = EMSEngine(config, ha_client, storage, mqtt_client)

app = FastAPI(
    title="Smart Residential EMS",
    description="Standalone EMS & Home Assistant Ingress Web Application",
    version="2.0.0",
    root_path=config.ingress_path,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize clients and start background orchestrations."""
    _LOGGER.info("Starting Smart Residential EMS Web Application...")
    # 1. Fetch initial HA states
    await ha_client.fetch_initial_states()
    # 2. Start HA WebSocket listener in background
    asyncio.create_task(ha_client.start_websocket_listener())
    # 3. Start MQTT Client if enabled
    if mqtt_client:
        asyncio.create_task(mqtt_client.start())
    # 4. Start periodic optimization engine loop
    asyncio.create_task(engine.run_loop())


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    """Return the latest EMS operational state."""
    return engine.latest_result or await engine.execute_arbitration_cycle()


@app.get("/api/history")
async def get_history(
    hours: int = 24,
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent telemetry from SQLite for time-series charts (relative or absolute range)."""
    return storage.get_recent_telemetry(hours=hours, start_time=start_time, end_time=end_time)


@app.get("/api/history/daily-solar")
async def get_daily_solar(days: int = 7) -> list[dict[str, Any]]:
    """Return aggregated daily solar energy (kWh): Solcast predicted vs Actual production."""
    return storage.get_daily_solar_comparison(days=days)


@app.get("/api/decisions")
async def get_decisions(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent decision explanation logs."""
    return storage.get_recent_decisions(limit=limit)


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    """Return current configuration."""
    return config.dict()


@app.post("/api/ml/retrain")
async def trigger_ml_retrain() -> dict[str, Any]:
    """Force manual retraining and reinforcement of ML models with latest observations."""
    res = engine.retrain_models()
    return {"status": "ok", "result": res}


@app.post("/api/config")
async def update_config(updates: dict[str, Any]) -> dict[str, Any]:
    """Dynamically update EMS configuration, reload runtime parameters, and persist to options.json."""
    for key, val in updates.items():
        if hasattr(config, key):
            setattr(config, key, val)

    # Propagate immediate runtime flags to arbitrator
    if "auto_mode" in updates:
        engine.arbitrator.auto_mode_enabled = bool(updates["auto_mode"])
    if "force_dhw_boost" in updates:
        engine.arbitrator.force_dhw_boost = bool(updates["force_dhw_boost"])
    if "force_tesla_charge" in updates:
        engine.arbitrator.force_tesla_charge = bool(updates["force_tesla_charge"])
    if "allow_thermal_overheat" in updates:
        engine.arbitrator.allow_thermal_overheat = bool(updates["allow_thermal_overheat"])

    # Persist to /data/options.json (HA Add-on) or ./config.json (Standalone Docker)
    options_file = "/data/options.json" if os.path.exists("/data") else "config.json"
    try:
        current_data = {}
        if os.path.exists(options_file):
            with open(options_file, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        current_data.update(updates)
        with open(options_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, indent=2)
        _LOGGER.info("Configuration updated and saved to %s", options_file)
    except Exception as err:
        _LOGGER.warning("Could not persist updated options to %s: %s", options_file, err)

    return {"status": "ok", "config": config.dict()}


@app.post("/api/action")
async def perform_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger manual override actions (e.g. force DHW boost, force Tesla charge, toggle auto mode)."""
    action = payload.get("action")
    value = payload.get("value", True)

    if action == "auto_mode":
        engine.arbitrator.auto_mode_enabled = bool(value)
        config.auto_mode = bool(value)
    elif action == "force_dhw_boost":
        engine.arbitrator.force_dhw_boost = bool(value)
        config.force_dhw_boost = bool(value)
    elif action == "force_tesla_charge":
        engine.arbitrator.force_tesla_charge = bool(value)
        config.force_tesla_charge = bool(value)
    elif action == "allow_thermal_overheat":
        engine.arbitrator.allow_thermal_overheat = bool(value)
        config.allow_thermal_overheat = bool(value)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    # Immediately re-evaluate cycle and return updated state
    res = await engine.execute_arbitration_cycle()
    return {"status": "ok", "action": action, "value": value, "state": res}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Live streaming WebSocket connection pushing power flows and priority updates to UI."""
    await websocket.accept()

    # Send initial state immediately
    if engine.latest_result:
        await websocket.send_text(json.dumps(engine.latest_result))

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def subscriber(payload: dict[str, Any]) -> None:
        queue.put_nowait(payload)

    engine.subscribe_ws(subscriber)

    try:
        while True:
            # Wait for either engine updates or client messages
            recv_task = asyncio.create_task(websocket.receive_text())
            queue_task = asyncio.create_task(queue.get())

            done, pending = await asyncio.wait(
                [recv_task, queue_task], return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            if queue_task in done:
                data = queue_task.result()
                await websocket.send_text(json.dumps(data))

            if recv_task in done:
                client_msg = recv_task.result()
                # Process any client ping / commands
                _LOGGER.debug("WS client message received: %s", client_msg)

    except (WebSocketDisconnect, asyncio.CancelledError):
        _LOGGER.debug("WebSocket client disconnected")
    finally:
        engine.unsubscribe_ws(subscriber)


# Mount compiled static frontend assets if available
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist"))
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    async def index_placeholder() -> HTMLResponse:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Smart Residential EMS</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 80vh; text-align: center; }
                .card { background: #1e293b; padding: 2rem; border-radius: 1rem; border: 1px solid #334155; max-width: 600px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
                h1 { color: #38bdf8; margin-top: 0; }
                p { color: #94a3b8; line-height: 1.6; }
                .badge { display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; background: #0284c7; color: white; font-weight: bold; font-size: 0.85rem; margin-bottom: 1rem; }
                a { color: #38bdf8; text-decoration: none; font-weight: bold; }
                code { background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 0.25rem; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="badge">Backend FastAPI & WebSockets v2.0.0 Actif</div>
                <h1>Smart Residential EMS</h1>
                <p>Le serveur backend FastAPI et le moteur d'arbitrage EMS sont opérationnels.</p>
                <p>Pour consulter l'état JSON temps réel : <a href="/api/state">/api/state</a><br>
                Documentation Swagger : <a href="/docs">/docs</a></p>
                <p>L'interface React + Vite + Tailwind est prête à être construite.</p>
            </div>
        </body>
        </html>
        """)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.backend.main:app", host="0.0.0.0", port=config.port, reload=False)
