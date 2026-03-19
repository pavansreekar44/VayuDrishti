from fastapi import APIRouter
from app.api.endpoints import navigation, dashboard

api_router = APIRouter()
api_router.include_router(navigation.router, prefix="/navigation", tags=["Navigation"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
