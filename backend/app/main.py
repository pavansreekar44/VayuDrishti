from dotenv import load_dotenv; load_dotenv()
import os
import pathlib

# Globally configure Google Application Default Credentials to use our Backend Service Account
# This ensures Vertex AI and Google Earth Engine SDKs authenticate seamlessly without Windows ADC hangs
try:
    credentials_path = os.path.join(os.path.dirname(__file__), "services", "ee-credentials.json")
    if os.path.exists(credentials_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        print(f"✓ Google credentials loaded from: {credentials_path}")
    else:
        print("⚠ Google credentials file not found - some Google services may be unavailable")
except Exception as e:
    print(f"⚠ Warning: Could not load Google credentials: {e}")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.endpoints import api_router
import asyncio

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # Set up CORS
    # Allow both development (localhost) and production (Vercel) origins
    cors_origins = [
        "http://localhost:3000",  # Development
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]
    
    # Add production frontend URLs from environment variable if available
    if frontend_url := os.getenv("FRONTEND_URL"):
        cors_origins.append(frontend_url)
    
    # In production on Azure, allow HTTPS from Vercel
    if os.getenv("ENVIRONMENT") == "azure":
        # Add your Vercel deployment URL from FRONTEND_URL env var
        vercel_url = os.getenv("FRONTEND_URL")
        if vercel_url:
            cors_origins.append(vercel_url)
            print(f"✓ Added Vercel frontend to CORS: {vercel_url}")
        else:
            # Fallback: allow any HTTPS origin in production (less secure but works)
            print("⚠ FRONTEND_URL not set - CORS may have issues")
            # You can temporarily use "*" or a specific list
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {"message": "Welcome to the Breath-Analyzer API"}

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    # Fire ML inference loop immediately at startup (not lazily on first request)
    @app.on_event("startup")
    async def startup_event():
        try:
            from app.api.endpoints.dashboard import _autonomous_ml_inference_loop
            asyncio.create_task(_autonomous_ml_inference_loop())
            print("[STARTUP] TNN background inference loop launched.")
        except Exception as e:
            print(f"[STARTUP] ML inference loop failed to launch (non-fatal, continuing): {e}")

    # Include routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    return app

app = create_app()
