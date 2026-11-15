"""Pull a fresh, minimal dashboard snapshot. Credentials stay in the local health project."""
import asyncio,json,os,sys
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('DATA_DIR', str(ROOT/'data'))
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
from config import settings
from connectors import garmin,renpho
from training_plan.context import get_context
from training_plan.garmin import extract_strength_sets
async def main():
 target=ROOT/'sites/momentum/dist/data.json'
 previous=json.loads(target.read_text())
 today=datetime.now(ZoneInfo('Europe/Berlin')).date();asof=today.isoformat()
 args=(settings.garmin_email,settings.garmin_password,settings.data_dir)
 client=await garmin.get_client(*args)
 acts=await garmin.get_recent_activities(*args,100)
 retained={a['id']:a for a in previous['activities']}
 for a in acts:
  day=(a.get('start_time') or '')[:10]
  if not day or day<'2026-10-01':continue
  aid=str(a['activity_id']);sets=retained.get(aid,{}).get('sets',[])
  if 'strength' in a['type']:
   try:sets=extract_strength_sets(await asyncio.to_thread(client.get_activity_exercise_sets,aid))
   except Exception:pass
  retained[aid]={'id':aid,'date':day,'name':a['name'],'type':a['type'],'minutes':a['duration_minutes'],'avgHr':a['avg_hr'],'maxHr':a['max_hr'],'sets':sets}
 recovery={r['date']:r for r in previous['recovery']}
 for n in range(7):
  day=(today-timedelta(days=n)).isoformat()
  try:
   sleep=await garmin.get_sleep(*args,day);hrv=await garmin.get_hrv_data(*args,day);stats=await asyncio.to_thread(client.get_stats,day)
   recovery[day]={'date':day,'sleep':sleep.get('duration_minutes') or None,'score':sleep.get('sleep_score'),'hrv':sleep.get('avg_hrv'),'hrvStatus':hrv.get('status'),'restingHr':stats.get('restingHeartRate'),'stress':stats.get('averageStressLevel')}
  except Exception:pass
 errors=[]
 weights={w['date']:w for w in previous['weights']}
 try:
  for w in await renpho.get_measurements_since(settings.renpho_email,settings.renpho_password,90):
   weights[w['date']]={'date':w['date'],'kg':w['weight_kg'],'fat':w['body_fat_pct']}
 except Exception:errors.append('Renpho: previous values retained')
 calendar=await get_context(*args, force=True)
 if not calendar.get('available'):
  errors.append('Garmin calendar unavailable; previous plan retained')
  plans=previous['plan']
 else:
  if calendar.get('stale'):errors.append('Garmin calendar: last known snapshot retained')
  start,end=calendar['range_start'],calendar['range_end']
  retained_plans=[p for p in previous['plan'] if not start<=p['date']<=end]
  plans=retained_plans+[{'date':w['date'],'name':w['title'],'type':'strength' if w['type']=='strength_training' else 'cardio'} for w in calendar['workouts']]
 out={'schemaVersion':1,'asOf':asof,'generatedAt':datetime.now(ZoneInfo('Europe/Berlin')).isoformat(),'activities':sorted(retained.values(),key=lambda a:(a['date'],a['id'])),'recovery':sorted(recovery.values(),key=lambda a:a['date']),'weights':sorted(weights.values(),key=lambda a:a['date']),'plan':sorted(plans,key=lambda a:a['date']), 'calendarAsOf':calendar.get('fetched_at'), 'warnings':errors}
 temp=target.with_suffix('.tmp');temp.write_text(json.dumps(out,ensure_ascii=False,indent=2));temp.replace(target)
 print(json.dumps({'asOf':asof,'activities':len(out['activities']),'warnings':errors}))
if __name__ == '__main__':
 asyncio.run(main())
