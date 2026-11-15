"""A bounded read-only view of the locally imported training history."""
import json
from pathlib import Path
import sqlite3


def recent_strength(data_dir: str) -> list[dict]:
    path = Path(data_dir)/'training/training_plan.sqlite3'
    if not path.is_file():
        return []
    try:
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as connection:
            rows = connection.execute("""SELECT local_start,strength_sets_json FROM activities
                 WHERE lower(activity_type) LIKE '%strength%'
                 ORDER BY local_start DESC LIMIT 3""").fetchall()
        result = []
        for day, raw in rows:
            exercises = []
            for item in json.loads(raw or '[]')[:12]:
                if item.get('set_type','').upper() == 'REST':
                    continue
                exercises.append({k:item.get(k) for k in ('exercise_name','reps','load_kg')})
            result.append({'date':day[:10], 'recorded_sets':exercises})
        return result
    except (sqlite3.Error,ValueError,TypeError):
        return []
