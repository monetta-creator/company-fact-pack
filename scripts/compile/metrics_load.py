"""Load governed metric definitions + observations into the compiled DB (D3).

current_observations view: superseded rows excluded — the single blessed value per
(metric, entity, period, dims).
"""

from __future__ import annotations

import json

import yaml

from factpack import config, db as dblib
from factpack.runlog import RunLog, run_isolated


def main() -> None:
    def run(log: RunLog) -> None:
        db = dblib.connect()
        db.executescript(
            """
            DROP TABLE IF EXISTS metric_definitions;
            DROP TABLE IF EXISTS metric_observations;
            DROP VIEW IF EXISTS current_observations;
            CREATE TABLE metric_definitions (
                metric_id TEXT PRIMARY KEY, name TEXT, formula TEXT, basis TEXT, unit TEXT,
                source_schedule TEXT, dims_allowed TEXT, notes TEXT);
            CREATE TABLE metric_observations (
                obs_id TEXT PRIMARY KEY, metric_id TEXT, entity_id TEXT, period TEXT,
                period_type TEXT, value REAL, unit TEXT, dims TEXT, source_doc TEXT,
                source_locator TEXT, as_of TEXT, valid_from TEXT, valid_to TEXT,
                epistemic_status TEXT, superseded_by TEXT);
            CREATE INDEX idx_obs ON metric_observations(metric_id, entity_id, period);
            CREATE VIEW current_observations AS
                SELECT * FROM metric_observations
                WHERE superseded_by IS NULL AND epistemic_status NOT IN ('draft','superseded');
            """
        )
        for d in yaml.safe_load((config.ROOT / "metrics/definitions/definitions.yaml").read_text()):
            db.execute(
                "INSERT INTO metric_definitions VALUES (?,?,?,?,?,?,?,?)",
                (d["metric_id"], d["name"], d["formula"], d["basis"], d["unit"],
                 d["source_schedule"], json.dumps(d.get("dims_allowed", [])), d.get("notes", "")),
            )
            log.count("definitions")
        for path in sorted((config.ROOT / "metrics/observations").glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                o = json.loads(line)
                db.execute(
                    "INSERT OR REPLACE INTO metric_observations VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (o["obs_id"], o["metric_id"], o["entity_id"], o["period"], o["period_type"],
                     o["value"], o["unit"], json.dumps(o.get("dims", {})),
                     o["source_ptr"]["doc_id"], o["source_ptr"].get("locator"),
                     o["as_of"], o.get("valid_from"), o.get("valid_to"),
                     o["epistemic_status"], o.get("superseded_by")),
                )
                log.count("observations")
        db.commit()
        db.close()

    run_isolated("compile.metrics_load", run)


if __name__ == "__main__":
    main()
