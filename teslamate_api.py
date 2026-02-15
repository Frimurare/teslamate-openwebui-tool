from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, date
from typing import Optional
import os, math, random

app = FastAPI(title="TeslaMate Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "database"),
        database=os.getenv("DATABASE_NAME", "teslamate"),
        user=os.getenv("DATABASE_USER", "teslamate"),
        password=os.getenv("DATABASE_PASS", "secret"),
        cursor_factory=RealDictCursor
    )

@app.get("/")
def root():
    return {"status": "TeslaMate Chat API Running", "version": "3.0"}

@app.get("/api/health")
def health_check():
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")

@app.get("/api/cars")
def get_cars():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, vin, model, marketing_name, trim_badging, name,
                   efficiency, exterior_color, wheel_type,
                   inserted_at, updated_at
            FROM cars ORDER BY id
        """)
        cars = cur.fetchall()
        conn.close()
        return {"cars": cars}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/total-distance")
def get_total_distance(car_id: Optional[int] = None, unit: str = "km"):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        where_clause = f"WHERE car_id = {car_id}" if car_id else ""
        cur.execute(f"SELECT SUM(distance) as total_km, COUNT(*) as total_trips FROM drives {where_clause}")
        result = cur.fetchone()
        # Also get odometer from latest position
        car_filter = f"WHERE car_id = {car_id}" if car_id else ""
        cur.execute(f"SELECT odometer FROM positions {car_filter} ORDER BY date DESC LIMIT 1")
        odo = cur.fetchone()
        conn.close()
        if result and result['total_km']:
            total = float(result['total_km'])
            if unit == "mi":
                total = total / 1.60934
            return {
                "total_distance_logged": round(total, 2),
                "odometer_km": round(float(odo['odometer']), 1) if odo and odo['odometer'] else None,
                "unit": "miles" if unit == "mi" else "kilometer",
                "total_trips": result['total_trips']
            }
        return {"total_distance_logged": 0, "odometer_km": None, "unit": unit, "total_trips": 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/battery-status")
def get_battery_status(car_id: Optional[int] = None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        where_clause = f"WHERE p.car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT p.battery_level, p.usable_battery_level, p.rated_battery_range_km,
                   p.ideal_battery_range_km, p.est_battery_range_km,
                   p.battery_heater, p.battery_heater_on,
                   p.outside_temp, p.inside_temp, p.odometer, p.date,
                   c.name as car_name, c.model
            FROM positions p JOIN cars c ON c.id = p.car_id {where_clause}
            ORDER BY p.date DESC LIMIT 1
        """)
        result = cur.fetchone()
        conn.close()
        if result:
            return {
                "battery_level_percent": result['battery_level'],
                "usable_battery_level_percent": result['usable_battery_level'],
                "rated_range_km": float(result['rated_battery_range_km']) if result['rated_battery_range_km'] else None,
                "ideal_range_km": float(result['ideal_battery_range_km']) if result['ideal_battery_range_km'] else None,
                "estimated_range_km": float(result['est_battery_range_km']) if result['est_battery_range_km'] else None,
                "battery_heater_on": result.get('battery_heater_on', False),
                "outside_temp_c": float(result['outside_temp']) if result['outside_temp'] else None,
                "inside_temp_c": float(result['inside_temp']) if result['inside_temp'] else None,
                "odometer_km": round(float(result['odometer']), 1) if result['odometer'] else None,
                "last_updated": result['date'].isoformat() if result['date'] else None,
                "car_name": result['car_name'], "car_model": result['model']
            }
        return {"error": "No battery data found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/battery-health")
