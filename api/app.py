from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .routes import api, messaging

app = FastAPI()

app.include_router(api.router)
app.include_router(messaging.router)


@app.get("/", response_class=HTMLResponse)
async def _root():
    return """<p>Welcome to the CSTV API!</p>"""
