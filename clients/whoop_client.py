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


SPORT_ID_MAP = {
    -1: "Activity", 0: "Running", 1: "Cycling", 16: "Baseball",
    17: "Basketball", 18: "Rowing", 21: "Football", 22: "Golf",
    24: "Ice Hockey", 25: "Lacrosse", 27: "Rugby", 29: "Skiing",
    30: "Soccer", 33: "Swimming", 34: "Tennis", 36: "Volleyball",
    39: "Boxing", 42: "Dance", 43: "Pilates", 44: "Yoga",
    45: "Weightlifting", 47: "CrossFit", 48: "Duathlon", 50: "HIIT",
    51: "Martial Arts", 52: "Hiking/Rucking", 55: "Triathlon",
    56: "Walking", 57: "Surfing", 63: "Functional Fitness",
    71: "Kickboxing", 73: "Meditation",
}


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

    def get_cycle(self) -> dict | None:
        return self._latest("/cycle")

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
        cycle = self.get_cycle() or {}

        # v2 recovery
        score = recovery.get("score", {}) or {}
        result: dict[str, Any] = {
            "recovery_score": score.get("recovery_score"),
            "hrv_rmssd": score.get("hrv_rmssd_milli"),
            "rhr": score.get("resting_heart_rate"),
            "spo2": score.get("spo2_percentage"),
            "skin_temp_c": score.get("skin_temp_celsius"),
        }

        # v2 sleep
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
        result["light_sleep_min"] = round((stage.get("total_light_sleep_time_milli") or 0) / 60000, 1) or None
        result["deep_sleep_min"] = round((stage.get("total_slow_wave_sleep_time_milli") or 0) / 60000, 1) or None
        result["rem_sleep_min"] = round((stage.get("total_rem_sleep_time_milli") or 0) / 60000, 1) or None
        result["awake_min"] = round((stage.get("total_awake_time_milli") or 0) / 60000, 1) or None
        sleep_need = sleep_score.get("sleep_needed", {}) or {}
        need_total_milli = (sleep_need.get("baseline_milli") or 0) + (sleep_need.get("need_from_sleep_debt_milli") or 0) + (sleep_need.get("need_from_recent_strain_milli") or 0)
        result["sleep_needed_min"] = round(need_total_milli / 60000, 1) if need_total_milli else None

        # v2 cycle (daily strain)
        cycle_score = cycle.get("score", {}) or {}
        result["day_strain"] = cycle_score.get("strain")
        kj = cycle_score.get("kilojoule")
        result["day_calories_kcal"] = round(kj / 4.184) if kj else None
        result["day_avg_hr"] = cycle_score.get("average_heart_rate")
        result["day_max_hr"] = cycle_score.get("max_heart_rate")

        # v2 workout (enhanced)
        workout_score = workout.get("score", {}) or {}
        result["workout_strain"] = workout_score.get("strain")
        sport_id = workout.get("sport_id")
        result["workout_sport"] = SPORT_ID_MAP.get(sport_id, f"Sport #{sport_id}") if sport_id is not None else None
        result["workout_avg_hr"] = workout_score.get("average_heart_rate")
        result["workout_max_hr"] = workout_score.get("max_heart_rate")
        wkj = workout_score.get("kilojoule")
        result["workout_calories_kcal"] = round(wkj / 4.184) if wkj else None
        result["workout_distance_m"] = workout_score.get("distance_meter")
        result["workout_altitude_m"] = workout_score.get("altitude_gain_meter")
        zones = workout_score.get("zone_duration", {}) or {}
        for i, key in enumerate(["zone_zero_milli", "zone_one_milli", "zone_two_milli",
                                  "zone_three_milli", "zone_four_milli", "zone_five_milli"]):
            ms = zones.get(key) or 0
            result[f"workout_zone_{i}_min"] = round(ms / 60000, 1) if ms else None

        result["_raw"] = {"recovery": recovery, "sleep": sleep, "workout": workout, "cycle": cycle}
        return result
