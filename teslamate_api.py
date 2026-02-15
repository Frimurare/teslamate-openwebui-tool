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
    return {"status": "TeslaMate Chat API Running", "version": "2.0"}

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
            SELECT id, vin, model, trim_badging, name,
                   efficiency, inserted_at, updated_at
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
        conn.close()
        if result and result['total_km']:
            total = float(result['total_km'])
            if unit == "mi":
                total = total / 1.60934
            return {"total_distance": round(total, 2), "unit": "miles" if unit == "mi" else "kilometer", "total_trips": result['total_trips']}
        return {"total_distance": 0, "unit": unit, "total_trips": 0}
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
                   p.ideal_battery_range_km, p.est_battery_range_km, p.battery_heater, p.date,
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
                "rated_range_km": result['rated_battery_range_km'],
                "ideal_range_km": result['ideal_battery_range_km'],
                "estimated_range_km": result['est_battery_range_km'],
                "battery_heater_on": result['battery_heater'],
                "last_updated": result['date'].isoformat() if result['date'] else None,
                "car_name": result['car_name'], "car_model": result['model']
            }
        return {"error": "No battery data found"}
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
            SELECT COUNT(*) as total_charges, SUM(cp.charge_energy_added) as total_kwh,
                   AVG(cp.charge_energy_added) as avg_kwh_per_charge,
                   SUM(cp.duration_min) as total_minutes, SUM(cp.cost) as total_cost
            FROM charging_processes cp WHERE cp.start_date >= %s {where_clause}
        """, (date_limit,))
        result = cur.fetchone()
        conn.close()
        if result and result['total_charges']:
            return {
                "period_days": days,
                "total_charging_sessions": result['total_charges'],
                "total_energy_kwh": round(float(result['total_kwh'] or 0), 2),
                "average_kwh_per_session": round(float(result['avg_kwh_per_charge'] or 0), 2),
                "total_charging_time_hours": round(float(result['total_minutes'] or 0) / 60, 2),
                "total_cost": round(float(result['total_cost'] or 0), 2)
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
                   COUNT(*) as trip_count
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
                "trip_count": result['trip_count']
            }
        return {"error": f"No drive data found for last {days} days"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
