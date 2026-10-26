# Chao Phraya Flood DSS

A flood decision support system for the Chao Phraya basin. It follows a flood through its three stages in one map-based workspace:

| Stage | Tab | What it does |
|---|---|---|
| Before | **Prediction** | Live water levels from 800+ telemetry stations, 7-day history, distance to bank, and a 48-hour forecast with low, expected and high cases |
| During | **Incident** | Record and track flood events on the map: severity, households affected, area flooded, status |
| After | **Compensation** | Process household damage claims from submission to payment, with automatic outlier checks against official rates, regional peers and photo evidence |

## Architecture

```
            DATA  ◄── ThaiWater (HII) sync every 15 min
              │
             DSS ─── PREDICTION TOOL  (scenarios from "today")
              │
             UI   map + timeline, incidents, compensation
```

| Layer | Stack | Folder |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, GeoAlchemy2 | `backend/` |
| Frontend | React 18, TypeScript, Vite, Mapbox GL JS, Recharts | `frontend/` |
| Database | PostgreSQL 16 + PostGIS | `docker-compose.yml` |

### Data model: series datasets

Every dataset has a `series_type`:

| Type | Holds | Table |
|---|---|---|
| `time` | Readings at a station over time (water level, rainfall, discharge) | `timeseries_values` |
| `feature` | Geometries that change over time (flood extents, buildings at LOD 1–4) | `features` |
| `attribute` | Time-varying values attached to a feature | `attribute_values` |
| `raster` | Gridded frames over time (radar, flood depth) stored as COG / file URIs | `raster_frames` |

Forecasts are stored per scenario (`scenarios`, `scenario_results`). Incidents and claims live in `incidents` and `compensation_claims`.

## Compensation outlier checks

Every claim gets a level (no issues, review, high risk), a 0–100 score and plain-language reasons.

| Check | What it flags |
|---|---|
| Official rate | Amount above rate × area (for example 2,240 ฿/rai for rice), above a lump-sum cap such as house repair, or area above the household limit (30 rai for crops) |
| Regional peers | Amount per rai, head or m² far above claims for the same damage type in the same province, using a median/MAD modified z-score. Falls back to all provinces when a province has fewer than 5 claims |
| Expected amount | The typical range for the claim, from the regional interquartile range × eligible area, capped at the official maximum |
| Duplicates | The same claimant twice in one incident (Thai titles such as นาย/นาง are ignored when matching) |
| Photo evidence | No photos on a larger claim, the same photo on two claims (SHA-256), GPS position far from the incident, or a photo dated before the flood. EXIF is read on the server |

Rates live in the `compensation_rates` table and can be edited, or overridden per province, from the **Rates** view. Defaults follow the MOAC farmer assistance criteria effective 21 Aug 2026 (2569) and the MOF 2025 (2568) advance-fund regulation. Check them against the official announcement before using them for payments.

Photos are stored in the `uploads` Docker volume (original, a 1600 px JPEG, and a thumbnail). JPEG, PNG and iPhone HEIC are accepted.

Load sample claims with deliberate outliers (this replaces all incidents and claims):

```bash
curl -X POST "http://localhost:8000/api/dev/seed-response?reset=true"
```

## Getting started

Requirements: Docker Desktop and a free [Mapbox access token](https://account.mapbox.com/).

```bash
cp .env.example .env        # set VITE_MAPBOX_TOKEN
docker compose up --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |

Stations import from ThaiWater automatically on startup. To load sample incidents and claims:

```bash
curl -X POST http://localhost:8000/api/dev/seed-response
```

### Local development without Docker

```bash
docker compose up -d db

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/stations` | All stations with metadata and latest reading |
| POST | `/api/sync/stations` | Refresh stations from ThaiWater |
| POST | `/api/stations/{id}/sync-history?days=7` | Fetch a station's recent history |
| GET | `/api/datasets/{id}/timeseries?station_id=` | Readings for a station |
| POST | `/api/prediction/run` | Run the forecast and store scenarios |
| GET | `/api/scenarios/{id}/results` | Scenario output |
| GET, POST, PATCH | `/api/incidents` | Flood incidents |
| GET, POST, PATCH | `/api/claims` | Compensation claims |
| GET | `/api/compensation/summary` | Totals by claim stage |
| GET | `/api/compensation/assessments` | Outlier level and score for every claim |
| GET | `/api/claims/{id}/assessment` | Full check for one claim: flags, expected range, official maximum |
| GET, POST, PATCH, DELETE | `/api/compensation/rates` | Official rates and provincial overrides |
| GET, POST | `/api/claims/{id}/photos` | List or upload photo evidence (multipart, field `files`) |
| GET, DELETE | `/api/photos/{id}/file?size=thumb\|display\|original` | Photo files |

## Data sources

| Data | Source | Licence / terms |
|---|---|---|
| Water levels, station metadata, bank levels | [ThaiWater](https://www.thaiwater.net) public API, Hydro-Informatics Institute ([HII](https://www.hii.or.th)) | Credit HII / ThaiWater |
| Base map | [Mapbox](https://www.mapbox.com) Light style | Mapbox terms; free tier covers internal use |
| Compensation rates | MOAC farmer disaster assistance criteria (2569), MOF advance-fund regulation (2568) | Official rates; verify before payment use |
| Building footprints (LOD 1) | [OpenStreetMap](https://www.openstreetmap.org/copyright) via Mapbox Streets | ODbL, keep the map attribution |

## Project status

This is an early working prototype.

- The forecast in `backend/app/services/prediction.py` is a trend-based placeholder. Replace `run_model` with the production model (for example MIKE+ / DHI runs); the API contract stays the same.
- Incidents and claims seeded by `/api/dev/*` are sample data. Remove or protect the `dev` router before deployment.
- The schema is created on startup. Move to Alembic migrations before production.
- Authentication and role-based access for reports are not implemented yet.

## Roadmap

- Import building footprints into PostGIS (OSM, Google Open Buildings) to count affected buildings per incident
- Serve flood-depth rasters through TiTiler as map layers
- Exportable situation reports and user roles
- Connect the hydraulic model to the prediction tool
