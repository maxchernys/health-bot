"""Claude-powered health assistant — answers questions using Whoop + Oura data."""
from __future__ import annotations

import logging

import anthropic

import config
from aggregator.aggregator import aggregate
from database.db import db, save_message, get_recent_messages

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are a personal health assistant. You have access to real-time data from the user's Whoop and Oura Ring devices.

Here are the user's current metrics:

{health_context}

Your personality:
- Talk like a real person, not a corporate assistant. Short, direct, no fluff.
- Never use markdown: no asterisks, no headers, no bullet points, no bold text. Plain text only.
- You can be a bit blunt if the data says something the user might not want to hear.
- Always communicate in Russian. Use "ты" form.

Your data sources:
- Whoop: recovery score, HRV, RHR, daily strain, workout strain/sport/HR zones, sleep performance, calories burned
- Oura: readiness score, deep/REM sleep stages, body temperature deviation, SpO2, stress level, resilience, VO2 max, workouts, optimal bedtime

How to use the data:
- Always ground your answers in actual numbers. Don't give generic advice.
- If HRV is low on both devices — say it clearly and explain what it means for today.
- If temperature is elevated — flag it as a potential early warning sign.
- Compare today's metrics to the user's personal baseline from the 7-day history provided. Use the history to spot trends.
- Consider the relationship between yesterday's strain and today's recovery when giving recommendations.
- If HRV or recovery is trending down over 3+ days — flag it as a concern.
- If temperature deviation is growing — warn about possible illness.

What you can do:
- Give a morning briefing when asked or on schedule
- Answer questions like "can I train hard today", "why am I tired", "how was my sleep"
- Notice trends over 7-14 days and proactively mention them
- Warn about signs of overtraining or approaching illness based on combined signals
- Learn about the user through conversation: their sport, training schedule, goals, lifestyle — and use this context in future responses

Conversation memory:
- You have access to the full conversation history with this user.
- Use it to remember what the user told you: their sport, training schedule, goals, injuries, lifestyle habits, preferences.
- If the user mentioned something relevant before — use it without asking again.
- Build a mental model of the user over time and personalize your advice accordingly.

Rules:
- Never give generic health advice that ignores the actual data
- If data from Whoop and Oura conflicts — mention both numbers and explain possible reason
- Don't sugarcoat bad recovery. If the person should rest, say so directly.
- Keep responses concise. No long paragraphs. Get to the point.
- Ask clarifying questions about the user's context when relevant — don't assume
- If asked something outside health/training/recovery — politely redirect back to your purpose
- If data is missing (None/—) — don't make it up, say the data is unavailable"""


