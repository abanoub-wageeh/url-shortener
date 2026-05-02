from fastapi import FastAPI

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.redirects import router as redirects_router
from app.api.v1.endpoints.urls import router as urls_router

app = FastAPI()


app.include_router(auth_router)
app.include_router(urls_router)
app.include_router(redirects_router)
