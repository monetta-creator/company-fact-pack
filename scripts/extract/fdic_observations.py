"""FDIC financials + SOD -> observations (deterministic). Primary bank-subsidiary series."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

FIELDS = {
    # RIS field -> (metric_id, period_type)  — balances are instants; RIS flows are YTD
    "ASSET": ("bank-total-assets", "instant"),
    "DEP": ("bank-total-deposits", "instant"),
    "NETINC": ("bank-net-income", "ytd"),
    "LNLSNET": ("bank-net-loans", "instant"),
    "LNCRCD": ("bank-credit-card-loans", "instant"),
    "EQ": ("bank-equity", "instant"),
    "ROA": ("bank-roa", "ytd"),
    "ROE": ("bank-roe", "ytd"),
    "NIMY": ("bank-nim", "ytd"),
}


def obs_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def quarter_label(repdte: str) -> str:
    y, m = int(repdte[:4]), int(repdte[4:6])
    return f"{y}Q{(m - 1) // 3 + 1}"


def main() -> None:
    def run(log: RunLog) -> None:
        today = dt.date.today().isoformat()
        rows: list[dict] = []
        for entity in config.FDIC_CERT:
            doc_id = f"fdic/financials_{entity}"
            path = mlib.doc_dir(doc_id) / "financials.json"
            if not path.exists():
                log.note(f"{doc_id}: missing")
                continue
            for r in json.loads(path.read_text()):
                repdte = str(r.get("REPDTE", ""))
                if len(repdte) != 8:
                    continue
                period = quarter_label(repdte)
                for field, (metric, ptype) in FIELDS.items():
                    val = r.get(field)
                    if val is None:
                        continue
                    unit = "pct" if field in ("ROA", "ROE", "NIMY") else "USD_thousands"
                    rows.append(
                        {
                            "obs_id": obs_id(metric, entity, period, field),
                            "metric_id": metric,
                            "entity_id": entity,
                            "period": period,
                            "period_type": ptype,
                            "value": float(val),
                            "unit": unit,
                            "dims": {},
                            "source_ptr": {"doc_id": doc_id, "locator": f"{field} REPDTE={repdte}"},
                            "as_of": today,
                            "valid_to": f"{repdte[:4]}-{repdte[4:6]}-{repdte[6:]}",
                            "epistemic_status": "reported",
                        }
                    )
            # SOD: state-level rollup per survey year
            sod_doc = f"fdic/sod_{entity}"
            sod_path = mlib.doc_dir(sod_doc) / "sod.json"
            if sod_path.exists():
                agg: dict[tuple[str, str], float] = {}
                for r in json.loads(sod_path.read_text()):
                    year = str(r.get("YEAR", ""))
                    state = str(r.get("STALPBR") or r.get("STALP") or "?")
                    dep = r.get("DEPSUMBR")
                    if not year or dep is None:
                        continue
                    agg[(year, state)] = agg.get((year, state), 0.0) + float(str(dep).replace(",", ""))
                for (year, state), total in sorted(agg.items()):
                    rows.append(
                        {
                            "obs_id": obs_id("sod-deposits", entity, year, state),
                            "metric_id": "sod-deposits",
                            "entity_id": entity,
                            "period": f"{year}-06",
                            "period_type": "instant",
                            "value": total,
                            "unit": "USD_thousands",
                            "dims": {"state": state},
                            "source_ptr": {"doc_id": sod_doc, "locator": f"YEAR={year} state={state}"},
                            "as_of": today,
                            "epistemic_status": "reported",
                        }
                    )
        out = config.ROOT / "metrics/observations/fdic.jsonl"
        out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
        log.ok(rows=len(rows))

    run_isolated("extract.fdic", run)


if __name__ == "__main__":
    main()