def get_battery_health(car_id: Optional[int] = None):
    """Battery degradation and health analysis."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        car_filter = f"AND car_id = {car_id}" if car_id else ""

        # Get current odometer
        cur.execute(f"SELECT odometer FROM positions WHERE 1=1 {car_filter} ORDER BY date DESC LIMIT 1")
        odo_row = cur.fetchone()
        odometer = float(odo_row['odometer']) if odo_row and odo_row['odometer'] else 0

        # Get max rated range ever seen (= "new" capacity)
        cur.execute(f"""
            SELECT MAX(rated_battery_range_km) as max_range
            FROM positions WHERE rated_battery_range_km IS NOT NULL
            AND battery_level >= 95 {car_filter}
        """)
        max_row = cur.fetchone()

        # Also check charging_processes for max range at high SOC
        cur.execute(f"""
            SELECT MAX(end_rated_range_km) as max_charge_range
            FROM charging_processes WHERE end_battery_level >= 95 {car_filter}
        """)
        max_charge = cur.fetchone()

        # Get recent rated range at 100% (or highest recent SOC)
        cur.execute(f"""
            SELECT rated_battery_range_km, battery_level, date
            FROM positions WHERE battery_level >= 90
            AND rated_battery_range_km IS NOT NULL {car_filter}
            ORDER BY date DESC LIMIT 1
        """)
        recent_high = cur.fetchone()

        # Calculate degradation using rated range as proxy
        # Tesla Model 3 LR: ~580 km rated range when new (WLTP)
        max_range_ever = 0
        if max_row and max_row['max_range']:
            max_range_ever = float(max_row['max_range'])
        if max_charge and max_charge['max_charge_range']:
            cr = float(max_charge['max_charge_range'])
            if cr > max_range_ever:
                max_range_ever = cr

        # Extrapolate recent to 100%
        current_range_at_100 = None
        if recent_high and recent_high['rated_battery_range_km'] and recent_high['battery_level']:
            soc = int(recent_high['battery_level'])
            rated = float(recent_high['rated_battery_range_km'])
            if soc > 0:
                current_range_at_100 = round(rated * 100 / soc, 1)

        # Battery capacity estimate (Model 3 LR = 77.8 kWh usable new)
        new_capacity_kwh = 77.8
        battery_health_pct = None
        capacity_now_kwh = None
        if max_range_ever > 0 and current_range_at_100:
            battery_health_pct = round(current_range_at_100 / max_range_ever * 100, 1)
            capacity_now_kwh = round(new_capacity_kwh * battery_health_pct / 100, 1)

        # Lifetime charging stats
        cur.execute(f"""
            SELECT COUNT(*) as total_charges,
                   SUM(charge_energy_added) as total_added_kwh,
                   SUM(charge_energy_used) as total_used_kwh,
                   SUM(CASE WHEN fast_charger_present THEN 1 ELSE 0 END) as dc_charges
            FROM charging_processes cp
            LEFT JOIN (
                SELECT DISTINCT charging_process_id, fast_charger_present
                FROM charges WHERE fast_charger_present = true
            ) fc ON fc.charging_process_id = cp.id
            WHERE 1=1 {car_filter}
        """)
        charge_stats = cur.fetchone()

        # Count charging cycles (rough: total kWh added / usable capacity)
        total_added = float(charge_stats['total_added_kwh'] or 0) if charge_stats else 0
        total_used = float(charge_stats['total_used_kwh'] or 0) if charge_stats else 0
        charging_cycles = round(total_added / new_capacity_kwh, 1) if new_capacity_kwh > 0 else 0
        charging_efficiency = round(total_added / total_used * 100, 1) if total_used > 0 else None

        conn.close()
        return {
            "odometer_km": round(odometer, 1),
            "max_range_at_100_new_km": round(max_range_ever, 1) if max_range_ever else None,
            "current_range_at_100_km": current_range_at_100,
            "range_lost_km": round(max_range_ever - current_range_at_100, 1) if max_range_ever and current_range_at_100 else None,
            "battery_health_percent": battery_health_pct,
            "degradation_percent": round(100 - battery_health_pct, 1) if battery_health_pct else None,
            "capacity_new_kwh": new_capacity_kwh,
            "capacity_now_kwh": capacity_now_kwh,
            "capacity_lost_kwh": round(new_capacity_kwh - capacity_now_kwh, 1) if capacity_now_kwh else None,
            "total_charges": charge_stats['total_charges'] if charge_stats else 0,
            "charging_cycles": charging_cycles,
            "total_energy_added_kwh": round(total_added, 1),
            "total_energy_used_kwh": round(total_used, 1),
            "charging_efficiency_percent": charging_efficiency,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/temperature")
def get_temperature(car_id: Optional[int] = None, hours: int = 24):
    """Current and recent temperature data."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        car_filter = f"AND car_id = {car_id}" if car_id else ""
        since = datetime.now() - timedelta(hours=hours)

        # Latest temps
        cur.execute(f"""
            SELECT outside_temp, inside_temp, is_climate_on,
                   driver_temp_setting, battery_heater_on, date
            FROM positions WHERE date >= %s {car_filter}
            AND outside_temp IS NOT NULL
            ORDER BY date DESC LIMIT 1
        """, (since,))
        latest = cur.fetchone()

        # Min/max/avg for period
        cur.execute(f"""
            SELECT MIN(outside_temp) as min_outside, MAX(outside_temp) as max_outside,
                   AVG(outside_temp) as avg_outside,
                   MIN(inside_temp) as min_inside, MAX(inside_temp) as max_inside,
                   AVG(inside_temp) as avg_inside
            FROM positions WHERE date >= %s {car_filter}
            AND outside_temp IS NOT NULL
        """, (since,))
        stats = cur.fetchone()
        conn.close()

        result = {"period_hours": hours}
        if latest:
            result["current"] = {
                "outside_temp_c": float(latest['outside_temp']) if latest['outside_temp'] else None,
                "inside_temp_c": float(latest['inside_temp']) if latest['inside_temp'] else None,
                "climate_on": latest['is_climate_on'],
                "driver_temp_setting_c": float(latest['driver_temp_setting']) if latest['driver_temp_setting'] else None,
                "battery_heater_on": latest['battery_heater_on'],
                "measured_at": latest['date'].isoformat(),
            }
        if stats and stats['min_outside'] is not None:
            result["stats"] = {
                "outside_min_c": round(float(stats['min_outside']), 1),
                "outside_max_c": round(float(stats['max_outside']), 1),
                "outside_avg_c": round(float(stats['avg_outside']), 1),
                "inside_min_c": round(float(stats['min_inside']), 1) if stats['min_inside'] else None,
                "inside_max_c": round(float(stats['max_inside']), 1) if stats['max_inside'] else None,
                "inside_avg_c": round(float(stats['avg_inside']), 1) if stats['avg_inside'] else None,
            }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tire-pressure")
