from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from tuck_api.auth import AuthenticationMiddleware, auth_router
from tuck_api.lists import lists_router
from tuck_api.notes import notes_router
from tuck_api.reminders import reminders_router
from tuck_api.settings import get_settings as get_settings

app = FastAPI(title="Tuck API")
app.add_middleware(AuthenticationMiddleware)
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(lists_router)
app.include_router(reminders_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/ready")
def readiness() -> dict[str, str]:
    try:
        get_settings()
    except ValidationError as error:
        raise HTTPException(
            status_code=503,
            detail="Application configuration is invalid",
        ) from error
    return {"status": "ready"}
