"""Read-only Garmin calendar context shared by Telegram and dashboard exports.

Local planner previews are deliberately never a fallback for scheduled workouts.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from connectors import garmin

logger = logging.getLogger(__name__)
TZ = ZoneInfo('Europe/Berlin')
TTL = timedelta(minutes=15)
_inflight = {}


def _cache_path(data_dir):
    return Path(data_dir) / 'training/calendar_cache.json'


def _read_cache(path):
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
        if (isinstance(result,dict) and result.get('schema_version') == 1
                and isinstance(result.get('workouts'), list)
                and all(isinstance(w,dict) and isinstance(w.get('date'),str)
                        and isinstance(w.get('title'),str) and isinstance(w.get('steps'),list)
                        and w.get('schedule_id') for w in result['workouts'])
                and datetime.fromisoformat(result['fetched_at']).tzinfo is not None):
            return result
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _save_cache(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _view(value, now, *, stale=False):
    result = deepcopy(value)
    result['available'] = True
    result['stale'] = stale
    result['today'] = now.date().isoformat()
    result['workouts'] = [w for w in result['workouts']
                          if (now.date() - timedelta(days=7)).isoformat() <= w['date']
                          <= (now.date() + timedelta(days=14)).isoformat()]
    return result


def workout_steps(detail):
    """Keep displayable set/interval instructions, never unrelated account data."""
    result = []
    def walk(steps, repetitions=None):
        for step in steps or []:
            repeats = step.get('numberOfIterations') or repetitions
            if step.get('workoutSteps'):
                walk(step['workoutSteps'], repeats)
                continue
            condition = step.get('endCondition') or {}
            result.append({key: val for key, val in {
                'exercise': step.get('exerciseName'),
                'description': (step.get('description') or '')[:400],
                'condition': condition.get('conditionTypeKey'),
                'value': step.get('endConditionValue'),
                'repetitions': repeats,
            }.items() if val is not None and val != ''})
    for segment in detail.get('workoutSegments') or []:
        walk(segment.get('workoutSteps'))
    return result[:40]


async def _fetch(email, password, data_dir, now):
    client = await garmin.get_client(email, password, data_dir)
    start, end = now.date() - timedelta(days=7), now.date() + timedelta(days=14)
    months = sorted({((start + timedelta(days=n)).year, (start + timedelta(days=n)).month)
                     for n in range((end-start).days+1)})
    # All calendar months must succeed before replacing a last-known-good cache.
    pages = await asyncio.gather(*(asyncio.to_thread(client.get_scheduled_workouts, y, m) for y, m in months))
    records = {}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('calendarItems'), list):
            raise ValueError('Unexpected calendar response')
        for item in page['calendarItems']:
            day = str(item.get('date') or '')[:10]
            if item.get('itemType') != 'workout' or not start.isoformat() <= day <= end.isoformat():
                continue
            identity = str(item.get('id') or item.get('scheduleId') or
                           hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()[:20])
            records[(day, identity)] = {
                'schedule_id': identity, 'workout_id': str(item.get('workoutId') or ''),
                'date': day, 'title': str(item.get('title') or 'Garmin-Workout')[:200],
                'type': str(item.get('sportTypeKey') or ''), 'steps': [],
            }
    workouts = sorted(records.values(), key=lambda w: (w['date'], w['schedule_id']))
    today = now.date().isoformat()
    # Enrich today and the next scheduled day; avoid dozens of detail requests.
    next_day = next((w['date'] for w in workouts if w['date'] > today), None)
    selected = [w for w in workouts if w['date'] in (today, next_day)]
    semaphore = asyncio.Semaphore(3)
    async def enrich(workout):
        async with semaphore:
            try:
                if workout['workout_id']:
                    detail = await asyncio.wait_for(asyncio.to_thread(client.get_workout_by_id, workout['workout_id']), 5)
                else:
                    scheduled = await asyncio.wait_for(asyncio.to_thread(client.get_scheduled_workout_by_id, workout['schedule_id']), 5)
                    detail = scheduled.get('workout') or scheduled
                    identifier = detail.get('workoutId') or scheduled.get('workoutId')
                    if identifier:
                        workout['workout_id'] = str(identifier)
                        if not detail.get('workoutSegments'):
                            detail = await asyncio.wait_for(asyncio.to_thread(client.get_workout_by_id, identifier), 5)
                workout['steps'] = workout_steps(detail)
                workout['description'] = str(detail.get('description') or '')[:800]
                seconds = detail.get('estimatedDurationInSecs')
                if isinstance(seconds, (int,float)) and seconds > 0:
                    workout['estimated_minutes'] = round(seconds / 60)
            except Exception as exc:
                # Calendar entries remain useful when optional detail calls fail.
                logger.info('Optional workout details unavailable: %s', type(exc).__name__)
    try:
        await asyncio.wait_for(asyncio.gather(*(enrich(w) for w in selected)), timeout=12)
    except TimeoutError:
        logger.info('Workout detail budget exceeded; keeping calendar entries')
    result = {'schema_version': 1, 'source': 'garmin_calendar', 'fetched_at': now.isoformat(timespec='seconds'),
              'range_start': start.isoformat(), 'range_end': end.isoformat(), 'workouts': workouts}
    _save_cache(_cache_path(data_dir), result)
    return result


async def get_context(email, password, data_dir, *, now=None, force=False):
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError('Calendar time must be timezone-aware')
    cache = _read_cache(_cache_path(data_dir))
    if cache and not force and timedelta(0) <= now - datetime.fromisoformat(cache['fetched_at']) < TTL:
        return _view(cache, now)
    key = (asyncio.get_running_loop(), str(Path(data_dir).resolve()))
    task = _inflight.get(key)
    if task is None or task.done():
        task = asyncio.create_task(asyncio.wait_for(_fetch(email,password,data_dir,now), timeout=20))
        _inflight[key] = task
        def finished(done):
            if _inflight.get(key) is done:
                _inflight.pop(key, None)
            if not done.cancelled():
                done.exception()  # Retrieve failures even when all callers timed out.
        task.add_done_callback(finished)
    try:
        return _view(await asyncio.shield(task), now)
    except Exception as exc:
        logger.warning('Training calendar unavailable: %s', type(exc).__name__)
        if cache:
            return _view(cache, now, stale=True)
        return {'available': False, 'stale': False, 'today': now.date().isoformat(),
                'source': 'garmin_calendar', 'fetched_at': None, 'workouts': []}


def with_activities(context, activities):
    result = deepcopy(context)
    for workout in result.get('workouts', []):
        matches = [a for a in activities
                   if workout.get('workout_id') and str(a.get('workout_id') or '') == workout['workout_id']
                   and str(a.get('start_time') or '')[:10] == workout['date']]
        workout['completed_activity_ids'] = [str(a['activity_id']) for a in matches if a.get('activity_id')]
        workout['completion'] = 'linked' if matches else 'unconfirmed'
    return result


def prompt_context(context, question='', *, limit=2200):
    """Small reference payload; explicit no-write policy lives in the system prompt."""
    if not context:
        return ''
    today = context.get('today', '')
    workouts = context.get('workouts') or []
    # Today's and next day's details first. Other dates remain a compact calendar.
    selection = sorted(workouts, key=lambda w: (w['date'] < today, w['date']))
    payload = {key: context.get(key) for key in ('source','fetched_at','available','stale','today')}
    if any(term in question.lower() for term in ('gewicht','satz','sätze','wiederholung','übung','letzte','vergleich','verlauf')):
        payload['imported_strength_history'] = context.get('imported_strength_history', [])[:2]
        while len(json.dumps(payload,ensure_ascii=False)) > limit // 2 and payload['imported_strength_history']:
            payload['imported_strength_history'].pop()
    payload['scheduled'] = []
    for w in selection:
        summary = {k:w[k] for k in ('date','title','type','completion','estimated_minutes') if k in w}
        if not payload['scheduled']:
            summary['steps'] = w.get('steps', [])[:8]
            summary['description'] = w.get('description','')[:300]
        candidate = {**payload, 'scheduled': payload['scheduled']+[summary]}
        if len(json.dumps(candidate,ensure_ascii=False)) > limit:
            summary.pop('steps', None); summary.pop('description',None)
            candidate = {**payload,'scheduled':payload['scheduled']+[summary]}
        if len(json.dumps(candidate,ensure_ascii=False)) <= limit:
            payload['scheduled'].append(summary)
    return json.dumps(payload,ensure_ascii=False)
