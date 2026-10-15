import asyncio
import logging
import os
import signal

import click
import uvicorn

from dash.config import Settings


@click.group()
def main() -> None:
    """dash: always-on assistant in front of hermes-agent."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@main.command()
def migrate() -> None:
    """Upgrade the database schema to head. Needs DATABASE_URL."""
    from dash.db import migrate as run

    run(Settings.from_env().database_url)


@main.command()
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Address to bind. Use 0.0.0.0 only inside a container.",
)
@click.option("--port", default=8000, show_default=True, help="Port to bind.")
def serve(*, host: str, port: int) -> None:
    """Run the web UI and API."""
    uvicorn.run("dash.web:create_production_app", factory=True, host=host, port=port)


@main.command()
@click.option(
    "--source",
    "-s",
    "specs",
    multiple=True,
    envvar="SCRAPE_SOURCES",
    help="web:<url>. Repeatable, or space-separated in SCRAPE_SOURCES.",
)
@click.option("--dry-run", is_flag=True, help="Fetch and print new items without enqueuing.")
def scrape(*, specs: tuple[str, ...], dry_run: bool) -> None:
    """Fetch real-world updates and enqueue new ones for the worker. Run it from a cron."""
    from dash.sources.common import Source
    from dash.sources.web import run

    try:
        sources = [Source.parse(spec) for spec in specs]
    except ValueError as ex:
        raise click.BadParameter(str(ex), param_hint="--source") from ex
    if not sources:
        raise click.UsageError("No sources: pass --source or set SCRAPE_SOURCES.")
    # Scraping only needs Redis, so don't demand DATABASE_URL like Settings.from_env().
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    report = asyncio.run(run(sources, redis_url, dry_run=dry_run))
    for item in report.enqueued:
        click.echo(f"{'new' if dry_run else 'enqueued'} {item.source} {item.title} <{item.url}>")
    for source, error in report.failed.items():
        click.echo(f"failed {source}: {error}", err=True)
    click.echo(
        f"{len(sources)} sources, {report.found} items, {len(report.enqueued)} new, "
        f"{len(report.failed)} failed",
        err=True,
    )
    # Only fail the cron run when nothing worked, so one flaky site doesn't page anyone.
    if report.failed and len(report.failed) == len(sources):
        raise SystemExit(1)


@main.command()
def worker() -> None:
    """Consume the job queue and answer through hermes."""
    asyncio.run(_worker())


async def _worker() -> None:
    from dash.db import Store
    from dash.hermes import Hermes
    from dash.memory import Bedrock
    from dash.queue import Queue
    from dash.worker import Worker

    settings = Settings.from_env()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    bedrock = Bedrock(settings.embed_model, settings.extract_model)
    hermes = Hermes(settings.hermes_base_url, settings.hermes_api_key, settings.hermes_model)
    queue = Queue.from_url(settings.redis_url)
    async with Store.connect(settings.database_url) as store:
        try:
            await Worker(
                store=store,
                queue=queue,
                chat=hermes,
                embedder=bedrock,
                extractor=bedrock,
                top_k=settings.memory_top_k,
            ).run(stop)
        finally:
            await hermes.close()
            await queue.close()