def _get_history(chat_id: int, days: int = 7) -> str:
    """Fetch last N days of metrics from DB for trend analysis."""
    lines = []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT d.date,
                   d.composite_recovery, d.training_readiness,
                   w.recovery_score, w.hrv_rmssd, w.rhr, w.sleep_duration_min,
                   w.sleep_efficiency, w.workout_strain,
                   w.day_strain, w.day_calories_kcal,
                   o.readiness_score, o.sleep_score, o.activity_score,
                   o.stress_high, o.temperature_deviation
            FROM daily_scores d
            LEFT JOIN whoop_metrics w ON w.chat_id = d.chat_id AND w.date = d.date
            LEFT JOIN oura_metrics o ON o.chat_id = d.chat_id AND o.date = d.date
            WHERE d.chat_id = ? AND d.date < date('now')
            ORDER BY d.date DESC
            LIMIT ?
            """,
            (chat_id, days),
        ).fetchall()

    if not rows:
        return ""

    lines.append(f"\n--- History (last {len(rows)} days) ---")
    for r in rows:
        hrv = f"{r['hrv_rmssd']:.0f}" if r["hrv_rmssd"] else "—"
        rhr = f"{r['rhr']:.0f}" if r["rhr"] else "—"
        sleep = ""
        if r["sleep_duration_min"]:
            h, m = divmod(int(r["sleep_duration_min"]), 60)
            sleep = f"{h}h{m}m"
        else:
            sleep = "—"
        day_strain = f"{r['day_strain']:.1f}" if r["day_strain"] else "—"
        w_strain = f"{r['workout_strain']:.1f}" if r["workout_strain"] else "—"
        cal = f"{r['day_calories_kcal']:.0f}" if r["day_calories_kcal"] else "—"
        stress = f"{r['stress_high']:.1f}h" if r["stress_high"] else "—"
        temp = f"{r['temperature_deviation']:+.2f}" if r["temperature_deviation"] is not None else "—"

        lines.append(
            f"  {r['date']}: recovery={r['composite_recovery'] or '—'}, "
            f"HRV={hrv}, RHR={rhr}, sleep={sleep}, "
            f"day_strain={day_strain}, workout={w_strain}, cal={cal}, "
            f"stress={stress}, temp_dev={temp}"
        )

    return "\n".join(lines)


def _build_health_context(data: dict) -> str:
    """Format aggregate() data into readable context for Claude."""
    w = data.get("whoop", {})
    o = data.get("oura", {})
    lines = []

    lines.append(f"Дата: {data.get('date', 'неизвестно')}")
    lines.append(f"Composite Recovery: {data.get('composite_recovery', '—')}/100")
    lines.append(f"Training Readiness: {data.get('training_readiness', '—')}/100")

    lines.append("\n--- Whoop Recovery ---")
    lines.append(f"Recovery Score: {w.get('recovery_score', '—')}/100")
    lines.append(f"HRV (RMSSD): {w.get('hrv_rmssd', '—')} ms")
    lines.append(f"Resting HR: {w.get('rhr', '—')} bpm")
    lines.append(f"SpO2: {w.get('spo2', '—')}%")
    lines.append(f"Skin Temp: {w.get('skin_temp_c', '—')}°C")

    lines.append("\n--- Whoop Sleep ---")
    lines.append(f"Sleep Performance: {w.get('sleep_performance', '—')}%")
    sleep_min = w.get("sleep_duration_min")
    sleep_needed = w.get("sleep_needed_min")
    if sleep_min:
        h, m = divmod(int(sleep_min), 60)
        lines.append(f"Sleep Duration: {h}h {m}m")
    else:
        lines.append("Sleep Duration: —")
    if sleep_needed:
        h, m = divmod(int(sleep_needed), 60)
        lines.append(f"Sleep Needed: {h}h {m}m")
    lines.append(f"Sleep Efficiency: {w.get('sleep_efficiency', '—')}%")
    lines.append(f"Sleep Consistency: {w.get('sleep_consistency', '—')}%")
    lines.append(f"Deep Sleep: {w.get('deep_sleep_min', '—')} min")
    lines.append(f"REM Sleep: {w.get('rem_sleep_min', '—')} min")
    lines.append(f"Light Sleep: {w.get('light_sleep_min', '—')} min")
    lines.append(f"Respiratory Rate: {w.get('respiratory_rate', '—')}/min")
    lines.append(f"Disturbances: {w.get('disturbance_count', '—')}")

    lines.append(f"\n--- Whoop Daily Strain ---")
    lines.append(f"Day Strain: {w.get('day_strain', '—')}")
    day_cal = w.get("day_calories_kcal")
    lines.append(f"Day Calories: {day_cal} kcal" if day_cal else "Day Calories: —")
    lines.append(f"Day Avg HR: {w.get('day_avg_hr', '—')} bpm")
    lines.append(f"Day Max HR: {w.get('day_max_hr', '—')} bpm")

    lines.append(f"\n--- Whoop Workout ---")
    lines.append(f"Workout Strain: {w.get('workout_strain', '—')}")
    lines.append(f"Sport: {w.get('workout_sport', '—')}")
    lines.append(f"Avg HR: {w.get('workout_avg_hr', '—')} bpm")
    lines.append(f"Max HR: {w.get('workout_max_hr', '—')} bpm")
    wcal = w.get("workout_calories_kcal")
    lines.append(f"Calories: {wcal} kcal" if wcal else "Calories: —")
    wdist = w.get("workout_distance_m")
    if wdist:
        lines.append(f"Distance: {wdist:.0f} m")
    walt = w.get("workout_altitude_m")
    if walt:
        lines.append(f"Altitude Gain: {walt:.0f} m")
    zones = []
    for i in range(6):
        z = w.get(f"workout_zone_{i}_min")
        if z:
            zones.append(f"Z{i}={z:.1f}m")
    if zones:
        lines.append(f"HR Zones: {', '.join(zones)}")

    lines.append("\n--- Oura Ring ---")
    lines.append(f"Readiness Score: {o.get('readiness_score', '—')}/100")
    lines.append(f"Sleep Score: {o.get('sleep_score', '—')}/100")
    lines.append(f"Activity Score: {o.get('activity_score', '—')}/100")
    lines.append(f"Steps: {o.get('steps', '—')}")
    o_total_cal = o.get("total_calories")
    o_active_cal = o.get("active_calories")
    if o_total_cal:
        bmr = o_total_cal - (o_active_cal or 0)
        lines.append(f"Calories: {o_total_cal} total / {o_active_cal or 0} active / {bmr} BMR")
    else:
        lines.append("Calories: —")
    lines.append(f"Stress (high hours): {o.get('stress_high', '—')}h")
    lines.append(f"Recovery (high hours): {o.get('recovery_high', '—')}h")
    lines.append(f"Temperature Deviation: {o.get('temperature_deviation', '—')}°C")
    lines.append(f"SpO2 avg: {o.get('spo2_avg', '—')}%")
    lines.append(f"Resilience: {o.get('resilience_level', '—')}")
    vo2 = o.get("vo2_max")
    lines.append(f"VO2 Max: {vo2}" if vo2 else "VO2 Max: —")

    oura_wtype = o.get("oura_workout_type")
    if oura_wtype:
        lines.append(f"\n--- Oura Workout ---")
        lines.append(f"Type: {oura_wtype}")
        lines.append(f"Intensity: {o.get('oura_workout_intensity', '—')}")
        ocal = o.get("oura_workout_calories")
        lines.append(f"Calories: {ocal} kcal" if ocal else "Calories: —")
        odist = o.get("oura_workout_distance_m")
        if odist:
            lines.append(f"Distance: {odist:.0f} m")
        lines.append(f"Avg HR: {o.get('oura_workout_avg_hr', '—')} bpm")
        lines.append(f"Max HR: {o.get('oura_workout_max_hr', '—')} bpm")

    bed_start = o.get("optimal_bedtime_start")
    if bed_start:
        lines.append(f"\n--- Optimal Bedtime ---")
        lines.append(f"Window: {bed_start} – {o.get('optimal_bedtime_end', '—')}")
        lines.append(f"Status: {o.get('optimal_bedtime_status', '—')}")

    errors = data.get("errors", [])
    if errors:
        lines.append("\n⚠️ Partial data:")
        for err in errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


def _build_health_context_with_history(chat_id: int, data: dict) -> str:
    """Build health context including 7-day history."""
    context = _build_health_context(data)
    history = _get_history(chat_id, 7)
    if history:
        context += "\n" + history
    return context


def ask_health_assistant(chat_id: int, question: str, *, save: bool = True) -> str:
    """Fetch current health data and answer user's question with Claude."""
    try:
        data = aggregate(chat_id)
        context = _build_health_context_with_history(chat_id, data)
        system = SYSTEM_PROMPT.format(health_context=context)

        history = get_recent_messages(chat_id)
        messages = history + [{"role": "user", "content": question}]

        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        answer = response.content[0].text

        if save:
            save_message(chat_id, "user", question)
            save_message(chat_id, "assistant", answer)

        return answer
    except Exception as e:
        logger.exception("[Assistant] Error")
        return f"Ошибка при обработке вопроса: {e}"


