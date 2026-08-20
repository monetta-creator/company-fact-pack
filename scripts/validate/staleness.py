"""Decay policy (rule 6): report briefs past review_by and sources gone quiet.

Always writes build/staleness_report.md. Exit code is 0 unless a brief lacks
review_by entirely (schema_check also catches that).
"""

from __future__ import annotations

import datetime as dt

import yaml

from factpack import config, manifest as mlib
from scripts.validate.schema_check import parse_frontmatter

# expected max age (days) of the newest doc per source, by cadence in PLAN.md §4
CADENCE_DAYS = {
    "edgar-cof": 100,      # 10-Q quarterly
    "edgar-comet": 40,     # 10-D monthly
    "edgar-dcent": 40,
    "fdic": 120,
    "cfpb-complaints": 120,
    "cfpb-agreements": 150,
}


def main() -> int:
    today = dt.date.today()
    lines = [f"# Staleness report — {today}\n"]

    overdue = []
    for path in sorted((config.ROOT / "briefs").glob("*.md")):
        fm = parse_frontmatter(path.read_text())
        rb = dt.date.fromisoformat(fm["review_by"])
        if rb < today:
            overdue.append(f"- brief `{fm['id']}` review_by {rb} ({(today - rb).days}d overdue)")
    lines.append(f"## Briefs past review_by: {len(overdue)}\n")
    lines.extend(overdue or ["(none)"])

    newest: dict[str, str] = {}
    for _, m in mlib.iter_manifests():
        d = m.get("filed_date") or m["retrieved_at"][:10]
        if m["source"] not in newest or d > newest[m["source"]]:
            newest[m["source"]] = d
    lines.append("\n## Source freshness\n")
    for source, latest in sorted(newest.items()):
        age = (today - dt.date.fromisoformat(latest)).days
        limit = CADENCE_DAYS.get(source)
        flag = " **STALE**" if limit and age > limit else ""
        lines.append(f"- {source}: newest doc {latest} ({age}d){flag}")

    config.BUILD.mkdir(exist_ok=True)
    (config.BUILD / "staleness_report.md").write_text("\n".join(lines) + "\n")
    print(f"staleness: {len(overdue)} overdue brief(s); report at build/staleness_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
