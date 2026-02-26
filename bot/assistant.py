"""Claude-powered health assistant — answers questions using Whoop + Oura data."""
from __future__ import annotations

import logging

import anthropic

import config
from aggregator.aggregator import aggregate

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
- Whoop: recovery score, HRV, RHR, strain, sleep performance
- Oura: readiness score, deep/REM sleep stages, body temperature deviation, SpO2, stress level

How to use the data:
- Always ground your answers in actual numbers. Don't give generic advice.
- If HRV is low on both devices — say it clearly and explain what it means for today.
- If temperature is elevated — flag it as a potential early warning sign.
- Compare today's metrics to the user's personal baseline, not population averages.
- Consider the relationship between yesterday's strain and today's recovery when giving recommendations.

What you can do:
- Give a morning briefing when asked or on schedule
- Answer questions like "can I train hard today", "why am I tired", "how was my sleep"
- Notice trends over 7-14 days and proactively mention them
- Warn about signs of overtraining or approaching illness based on combined signals
- Learn about the user through conversation: their sport, training schedule, goals, lifestyle — and use this context in future responses

Rules:
- Never give generic health advice that ignores the actual data
- If data from Whoop and Oura conflicts — mention both numbers and explain possible reason
- Don't sugarcoat bad recovery. If the person should rest, say so directly.
- Keep responses concise. No long paragraphs. Get to the point.
- Ask clarifying questions about the user's context when relevant — don't assume
- If asked something outside health/training/recovery — politely redirect back to your purpose
- If data is missing (None/—) — don't make it up, say the data is unavailable"""


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

    lines.append(f"\n--- Whoop Strain ---")
    lines.append(f"Workout Strain: {w.get('workout_strain', '—')}")

    lines.append("\n--- Oura Ring ---")
    lines.append(f"Readiness Score: {o.get('readiness_score', '—')}/100")
    lines.append(f"Sleep Score: {o.get('sleep_score', '—')}/100")
    lines.append(f"Activity Score: {o.get('activity_score', '—')}/100")
    lines.append(f"Steps: {o.get('steps', '—')}")
    lines.append(f"Stress (high hours): {o.get('stress_high', '—')}h")
    lines.append(f"Recovery (high hours): {o.get('recovery_high', '—')}h")
    lines.append(f"Temperature Deviation: {o.get('temperature_deviation', '—')}°C")
    lines.append(f"SpO2 avg: {o.get('spo2_avg', '—')}%")

    errors = data.get("errors", [])
    if errors:
        lines.append("\n⚠️ Partial data:")
        for err in errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


def ask_health_assistant(question: str) -> str:
    """Fetch current health data and answer user's question with Claude."""
    try:
        data = aggregate()
        context = _build_health_context(data)
        system = SYSTEM_PROMPT.format(health_context=context)

        message = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": question}],
        )
        return message.content[0].text
    except Exception as e:
        logger.exception("[Assistant] Error")
        return f"Ошибка при обработке вопроса: {e}"
