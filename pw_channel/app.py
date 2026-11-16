import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from pw_channel.bootstrap import prepare
from pw_sdk import config as client_config

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).resolve().parent / "static" / "dashboard"


async def _probe_brain(config) -> str:
    from pw_sdk.utils import http

    if not config.PW_CHAT_ENABLED:
        return "disabled (PW_CHAT_ENABLED is off)"
    try:
        response = await http.request("GET", config.PW_CHAT_API_URL, retries=0, timeout=config.PW_CHAT_CONNECT_TIMEOUT_SECS)
        return f"HTTP {response.status_code} · {config.PW_CHAT_API_URL}"
    except Exception as error:
        return f"unreachable at {config.PW_CHAT_API_URL}: {type(error).__name__}"


def validate_platform(client: client_config.ClientConfig) -> None:
    from pw_channel.intake import adapters
    from pw_channel.orchestrator import service

    service.use_templates(None)
    templates = service.templates()
    for intake_id, spec in client.intakes.items():
        if spec.journey and spec.journey not in templates:
            raise RuntimeError(f"intake {intake_id} uses journey {spec.journey!r}, which pw.toml does not define")
    adapters.require([spec.adapter for spec in client.intakes.values()])


@asynccontextmanager
async def lifespan(app: FastAPI):
    from pw_channel import config
    from pw_channel.core import registry
    from pw_channel.db.bootstrap import bring_up
    from pw_channel.intake import intakes
    from pw_channel.settings import watcher as settings_watcher
    from pw_channel.channels.voice.brain import close_client
    from pw_channel.observability import console, log_event, shutdown_logging
    from pw_sdk.utils import http

    client = client_config.current()
    console.note("client", f"{client.client.name} ({client.client.slug})")
    async with console.step("database") as row:
        state = await bring_up()
        row.detail = state.get("url") or "DATABASE_URL is empty"
    if state.get("ready"):
        synced = intakes.sync_from_config(client.intakes)
        console.note("intakes", ", ".join(synced) or "none in pw.toml")
    validate_platform(client)
    await settings_watcher.start()
    for name, channel in registry.active().items():
        await channel.startup()
    console.note("channels", ", ".join(registry.active()) or "none")
    if "voice" in registry.active():
        from pw_channel.channels.voice.stt.factory import warm_up_stt
        from pw_channel.channels.voice.tts.factory import warm_up_tts

        async with console.step("stt"):
            await warm_up_stt()
        async with console.step("tts", config.TTS_PROVIDER):
            await warm_up_tts()
        async with console.step("llm") as row:
            row.detail = await _probe_brain(config)
    log_event("server.started", client=client.client.slug, channels=list(registry.active()))
    console.report()
    yield
    log_event("server.stopping")
    for channel in registry.active().values():
        await channel.shutdown()
    await settings_watcher.stop()
    await close_client()
    await http.close_all()
    shutdown_logging()


def create_app(client: client_config.ClientConfig | None = None) -> FastAPI:
    loaded = prepare(client)
    from pw_channel import config
    from pw_channel.observability import adopt_uvicorn_loggers, configure_logging

    configure_logging(config.LOG_LEVEL, service="channel")
    adopt_uvicorn_loggers()

    from pw_channel.admin import internal
    from pw_channel.core import registry
    from pw_channel.intake import routes as intake_routes
    from pw_channel.channels.voice.routes import calls, control, dynamic
    from pw_channel.channels.voice.routes import ws as ws_routes
    from pw_channel.channels.voice.telephony import registry as telephony

    app = FastAPI(title=f"{loaded.client.name} channel service", version="0.1.0", lifespan=lifespan)
    origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "*").split(",") if item.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    for router in (control.router, calls.router, intake_routes.router, intake_routes.legacy_router, internal.router):
        app.include_router(router)
    for channel in registry.active().values():
        for router in channel.routes():
            app.include_router(router)

    if config.DASHBOARD_ENABLED:
        from pw_channel.admin import brain, data, journeys, secrets, team, usecases
        from pw_channel.admin import routes as admin_routes
        from pw_channel.auth import transport_crypto

        app.add_middleware(transport_crypto.PayloadEncryptionMiddleware)
        for router in (transport_crypto.router, admin_routes.router, team.router, usecases.router, brain.router,
                       secrets.router, data.router, journeys.router):
            app.include_router(router)
        if DASHBOARD_DIR.is_dir():
            app.mount("/dashboard/assets", StaticFiles(directory=DASHBOARD_DIR / "assets"), name="dashboard-assets")

            @app.get("/dashboard", include_in_schema=False)
            @app.get("/dashboard/{path:path}", include_in_schema=False)
            async def dashboard(path: str = ""):
                asset = DASHBOARD_DIR / path
                return FileResponse(asset if path and asset.is_file() else DASHBOARD_DIR / "index.html")

        @app.get("/", include_in_schema=False)
        async def root():
            return RedirectResponse("/dashboard")

    for provider in telephony.all_providers():
        provider.register_routes()
    ws_routes.install_channel_routes
    dynamic.install(app)

    @config.on_reload
    def rebuild_routes(changes: dict) -> None:
        if any(key.startswith("ENABLE_") or key.endswith("_WS_PATH") or key == "ACEFONE_WEBHOOK_PATH" for key in changes):
            dynamic.rebuild("a channel or webhook setting changed")

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        from pw_channel.intake import adapters

        return {"status": "ok", "client": loaded.client.slug, "channels": list(registry.active()),
                "telephony": [provider.status() for provider in telephony.all_providers()], "adapters": adapters.report()}

    return app
