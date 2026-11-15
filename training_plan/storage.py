from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
  activity_id TEXT PRIMARY KEY,
  local_start TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  duration_seconds INTEGER NOT NULL,
  average_hr REAL,
  max_hr REAL,
  distance_m REAL,
  hr_samples_json TEXT NOT NULL DEFAULT '[]',
  strength_sets_json TEXT NOT NULL DEFAULT '[]',
  imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS feedback (
  activity_id TEXT PRIMARY KEY REFERENCES activities(activity_id) ON DELETE CASCADE,
  rpe INTEGER,
  symptoms INTEGER NOT NULL DEFAULT 0,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS vo2_estimates (
  date TEXT NOT NULL,
  metric_name TEXT NOT NULL,
  value REAL NOT NULL,
  PRIMARY KEY(date, metric_name)
);
CREATE TABLE IF NOT EXISTS sync_ledger (
  stable_id TEXT PRIMARY KEY,
  workout_date TEXT NOT NULL,
  workout_kind TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  external_id TEXT,
  state TEXT NOT NULL CHECK(state IN ('preview','uploaded','failed')),
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sync_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(activities)")}
        if "strength_sets_json" not in columns:
            self.db.execute("ALTER TABLE activities ADD COLUMN strength_sets_json TEXT NOT NULL DEFAULT '[]'")
        self.db.commit()

    def upsert_activity(self, activity: dict[str, Any]) -> None:
        self.db.execute("""INSERT INTO activities
          (activity_id,local_start,activity_type,duration_seconds,average_hr,max_hr,distance_m,hr_samples_json,strength_sets_json)
          VALUES (:activity_id,:local_start,:activity_type,:duration_seconds,:average_hr,:max_hr,:distance_m,:hr_samples_json,:strength_sets_json)
          ON CONFLICT(activity_id) DO UPDATE SET
          local_start=excluded.local_start,activity_type=excluded.activity_type,
          duration_seconds=excluded.duration_seconds,average_hr=excluded.average_hr,
          max_hr=excluded.max_hr,distance_m=excluded.distance_m,hr_samples_json=excluded.hr_samples_json,
          strength_sets_json=excluded.strength_sets_json""", activity)
        self.db.commit()

    def activities(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        rows = self.db.execute("""SELECT a.*,f.rpe,f.symptoms,f.note FROM activities a
          LEFT JOIN feedback f USING(activity_id)
          WHERE substr(local_start,1,10)>=? AND substr(local_start,1,10)<=?
          ORDER BY local_start""", (start_date, end_date)).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["hr_samples"] = json.loads(row.pop("hr_samples_json"))
            row["strength_sets"] = json.loads(row.pop("strength_sets_json"))
        return result

    def count_cardio_since(self, start_date: str) -> int:
        return int(self.db.execute("""SELECT COUNT(*) FROM activities
          WHERE substr(local_start,1,10)>=? AND
          (lower(activity_type) LIKE '%cycling%' OR lower(activity_type) LIKE '%rowing%'
           OR lower(activity_type) LIKE '%elliptical%' OR lower(activity_type) LIKE '%cardio%'
          OR lower(activity_type) LIKE '%ski%')""", (start_date,)).fetchone()[0])

    def upsert_vo2_estimates(self, estimates: list[dict[str, Any]]) -> None:
        self.db.executemany("""INSERT INTO vo2_estimates(date,metric_name,value) VALUES(?,?,?)
          ON CONFLICT(date,metric_name) DO UPDATE SET value=excluded.value""",
          [(item["date"], item["metric_name"], item["value"]) for item in estimates])
        self.db.commit()

    def vo2_estimates(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT date,metric_name,value FROM vo2_estimates ORDER BY date,metric_name").fetchall()]

    def record_previews(self, workouts: list[Any]) -> None:
        import hashlib
        payloads = []
        for workout in workouts:
            data = workout.to_dict()
            payload_hash = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            payloads.append((data["stable_id"], data["date"], data["kind"], payload_hash, "preview"))
        self.db.executemany("""INSERT INTO sync_ledger(stable_id,workout_date,workout_kind,payload_hash,state)
          VALUES(?,?,?,?,?) ON CONFLICT(stable_id) DO UPDATE SET
          workout_date=excluded.workout_date,workout_kind=excluded.workout_kind,
          payload_hash=excluded.payload_hash,updated_at=CURRENT_TIMESTAMP
          WHERE sync_ledger.state='preview'""", payloads)
        self.db.commit()

    def add_feedback(self, activity_id: str, rpe: int | None, symptoms: bool, note: str = "") -> None:
        if rpe is not None and not 1 <= rpe <= 10:
            raise ValueError("RPE must be between 1 and 10")
        self.db.execute("""INSERT INTO feedback(activity_id,rpe,symptoms,note) VALUES(?,?,?,?)
          ON CONFLICT(activity_id) DO UPDATE SET rpe=excluded.rpe,symptoms=excluded.symptoms,note=excluded.note""",
          (activity_id, rpe, int(symptoms), note))
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def get_sync_state(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set_sync_state(self, key: str, value: str) -> None:
        self.db.execute("""INSERT INTO sync_state(key,value) VALUES(?,?)
          ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP""", (key, value))
        self.db.commit()
