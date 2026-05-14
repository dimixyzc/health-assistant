import aiosqlite
import logging
import os
from datetime import date, datetime
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
