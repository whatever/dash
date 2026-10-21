import asyncio
import logging
import os
import signal
from typing import TYPE_CHECKING

import click
import uvicorn

from dash.config import Settings

if TYPE_CHECKING:
    from dash.sources.common import Report, Source


@click.group()
def main() -> None:
    """dash: always-on assistant with its own agent, memories and connected apps."""
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

    try:
        sources = [Source.parse(spec) for spec in specs]
    except ValueError as ex:
        raise click.BadParameter(str(ex), param_hint="--source") from ex
    database_url = os.environ.get("DATABASE_URL")
    if not sources and not database_url:
        raise click.UsageError(
            "No sources: pass --source, set SCRAPE_SOURCES, or set DATABASE_URL."
        )
    # DATABASE_URL is optional here: without it, only the --source list runs.
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    sources, report = asyncio.run(_scrape(sources, redis_url, database_url, dry_run=dry_run))
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


async def _scrape(
    sources: list["Source"], redis_url: str, database_url: str | None, *, dry_run: bool
) -> tuple[list["Source"], "Report"]:
    """Return every scraped source and the report for the given and the due stored sources."""
    from datetime import UTC, datetime

    from dash.db import Store
    from dash.sources.common import Source
    from dash.sources.db import SourceStore
    from dash.sources.scrape import run

    if not database_url:
        return sources, await run(sources, redis_url, dry_run=dry_run)
    now = datetime.now(UTC)
    async with Store.connect(database_url) as store:
        stored = SourceStore(store.sessions)
        due = await stored.due(now)
        sources = list(dict.fromkeys([*sources, *(Source(row.kind, row.target) for row in due)]))
        report = await run(sources, redis_url, dry_run=dry_run)
        if not dry_run:
            await stored.mark_checked([row.id for row in due], now)
    return sources, report


@main.command()
def worker() -> None:
    """Consume the job queue and answer with the agent."""
    asyncio.run(_worker())


async def _worker() -> None:
    from pathlib import Path

    import httpx
    from pydantic_ai import UsageLimits
    from pydantic_ai.toolsets import AbstractToolset

    from dash.agent import Engine, build_agent, build_model, mcp
    from dash.agent.deps import TurnDeps
    from dash.agent.policy import ToolPolicy
    from dash.agent.sandbox import Sandbox, private_key_copy
    from dash.agent.tools import inbox_tools, memory_tools, sandbox_tools, web_tools
    from dash.agent.web import Fetcher
    from dash.db import Store
    from dash.inbox.db import InboxStore
    from dash.memory import Bedrock
    from dash.queue import Queue
    from dash.worker import Worker

    settings = Settings.from_env()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    bedrock = Bedrock(settings.embed_model, settings.extract_model)
    model = build_model(settings.agent_model, settings.agent_base_url, settings.agent_api_key)
    policy = ToolPolicy.parse(settings.agent_tool_policy)
    servers = [mcp.ServerTools.connect(s) for s in mcp.parse(settings.agent_mcp_servers)]
    queue = Queue.from_url(settings.redis_url)
    async with (
        Store.connect(settings.database_url) as store,
        httpx.AsyncClient(timeout=20, headers={"User-Agent": "dash"}) as http,
    ):
        inbox = InboxStore(store.sessions)
        toolsets: list[AbstractToolset[TurnDeps]] = [
            web_tools(Fetcher(http)),
            memory_tools(store, bedrock),
            inbox_tools(inbox),
        ]
        if settings.sandbox_host:
            key = private_key_copy(Path(settings.sandbox_key_path))
            sandbox = Sandbox(
                settings.sandbox_host, settings.sandbox_port, settings.sandbox_user, key
            )
            toolsets.append(sandbox_tools(sandbox))
        agent = build_agent(
            model,
            toolsets=toolsets,
            policy=policy,
            web_search=settings.agent_web_search,
            thinking=settings.agent_thinking,
        )
        limits = UsageLimits(
            request_limit=settings.agent_request_limit,
            tool_calls_limit=settings.agent_tool_call_limit,
        )
        engine = Engine(agent, limits, servers=servers, policy=policy)
        try:
            await Worker(
                store=store,
                inbox=inbox,
                queue=queue,
                agent=engine,
                embedder=bedrock,
                extractor=bedrock,
                top_k=settings.memory_top_k,
            ).run(stop)
        finally:
            await queue.close()
