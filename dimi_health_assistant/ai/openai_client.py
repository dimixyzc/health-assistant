import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

def _hm(minutes) -> str:
    """Konvertiert Minuten zu 'Xh Ymin' — nie rohe Minuten wenn >= 60."""
    if not minutes:
        return "k.A."
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return "k.A."
    h, mins = divmod(m, 60)
    return f"{h}h {mins}min" if h else f"{mins}min"


_ATHLETE_PROFILE = """
Du bist ein evidenzorientierter AI-Health- und Performance-Coach für Dimitri, einen Hybrid-Athleten.
Trainingsziel: 3x pro Woche Krafttraining im Gym + 3x Laufen pro Woche.
Dimitri ist sportlich aktiv, verfolgt seine Daten mit einer Garmin-Uhr und einer Renpho-Waage.

AUSGABEFORMAT — immer einhalten:
- Antworte auf Deutsch
- Kein Fließtext — stattdessen strukturierte Bullet-Points (•)
- Jeder Bullet beginnt mit einem passenden Emoji zur schnellen Einordnung
- Emojis als Status-Signale: ✅ gut/erreicht, ⚠️ Achtung, 🔴 kritisch, 💡 Tipp, 📈 Trend positiv, 📉 Trend negativ
- Wissenschaftlich gehaltvoll, aber verständlich: erkläre Mechanismus → Bedeutung → Handlung
- Keine Diagnose, keine Heilversprechen; bei auffälligen Mustern ärztliche Abklärung empfehlen
- Kompakt schreiben: maximal 1-2 kurze Sätze pro Bullet
- Keine langen Trainingsrezepte in einem Bullet; Details knapp halten
- Keine Einleitung, kein Abschluss-Satz wie "Viel Erfolg!" — nur die Bullets
- Wiederhole keine Rohdatenliste, wenn die Daten separat formatiert werden
- Du darfst einzelne Werte zitieren, wenn du damit eine konkrete Aussage begründest
- Schlaf NIEMALS in Minuten angeben — immer als "Xh Ymin" (z.B. "1h 45min" statt "105 Min")
- Interpretiere Tageswerte immer relativ zum Zeitpunkt der Datenabfrage.
- Niedrige Body Battery am Abend ist meist normaler Tagesverbrauch; werte sie nur mit Zusatzsignalen als Problem.
- Vermeide generische Warn- und Stoppsignal-Floskeln ohne konkreten Datenbezug.
- Schreibe keine Aussagen wie "bei schweren Beinen locker" oder "bei ungewöhnlich hohem Puls Intensität reduzieren".
"""


