from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.v1 import auth, chat, contacts, users
from app.config import get_settings
from app.database import Base, engine

# Import all models so Base knows about every table before create_all
import app.models.user          # noqa: F401
import app.models.otp           # noqa: F401
import app.models.token         # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.message       # noqa: F401

# Create all tables that don't exist yet (safe to call on every startup)
Base.metadata.create_all(bind=engine)

settings = get_settings()
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    version="1.0.0"
)


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(contacts.router, prefix=settings.API_V1_PREFIX)
app.include_router(chat.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)

# Health check endpoint
@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "status": "active",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}