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

    # --- Whoop Daily Strain ---
    day_strain = w.get("day_strain")
    if day_strain:
        lines.append(f"\n*Whoop — Daily*")
        lines.append(f"  Day Strain: `{day_strain:.1f}`")
        day_cal = w.get("day_calories_kcal")
        lines.append(f"  Calories:   `{day_cal:.0f} kcal`" if day_cal else "  Calories:   —")
        day_avg = w.get("day_avg_hr")
        lines.append(f"  Avg HR:     `{day_avg:.0f} bpm`" if day_avg else "  Avg HR:     —")
        day_max = w.get("day_max_hr")
        lines.append(f"  Max HR:     `{day_max:.0f} bpm`" if day_max else "  Max HR:     —")

    # --- Whoop Workout ---
    w_strain = w.get("workout_strain")
    if w_strain:
        lines.append(f"\n*Whoop — Workout*")
        lines.append(f"  Strain:     `{w_strain:.1f}`")
        lines.append(f"  Sport:      `{w.get('workout_sport', '—')}`")
        w_avg = w.get("workout_avg_hr")
        lines.append(f"  Avg HR:     `{w_avg:.0f} bpm`" if w_avg else "  Avg HR:     —")
        w_max = w.get("workout_max_hr")
        lines.append(f"  Max HR:     `{w_max:.0f} bpm`" if w_max else "  Max HR:     —")
        wcal = w.get("workout_calories_kcal")
        lines.append(f"  Calories:   `{wcal:.0f} kcal`" if wcal else "  Calories:   —")
        wdist = w.get("workout_distance_m")
        if wdist:
            lines.append(f"  Distance:   `{wdist:.0f} m`")
        walt = w.get("workout_altitude_m")
        if walt:
            lines.append(f"  Altitude:   `{walt:.0f} m`")
        zones = []
        for i in range(6):
            z = w.get(f"workout_zone_{i}_min")
            if z:
                zones.append(f"Z{i}:`{z:.0f}m`")
        if zones:
            lines.append(f"  HR Zones:   {' '.join(zones)}")

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
    o_total_cal = o.get("total_calories")
    o_active_cal = o.get("active_calories")
    if o_total_cal:
        bmr = o_total_cal - (o_active_cal or 0)
        lines.append(f"  Calories:   `{o_total_cal:,}` total / `{o_active_cal or 0:,}` active / `{bmr:,}` BMR")
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
    o_resil = o.get("resilience_level")
    lines.append(f"  Resilience: `{o_resil}`" if o_resil else "  Resilience: —")
    o_vo2 = o.get("vo2_max")
    lines.append(f"  VO₂ Max:    `{o_vo2:.1f}`" if o_vo2 else "  VO₂ Max:    —")

    # --- Oura Workout ---
    o_wtype = o.get("oura_workout_type")
    if o_wtype:
        lines.append(f"\n*Oura — Workout*")
        lines.append(f"  Type:       `{o_wtype}`")
        o_wint = o.get("oura_workout_intensity")
        lines.append(f"  Intensity:  `{o_wint}`" if o_wint else "  Intensity:  —")
        o_wcal = o.get("oura_workout_calories")
        lines.append(f"  Calories:   `{o_wcal:.0f} kcal`" if o_wcal else "  Calories:   —")
        o_wdist = o.get("oura_workout_distance_m")
        if o_wdist:
            lines.append(f"  Distance:   `{o_wdist:.0f} m`")
        o_wavg = o.get("oura_workout_avg_hr")
        lines.append(f"  Avg HR:     `{o_wavg:.0f} bpm`" if o_wavg else "  Avg HR:     —")
        o_wmax = o.get("oura_workout_max_hr")
        lines.append(f"  Max HR:     `{o_wmax:.0f} bpm`" if o_wmax else "  Max HR:     —")

    # --- Optimal Bedtime ---
    bed_start = o.get("optimal_bedtime_start")
    if bed_start:
        bed_end = o.get("optimal_bedtime_end", "—")
        bed_status = o.get("optimal_bedtime_status", "—")
        lines.append(f"\n*Optimal Bedtime*")
        lines.append(f"  Window:     `{bed_start} – {bed_end}`")
        lines.append(f"  Status:     `{bed_status}`")

    if errors:
        lines.append("\n⚠️ *Partial data:*")
        for err in errors:
            lines.append(f"  • {err}")

    return "\n".join(lines)


