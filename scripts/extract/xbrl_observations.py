"""XBRL companyfacts -> metrics/observations/xbrl_<entity>.jsonl (deterministic).

Restatements: the same (metric, entity, period) reported in a later filing supersedes
the earlier observation — the old row stays, marked superseded_by (rule 5 as code).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import yaml

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

MAP_PATH = config.ROOT / "metrics/definitions/xbrl_map.yaml"


def obs_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def period_of(entry: dict, kind: str) -> tuple[str, str] | None:
    """-> (period, period_type) or None if the duration shape isn't quarterly/annual."""
    end = entry.get("end")
    if not end:
        return None
    if kind == "instant":
        return end, "instant"
    start = entry.get("start")
    if not start:
        return None
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
    y, m = int(end[:4]), int(end[5:7])
    if days <= 100:
        return f"{y}Q{(m - 1) // 3 + 1}", "quarter"
    if 350 <= days <= 380:
        return f"FY{y}", "fy"
    return None  # 6/9-month YTD windows are skipped to keep one blessed shape per period


def extract_entity(entity: str, log: RunLog) -> None:
    doc_id = f"edgar-{entity}/xbrl_companyfacts"
    path = mlib.doc_dir(doc_id) / "companyfacts.json"
    if not path.exists():
        path = mlib.cache_dir(doc_id) / "companyfacts.json"
    facts = json.loads(path.read_text()).get("facts", {}).get("us-gaap", {})
    mapping = yaml.safe_load(MAP_PATH.read_text())
    today = dt.date.today().isoformat()

    rows: list[dict] = []
    for m in mapping:
        tag = next((t for t in m["tags"] if t in facts), None)
        if tag is None:
            log.note(f"{entity}: no tag found for {m['metric_id']} (candidates {m['tags'][:3]}...)")
            continue
        units = facts[tag].get("units", {})
        entries = units.get(m["unit_key"], [])
        # group by period; latest filed wins, earlier become superseded
        by_period: dict[tuple[str, str], list[dict]] = {}
        for e in entries:
            if e.get("val") is None:
                continue
            p = period_of(e, m["kind"])
            if p is None:
                continue
            by_period.setdefault(p, []).append(e)
        for (period, ptype), es in by_period.items():
            es.sort(key=lambda e: (e.get("filed") or "", e.get("accn") or ""))
            ids = [
                obs_id(m["metric_id"], entity, period, e.get("accn", ""), str(e["val"]))
                for e in es
            ]
            # collapse exact-duplicate re-reports (same value re-filed) to the first
            seen_vals: dict[float, int] = {}
            keep: list[int] = []
            for i, e in enumerate(es):
                v = float(e["val"])
                if v in seen_vals:
                    continue
                seen_vals[v] = i
                keep.append(i)
            for j, i in enumerate(keep):
                e = es[i]
                current = j == len(keep) - 1
                rows.append(
                    {
                        "obs_id": ids[i],
                        "metric_id": m["metric_id"],
                        "entity_id": entity,
                        "period": period,
                        "period_type": ptype,
                        "value": float(e["val"]),
                        "unit": m["unit_key"],
                        "dims": {"tag": tag},
                        "source_ptr": {
                            "doc_id": doc_id,
                            "locator": f"us-gaap:{tag} accn={e.get('accn')} filed={e.get('filed')}",
                        },
                        "as_of": today,
                        "valid_from": e.get("start") or e.get("end"),
                        "valid_to": e.get("end"),
                        "epistemic_status": "superseded" if not current else "reported",
                        "superseded_by": None if current else ids[keep[j + 1]],
                    }
                )
        log.count(f"{entity}_metrics")
    out = config.ROOT / "metrics/observations" / f"xbrl_{entity}.jsonl"
    out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
    log.count(f"{entity}_rows", len(rows))


def main() -> None:
    def run(log: RunLog) -> None:
        for entity in ("cof", "dfs"):
            extract_entity(entity, log)

    run_isolated("extract.xbrl", run)


if __name__ == "__main__":
    main()
