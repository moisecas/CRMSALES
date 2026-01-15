from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.operations import router as operations_router
from app.routers.sales import router as sales_router
from app.routers.products import router as products_router
from app.routers.inventory import router as inventory_router

app = FastAPI(title="Inventario Pro (MVP)")

templates = Jinja2Templates(directory="app/templates")
app.state.templates = templates

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def root():
    # Evita 404 luego del login (si rediriges a "/")
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/health")
async def health():
    return {"ok": True}


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(operations_router)
app.include_router(sales_router)
app.include_router(products_router)
app.include_router(inventory_router)
