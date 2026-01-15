# app/main.py
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dependencies import _get_token
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.inventory import router as inventory_router
from app.routers.operations import router as operations_router
from app.routers.products import router as products_router
from app.routers.sales import router as sales_router

app = FastAPI(title="Inventario Pro (MVP)")

templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

# ✅ static robusto (no revienta si no existe)
STATIC_DIR = Path(__file__).resolve().parent / "static"  # app/static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ✅ root: si hay token -> dashboard, si no -> login
@app.get("/")
async def root(request: Request):
    token = _get_token(request)
    return RedirectResponse(url="/dashboard" if token else "/login", status_code=302)


@app.get("/health")
async def health():
    return {"ok": True}


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(operations_router)
app.include_router(sales_router)
app.include_router(products_router)
app.include_router(inventory_router)
