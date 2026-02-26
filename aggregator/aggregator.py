"""Aggregator — merges Whoop + Oura data, computes composite scores, saves to DB."""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from clients.whoop_client import WhoopClient, WhoopAuthError
from clients.oura_client import OuraClient, OuraAuthError
from database.db import db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _safe(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _composite_recovery(whoop: dict, oura: dict) -> float | None:
    """
    Weighted average of Whoop recovery score (0-100) and Oura readiness (0-100).
    If only one source is available, use that alone.
    """
    w_score = _safe(whoop.get("recovery_score"))
    o_score = _safe(oura.get("readiness_score"))

    if w_score is not None and o_score is not None:
        return round(w_score * 0.5 + o_score * 0.5, 1)
    if w_score is not None:
        return round(w_score, 1)
    if o_score is not None:
        return round(o_score, 1)
    return None


def _training_readiness(whoop: dict, oura: dict, composite: float | None) -> float | None:
    """
    Composite score penalized by:
      - High HRV deviation from baseline (proxy: low HRV → penalty)
      - High stress (Oura)
      - Temperature deviation
    Returns 0-100.
    """
    if composite is None:
        return None

    score = composite

    # Stress penalty (0-100 scale → subtract up to 10 pts)
    stress = _safe(oura.get("stress_high"))
    if stress is not None:
        # stress_high is hours; >8h is high
        penalty = min(10.0, stress * 1.25)
        score -= penalty

    # Temperature deviation penalty (|dev| > 0.5°C → penalize)
    temp_dev = _safe(oura.get("temperature_deviation"))
    if temp_dev is not None:
        penalty = min(5.0, abs(temp_dev) * 5)
        score -= penalty

    # SpO2 bonus/penalty (optimal ≥ 95%)
    spo2 = _safe(whoop.get("spo2"))
    if spo2 is not None and spo2 < 95:
        score -= (95 - spo2) * 2

    return round(max(0.0, min(100.0, score)), 1)


# ---------------------------------------------------------------------------
# Main aggregate function
# ---------------------------------------------------------------------------

def aggregate() -> dict:
    """
    Fetch data from Whoop and Oura, compute composite scores, persist to DB.
    Returns a unified summary dict ready for display.
    """
    today = date.today().isoformat()

    whoop: dict = {}
    oura: dict = {}
    errors: list[str] = []

    try:
        whoop = WhoopClient().get_all()
    except WhoopAuthError as e:
        errors.append(f"Whoop: {e}")
        logger.warning("[Aggregator] %s", e)
    except Exception as e:
        errors.append(f"Whoop error: {e}")
        logger.exception("[Aggregator] Whoop fetch failed")

    try:
        oura = OuraClient().get_all()
    except OuraAuthError as e:
        errors.append(f"Oura: {e}")
        logger.warning("[Aggregator] %s", e)
    except Exception as e:
        errors.append(f"Oura error: {e}")
        logger.exception("[Aggregator] Oura fetch failed")

    composite = _composite_recovery(whoop, oura)
    training = _training_readiness(whoop, oura, composite)

    # Persist Whoop metrics
    if whoop and not all(v is None for k, v in whoop.items() if not k.startswith("_")):
        _save_whoop(today, whoop)

    # Persist Oura metrics
    if oura and not all(v is None for k, v in oura.items() if not k.startswith("_")):
        _save_oura(today, oura)

    # Persist composite scores
    if composite is not None or training is not None:
        _save_daily_scores(today, composite, training)

    return {
        "date": today,
        "whoop": whoop,
        "oura": oura,
        "composite_recovery": composite,
        "training_readiness": training,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

def _save_whoop(today: str, w: dict) -> None:
    raw = json.dumps(w.get("_raw", {}))
    with db() as conn:
        conn.execute(
            """
            INSERT INTO whoop_metrics
                (date, recovery_score, hrv_rmssd, rhr, spo2, skin_temp_c,
                 sleep_score, sleep_duration_min, sleep_efficiency, workout_strain, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                recovery_score   = excluded.recovery_score,
                hrv_rmssd        = excluded.hrv_rmssd,
                rhr              = excluded.rhr,
                spo2             = excluded.spo2,
                skin_temp_c      = excluded.skin_temp_c,
                sleep_score      = excluded.sleep_score,
                sleep_duration_min = excluded.sleep_duration_min,
                sleep_efficiency = excluded.sleep_efficiency,
                workout_strain   = excluded.workout_strain,
                raw_json         = excluded.raw_json
            """,
            (
                today,
                _safe(w.get("recovery_score")),
                _safe(w.get("hrv_rmssd")),
                _safe(w.get("rhr")),
                _safe(w.get("spo2")),
                _safe(w.get("skin_temp_c")),
                _safe(w.get("sleep_score")),
                _safe(w.get("sleep_duration_min")),
                _safe(w.get("sleep_efficiency")),
                _safe(w.get("workout_strain")),
                raw,
            ),
        )
    logger.info("[Aggregator] Whoop metrics saved for %s", today)


def _save_oura(today: str, o: dict) -> None:
    raw = json.dumps(o.get("_raw", {}))
    with db() as conn:
        conn.execute(
            """
            INSERT INTO oura_metrics
                (date, readiness_score, readiness_contributors, sleep_score, sleep_contributors,
                 activity_score, activity_contributors, stress_high, recovery_high, day_summary,
                 temperature_deviation, temperature_trend_deviation, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                readiness_score              = excluded.readiness_score,
                readiness_contributors       = excluded.readiness_contributors,
                sleep_score                  = excluded.sleep_score,
                sleep_contributors           = excluded.sleep_contributors,
                activity_score               = excluded.activity_score,
                activity_contributors        = excluded.activity_contributors,
                stress_high                  = excluded.stress_high,
                recovery_high                = excluded.recovery_high,
                day_summary                  = excluded.day_summary,
                temperature_deviation        = excluded.temperature_deviation,
                temperature_trend_deviation  = excluded.temperature_trend_deviation,
                raw_json                     = excluded.raw_json
            """,
            (
                today,
                o.get("readiness_score"),
                json.dumps(o.get("readiness_contributors")),
                o.get("sleep_score"),
                json.dumps(o.get("sleep_contributors")),
                o.get("activity_score"),
                json.dumps(o.get("activity_contributors")),
                _safe(o.get("stress_high")),
                _safe(o.get("recovery_high")),
                o.get("day_summary"),
                _safe(o.get("temperature_deviation")),
                _safe(o.get("temperature_trend_deviation")),
                raw,
            ),
        )
    logger.info("[Aggregator] Oura metrics saved for %s", today)


def _save_daily_scores(today: str, composite: float | None, training: float | None) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO daily_scores (date, composite_recovery, training_readiness)
            VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                composite_recovery = excluded.composite_recovery,
                training_readiness = excluded.training_readiness
            """,
            (today, composite, training),
        )
    logger.info("[Aggregator] Daily scores saved for %s", today)
