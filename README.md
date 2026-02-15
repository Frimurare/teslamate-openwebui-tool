# TeslaMate Open WebUI Tool

An [Open WebUI](https://openwebui.com/) Tool that lets you **chat with your Tesla** using natural language. Powered by [TeslaMate](https://github.com/teslamate-org/teslamate) data.

Ask questions like:
- "Hur är batteriet?" (How's the battery?)
- "Visa körjournal för januari" (Show driving journal for January)
- "Var har jag kört senaste veckan?" (Where have I driven this week?)
- "Hur mycket har jag laddat?" (How much have I charged?)

## Components

### `teslamate_tool.py` — Open WebUI Tool
The tool that gets installed in Open WebUI. Provides 10 functions the LLM can call:

| Function | Description |
|----------|-------------|
| `get_current_date` | Returns today's date (helps models that lack time awareness) |
| `get_car_info` | Car name, model, VIN, efficiency |
| `get_battery_status` | Battery level, range estimates, heater status |
| `get_total_distance` | Total km/mil driven since tracking started |
| `get_charging_stats` | Charging sessions, energy, costs for a period |
| `get_recent_drives` | Last N drives with locations and distances |
| `get_drives_by_date` | All drives within a date range |
| `get_driving_journal` | Swedish körjournal with mil and reimbursement |
| `get_efficiency` | Energy efficiency in Wh/km and kWh/100km |
| `get_health_status` | TeslaMate API and database health check |

### `teslamate_api.py` — FastAPI Backend
A REST API that sits between Open WebUI and the TeslaMate PostgreSQL database. Runs as a Docker container alongside TeslaMate.

**Endpoints:**
- `GET /api/cars` — List cars
- `GET /api/battery-status` — Current battery state
- `GET /api/total-distance` — Odometer
- `GET /api/charging-stats?days=30` — Charging statistics
- `GET /api/recent-drives?limit=10` — Recent trips
- `GET /api/drives-by-date?start_date=2026-01-01&end_date=2026-01-31` — Date-filtered drives
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
3. Update `TESLAMATE_API` URL if your API isn't at `http://192.168.86.200:8000`
4. Save

### 3. Use it
Start a new chat, enable the TeslaMate tool, and ask away!

## Swedish Driving Journal (Körjournal)

The driving journal feature generates tax-compliant mileage reports:
- Distances in Swedish **mil** (1 mil = 10 km)
- Reimbursement at **25 kr/mil** (configurable)
- Adds realistic extra km for parking, charging stops, etc.
- Groups all drives by day with automatic destination detection

## Requirements
- TeslaMate (running with PostgreSQL)
- Open WebUI v0.6+
- Python 3.10+ (for the API)
- An Ollama model (tested with qwen3:14b)

## License
MIT
