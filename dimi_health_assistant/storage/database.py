import aiosqlite
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_DB_FILE = "health_assistant.db"


def db_path(data_dir: str) -> str:
    return os.path.join(data_dir, _DB_FILE)


async def init_db(data_dir: str) -> None:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS renpho_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                weight_kg REAL,
                bmi REAL,
                body_fat_pct REAL,
                subfat_pct REAL,
                muscle_mass_kg REAL,
                lean_mass_kg REAL,
                fat_free_weight_kg REAL,
                bone_mass_kg REAL,
                body_water_pct REAL,
                protein_pct REAL,
                visceral_fat REAL,
                bmr_kcal REAL,
                metabolic_age REAL,
                fetched_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_renpho_date ON renpho_measurements(date)
        """)
        # Migrate existing DB: add new columns if they don't exist yet
        for col, coltype in [
            ("subfat_pct", "REAL"),
            ("lean_mass_kg", "REAL"),
            ("fat_free_weight_kg", "REAL"),
            ("protein_pct", "REAL"),
        ]:
            try:
                await db.execute(f"ALTER TABLE renpho_measurements ADD COLUMN {col} {coltype}")
            except Exception:
                pass  # Column already exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hypothesis TEXT,
                target_metric TEXT,
                start_date TEXT NOT NULL,
                end_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS coach_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                report_type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS health_metric_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL,
                text_value TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(date, metric)
            )
        """)
        await db.commit()


async def upsert_renpho(data_dir: str, measurement: dict) -> None:
    if not measurement or not measurement.get("date"):
        return
    async with aiosqlite.connect(db_path(data_dir)) as db:
        await db.execute("""
            INSERT INTO renpho_measurements
              (date, weight_kg, bmi, body_fat_pct, subfat_pct, muscle_mass_kg, lean_mass_kg,
               fat_free_weight_kg, bone_mass_kg, body_water_pct, protein_pct,
               visceral_fat, bmr_kcal, metabolic_age, fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
              weight_kg=excluded.weight_kg, bmi=excluded.bmi,
              body_fat_pct=excluded.body_fat_pct, subfat_pct=excluded.subfat_pct,
              muscle_mass_kg=excluded.muscle_mass_kg, lean_mass_kg=excluded.lean_mass_kg,
              fat_free_weight_kg=excluded.fat_free_weight_kg,
              bone_mass_kg=excluded.bone_mass_kg, body_water_pct=excluded.body_water_pct,
              protein_pct=excluded.protein_pct, visceral_fat=excluded.visceral_fat,
              bmr_kcal=excluded.bmr_kcal, metabolic_age=excluded.metabolic_age,
              fetched_at=excluded.fetched_at
        """, (
            measurement["date"],
            measurement.get("weight_kg"),
            measurement.get("bmi"),
            measurement.get("body_fat_pct"),
            measurement.get("subfat_pct"),
            measurement.get("muscle_mass_kg"),
            measurement.get("lean_mass_kg"),
            measurement.get("fat_free_weight_kg"),
            measurement.get("bone_mass_kg"),
            measurement.get("body_water_pct"),
            measurement.get("protein_pct"),
            measurement.get("visceral_fat"),
            measurement.get("bmr_kcal"),
            measurement.get("metabolic_age"),
            datetime.now().isoformat(),
        ))
        await db.commit()


async def get_renpho_history(data_dir: str, days: int = 30) -> list[dict]:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM renpho_measurements
            WHERE date >= date('now', ?)
            ORDER BY date ASC
        """, (f"-{days} days",))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_latest_renpho(data_dir: str) -> Optional[dict]:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM renpho_measurements ORDER BY date DESC LIMIT 1
        """)
        row = await cursor.fetchone()
        return dict(row) if row else None


async def days_since_last_renpho(data_dir: str) -> Optional[int]:
    latest = await get_latest_renpho(data_dir)
    if not latest or not latest.get("date"):
        return None
    last_date = date.fromisoformat(latest["date"])
    return (date.today() - last_date).days


async def create_experiment(data_dir: str, experiment: dict) -> dict:
    start = experiment.get("start_date") or date.today().isoformat()
    duration_days = int(experiment.get("duration_days") or 14)
    end = experiment.get("end_date") or (date.fromisoformat(start) + timedelta(days=duration_days - 1)).isoformat()
    now = datetime.now().isoformat(timespec="seconds")
    async with aiosqlite.connect(db_path(data_dir)) as db:
        cursor = await db.execute("""
            INSERT INTO experiments (name, hypothesis, target_metric, start_date, end_date, status, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (
            experiment["name"],
            experiment.get("hypothesis"),
            experiment.get("target_metric"),
            start,
            end,
            experiment.get("status") or "active",
            now,
        ))
        await db.commit()
        experiment_id = cursor.lastrowid
    created = await get_experiment(data_dir, experiment_id)
    return created or {"id": experiment_id, **experiment, "start_date": start, "end_date": end, "status": "active"}


async def get_experiment(data_dir: str, experiment_id: int) -> Optional[dict]:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_active_experiments(data_dir: str) -> list[dict]:
    today = date.today().isoformat()
    async with aiosqlite.connect(db_path(data_dir)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM experiments
            WHERE status = 'active' AND (end_date IS NULL OR end_date >= ?)
            ORDER BY start_date ASC, id ASC
        """, (today,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def save_coach_message(data_dir: str, report_type: str, content: str, message_date: str) -> None:
    if not content or not message_date:
        return
    async with aiosqlite.connect(db_path(data_dir)) as db:
        await db.execute(
            "INSERT INTO coach_history (date, report_type, content, created_at) VALUES (?,?,?,?)",
            (message_date, report_type, content, datetime.now().isoformat(timespec="seconds")),
        )
        await db.commit()


async def get_recent_coach_messages(data_dir: str, report_type: str, limit: int = 5) -> list[str]:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        cursor = await db.execute(
            "SELECT content FROM coach_history WHERE report_type = ? ORDER BY id DESC LIMIT ?",
            (report_type, limit),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def upsert_health_metrics(data_dir: str, message_date: str, metrics: dict) -> None:
    if not message_date:
        return
    async with aiosqlite.connect(db_path(data_dir)) as db:
        for metric, value in (metrics or {}).items():
            if value is None or metric in {"available", "date"}:
                continue
            numeric = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            text_value = None if numeric is not None else str(value)
            await db.execute(
                """INSERT INTO health_metric_history (date, metric, value, text_value, created_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(date, metric) DO UPDATE SET value=excluded.value,
                   text_value=excluded.text_value, created_at=excluded.created_at""",
                (message_date, metric, numeric, text_value, datetime.now().isoformat(timespec="seconds")),
            )
        await db.commit()


async def get_previous_health_metrics(data_dir: str, message_date: str) -> dict:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        cursor = await db.execute(
            """SELECT metric, value, text_value FROM health_metric_history
               WHERE date < ? ORDER BY date DESC, id DESC""",
            (message_date,),
        )
        rows = await cursor.fetchall()
    previous = {}
    for metric, value, text_value in rows:
        if metric not in previous:
            previous[metric] = value if value is not None else text_value
    return previous


async def get_health_metric_history(data_dir: str, metric: str, before_date: str, limit: int = 7) -> list[float]:
    async with aiosqlite.connect(db_path(data_dir)) as db:
        cursor = await db.execute(
            """SELECT value FROM health_metric_history
               WHERE metric = ? AND date < ? AND value IS NOT NULL
               ORDER BY date DESC LIMIT ?""",
            (metric, before_date, limit),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
