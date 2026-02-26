"""Human-readable formatting helpers for health metrics."""
from __future__ import annotations

from typing import Any


def _pct_bar(value: float | None, width: int = 10) -> str:
    """Return a simple ASCII progress bar."""
    if value is None:
        return "░" * width
    filled = round((value / 100) * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def _score_emoji(value: float | None) -> str:
    if value is None:
        return "❓"
    if value >= 80:
        return "🟢"
    if value >= 60:
        return "🟡"
    return "🔴"


def _daily_tip(recovery: float | None, readiness: float | None) -> str:
    if recovery is None and readiness is None:
        return "❓ Недостаточно данных для рекомендации"
    score = recovery or readiness or 0
    if score >= 80:
        return "💪 Отличный день для интенсивной тренировки"
    if score >= 67:
        return "👍 Можно тренироваться, но без фанатизма"
    if score >= 50:
        return "🚶 Лёгкая активность — йога, прогулка, растяжка"
    return "🛌 Тело просит отдых. Лучше восстановиться"


def format_health_summary(data: dict) -> str:
    """Format aggregate() output as a Telegram-ready message."""
    today = data.get("date", "today")
    w = data.get("whoop", {})
    o = data.get("oura", {})
    comp = data.get("composite_recovery")
    train = data.get("training_readiness")
    errors = data.get("errors", [])

    lines = [f"📊 *Health Summary — {today}*\n"]

    # --- Composite scores ---
    lines.append("*Overall*")
    lines.append(
        f"  Recovery:   {_score_emoji(comp)} `{comp:.0f}/100` {_pct_bar(comp)}"
        if comp is not None
        else "  Recovery:   ❓ no data"
    )
    lines.append(
        f"  Training:   {_score_emoji(train)} `{train:.0f}/100` {_pct_bar(train)}"
        if train is not None
        else "  Training:   ❓ no data"
    )
    lines.append(f"\n  {_daily_tip(comp, train)}")

    # --- Whoop Recovery ---
    w_rec = w.get("recovery_score")
    lines.append("\n*Whoop — Recovery*")
    lines.append(
        f"  Score:      {_score_emoji(w_rec)} `{w_rec:.0f}/100` {_pct_bar(w_rec)}"
        if w_rec is not None
        else "  Score:      —"
    )
    hrv = w.get("hrv_rmssd")
    rhr = w.get("rhr")
    spo2 = w.get("spo2")
    skin_temp = w.get("skin_temp_c")
    lines.append(f"  HRV:        `{hrv:.1f} ms`" if hrv else "  HRV:        —")
    lines.append(f"  RHR:        `{rhr:.0f} bpm`" if rhr else "  RHR:        —")
    lines.append(f"  SpO₂:       `{spo2:.1f}%`" if spo2 else "  SpO₂:       —")
    lines.append(f"  Skin temp:  `{skin_temp:.1f}°C`" if skin_temp else "  Skin temp:  —")

    # --- Whoop Sleep ---
    w_sleep_perf = w.get("sleep_performance")
    lines.append("\n*Whoop — Sleep*")
    lines.append(
        f"  Performance: {_score_emoji(w_sleep_perf)} `{w_sleep_perf:.0f}%`"
        if w_sleep_perf is not None
        else "  Performance: —"
    )
    sleep_dur = w.get("sleep_duration_min")
    sleep_needed = w.get("sleep_needed_min")
    if sleep_dur:
        h, m = divmod(int(sleep_dur), 60)
        lines.append(f"  Duration:   `{h}h {m}m`")
    else:
        lines.append("  Duration:   —")
    if sleep_needed:
        h, m = divmod(int(sleep_needed), 60)
        lines.append(f"  Needed:     `{h}h {m}m`")
    w_eff = w.get("sleep_efficiency")
    lines.append(f"  Efficiency: `{w_eff:.1f}%`" if w_eff else "  Efficiency: —")
    deep = w.get("deep_sleep_min")
    rem = w.get("rem_sleep_min")
    light = w.get("light_sleep_min")
    if deep:
        lines.append(f"  Deep:       `{int(deep)}m`  REM: `{int(rem or 0)}m`  Light: `{int(light or 0)}m`")
    resp = w.get("respiratory_rate")
    lines.append(f"  Resp rate:  `{resp:.1f}/min`" if resp else "  Resp rate:  —")
    dist = w.get("disturbance_count")
    lines.append(f"  Disturb.:   `{dist}`" if dist is not None else "  Disturb.:   —")

    # --- Whoop Strain ---
    strain = w.get("workout_strain")
    if strain:
        lines.append(f"\n*Whoop — Strain*")
        lines.append(f"  Workout:    `{strain:.1f}`")

    # --- Oura ---
    lines.append("\n*Oura*")
    o_ready = o.get("readiness_score")
    o_sleep = o.get("sleep_score")
    o_act = o.get("activity_score")
    o_stress = o.get("stress_high")
    o_temp = o.get("temperature_deviation")
    o_steps = o.get("steps")

    lines.append(
        f"  Readiness:  {_score_emoji(o_ready)} `{o_ready}/100`"
        if o_ready is not None
        else "  Readiness:  —"
    )
    lines.append(
        f"  Sleep:      {_score_emoji(o_sleep)} `{o_sleep}/100`"
        if o_sleep is not None
        else "  Sleep:      —"
    )
    lines.append(
        f"  Activity:   {_score_emoji(o_act)} `{o_act}/100`"
        if o_act is not None
        else "  Activity:   —"
    )
    lines.append(f"  Steps:      `{o_steps:,}`" if o_steps else "  Steps:      —")
    lines.append(
        f"  Stress hrs: `{o_stress:.1f}h`" if o_stress is not None else "  Stress hrs: —"
    )
    lines.append(
        f"  Temp dev:   `{o_temp:+.2f}°C`" if o_temp is not None else "  Temp dev:   —"
    )
    o_spo2 = o.get("spo2_avg")
    lines.append(
        f"  SpO₂ avg:   `{o_spo2:.1f}%`" if o_spo2 is not None else "  SpO₂ avg:   —"
    )

    if errors:
        lines.append("\n⚠️ *Partial data:*")
        for err in errors:
            lines.append(f"  • {err}")

    return "\n".join(lines)


