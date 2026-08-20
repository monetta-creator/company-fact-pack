"""FR Y-9C slices -> observations, driven by the versioned MDRM map.

Runs only over ffiec-y9c corpus docs (present once the NIC ladder or manual inbox
provides bulk ZIPs). Values are USD thousands; income items are calendar YTD.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json

import yaml

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

MAP_PATH = config.ROOT / "metrics/definitions/y9c_mdrm_map.yaml"
RSSD_TO_ENTITY = {"2277860": "cof", "3846375": "dfs"}
YTD_METRICS = {"y9c-net-income", "y9c-net-interest-income", "y9c-cc-charge-offs", "y9c-cc-recoveries"}


def code_active(entry: dict, quarter_iso: str) -> bool:
    vf, vt = entry.get("valid_from"), entry.get("valid_to")
    return (vf is None or vf <= quarter_iso) and (vt is None or quarter_iso <= vt)


def main() -> None:
    def run(log: RunLog) -> None:
        mapping = yaml.safe_load(MAP_PATH.read_text())
        today = dt.date.today().isoformat()
        rows: list[dict] = []
        docs = [(d, m) for d, m in mlib.iter_manifests() if m["source"] == "ffiec-y9c"]
        if not docs:
            log.note("no ffiec-y9c docs in corpus (NIC blocked; see fetch.ffiec_y9c status)")
        for doc_id, m in docs:
            slice_path = next(
                (mlib.file_location(doc_id, f) for f in m["files"] if f["role"] == "raw"), None
            )
            if slice_path is None or not slice_path.exists():
                continue
            period_end = m["period_end"]
            quarter = f"{period_end[:4]}Q{(int(period_end[5:7]) - 1) // 3 + 1}"
            lines = slice_path.read_text(errors="replace").splitlines()
            if len(lines) < 2:
                continue
            delim = "^" if "^" in lines[0] else "\t"
            cols = [c.strip('"') for c in lines[0].split(delim)]
            idx = {c: i for i, c in enumerate(cols)}
            rssd_i = idx.get("RSSD9001", 0)
            for line in lines[1:]:
                parts = [p.strip('"') for p in line.split(delim)]
                entity = RSSD_TO_ENTITY.get(parts[rssd_i].strip())
                if entity is None:
                    continue
                for spec in mapping:
                    vals = []
                    for entry in spec["codes"]:
                        if not code_active(entry, period_end):
                            continue
                        i = idx.get(entry["code"])
                        if i is None or i >= len(parts) or not parts[i].strip():
                            continue
                        try:
                            vals.append(float(parts[i].replace(",", "")))
                        except ValueError:
                            continue
                    if not vals:
                        continue
                    value = sum(vals) if spec.get("sum") else vals[0]
                    metric = spec["metric_id"]
                    rows.append(
                        {
                            "obs_id": hashlib.sha256(
                                f"{metric}|{entity}|{quarter}".encode()
                            ).hexdigest()[:16],
                            "metric_id": metric,
                            "entity_id": entity,
                            "period": quarter,
                            "period_type": "ytd" if metric in YTD_METRICS else "instant",
                            "value": value,
                            "unit": "USD_thousands",
                            "dims": {},
                            "source_ptr": {
                                "doc_id": doc_id,
                                "locator": "+".join(e["code"] for e in spec["codes"]),
                            },
                            "as_of": today,
                            "valid_to": period_end,
                            "epistemic_status": "reported",
                        }
                    )
            log.count("docs")
        out = config.ROOT / "metrics/observations/y9c.jsonl"
        out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
        log.ok(rows=len(rows))

    run_isolated("extract.y9c", run)


if __name__ == "__main__":
    main()
