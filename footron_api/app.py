from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .constants import BASE_URL
from .routes import api, messaging

app = FastAPI()

app.include_router(api.router)
app.include_router(messaging.router)

origins = [
    "http://localhost",
    "http://localhost:3000",
    # Note that we need to make sure BASE_URL starts with the protocol (http(s)://)
    BASE_URL,
]

# To future maintainers: if you want to have CORS headers on errors, see this discussion:
# https://github.com/tiangolo/fastapi/issues/775
# TODO: See if there's any hardening we can do here
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def _root():
    return """<p>Welcome to the CSTV API!</p>"""
