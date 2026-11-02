from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import models
from models.connection import engine, Base
from router import (
    session_router,
    room_router,
    service_router,
    booking_router,
    rag_router
)
from chatbot import router as chatbot_router

Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="Pearl Continental (PC) Lahore AI HotelAgent API",
    version="6.0.0",
    description="Clean, modular FastAPI backend for Pearl Continental Hotel Lahore."
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Modular Routers
app.include_router(session_router.router)
app.include_router(room_router.router)
app.include_router(service_router.router)
app.include_router(booking_router.router)
app.include_router(rag_router.router)
app.include_router(chatbot_router.router)

# Mount Frontend Static Directory (if exists)
frontend_dir = Path(__file__).resolve().parent.parent / "pc-lahore-frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    @app.get("/")
    def welcome_message():
        return {"message": "Welcome to Pearl Continental (PC) Lahore AI HotelAgent API. Visit /docs for Swagger UI."}