def get_tire_pressure(car_id: Optional[int] = None):
    """Latest tire pressure readings (TPMS)."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        car_filter = f"AND car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT tpms_pressure_fl, tpms_pressure_fr,
                   tpms_pressure_rl, tpms_pressure_rr,
                   outside_temp, date
            FROM positions
            WHERE tpms_pressure_fl IS NOT NULL {car_filter}
            ORDER BY date DESC LIMIT 1
        """)
        result = cur.fetchone()
        conn.close()
        if result:
            pressures = {
                "front_left_bar": float(result['tpms_pressure_fl']),
                "front_right_bar": float(result['tpms_pressure_fr']),
                "rear_left_bar": float(result['tpms_pressure_rl']),
                "rear_right_bar": float(result['tpms_pressure_rr']),
            }
            avg = sum(pressures.values()) / 4
            return {
                **pressures,
                "average_bar": round(avg, 1),
                "outside_temp_c": float(result['outside_temp']) if result['outside_temp'] else None,
                "measured_at": result['date'].isoformat(),
            }
        return {"error": "No tire pressure data available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/car-state")
def get_car_state(car_id: Optional[int] = None):
    """Current state: driving, charging, sleeping, online."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        car_filter = f"AND car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT state, start_date, end_date
            FROM states WHERE 1=1 {car_filter}
            ORDER BY start_date DESC LIMIT 5
        """)
        states = cur.fetchall()
        conn.close()
        if states:
            current = states[0]
            duration = None
            if current['start_date']:
                delta = datetime.now() - current['start_date']
                hours = delta.total_seconds() / 3600
                if hours < 1:
                    duration = f"{int(delta.total_seconds() / 60)} min"
                elif hours < 24:
                    duration = f"{hours:.1f} timmar"
                else:
                    duration = f"{hours / 24:.1f} dagar"
            return {
                "current_state": current['state'],
                "since": current['start_date'].isoformat() if current['start_date'] else None,
                "duration": duration,
                "recent_states": [
                    {
                        "state": s['state'],
                        "start": s['start_date'].isoformat() if s['start_date'] else None,
                        "end": s['end_date'].isoformat() if s['end_date'] else None,
                    } for s in states
                ]
            }
        return {"error": "No state data available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/drive-stats")
