from dotenv import load_dotenv; load_dotenv()
import os
import re
import time
import pathlib

# Clean up any trailing newlines or whitespace from environment variables (e.g. from copy-paste in secrets)
for k, v in list(os.environ.items()):
    os.environ[k] = v.strip()

# Globally configure Google Application Default Credentials to use our Backend Service Account
credentials_path = os.path.join(os.path.dirname(__file__), "services", "ee-credentials.json")
if os.path.exists(credentials_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.api.endpoints import api_router
import asyncio

# Track startup time for uptime calculation
_start_time = time.time()

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json"
    )

    # CORS — restricted to explicit origins in production with wildcard support
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    origins_list = [o.strip() for o in cors_origins_env.split(",") if o.strip()] if cors_origins_env else []
    
    allowed_origins = []
    allowed_origin_regex = None
    allow_credentials = True
    
    if not origins_list:
        allowed_origins = ["*"]
        allow_credentials = False
    else:
        allowed_origin_regexes = []
        for origin in origins_list:
            if origin == "*":
                allowed_origins = ["*"]
                allow_credentials = False
                break
            elif "*" in origin:
                escaped = re.escape(origin).replace(r"\*", ".*")
                allowed_origin_regexes.append(f"^{escaped}$")
            else:
                allowed_origins.append(origin)
        
        if allowed_origin_regexes:
            allowed_origin_regex = "|".join(allowed_origin_regexes)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=allowed_origin_regex,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Request Logging Middleware ───────────────────────────────────────────────
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = f"req_{int(time.time() * 1000) % 100000}"
        start = time.time()
        response = await call_next(request)
        elapsed = int((time.time() - start) * 1000)
        status = response.status_code
        slow_flag = " ⚠ SLOW" if elapsed > 1000 else ""
        print(f"[{request_id}] {request.method} {request.url.path} → {status} ({elapsed}ms){slow_flag}")
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed}ms"
        return response

    @app.get("/")
    async def root():
        return {"message": "VayuDrishti API — use /health for diagnostics"}

    @app.get("/health")
    async def health_check():
        """Real system diagnostics. Not a static OK."""
        uptime_seconds = int(time.time() - _start_time)
        return {
            "status": "healthy",
            "version": settings.VERSION,
            "uptime_seconds": uptime_seconds,
            "waqi_configured": bool(os.getenv("WAQI_TOKEN")),
            "gcp_configured": bool(os.getenv("GCP_PROJECT_ID")),
            "gemini_model": "gemini-3.1-pro-preview",
            "cors_origins": allowed_origins,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # Fire hourly ML inference loop at startup
    @app.on_event("startup")
    async def startup_event():
        print(f"[STARTUP] VayuDrishti {settings.VERSION} initializing...")
        print(f"[STARTUP] GCP configured: {bool(os.getenv('GCP_PROJECT_ID'))}")
        try:
            from app.api.endpoints.dashboard import _hourly_ml_inference_loop
            asyncio.create_task(_hourly_ml_inference_loop())
            print("[STARTUP] Hourly ML inference loop launched.")
        except Exception as e:
            print(f"[STARTUP] ML inference loop failed to launch (non-fatal): {e}")

    # Include routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    # Serve frontend static files if available
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    if os.path.exists(static_dir):
        app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")
        
        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            """Serve frontend for all non-API routes"""
            if full_path.startswith("api/"):
                return JSONResponse({"error": "Not found"}, status_code=404)
            
            file_path = os.path.join(static_dir, full_path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
            
            # Serve index.html for SPA routing
            return FileResponse(os.path.join(static_dir, "index.html"))

    return app

app = create_app()
