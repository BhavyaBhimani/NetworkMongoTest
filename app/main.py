import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes import router as api_router
from app.db.mongo import get_db

app = FastAPI(
    title="NetTrace AI",
    description="Context-Aware Network Policy CI/CD & Attestation Engine Powered by MongoDB",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path)

@app.on_event("startup")
def on_startup():
    db = get_db()
    print("==================================================================")
    print("  NETTRACE AI - MONGODB TORONTO HACKATHON")
    print("  Theme: Agents in Context - No Cold Start via Persistent Memory")
    print(f"  Connected Engine: {'MongoDB Atlas' if db.is_atlas else 'High-Performance Embedded In-Memory MongoDB'}")
    print(f"  Dashboard available at: http://{settings.HOST}:{settings.PORT}")
    print("==================================================================")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
