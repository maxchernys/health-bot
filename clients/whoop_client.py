"""Whoop API v2 client — fetches recovery, sleep, workout for today."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

import config
from auth.flask_server import get_valid_token

logger = logging.getLogger(__name__)


class WhoopAuthError(Exception):
    pass


class WhoopClient:
    def __init__(self, chat_id: int):
        self.base = config.WHOOP_API_BASE
        self.chat_id = chat_id

    def _headers(self) -> dict[str, str]:
        token = get_valid_token(self.chat_id, "whoop")
        if not token:
            raise WhoopAuthError("No valid Whoop token. Run /connect_whoop first.")
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base}{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=15)
        if resp.status_code == 401:
            raise WhoopAuthError("Whoop token expired or invalid.")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _today_window() -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z")
        end = now.strftime("%Y-%m-%dT23:59:59.999Z")
        return start, end

    def _latest(self, endpoint: str) -> dict | None:
        start, end = self._today_window()
        try:
            data = self._get(endpoint, params={"start": start, "end": end, "limit": 1})
            records = data.get("records", [])
            if records:
                return records[0]
            data = self._get(endpoint, params={"limit": 1})
            records = data.get("records", [])
            return records[0] if records else None
        except Exception as e:
            logger.error("[Whoop] %s failed: %s", endpoint, e)
            return None

    def get_recovery(self) -> dict | None:
        return self._latest("/recovery")

    def get_sleep(self) -> dict | None:
        return self._latest("/activity/sleep")

    def get_workout(self) -> dict | None:
        start, end = self._today_window()
        try:
            data = self._get("/activity/workout", params={"start": start, "end": end, "limit": 1})
            records = data.get("records", [])
            return records[0] if records else None
        except Exception as e:
            logger.error("[Whoop] /activity/workout failed: %s", e)
            return None

    def get_all(self) -> dict:
        recovery = self.get_recovery() or {}
        sleep = self.get_sleep() or {}
        workout = self.get_workout() or {}

        # v2 recovery: {"score": {"recovery_score": 57.0, "resting_heart_rate": 51.0, ...}}
        score = recovery.get("score", {}) or {}
        result: dict[str, Any] = {
            "recovery_score": score.get("recovery_score"),
            "hrv_rmssd": score.get("hrv_rmssd_milli"),
            "rhr": score.get("resting_heart_rate"),
            "spo2": score.get("spo2_percentage"),
            "skin_temp_c": score.get("skin_temp_celsius"),
        }

        # v2 sleep: {"score": {"stage_summary": {...}, "sleep_performance_percentage": 93.0, ...}}
        sleep_score = sleep.get("score", {}) or {}
        stage = sleep_score.get("stage_summary", {}) or {}
        total_sleep_milli = (
            (stage.get("total_light_sleep_time_milli") or 0)
            + (stage.get("total_slow_wave_sleep_time_milli") or 0)
            + (stage.get("total_rem_sleep_time_milli") or 0)
        )
        result["sleep_duration_min"] = round(total_sleep_milli / 60000, 1) if total_sleep_milli else None
        result["sleep_efficiency"] = sleep_score.get("sleep_efficiency_percentage")
        result["sleep_performance"] = sleep_score.get("sleep_performance_percentage")
        result["sleep_consistency"] = sleep_score.get("sleep_consistency_percentage")
        result["respiratory_rate"] = sleep_score.get("respiratory_rate")
        result["disturbance_count"] = stage.get("disturbance_count")
        result["sleep_cycles"] = stage.get("sleep_cycle_count")
        # Sleep stages in minutes
        result["light_sleep_min"] = round((stage.get("total_light_sleep_time_milli") or 0) / 60000, 1) or None
        result["deep_sleep_min"] = round((stage.get("total_slow_wave_sleep_time_milli") or 0) / 60000, 1) or None
        result["rem_sleep_min"] = round((stage.get("total_rem_sleep_time_milli") or 0) / 60000, 1) or None
        result["awake_min"] = round((stage.get("total_awake_time_milli") or 0) / 60000, 1) or None
        # Sleep need
        sleep_need = sleep_score.get("sleep_needed", {}) or {}
        need_total_milli = (sleep_need.get("baseline_milli") or 0) + (sleep_need.get("need_from_sleep_debt_milli") or 0) + (sleep_need.get("need_from_recent_strain_milli") or 0)
        result["sleep_needed_min"] = round(need_total_milli / 60000, 1) if need_total_milli else None

        # v2 workout: {"score": {"strain": 4.43, ...}}
        workout_score = workout.get("score", {}) or {}
        result["workout_strain"] = workout_score.get("strain")

        result["_raw"] = {"recovery": recovery, "sleep": sleep, "workout": workout}
        return result
