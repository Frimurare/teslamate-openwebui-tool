"""
title: TeslaMate - Bulldog Rover
author: Claude
version: 3.0
description: Chat with your Tesla via TeslaMate API. Battery health, temperatures, tire pressure, driving stats, charging, efficiency, and Swedish driving journals.
"""

import requests
from datetime import datetime, timedelta, date
from pydantic import BaseModel, Field
from typing import Optional


class Tools:
    TESLAMATE_API = "http://192.168.86.200:8000"

    def __init__(self):
        pass

    def _api_call(self, endpoint: str, params: dict = None) -> dict:
        try:
            url = f"{self.TESLAMATE_API}{endpoint}"
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            return {"error": "Could not connect to TeslaMate API. Is the service running?"}
        except requests.exceptions.Timeout:
            return {"error": "TeslaMate API timed out"}
        except Exception as e:
            return {"error": str(e)}

    def _parse_date(self, date_str: str) -> str:
        today = date.today()
        if not date_str or date_str.strip() == "":
            return today.isoformat()
        low = date_str.strip().lower()
        if low in ("idag", "today"):
            return today.isoformat()
        if low in ("igår", "yesterday"):
            return (today - timedelta(days=1)).isoformat()
        if low in ("senaste veckan", "last week", "förra veckan", "denna vecka", "this week"):
            return (today - timedelta(days=7)).isoformat()
        if low in ("senaste månaden", "last month", "denna månad", "this month", "denna månaden"):
            return today.replace(day=1).isoformat()
        if low in ("förra månaden", "previous month"):
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            return last_prev.replace(day=1).isoformat()
        if low in ("i år", "this year", "året", "hela året"):
            return today.replace(month=1, day=1).isoformat()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        swedish_months = {
            "januari": 1, "februari": 2, "mars": 3, "april": 4,
            "maj": 5, "juni": 6, "juli": 7, "augusti": 8,
            "september": 9, "oktober": 10, "november": 11, "december": 12
        }
        for name, num in swedish_months.items():
            if name in low:
                return date(today.year, num, 1).isoformat()
        return date_str.strip()

    def get_current_date(self) -> str:
        """
        Get today's date and current time. ALWAYS call this FIRST before any other function
        that needs dates, so you know what the current date is.
        Use this when asked about anything time-related, or before calling functions that need date parameters.
        """
        now = datetime.now()
        weekdays_sv = ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"]
        weekday = weekdays_sv[now.weekday()]
        return (
            f"**Dagens datum:** {now.strftime('%Y-%m-%d')}\n"
            f"**Tid:** {now.strftime('%H:%M')}\n"
            f"**Veckodag:** {weekday}\n"
            f"**Vecka:** {now.isocalendar()[1]}\n\n"
            f"Use this date as reference for 'senaste veckan', 'denna månad', etc."
        )

    def get_car_info(self) -> str:
        """
        Get information about the Tesla car - name, model, VIN, color, wheels, and efficiency.
        Use this when asked about the car itself, what car it is, or general vehicle info.
        """
        data = self._api_call("/api/cars")
        if "error" in data:
            return f"Error: {data['error']}"
        cars = data.get("cars", [])
        if not cars:
            return "No cars found in TeslaMate."
        lines = []
        for car in cars:
            lines.append(f"**{car.get('name', 'Unknown')}**")
            lines.append(f"- Model: Tesla {car.get('model', 'Unknown')}")
            if car.get('marketing_name'):
                lines.append(f"- Marketing name: {car['marketing_name']}")
            if car.get('trim_badging'):
                lines.append(f"- Trim: {car['trim_badging']}")
            lines.append(f"- VIN: {car.get('vin', 'Unknown')}")
            if car.get('exterior_color'):
                lines.append(f"- Color: {car['exterior_color']}")
            if car.get('wheel_type'):
                lines.append(f"- Wheels: {car['wheel_type']}")
            lines.append(f"- Efficiency: {car.get('efficiency', 'N/A')} kWh/km")
        return "\n".join(lines)

    def get_battery_status(self) -> str:
        """
        Get current battery level, range estimates, temperatures, and battery heater status.
        Use this when asked about battery, charge level, range, how far the car can drive,
        current temperature at the car, or anything related to battery state.
        """
        data = self._api_call("/api/battery-status")
        if "error" in data:
            return f"Error: {data['error']}"
        lines = [
            f"**Battery Status — {data.get('car_name', '')}**",
            f"- Battery Level: {data.get('battery_level_percent', 'N/A')}%",
            f"- Usable Battery: {data.get('usable_battery_level_percent', 'N/A')}%",
            f"- Rated Range: {data.get('rated_range_km', 'N/A')} km",
            f"- Estimated Range: {data.get('estimated_range_km', 'N/A')} km",
            f"- Battery Heater: {'On' if data.get('battery_heater_on') else 'Off'}",
            f"- Outside Temp: {data.get('outside_temp_c', 'N/A')}°C",
            f"- Inside Temp: {data.get('inside_temp_c', 'N/A')}°C",
            f"- Odometer: {data.get('odometer_km', 'N/A')} km",
            f"- Last Updated: {data.get('last_updated', 'N/A')}",
        ]
        return "\n".join(lines)

    def get_battery_health(self) -> str:
        """
        Get battery degradation and health analysis. Shows capacity loss, range loss,
        estimated battery health percentage, charging cycles, and charging efficiency.
        Use this when asked about battery health, degradation, how much capacity is left,
        battery wear, or how the battery has aged.
        """
        data = self._api_call("/api/battery-health")
        if "error" in data:
            return f"Error: {data['error']}"
        lines = [
            "**Battery Health & Degradation**",
            f"- Odometer: {data.get('odometer_km', 'N/A')} km",
            "",
            "**Capacity:**",
            f"- New: {data.get('capacity_new_kwh', 'N/A')} kWh",
            f"- Now: {data.get('capacity_now_kwh', 'N/A')} kWh",
            f"- Lost: {data.get('capacity_lost_kwh', 'N/A')} kWh",
            "",
            "**Range at 100%:**",
            f"- When new: {data.get('max_range_at_100_new_km', 'N/A')} km",
            f"- Now: {data.get('current_range_at_100_km', 'N/A')} km",
            f"- Lost: {data.get('range_lost_km', 'N/A')} km",
            "",
            f"**Battery Health: {data.get('battery_health_percent', 'N/A')}%**",
            f"**Degradation: {data.get('degradation_percent', 'N/A')}%**",
            "",
            "**Charging Lifetime:**",
            f"- Total charges: {data.get('total_charges', 0)}",
            f"- Charging cycles: {data.get('charging_cycles', 0)}",
            f"- Energy added: {data.get('total_energy_added_kwh', 0)} kWh ({round(data.get('total_energy_added_kwh', 0) / 1000, 2)} MWh)",
            f"- Energy used: {data.get('total_energy_used_kwh', 0)} kWh ({round(data.get('total_energy_used_kwh', 0) / 1000, 2)} MWh)",
            f"- Charging efficiency: {data.get('charging_efficiency_percent', 'N/A')}%",
        ]
        return "\n".join(lines)

    def get_temperature(self, hours: int = 24) -> str:
        """
        Get current and recent temperature data — outside temp, inside temp, climate status,
        and min/max/average for a period.
        Use this when asked about temperature, how cold/warm it is, climate, heating,
        or weather conditions at the car.

        :param hours: Number of hours to look back for statistics (default 24)
        """
        data = self._api_call("/api/temperature", {"hours": hours})
        if "error" in data:
            return f"Error: {data['error']}"
        lines = [f"**Temperature (last {hours}h)**"]
        cur = data.get("current", {})
        if cur:
            lines.append(f"- Outside: {cur.get('outside_temp_c', 'N/A')}°C")
            lines.append(f"- Inside: {cur.get('inside_temp_c', 'N/A')}°C")
            lines.append(f"- Climate: {'On' if cur.get('climate_on') else 'Off'}")
            if cur.get('driver_temp_setting_c'):
                lines.append(f"- Set temp: {cur['driver_temp_setting_c']}°C")
            lines.append(f"- Battery heater: {'On' if cur.get('battery_heater_on') else 'Off'}")
            lines.append(f"- Measured: {cur.get('measured_at', '')}")
        stats = data.get("stats", {})
        if stats:
            lines.append(f"\n**Period stats ({hours}h):**")
            lines.append(f"- Outside: {stats.get('outside_min_c')}°C to {stats.get('outside_max_c')}°C (avg {stats.get('outside_avg_c')}°C)")
            if stats.get('inside_min_c') is not None:
                lines.append(f"- Inside: {stats.get('inside_min_c')}°C to {stats.get('inside_max_c')}°C (avg {stats.get('inside_avg_c')}°C)")
        return "\n".join(lines)

    def get_tire_pressure(self) -> str:
        """
        Get current tire pressure for all four tires (TPMS).
        Use this when asked about tire pressure, tires, TPMS, or if tires need air.
        """
        data = self._api_call("/api/tire-pressure")
        if "error" in data:
            return f"Error: {data['error']}"
        lines = [
            "**Tire Pressure (TPMS)**",
            f"- Front Left:  {data.get('front_left_bar', 'N/A')} bar",
            f"- Front Right: {data.get('front_right_bar', 'N/A')} bar",
            f"- Rear Left:   {data.get('rear_left_bar', 'N/A')} bar",
            f"- Rear Right:  {data.get('rear_right_bar', 'N/A')} bar",
            f"- Average:     {data.get('average_bar', 'N/A')} bar",
            f"- Outside temp: {data.get('outside_temp_c', 'N/A')}°C",
            f"- Measured: {data.get('measured_at', 'N/A')}",
        ]
        return "\n".join(lines)

    def get_car_state(self) -> str:
        """
        Get the car's current state — driving, charging, sleeping, or online.
        Shows how long it has been in that state and recent state history.
        Use this when asked what the car is doing, if it's sleeping, driving, or charging right now.
        """
        data = self._api_call("/api/car-state")
        if "error" in data:
            return f"Error: {data['error']}"
        state_sv = {
            "asleep": "Sover", "online": "Online", "driving": "Kör",
            "charging": "Laddar", "suspended": "Vilande"
        }
        current = data.get("current_state", "unknown")
        lines = [
            f"**Car State: {state_sv.get(current, current)}**",
            f"- Since: {data.get('since', 'N/A')}",
            f"- Duration: {data.get('duration', 'N/A')}",
        ]
        recent = data.get("recent_states", [])
        if len(recent) > 1:
            lines.append("\n**Recent states:**")
            for s in recent[1:]:
                lines.append(f"- {state_sv.get(s['state'], s['state'])}: {s.get('start', '')}")
        return "\n".join(lines)

    def get_drive_stats(self, days: int = 30) -> str:
        """
        Get detailed driving statistics — total distance, top speed, max power,
        average speed, temperature averages, longest drive.
        Use this when asked about driving statistics, how much driving, top speed,
        performance stats, or driving summary for a period.

        :param days: Number of days to look back (default 30)
        """
        data = self._api_call("/api/drive-stats", {"days": days})
        if "error" in data:
            return f"Error: {data['error']}"
        lines = [
            f"**Driving Statistics (last {days} days)**",
            f"- Total drives: {data.get('total_drives', 0)}",
            f"- Distance: {data.get('total_km', 0)} km ({data.get('total_mil', 0)} mil)",
            f"- Driving time: {data.get('total_hours', 0)} hours",
            f"- Avg per drive: {data.get('avg_km_per_drive', 0)} km",
            f"- Longest drive: {data.get('longest_drive_km', 0)} km",
            f"- Average speed: {data.get('avg_speed_kmh', 0)} km/h",
            f"- Top speed: {data.get('top_speed_kmh', 'N/A')} km/h",
            f"- Max power: {data.get('max_power_kw', 'N/A')} kW",
            f"- Max regen: {data.get('max_regen_kw', 'N/A')} kW",
            f"- Avg outside temp: {data.get('avg_outside_temp_c', 'N/A')}°C",
            f"- Avg inside temp: {data.get('avg_inside_temp_c', 'N/A')}°C",
        ]
        return "\n".join(lines)

    def get_total_distance(self) -> str:
        """
        Get total distance driven and odometer reading.
        Use this when asked about total kilometers, odometer, mileage, how far the car has driven.
        """
        data = self._api_call("/api/total-distance")
        if "error" in data:
            return f"Error: {data['error']}"
        logged = data.get("total_distance_logged", 0)
        odo = data.get("odometer_km", 0)
        return (
            f"**Distance**\n"
            f"- Odometer: {odo:,.1f} km\n"
            f"- Logged in TeslaMate: {logged:,.1f} km\n"
            f"- Total trips: {data.get('total_trips', 0)}"
        )

    def get_charging_stats(self, days: int = 30) -> str:
        """
        Get charging statistics — sessions, energy, efficiency, costs, and temperature.
        Use this when asked about charging, electricity usage, costs, or energy consumption.

        :param days: Number of days to look back (default 30)
        """
        data = self._api_call("/api/charging-stats", {"days": days})
        if "error" in data:
            return f"Error: {data['error']}"
        return (
            f"**Charging Statistics (last {days} days)**\n"
            f"- Sessions: {data.get('total_charging_sessions', 0)}\n"
            f"- Energy added: {data.get('total_energy_added_kwh', 0)} kWh\n"
            f"- Energy used: {data.get('total_energy_used_kwh', 0)} kWh\n"
            f"- Efficiency: {data.get('charging_efficiency_percent', 'N/A')}%\n"
            f"- Avg per session: {data.get('average_kwh_per_session', 0)} kWh\n"
            f"- Total time: {data.get('total_charging_time_hours', 0)} hours\n"
            f"- Total cost: {data.get('total_cost_sek', 0)} SEK\n"
            f"- Avg outside temp: {data.get('avg_outside_temp_c', 'N/A')}°C"
        )

    def get_recent_drives(self, limit: int = 10) -> str:
        """
        Get the most recent drives with locations, distance, duration, and temperature.
        Use this when asked about recent trips, last drives, or where the car has been.

        :param limit: Number of recent drives to show (default 10, max 50)
        """
        if limit > 50:
            limit = 50
        data = self._api_call("/api/recent-drives", {"limit": limit})
        if "error" in data:
            return f"Error: {data['error']}"
        drives = data.get("recent_drives", [])
        if not drives:
            return "No recent drives found."
        lines = [f"**Last {len(drives)} Drives**\n"]
        for i, d in enumerate(drives, 1):
            dist = round(float(d.get("distance_km", 0) or 0), 1)
            dur = d.get("duration_min", 0) or 0
            start = d.get("start_location", "Unknown")
            end = d.get("end_location", "Unknown")
            temp = d.get("outside_temp_avg")
            date_str = d.get("start_date", "")
            if date_str:
                try:
                    dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            temp_str = f", {temp}°C" if temp else ""
            lines.append(f"{i}. **{date_str}** — {dist} km, {dur} min{temp_str}")
            lines.append(f"   {start} → {end}")
        return "\n".join(lines)

    def get_drives_by_date(self, start_date: str = "", end_date: str = "") -> str:
        """
        Get all drives within a date range with locations, distance, and temperature.
        IMPORTANT: Call get_current_date first to know today's date!

        :param start_date: YYYY-MM-DD or relative: 'senaste veckan', 'denna månad', 'igår'. Default: 7 days ago.
        :param end_date: YYYY-MM-DD. Default: today.
        """
        today = date.today()
        parsed_start = self._parse_date(start_date) if start_date else (today - timedelta(days=7)).isoformat()
        parsed_end = self._parse_date(end_date) if end_date else today.isoformat()
        params = {"start_date": parsed_start, "end_date": parsed_end}
        data = self._api_call("/api/drives-by-date", params)
        if "error" in data:
            return f"Error: {data['error']}"
        drives = data.get("drives", [])
        total_km = data.get("total_distance_km", 0)
        total_min = data.get("total_duration_min", 0)
        if not drives:
            return f"No drives found between {parsed_start} and {parsed_end}."
        lines = [
            f"**Drives {parsed_start} to {parsed_end}**",
            f"Total: {len(drives)} drives, {total_km} km, {total_min} min\n"
        ]
        for i, d in enumerate(drives, 1):
            dist = round(float(d.get("distance_km", 0) or 0), 1)
            dur = d.get("duration_min", 0) or 0
            start = d.get("start_location", "Unknown")
            end = d.get("end_location", "Unknown")
            date_str = d.get("start_date", "")
            if date_str:
                try:
                    dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
                    date_str = dt.strftime("%H:%M")
                except:
                    pass
            lines.append(f"{i}. **{date_str}** — {dist} km, {dur} min: {start} → {end}")
        return "\n".join(lines)

    def get_driving_journal(self, start_date: str = "", end_date: str = "") -> str:
        """
        Generate a Swedish driving journal (körjournal) for tax reimbursement at 25 kr/mil.
        IMPORTANT: Call get_current_date first to know today's date!

        :param start_date: YYYY-MM-DD or relative: 'senaste veckan', 'denna månad', 'januari'. Default: 7 days ago.
        :param end_date: YYYY-MM-DD. Default: today.
        """
        today = date.today()
        parsed_start = self._parse_date(start_date) if start_date else (today - timedelta(days=7)).isoformat()
        parsed_end = self._parse_date(end_date) if end_date else today.isoformat()
        params = {"start_date": parsed_start, "end_date": parsed_end}
        data = self._api_call("/api/driving-journal", params)
        if "error" in data:
            return f"Error: {data['error']}"
        entries = data.get("entries", [])
        summary = data.get("summary", {})
        period = data.get("period", {})
        if not entries:
            return f"No driving data found for {parsed_start} to {parsed_end}."
        lines = [
            f"**Körjournal {period.get('start', '')} — {period.get('end', '')}**\n",
            "| Datum | Dag | Destination | Km | Mil | Ersättning |",
            "|-------|-----|-------------|----:|-----:|-----------:|",
        ]
        for e in entries:
            d = e.get("date", "")
            day = e.get("weekday", "")
            dest = e.get("destination", "Unknown")
            if len(dest) > 40:
                dest = dest[:37] + "..."
            km = e.get("distance_km_journal", 0)
            mil = e.get("distance_mil", 0)
            sek = e.get("reimbursement_sek", 0)
            lines.append(f"| {d} | {day} | {dest} | {km} | {mil} | {sek} kr |")
        lines.append("")
        lines.append("**Summering:**")
        lines.append(f"- Antal dagar: {summary.get('total_days', 0)}")
        lines.append(f"- Total sträcka: {summary.get('total_mil', 0)} mil ({summary.get('total_km', 0)} km)")
        lines.append(f"- Total ersättning: {summary.get('total_reimbursement_sek', 0)} kr")
        lines.append(f"- Milersättning: {summary.get('rate_per_mil', 25)} kr/mil")
        return "\n".join(lines)

    def get_efficiency(self, days: int = 30) -> str:
        """
        Get energy efficiency — Wh/km and kWh/100km averages with temperature context.
        Use this when asked about efficiency, energy usage, consumption per km.

        :param days: Number of days to look back (default 30)
        """
        data = self._api_call("/api/efficiency", {"days": days})
        if "error" in data:
            return f"Error: {data['error']}"
        return (
            f"**Efficiency (last {days} days)**\n"
            f"- Average: {data.get('average_wh_per_km', 'N/A')} Wh/km\n"
            f"- Average: {data.get('average_kwh_per_100km', 'N/A')} kWh/100km\n"
            f"- Total Distance: {data.get('total_distance_km', 0)} km\n"
            f"- Trips: {data.get('trip_count', 0)}\n"
            f"- Avg outside temp: {data.get('avg_outside_temp_c', 'N/A')}°C"
        )

    def get_health_status(self) -> str:
        """
        Check if the TeslaMate system and database are running.
        Use this to diagnose connection issues.
        """
        data = self._api_call("/api/health")
        if "error" in data:
            return f"TeslaMate API Error: {data['error']}"
        return (
            f"**TeslaMate System Status**\n"
            f"- API: Running\n"
            f"- Database: {data.get('database', 'Unknown')}"
        )
