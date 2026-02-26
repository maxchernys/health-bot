"""Oura Ring API v2 client — fetches readiness, sleep, activity, stress, temperature."""
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
    def __init__(self):
        self.base = config.OURA_API_BASE

    def _headers(self) -> dict[str, str]:
        token = get_valid_token("oura")
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

    # ------------------------------------------------------------------
    # Convenience: all metrics
    # ------------------------------------------------------------------
    def get_all(self) -> dict:
        readiness = self.get_readiness() or {}
        sleep = self.get_sleep() or {}
        activity = self.get_activity() or {}
        stress = self.get_stress() or {}
        spo2 = self.get_spo2() or {}

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
        }

        result["_raw"] = {
            "readiness": readiness,
            "sleep": sleep,
            "activity": activity,
            "stress": stress,
            "spo2": spo2,
        }

        return result
