from fastapi import APIRouter

from app.api.routes import auth, config, dashboard, entries, flow, meta, stats

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(meta.router)
api_router.include_router(entries.router)
# Screens 2-4 share the /entries prefix, so they mount after the base routes.
api_router.include_router(flow.router)
api_router.include_router(dashboard.router)
api_router.include_router(stats.router)
api_router.include_router(config.router)
