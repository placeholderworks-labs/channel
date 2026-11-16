import argparse
import asyncio
import os
import sys
from pathlib import Path

from pw_sdk import config as client_config


def _load(path: str | None, default_config: Path | None) -> client_config.ClientConfig:
    target = path or os.getenv(client_config.CONFIG_ENV) or (str(default_config) if default_config else None)
    loaded = client_config.load(target)
    if loaded.path:
        os.environ[client_config.CONFIG_ENV] = str(loaded.path)
    return client_config.use(loaded)


def _serve(factory: str, host: str, port: int, reload: bool) -> int:
    import uvicorn

    uvicorn.run(factory, factory=True, host=host, port=port, reload=reload, log_config=None)
    return 0


def run_llm(args) -> int:
    return _serve("pw_llm.app:create_app", args.host, args.port or int(os.getenv("LLM_PORT", "8010")), args.reload)


def run_channel(args) -> int:
    return _serve("pw_channel.app:create_app", args.host, args.port or int(os.getenv("PORT", "8420")), args.reload)


def run_worker(args) -> int:
    from pw_channel.bootstrap import prepare

    prepare()
    from pw_channel import config
    from pw_channel.core import registry
    from pw_channel.orchestrator.worker import Worker
    from pw_channel.observability import configure_logging

    configure_logging(config.LOG_LEVEL, service="worker")

    async def main() -> None:
        from pw_channel.app import validate_platform

        validate_platform(client_config.current())
        for channel in registry.active().values():
            await channel.startup()
        worker = Worker()
        try:
            await worker.run()
        finally:
            for channel in registry.active().values():
                await channel.shutdown()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    return 0


def run_migrate(args) -> int:
    from pw_channel.bootstrap import prepare

    prepare()
    from pw_channel.db.core import init_database
    from pw_channel.intake import intakes

    applied = init_database()
    intakes.ensure_builtin()
    synced = intakes.sync_from_config(client_config.current().intakes)
    print(f"migrations applied: {', '.join(applied) or 'none'}")
    print(f"intakes synced from pw.toml: {', '.join(synced) or 'none'}")
    return 0


def run_check(args) -> int:
    from pw_channel.bootstrap import prepare

    prepare()
    from pw_channel.app import validate_platform
    from pw_channel.intake import adapters

    validate_platform(client_config.current())
    report = adapters.report()
    print(f"adapters: {', '.join(report['loaded'])}")
    print("journeys: " + ", ".join(__import__("pw_channel.orchestrator.service", fromlist=["x"]).templates()))
    print("configuration is valid")
    return 0


def main(argv: list[str] | None = None, default_config: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pw-channel", description="Run the PlaceholderWorks platform for one client")
    parser.add_argument("--config", help="path to pw.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler, help_text in (
        ("llm", run_llm, "start the brain (pw-llm)"),
        ("channel", run_channel, "start the channel service: intake, webhooks, voice, dashboard"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--host", default="0.0.0.0")
        command.add_argument("--port", type=int)
        command.add_argument("--reload", action="store_true")
        command.set_defaults(run=handler)
    commands.add_parser("worker", help="start the journey scheduler worker").set_defaults(run=run_worker)
    commands.add_parser("migrate", help="create or upgrade the database and sync intakes").set_defaults(run=run_migrate)
    commands.add_parser("check", help="validate pw.toml, adapters and journeys").set_defaults(run=run_check)
    args = parser.parse_args(argv)
    _load(args.config, default_config)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
