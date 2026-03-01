"""Oura Ring API v2 client — fetches readiness, sleep, activity, stress, resilience, VO2 max, workouts, bedtime."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import requests

import config
from auth.flask_server import get_valid_token

logger = logging.getLogger(__name__)


class OuraAuthError(Exception):
    pass


class OuraClient:
    def __init__(self, chat_id: int):
        self.base = config.OURA_API_BASE
        self.chat_id = chat_id

    def _headers(self) -> dict[str, str]:
        token = get_valid_token(self.chat_id, "oura")
        if not token:
            raise OuraAuthError("No valid Oura token. Run /connect_oura first.")
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code == 401:
            raise OuraAuthError("Oura token expired or invalid.")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _today() -> str:
        return date.today().isoformat()

    def _fetch_today(self, endpoint: str, fallback_days: int = 0) -> dict | None:
        today = self._today()
        try:
            data = self._get(endpoint, params={"start_date": today, "end_date": today})
            items = data.get("data", [])
            if items:
                return items[0]
            if fallback_days > 0:
                start = (date.today() - timedelta(days=fallback_days)).isoformat()
                data = self._get(endpoint, params={"start_date": start, "end_date": today})
                items = data.get("data", [])
                return items[-1] if items else None
            return None
        except Exception as e:
            logger.error("[Oura] %s failed: %s", endpoint, e)
            return None

    # ------------------------------------------------------------------
    # Individual endpoints
    # ------------------------------------------------------------------
    def get_readiness(self) -> dict | None:
        return self._fetch_today("/daily_readiness")

    def get_sleep(self) -> dict | None:
        return self._fetch_today("/daily_sleep")

    def get_activity(self) -> dict | None:
        return self._fetch_today("/daily_activity", fallback_days=2)

    def get_stress(self) -> dict | None:
        return self._fetch_today("/daily_stress")

    def get_spo2(self) -> dict | None:
        return self._fetch_today("/daily_spo2")

    def get_resilience(self) -> dict | None:
        return self._fetch_today("/daily_resilience")

    def get_vo2_max(self) -> dict | None:
        return self._fetch_today("/vo2_max", fallback_days=7)

    def get_workout(self) -> dict | None:
        """Get the most recent workout for today."""
        today = self._today()
        try:
            data = self._get("/workout", params={"start_date": today, "end_date": today})
            items = data.get("data", [])
            return items[-1] if items else None
        except Exception as e:
            logger.error("[Oura] /workout failed: %s", e)
            return None

    def get_sleep_time(self) -> dict | None:
        return self._fetch_today("/sleep_time")

    @staticmethod
    def _offset_to_time(offset: int | None) -> str | None:
        """Convert seconds-from-midnight offset to HH:MM string."""
        if offset is None:
            return None
        h, remainder = divmod(abs(offset), 3600)
        m = remainder // 60
        return f"{h:02d}:{m:02d}"

    # ------------------------------------------------------------------
    # Convenience: all metrics
    # ------------------------------------------------------------------
    def get_all(self) -> dict:
        readiness = self.get_readiness() or {}
        sleep = self.get_sleep() or {}
        activity = self.get_activity() or {}
        stress = self.get_stress() or {}
        spo2 = self.get_spo2() or {}
        resilience = self.get_resilience() or {}
        vo2 = self.get_vo2_max() or {}
        workout = self.get_workout() or {}
        sleep_time = self.get_sleep_time() or {}

        spo2_pct = spo2.get("spo2_percentage", {}) or {}

        result: dict[str, Any] = {
            # Readiness
            "readiness_score": readiness.get("score"),
            "readiness_contributors": readiness.get("contributors"),
            "readiness_level": readiness.get("level"),
            # Sleep
            "sleep_score": sleep.get("score"),
            "sleep_contributors": sleep.get("contributors"),
            # Activity
            "activity_score": activity.get("score"),
            "activity_contributors": activity.get("contributors"),
            "steps": activity.get("steps"),
            "total_calories": activity.get("total_calories"),
            "active_calories": activity.get("active_calories"),
            # Stress (API returns seconds, convert to hours)
            "stress_high": round(stress.get("stress_high", 0) / 3600, 1) if stress.get("stress_high") is not None else None,
            "recovery_high": round(stress.get("recovery_high", 0) / 3600, 1) if stress.get("recovery_high") is not None else None,
            "day_summary": stress.get("day_summary"),
            # Temperature (from readiness response)
            "temperature_deviation": readiness.get("temperature_deviation"),
            "temperature_trend_deviation": readiness.get("temperature_trend_deviation"),
            # SpO2
            "spo2_avg": spo2_pct.get("average"),
            # Resilience
            "resilience_level": resilience.get("level"),
            "resilience_contributors": resilience.get("contributors"),
            # VO2 Max
            "vo2_max": vo2.get("vo2_max"),
            # Workout
            "oura_workout_type": workout.get("activity"),
            "oura_workout_calories": workout.get("calories"),
            "oura_workout_distance_m": workout.get("distance"),
            "oura_workout_intensity": workout.get("intensity"),
            "oura_workout_avg_hr": workout.get("average_heart_rate"),
            "oura_workout_max_hr": workout.get("max_heart_rate"),
            # Optimal bedtime
            "optimal_bedtime_start": self._offset_to_time(sleep_time.get("recommendation", {}).get("optimal_bedtime", {}).get("start_offset")),
            "optimal_bedtime_end": self._offset_to_time(sleep_time.get("recommendation", {}).get("optimal_bedtime", {}).get("end_offset")),
            "optimal_bedtime_status": sleep_time.get("recommendation", {}).get("status"),
        }

        result["_raw"] = {
            "readiness": readiness,
            "sleep": sleep,
            "activity": activity,
            "stress": stress,
            "spo2": spo2,
            "resilience": resilience,
            "vo2_max": vo2,
            "workout": workout,
            "sleep_time": sleep_time,
        }

        return result
