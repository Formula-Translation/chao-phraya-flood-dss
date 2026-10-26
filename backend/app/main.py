import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import models  # noqa: F401  (register tables)
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.routers import compensation, datasets, dev, prediction, reports, response, stations
from app.services import rates, thaiwater

log = logging.getLogger("cfm")
SYNC_EVERY_S = 15 * 60


def _sync_once():
    with SessionLocal() as db:
        log.warning("ThaiWater sync: %s", thaiwater.sync_stations(db))


async def _sync_loop():
    while True:
        try:
            await asyncio.to_thread(_sync_once)
        except Exception as e:  # keep the app up if ThaiWater is down
            log.warning("ThaiWater sync failed: %s", e)
        await asyncio.sleep(SYNC_EVERY_S)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Dev convenience; switch to Alembic migrations when the schema settles.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, cols in models.EXTRA_COLUMNS.items():
            for col, typ in cols.items():
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
    with SessionLocal() as db:
        rates.ensure_defaults(db)
    task = asyncio.create_task(_sync_loop())
    yield
    task.cancel()


app = FastAPI(title=settings.project_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets.router)
app.include_router(stations.router)
app.include_router(response.router)
app.include_router(compensation.router)
app.include_router(prediction.router)
app.include_router(reports.router)
app.include_router(dev.router)


@app.get("/health")
def health():
    return {"status": "ok"}
