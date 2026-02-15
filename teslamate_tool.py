"""
title: TeslaMate - Bulldog Rover
author: Claude
version: 2.1
description: Chat with your Tesla via TeslaMate API. Get battery status, driving history, charging stats, efficiency data, and Swedish driving journals (körjournaler).
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
        """Make API call to TeslaMate."""
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
        """Parse a date string or relative term into YYYY-MM-DD format."""
        today = date.today()
        if not date_str or date_str.strip() == "":
            return today.isoformat()
        low = date_str.strip().lower()
        # Handle Swedish and English relative terms
        if low in ("idag", "today"):
            return today.isoformat()
        if low in ("igår", "yesterday", "igår"):
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
        # Try parsing as a date
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # Try month names (Swedish)
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
        Get information about the Tesla car - name, model, VIN, and efficiency rating.
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
            if car.get('trim_badging'):
                lines.append(f"- Trim: {car['trim_badging']}")
            lines.append(f"- VIN: {car.get('vin', 'Unknown')}")
            lines.append(f"- Efficiency: {car.get('efficiency', 'N/A')} kWh/km")
            lines.append(f"- Added: {car.get('inserted_at', 'Unknown')}")
        return "\n".join(lines)

    def get_battery_status(self) -> str:
        """
        Get current battery level, range estimates, and battery heater status.
        Use this when asked about battery, charge level, range, how far the car can drive,
        or anything related to the battery state.
        """
        data = self._api_call("/api/battery-status")
        if "error" in data:
            return f"Error: {data['error']}"
        lines = [
            "**Battery Status**",
            f"- Battery Level: {data.get('battery_level_percent', 'N/A')}%",
            f"- Usable Battery: {data.get('usable_battery_level_percent', 'N/A')}%",
            f"- Rated Range: {data.get('rated_range_km', 'N/A')} km",
            f"- Ideal Range: {data.get('ideal_range_km', 'N/A')} km",
            f"- Estimated Range: {data.get('estimated_range_km', 'N/A')} km",
            f"- Battery Heater: {'On' if data.get('battery_heater_on') else 'Off'}",
            f"- Car: {data.get('car_name', '')} ({data.get('car_model', '')})",
            f"- Last Updated: {data.get('last_updated', 'N/A')}",
        ]
        return "\n".join(lines)

    def get_total_distance(self) -> str:
        """
        Get the total distance the car has driven since tracking started.
        Use this when asked about total kilometers, total miles, how far the car has driven overall,
        or total number of trips recorded.
        """
        data = self._api_call("/api/total-distance")
        if "error" in data:
            return f"Error: {data['error']}"
        km = data.get("total_distance", 0)
        mil = round(km / 10, 1)
        miles = round(km / 1.60934, 1)
        return (
            f"**Total Distance**\n"
            f"- {km:,.1f} km ({mil:,.1f} Swedish mil / {miles:,.1f} miles)\n"
            f"- Total recorded trips: {data.get('total_trips', 0)}"
        )

    def get_charging_stats(self, days: int = 30) -> str:
        """
        Get charging statistics for a given period. Shows total sessions, energy consumed,
        charging time, and costs. Default is last 30 days.
        Use this when asked about charging, electricity usage, charging costs, how often the car charges,
        or energy consumption.

        :param days: Number of days to look back (default 30)
        """
        data = self._api_call("/api/charging-stats", {"days": days})
        if "error" in data:
            return f"Error: {data['error']}"
        return (
            f"**Charging Statistics (last {days} days)**\n"
            f"- Sessions: {data.get('total_charging_sessions', 0)}\n"
            f"- Total Energy: {data.get('total_energy_kwh', 0)} kWh\n"
            f"- Avg per Session: {data.get('average_kwh_per_session', 0)} kWh\n"
            f"- Total Charging Time: {data.get('total_charging_time_hours', 0)} hours\n"
            f"- Total Cost: {data.get('total_cost', 0)} SEK"
        )

    def get_recent_drives(self, limit: int = 10) -> str:
        """
        Get the most recent drives with start/end locations, distance, and duration.
        Use this when asked about recent trips, last drives, where the car has been lately,
        or recent driving history.

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
            date_str = d.get("start_date", "")
            if date_str:
                try:
                    dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            lines.append(f"{i}. **{date_str}** — {dist} km, {dur} min")
            lines.append(f"   {start} → {end}")
        return "\n".join(lines)

    def get_drives_by_date(self, start_date: str = "", end_date: str = "") -> str:
        """
        Get all drives within a specific date range. Shows each individual drive with
        start/end locations, distance, duration, and range used.
        Use this when asked about drives on a specific day, drives this week/month,
        or driving history for a date range.
        IMPORTANT: Call get_current_date first to know today's date!

        :param start_date: Start date as YYYY-MM-DD, or a relative term like 'senaste veckan', 'denna månad', 'igår'. Defaults to 7 days ago.
        :param end_date: End date as YYYY-MM-DD. Defaults to today.
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
        Generate a Swedish driving journal (körjournal) for tax reimbursement purposes.
        Shows each day's driving with distances in Swedish mil, purpose, and reimbursement at 25 kr/mil.
        Use this when asked about körjournal, driving journal, milersättning, tax deductions for driving,
        reseräkning, or reimbursement calculations.
        IMPORTANT: Call get_current_date first to know today's date!

        :param start_date: Start date as YYYY-MM-DD, or a relative term like 'senaste veckan', 'denna månad', 'januari'. Defaults to 7 days ago.
        :param end_date: End date as YYYY-MM-DD. Defaults to today.
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
        lines.append(f"**Summering:**")
        lines.append(f"- Antal dagar: {summary.get('total_days', 0)}")
        lines.append(f"- Total sträcka: {summary.get('total_mil', 0)} mil ({summary.get('total_km', 0)} km)")
        lines.append(f"- Total ersättning: {summary.get('total_reimbursement_sek', 0)} kr")
        lines.append(f"- Milersättning: {summary.get('rate_per_mil', 25)} kr/mil")
        return "\n".join(lines)

    def get_efficiency(self, days: int = 30) -> str:
        """
        Get energy efficiency statistics - how much electricity the car uses per kilometer.
        Shows Wh/km and kWh/100km averages.
        Use this when asked about efficiency, energy usage, electricity consumption per km,
        how efficient the car is, or consumption statistics.

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
            f"- Trips Analyzed: {data.get('trip_count', 0)}"
        )

    def get_health_status(self) -> str:
        """
        Check if the TeslaMate system and database are running properly.
        Use this when asked if TeslaMate is working, system status, or to diagnose connection issues.
        """
        data = self._api_call("/api/health")
        if "error" in data:
            return f"TeslaMate API Error: {data['error']}"
        return (
            f"**TeslaMate System Status**\n"
            f"- API: Running\n"
            f"- Database: {data.get('database', 'Unknown')}"
        )