class OpenAIHealthAssistant:
    def __init__(self, api_key: str, model: str = "gpt-5.5"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate_morning_briefing(self, snapshot: dict) -> str:
        readiness = snapshot.get("readiness") or {}
        prompt = f"""
Morgen-Briefing — bewerte Erholung und gib 1 konkreten Trainingstipp für heute.

Readiness: {readiness.get('score', 'k.A.')}/100 ({readiness.get('recommendation', 'k.A.')})
Limitierende Faktoren: {', '.join(readiness.get('limiting_factors') or []) or 'k.A.'}
Schlaf: {_hm(snapshot.get('sleep_duration_minutes'))}, Score: {snapshot.get('sleep_score', 'k.A.')}
Tiefschlaf: {_hm(snapshot.get('deep_sleep_minutes'))} | REM: {_hm(snapshot.get('rem_sleep_minutes'))}
HRV: {snapshot.get('avg_hrv', 'k.A.')} ms ({snapshot.get('hrv_status', 'k.A.')})
Body Battery: {snapshot.get('body_battery', 'k.A.')} | Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm
Datenabfrage: {snapshot.get('fetched_time', 'k.A.')} Uhr

Format: 4 Bullets:
• Erholung/Readiness einordnen
• Schlaf oder HRV physiologisch erklären, aber kompakt
• Trainingsempfehlung mit grober Intensität
• konkrete Tagessteuerung, nur wenn aus Daten ableitbar
Jeder Bullet maximal 22 Wörter.
Keine reine Rohdatenliste.
Keine generischen Warnsignale oder "abhängig vom Gefühl"-Hinweise.
"""
        return await self._chat(prompt)

    async def generate_evening_summary(self, snapshot: dict, activities: list) -> str:
        activity_lines = "\n".join(
            f"- {a.get('type', '?')}: {a.get('duration_minutes')} Min, {a.get('distance_km', 0)} km, HR: {a.get('avg_hr', '?')} bpm"
            for a in activities
        ) or "Keine Aktivitäten heute"

        prompt = f"""
Tages-Zusammenfassung — bewerte den Tag und gib 1 Tipp für morgen.

Schritte: {snapshot.get('steps', 0)} | Aktive Min: {snapshot.get('active_minutes', 0)}
Kalorien: {snapshot.get('calories', 0)} kcal | Stress: {snapshot.get('avg_stress', 'k.A.')}
Body Battery: {snapshot.get('body_battery', 'k.A.')}
Datenabfrage: {snapshot.get('fetched_time', 'k.A.')} Uhr

Aktivitäten:
{activity_lines}

Format: 3-4 Bullets:
• Tagesbelastung einordnen
• Regenerationsbedarf erklären
• Zusammenhang zu morgen herstellen
• konkrete Empfehlung für Schlaf, Training oder aktive Erholung
Jeder Bullet maximal 22 Wörter.
Keine reine Rohdatenliste.
Body Battery abends als normalen Tagesverbrauch einordnen, nicht pauschal als schlechte Erholung.
"""
        return await self._chat(prompt)

    async def generate_weekly_summary(self, weekly: dict) -> str:
        w_available = weekly.get('weight_available', False)
        weight_section = f"""
KÖRPERKOMPOSITION (letzte 30 Tage):
Gewicht: {weekly.get('latest_weight')} kg ({_delta_str(weekly.get('weight_delta'))} kg Trend)
Körperfett: {weekly.get('latest_body_fat')} % ({_delta_str(weekly.get('fat_delta'))} %)
Muskelmasse: {weekly.get('latest_muscle_mass')} kg ({_delta_str(weekly.get('muscle_delta'))} kg)
Unterhautfett: {weekly.get('latest_subfat')} % · Viszeralfett Level: {weekly.get('latest_visceral_fat')}
Protein: {weekly.get('latest_protein')} % · Körperalter: {weekly.get('latest_metabolic_age')} Jahre
""" if w_available else "\nKÖRPERKOMPOSITION: Keine Renpho-Daten diese Woche.\n"

        prompt = f"""
Erstelle eine strukturierte wöchentliche Trainings-, Schlaf- und Körperkompositions-Zusammenfassung:

📅 Woche: {weekly.get('week_start')} bis {weekly.get('week_end')}

TRAINING:
Gym-Einheiten: {weekly.get('gym_days')} (Ziel: 3)
Lauf-Einheiten: {weekly.get('run_days')} (Ziel: 3)
Gesamtdistanz: {weekly.get('total_distance_km')} km
Trainingsdauer: {_hm(weekly.get('total_duration_minutes'))}
Kalorien (Training): {weekly.get('total_calories_burned')} kcal
Training Load: {weekly.get('total_load', 'k.A.')}
Fitness/Fatigue/Form: {(weekly.get('training_trend') or {}).get('fitness', 'k.A.')} / {(weekly.get('training_trend') or {}).get('fatigue', 'k.A.')} / {(weekly.get('training_trend') or {}).get('form', 'k.A.')}

SCHLAF (Wochendurchschnitt):
Schlafdauer: {_hm(weekly.get('avg_sleep_minutes'))}
Schlaf-Score: {weekly.get('avg_sleep_score', 'k.A.')}
Tiefschlaf: {_hm(weekly.get('avg_deep_sleep_minutes'))}
REM-Schlaf: {_hm(weekly.get('avg_rem_sleep_minutes'))}

ERHOLUNG (aktuell):
HRV: {weekly.get('today_hrv', 'k.A.')} ms
Body Battery: {weekly.get('today_body_battery', 'k.A.')}
Ruhe-Puls: {weekly.get('today_resting_hr', 'k.A.')} bpm
Datenabfrage: {(weekly.get('snapshot') or {}).get('fetched_time', 'k.A.')} Uhr
{weight_section}
Format: 5-6 Bullets:
• Wochenfazit zu Trainingsziel und Load
• Fitness/Fatigue/Form interpretieren
• Schlaf und Recovery im Kontext der Belastung erklären
• Körperkomposition trendbasiert einordnen, falls vorhanden
• stärkster Hebel für nächste Woche
• konkrete Empfehlung zu Training, Erholung oder Ernährung
Jeder Bullet maximal 24 Wörter.
Keine reine Rohdatenliste, die Statistik kommt separat.

Setze die Werte in Perspektive für einen Hybrid-Athleten (3x Gym + 3x Laufen/Woche).
"""
        return await self._chat(prompt)

    async def generate_weight_insight(self, trend: dict) -> str:
        if not trend.get("available"):
            return "📊 Keine Renpho-Daten vorhanden. Bitte wiege dich!"

        prompt = f"""
Analysiere diese Körperkompositions-Daten der letzten {trend.get('period_days')} Tage:

GEWICHT & BMI:
Gewicht: {trend.get('latest_weight')} kg ({_delta_str(trend.get('weight_delta'))} kg Trend)
BMI: {trend.get('latest_bmi')}

KÖRPERFETT:
Gesamtkörperfett: {trend.get('latest_body_fat')} % ({_delta_str(trend.get('fat_delta'))} % Trend)
Unterhautfett: {trend.get('latest_subfat')} %
Viszeralfett Level: {trend.get('latest_visceral_fat')}

MUSKELN & MASSE:
Muskelmasse: {trend.get('latest_muscle_mass')} kg ({_delta_str(trend.get('muscle_delta'))} kg Trend)
Fettfreie Masse: {trend.get('latest_lean_mass')} kg
Fettfreies Gewicht: {trend.get('latest_fat_free_weight')} kg
Knochenmasse: {trend.get('latest_bone_mass')} kg

STOFFWECHSEL & WEITERE:
Körperwasser: {trend.get('latest_body_water')} %
Protein: {trend.get('latest_protein')} %
Grundumsatz (BMR): {trend.get('latest_bmr')} kcal
Körperalter: {trend.get('latest_metabolic_age')} Jahre

Anzahl Messungen: {trend.get('measurements_count')} in {trend.get('period_days')} Tagen

Format: 4-5 Bullets:
• Trendqualität und Messfrequenz einordnen
• Gewichtstrend mit Körperfett und Muskelmasse zusammen interpretieren
• BIA-Messrauschen knapp erklären
• konkrete Empfehlung für nächste 7 Tage
Jeder Bullet maximal 24 Wörter.
Keine reine Rohdatenliste.
"""
        return await self._chat(prompt)

    async def generate_plan_explanation(self, plan: dict) -> str:
        snapshot = plan.get("snapshot") or {}
        weekly = plan.get("weekly") or {}
        readiness = plan.get("readiness") or {}
        trend = weekly.get("training_trend") or {}
        prompt = f"""
Erkläre die heutige Trainingsentscheidung evidenzorientiert.

ENTSCHEIDUNG:
Readiness: {readiness.get('score', 'k.A.')}/100
Empfehlung: {readiness.get('recommendation', 'k.A.')}
Vorgeschlagene Einheit: {plan.get('suggested_session', 'k.A.')}
Limitierende Faktoren: {', '.join(readiness.get('limiting_factors') or []) or 'keine'}

HEUTE:
Schlaf: {_hm(snapshot.get('sleep_duration_minutes'))}, Score: {snapshot.get('sleep_score', 'k.A.')}
HRV: {snapshot.get('avg_hrv', 'k.A.')} ms ({snapshot.get('hrv_status', 'k.A.')})
Body Battery: {snapshot.get('body_battery', 'k.A.')}
Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm
Stress: {snapshot.get('avg_stress', 'k.A.')}
Datenabfrage: {snapshot.get('fetched_time', 'k.A.')} Uhr

WOCHE:
Gym: {weekly.get('gym_days', 0)}/{weekly.get('gym_goal', 3)}
Laufen: {weekly.get('run_days', 0)}/{weekly.get('run_goal', 3)}
Load: {weekly.get('total_load', 0)}
Fitness/Fatigue/Form: {trend.get('fitness', 0)} / {trend.get('fatigue', 0)} / {trend.get('form', 0)}

Format: 4 Bullets:
• warum diese Entscheidung heute sinnvoll ist
• physiologische Begründung
• Wochenziel-Kontext
• konkrete Anpassungsregel nur bei direktem Datenbezug
Jeder Bullet maximal 22 Wörter.
Keine generischen Stoppsignale, schweren-Beine-Floskeln oder offensichtlichen Warnhinweise.
"""
        return await self._chat(prompt)

    async def answer_free_question(
        self,
        question: str,
        snapshot: dict,
        activities: list,
        weight_trend: dict | None = None,
        hrv_trend: dict | None = None,
    ) -> str:
        recent = "\n".join(
            f"- {a.get('start_time', '')[:10]} | {a.get('name', a.get('type', '?'))} | "
            f"{a.get('duration_minutes')} Min | {a.get('distance_km', 0)} km | "
            f"Ø HR: {a.get('avg_hr', '?')} bpm | Pace: {a.get('avg_pace_min_km', '?')} min/km | "
            f"SPM: {a.get('avg_spm', '?')} | +{a.get('elevation_gain_m', 0)} m"
            for a in activities[:10]
        ) or "Keine Aktivitäten verfügbar"

        wt = weight_trend or {}
        if wt.get("available"):
            weight_section = f"""
RENPHO KÖRPERKOMPOSITION (letzte 30 Tage):
Gewicht: {wt.get('latest_weight')} kg ({_delta_str(wt.get('weight_delta'))} kg Trend)
BMI: {wt.get('latest_bmi')}
Körperfett gesamt: {wt.get('latest_body_fat')} % ({_delta_str(wt.get('fat_delta'))} %)
Unterhautfett: {wt.get('latest_subfat')} % · Viszeralfett Level: {wt.get('latest_visceral_fat')}
Muskelmasse: {wt.get('latest_muscle_mass')} kg ({_delta_str(wt.get('muscle_delta'))} kg)
Fettfreie Masse: {wt.get('latest_lean_mass')} kg · Fettfreies Gewicht: {wt.get('latest_fat_free_weight')} kg
Körperwasser: {wt.get('latest_body_water')} % · Protein: {wt.get('latest_protein')} %
Knochenmasse: {wt.get('latest_bone_mass')} kg · BMR: {wt.get('latest_bmr')} kcal
Körperalter: {wt.get('latest_metabolic_age')} Jahre
Messungen: {wt.get('measurements_count')} in 30 Tagen · Letzte: {wt.get('latest_date')}"""
        else:
            weight_section = "\nRENPHO: Keine Daten verfügbar."

        ht = hrv_trend or {}
        if ht.get("available"):
            hrv_samples = ", ".join(
                f"{s.get('date')}: {s.get('value')} ms"
                for s in ht.get("samples", [])[-14:]
            )
            hrv_section = f"""
HRV-VERLAUF ({ht.get('start_date')} bis {ht.get('end_date')}, {ht.get('samples_count')} Werte):
Aktuell: {ht.get('latest')} ms | Start: {ht.get('first')} ms | Delta: {_delta_str(ht.get('delta'))} ms
Ø: {ht.get('average')} ms | Min/Max: {ht.get('minimum')}/{ht.get('maximum')} ms
Trendhälften: {ht.get('early_avg')} → {ht.get('late_avg')} ms ({_delta_str(ht.get('trend_delta'))} ms)
Status-Verteilung: {ht.get('status_counts')}
Letzte Werte: {hrv_samples}"""
        elif hrv_trend is not None:
            hrv_section = f"""
HRV-VERLAUF:
Für die letzten {ht.get('period_days', 28)} Tage sind keine belastbaren HRV-Verlaufswerte verfügbar."""
        else:
            hrv_section = "\nHRV-VERLAUF: Nicht abgefragt, außer die Frage zielt auf HRV-Entwicklung."

        prompt = f"""
Beantworte diese Frage von Dimitri basierend auf seinen aktuellen Gesundheits- und Trainingsdaten:

FRAGE: {question}

AKTUELLE DATEN (heute):
Schlaf: {_hm(snapshot.get('sleep_duration_minutes'))}, Score: {snapshot.get('sleep_score', 'k.A.')}
HRV: {snapshot.get('avg_hrv', 'k.A.')} ms ({snapshot.get('hrv_status', 'k.A.')})
Body Battery: {snapshot.get('body_battery', 'k.A.')}
Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm
Schritte: {snapshot.get('steps', 0)}
Datenabfrage: {snapshot.get('fetched_time', 'k.A.')} Uhr
{weight_section}
{hrv_section}

LETZTE AKTIVITÄTEN:
{recent}

Format: Bullets — beantworte die Frage direkt, nutze die Daten zur Einordnung.
Bei Fragen zur HRV-Entwicklung: zuerst Verlauf/Trend beantworten, dann Tageswert und Kontext einordnen.
Wenn kein HRV-Verlauf verfügbar ist, klar sagen, dass keine belastbare Entwicklung ableitbar ist.
Zeitabhängige Werte wie Body Battery relativ zur Abfragezeit interpretieren.
"""
        return await self._chat(prompt)

    async def generate_training_tip(self, snapshot: dict, recent_activities: list) -> str:
        recent_types = [a.get("type") for a in recent_activities[:5]]
        readiness = snapshot.get("readiness") or {}
        prompt = f"""
Gib einen konkreten Trainingstipp basierend auf:

Aktuelle Erholung:
- Readiness: {readiness.get('score', 'k.A.')}/100 ({readiness.get('recommendation', 'k.A.')})
- Body Battery: {snapshot.get('body_battery', 'k.A.')}
- HRV: {snapshot.get('avg_hrv', 'k.A.')} ms (Status: {snapshot.get('hrv_status', 'k.A.')})
- Training Readiness: {snapshot.get('training_readiness_score', 'k.A.')}
- Ruhe-Puls: {snapshot.get('resting_hr', 'k.A.')} bpm

Letzte 5 Aktivitäten: {', '.join(str(t) for t in recent_types)}

Trainingsziel: 3x Gym + 3x Laufen pro Woche als Hybrid-Athlet.
Format: 3-4 Bullets — 1 Erholungs-Status, dann 2-3 spezifische, umsetzbare Tipps.
"""
        return await self._chat(prompt)

    async def _chat(self, user_message: str) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _ATHLETE_PROFILE},
                    {"role": "user", "content": user_message},
                ],
                max_completion_tokens=10000,
            )
            choice = response.choices[0]
            content = choice.message.content
            # gpt-5.5 kann refusal oder leeren content liefern
            refusal = getattr(choice.message, "refusal", None)
            logger.debug(f"OpenAI content: {repr(content)} | refusal: {repr(refusal)} | finish: {choice.finish_reason}")
            if refusal:
                logger.warning(f"OpenAI refusal: {refusal}")
                return ""
            if not content:
                logger.warning(f"OpenAI returned empty content (finish_reason={choice.finish_reason})")
                return ""
            return content.strip()
        except Exception as e:
            logger.error(f"OpenAI Fehler: {e}", exc_info=True)
            return ""


def _delta_str(delta: Optional[float]) -> str:
    if delta is None:
        return "k.A."
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}"