def get_drive_stats(car_id: Optional[int] = None, days: int = 30):
    """Detailed driving statistics for a period."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        car_filter = f"AND d.car_id = {car_id}" if car_id else ""
        since = datetime.now() - timedelta(days=days)
        cur.execute(f"""
            SELECT COUNT(*) as total_drives,
                   SUM(d.distance) as total_km,
                   SUM(d.duration_min) as total_min,
                   AVG(d.distance) as avg_km,
                   MAX(d.distance) as longest_km,
                   MAX(d.speed_max) as top_speed,
                   AVG(d.outside_temp_avg) as avg_outside_temp,
                   AVG(d.inside_temp_avg) as avg_inside_temp,
                   MAX(d.power_max) as max_power_kw,
                   MIN(d.power_min) as max_regen_kw
            FROM drives d WHERE d.start_date >= %s {car_filter} AND d.distance > 0
        """, (since,))
        result = cur.fetchone()
        conn.close()
        if result and result['total_drives']:
            total_km = float(result['total_km'] or 0)
            total_min = int(result['total_min'] or 0)
            return {
                "period_days": days,
                "total_drives": result['total_drives'],
                "total_km": round(total_km, 1),
                "total_mil": round(total_km / 10, 1),
                "total_hours": round(total_min / 60, 1),
                "avg_km_per_drive": round(float(result['avg_km'] or 0), 1),
                "longest_drive_km": round(float(result['longest_km'] or 0), 1),
                "top_speed_kmh": result['top_speed'],
                "avg_outside_temp_c": round(float(result['avg_outside_temp']), 1) if result['avg_outside_temp'] else None,
                "avg_inside_temp_c": round(float(result['avg_inside_temp']), 1) if result['avg_inside_temp'] else None,
                "max_power_kw": result['max_power_kw'],
                "max_regen_kw": result['max_regen_kw'],
                "avg_speed_kmh": round(total_km / (total_min / 60), 1) if total_min > 0 else 0,
            }
        return {"error": f"No drive data for last {days} days"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/charging-stats")
def get_charging_stats(car_id: Optional[int] = None, days: int = 30):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        date_limit = datetime.now() - timedelta(days=days)
        where_clause = f"AND cp.car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT COUNT(*) as total_charges,
                   SUM(cp.charge_energy_added) as total_kwh_added,
                   SUM(cp.charge_energy_used) as total_kwh_used,
                   AVG(cp.charge_energy_added) as avg_kwh_per_charge,
                   SUM(cp.duration_min) as total_minutes,
                   SUM(cp.cost) as total_cost,
                   AVG(cp.outside_temp_avg) as avg_temp
            FROM charging_processes cp WHERE cp.start_date >= %s {where_clause}
        """, (date_limit,))
        result = cur.fetchone()
        conn.close()
        if result and result['total_charges']:
            added = float(result['total_kwh_added'] or 0)
            used = float(result['total_kwh_used'] or 0)
            return {
                "period_days": days,
                "total_charging_sessions": result['total_charges'],
                "total_energy_added_kwh": round(added, 2),
                "total_energy_used_kwh": round(used, 2),
                "charging_efficiency_percent": round(added / used * 100, 1) if used > 0 else None,
                "average_kwh_per_session": round(float(result['avg_kwh_per_charge'] or 0), 2),
                "total_charging_time_hours": round(float(result['total_minutes'] or 0) / 60, 2),
                "total_cost_sek": round(float(result['total_cost'] or 0), 2),
                "avg_outside_temp_c": round(float(result['avg_temp']), 1) if result['avg_temp'] else None,
            }
        return {"error": f"No charging data found for last {days} days"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/recent-drives")
def get_recent_drives(car_id: Optional[int] = None, limit: int = 10):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        where_clause = f"WHERE d.car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT d.start_date, d.end_date, d.distance as distance_km, d.duration_min,
                   COALESCE(a1.display_name, 'Unknown') as start_location,
                   COALESCE(a2.display_name, 'Unknown') as end_location,
                   d.start_ideal_range_km, d.end_ideal_range_km,
                   d.outside_temp_avg, d.speed_max,
                   (d.start_ideal_range_km - d.end_ideal_range_km) as range_used_km
            FROM drives d
            LEFT JOIN addresses a1 ON d.start_address_id = a1.id
            LEFT JOIN addresses a2 ON d.end_address_id = a2.id
            {where_clause} ORDER BY d.start_date DESC LIMIT %s
        """, (limit,))
        drives = cur.fetchall()
        conn.close()
        return {"recent_drives": drives, "count": len(drives)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/drives-by-date")
def get_drives_by_date(start_date: str, end_date: Optional[str] = None, car_id: Optional[int] = None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        car_filter = f"AND d.car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT d.start_date, d.end_date, d.distance as distance_km, d.duration_min,
                   COALESCE(a1.display_name, 'Unknown') as start_location,
                   COALESCE(a2.display_name, 'Unknown') as end_location,
                   d.start_ideal_range_km, d.end_ideal_range_km,
                   d.outside_temp_avg, d.speed_max,
                   (d.start_ideal_range_km - d.end_ideal_range_km) as range_used_km
            FROM drives d
            LEFT JOIN addresses a1 ON d.start_address_id = a1.id
            LEFT JOIN addresses a2 ON d.end_address_id = a2.id
            WHERE d.start_date >= %s AND d.start_date < (%s::date + interval '1 day')
            {car_filter}
            ORDER BY d.start_date ASC
        """, (start_date, end_date))
        drives = cur.fetchall()
        total_km = sum(float(d['distance_km'] or 0) for d in drives)
        total_min = sum(int(d['duration_min'] or 0) for d in drives)
        conn.close()
        return {
            "start_date": start_date, "end_date": end_date,
            "drives": drives, "count": len(drives),
            "total_distance_km": round(total_km, 2),
            "total_duration_min": total_min
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/driving-journal")
def get_driving_journal(start_date: str, end_date: Optional[str] = None,
                        car_id: Optional[int] = None, rate_per_mil: float = 25.0):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        car_filter = f"AND d.car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT d.start_date, d.end_date, d.distance as distance_km, d.duration_min,
                   COALESCE(a1.display_name, 'Unknown') as start_location,
                   COALESCE(a2.display_name, 'Unknown') as end_location
            FROM drives d
            LEFT JOIN addresses a1 ON d.start_address_id = a1.id
            LEFT JOIN addresses a2 ON d.end_address_id = a2.id
            WHERE d.start_date >= %s AND d.start_date < (%s::date + interval '1 day')
            {car_filter}
            ORDER BY d.start_date ASC
        """, (start_date, end_date))
        drives = cur.fetchall()
        conn.close()

        days = {}
        for d in drives:
            day_key = d['start_date'].strftime("%Y-%m-%d")
            if day_key not in days:
                days[day_key] = []
            days[day_key].append(d)

        journal_entries = []
        total_mil = 0
        total_cost = 0

        for day_key in sorted(days.keys()):
            day_drives = days[day_key]
            day_km = sum(float(d['distance_km'] or 0) for d in day_drives)

            if day_km < 0.5:
                continue

            home = day_drives[0]['start_location']
            destination = home
            for d in day_drives:
                if d['end_location'] != home:
                    destination = d['end_location']
                    break

            extra_km = random.uniform(2, 5)
            if day_km > 80:
                extra_km += random.uniform(3, 7)
            if day_km > 150:
                extra_km += random.uniform(4, 8)
            if day_km > 300:
                extra_km += random.uniform(5, 12)

            total_km_with_extra = day_km + extra_km
            day_mil = round(total_km_with_extra / 10, 1)
            day_cost = round(day_mil * rate_per_mil, 2)

            total_mil += day_mil
            total_cost += day_cost

            weekdays_sv = {
                "Monday": "Mandag", "Tuesday": "Tisdag", "Wednesday": "Onsdag",
                "Thursday": "Torsdag", "Friday": "Fredag", "Saturday": "Lordag", "Sunday": "Sondag"
            }
            eng_day = datetime.strptime(day_key, "%Y-%m-%d").strftime("%A")

            journal_entries.append({
                "date": day_key,
                "weekday": weekdays_sv.get(eng_day, eng_day),
                "start": home,
                "destination": destination,
                "purpose": "Tjansteresa",
                "distance_km_actual": round(day_km, 1),
                "distance_km_journal": round(total_km_with_extra, 1),
                "distance_mil": day_mil,
                "reimbursement_sek": day_cost,
                "num_trips": len(day_drives)
            })

        return {
            "period": {"start": start_date, "end": end_date},
            "entries": journal_entries,
            "summary": {
                "total_days": len(journal_entries),
                "total_mil": round(total_mil, 1),
                "total_km": round(total_mil * 10, 1),
                "total_reimbursement_sek": round(total_cost, 2),
                "rate_per_mil": rate_per_mil
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/efficiency")
def get_efficiency(car_id: Optional[int] = None, days: int = 30):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        date_limit = datetime.now() - timedelta(days=days)
        where_clause = f"AND d.car_id = {car_id}" if car_id else ""
        cur.execute(f"""
            SELECT SUM(d.distance) as total_km,
                   SUM(d.start_ideal_range_km - d.end_ideal_range_km) as total_range_used,
                   COUNT(*) as trip_count,
                   AVG(d.outside_temp_avg) as avg_temp
            FROM drives d WHERE d.start_date >= %s {where_clause} AND d.distance > 0
        """, (date_limit,))
        result = cur.fetchone()
        conn.close()
        if result and result['total_km'] and result['total_range_used']:
            total_km = float(result['total_km'])
            range_used = float(result['total_range_used'])
            battery_capacity = 75
            kwh_per_km = (range_used / total_km) * (battery_capacity / 400)
            wh_per_km = kwh_per_km * 1000
            return {
                "period_days": days, "total_distance_km": round(total_km, 2),
                "average_wh_per_km": round(wh_per_km, 2),
                "average_kwh_per_100km": round(kwh_per_km * 100, 2),
                "trip_count": result['trip_count'],
                "avg_outside_temp_c": round(float(result['avg_temp']), 1) if result['avg_temp'] else None,
            }
        return {"error": f"No drive data found for last {days} days"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
