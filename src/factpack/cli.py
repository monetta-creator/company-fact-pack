"""factpack CLI: ask / search / metrics / entity / events / cost / serve."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _print_result(res) -> None:
    console.print(res.answer)
    console.print()
    if res.verify.flags:
        console.print("[bold red]VERIFY FLAGS[/bold red]")
        for f in res.verify.flags:
            console.print(f"  [{f['kind']}] {f['excerpt']!r}: {f['issue']}")
    else:
        console.print(
            f"[green]verified[/green]: {res.verify.quotes_checked} quotes, "
            f"{res.verify.numbers_checked} numbers, {res.verify.model_checked} claims checked"
        )
    if res.audit:
        console.print(f"[yellow]dropped citations (audit)[/yellow]: {res.audit}")
    console.print(f"[dim]citations: {res.citations}[/dim]")


@app.command()
def ask(question: str, deep: bool = typer.Option(False, "--deep"),
        fast: bool = typer.Option(False, "--fast", help="skip the model verify pass")):
    """Grounded, gated, verified answer over the compiled corpus."""
    if deep:
        from factpack.deep import deep_ask

        res = deep_ask(question, on_status=lambda m: console.print(f"[dim]{m}[/dim]"))
    else:
        from factpack.answer import ask as do_ask

        res = do_ask(question, skip_model_verify=fast)
    _print_result(res)


@app.command()
def search(query: str, limit: int = 10):
    """Raw hybrid retrieval (RRF + rerank), no generation."""
    from factpack.retrieve import retrieve_chunks

    for c in retrieve_chunks(query, {}, top_n=limit):
        console.print(f"[bold]{c['doc_id']}[/bold] §{c['section_id']} "
                      f"(score {c['rerank_score']:.2f})")
        console.print(f"  {c['preamble']}")


@app.command()
def metrics(hint: str, entity: str = typer.Option(None), period: str = typer.Option(None)):
    """Query the governed metric store (D3)."""
    from factpack import metrics_sql

    defs = metrics_sql.find_metrics(hint)
    if not defs:
        console.print("no matching metric definitions")
        raise typer.Exit(1)
    obs = metrics_sql.query_observations(
        [d["metric_id"] for d in defs], entity_id=entity, period_prefix=period
    )
    t = Table("metric", "entity", "period", "value", "unit", "source")
    for o in obs[:40]:
        t.add_row(o["metric_id"], o["entity_id"], o["period"],
                  f"{o['value']:,.2f}", o["unit"], o["source_doc"])
    console.print(t)


@app.command()
def entity(entity_id: str):
    from factpack import db as dblib

    db = dblib.connect()
    row = db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if not row:
        console.print(f"unknown entity {entity_id!r}")
        raise typer.Exit(1)
    console.print(json.dumps(dict(row), indent=2))


@app.command()
def events(entity: str = typer.Option(None), limit: int = 20):
    from factpack import db as dblib

    db = dblib.connect()
    if entity:
        rows = db.execute(
            "SELECT * FROM events WHERE entity_ids LIKE ? ORDER BY date DESC LIMIT ?",
            (f'%"{entity}"%', limit),
        )
    else:
        rows = db.execute("SELECT * FROM events ORDER BY date DESC LIMIT ?", (limit,))
    t = Table("date", "type", "title")
    for r in rows:
        t.add_row(r["date"], r["type"], r["title"][:90])
    console.print(t)


@app.command()
def cost():
    """Metered model spend (D10)."""
    from factpack.model import cost_rollup

    t = Table("feature", "calls", "input tok", "output tok", "cost USD")
    for feature, calls, itok, otok, usd in cost_rollup():
        t.add_row(str(feature), str(calls), f"{itok or 0:,}", f"{otok or 0:,}",
                  f"${usd or 0:.4f}")
    console.print(t)


@app.command()
def serve(port: int = 8787):
    """FastAPI answer surface with peek panels and verify flags."""
    import uvicorn

    uvicorn.run("factpack.server:app", port=port, log_level="warning")


if __name__ == "__main__":
    app()
