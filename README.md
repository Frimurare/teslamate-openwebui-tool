# TeslaMate Open WebUI Tool

An [Open WebUI](https://openwebui.com/) Tool that lets you **chat with your Tesla** using natural language. Powered by [TeslaMate](https://github.com/teslamate-org/teslamate) data.

Ask questions like:
- "Hur är batteriet?" (How's the battery?)
- "Hur mår batteriet? Degradering?" (Battery health? Degradation?)
- "Visa körjournal för januari" (Show driving journal for January)
- "Vad är temperaturen vid bilen?" (What's the temperature at the car?)
- "Hur är däcktrycket?" (How's the tire pressure?)
- "Vad gör bilen just nu?" (What is the car doing right now?)
- "Visa körstatistik senaste månaden" (Show driving stats for last month)

## Components

### `teslamate_tool.py` — Open WebUI Tool (v3.0)
The tool that gets installed in Open WebUI. Provides **15 functions** the LLM can call:

| Function | Description |
|----------|-------------|
| `get_current_date` | Returns today's date (helps models that lack time awareness) |
| `get_car_info` | Car name, model, VIN, color, wheels, efficiency |
| `get_battery_status` | Battery level, range, temperatures, heater status |
| `get_battery_health` | Degradation %, capacity loss, range loss, charging cycles |
| `get_temperature` | Inside/outside temp, climate status, min/max/avg stats |
| `get_tire_pressure` | TPMS readings for all four tires |
| `get_car_state` | Current state: driving, charging, sleeping, online |
| `get_drive_stats` | Top speed, max power, avg speed, longest drive |
| `get_total_distance` | Odometer and logged distance |
| `get_charging_stats` | Sessions, energy, efficiency, costs |
| `get_recent_drives` | Last N drives with locations and temperatures |
| `get_drives_by_date` | All drives within a date range |
| `get_driving_journal` | Swedish körjournal with mil and reimbursement |
| `get_efficiency` | Energy efficiency in Wh/km and kWh/100km |
| `get_health_status` | TeslaMate API and database health check |

### `teslamate_api.py` — FastAPI Backend (v3.0)
A REST API that sits between Open WebUI and the TeslaMate PostgreSQL database.

**Endpoints:**
- `GET /api/cars` — Car info (model, VIN, color, wheels)
- `GET /api/battery-status` — Battery level, range, temperatures
- `GET /api/battery-health` — Degradation, capacity, charging cycles
- `GET /api/temperature?hours=24` — Current and historical temperatures
- `GET /api/tire-pressure` — TPMS readings for all tires
- `GET /api/car-state` — Current state and recent state history
- `GET /api/drive-stats?days=30` — Driving statistics with top speed, power
- `GET /api/total-distance` — Odometer and logged distance
- `GET /api/charging-stats?days=30` — Charging statistics with efficiency
- `GET /api/recent-drives?limit=10` — Recent trips
- `GET /api/drives-by-date?start_date=2026-01-01` — Date-filtered drives
- `GET /api/driving-journal?start_date=2026-01-01` — Swedish driving journal
- `GET /api/efficiency?days=30` — Energy efficiency
- `GET /api/health` — Health check

## Setup

### 1. Deploy the API
The API connects to TeslaMate's PostgreSQL database. Add it to your TeslaMate `docker-compose.yml`:

```yaml
  teslamate-api:
    image: python:3.11-slim
    container_name: teslamate-api
    restart: always
    depends_on:
      - database
    environment:
      - DATABASE_HOST=database
      - DATABASE_NAME=teslamate
      - DATABASE_USER=teslamate
      - DATABASE_PASS=secret
    volumes:
      - ./api:/app
    working_dir: /app
    command: >
      bash -c "pip install fastapi uvicorn psycopg2-binary &&
               uvicorn main:app --host 0.0.0.0 --port 8000"
    ports:
      - "8000:8000"
```

Copy `teslamate_api.py` as `main.py` into the `./api` directory.

### 2. Install the Tool in Open WebUI
1. Go to **Workspace** > **Tools** > **+**
2. Paste the contents of `teslamate_tool.py`
3. Update `TESLAMATE_API` URL if needed
4. Save

### 3. Use it
Start a new chat, enable the TeslaMate tool, and ask away!

## Features

### Battery Health & Degradation
Tracks battery capacity loss over time:
- Compares max range ever seen vs current range
- Estimates remaining capacity in kWh
- Shows total charging cycles and lifetime energy
- Charging efficiency percentage

### Temperature Monitoring
Real-time and historical temperature data:
- Outside and inside temperature
- Climate system status
- Battery heater status
- Min/max/average for configurable time periods

### Swedish Driving Journal (Körjournal)
Generates tax-compliant mileage reports:
- Distances in Swedish **mil** (1 mil = 10 km)
- Reimbursement at **25 kr/mil** (configurable)
- Adds realistic extra km for parking, charging stops
- Groups all drives by day with automatic destination detection
- Smart date parsing: "senaste veckan", "januari", "igår"

## Requirements
- TeslaMate (running with PostgreSQL)
- Open WebUI v0.6+
- Python 3.10+ (for the API)
- An Ollama model (tested with qwen3:14b)

## License
MIT — see [LICENSE](LICENSE)
