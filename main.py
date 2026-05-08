import io
import os
import pandas as pd
import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()

# Configuración básica
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "12345"))
templates = Jinja2Templates(directory="templates")

# Supabase
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_KEY")
)

DARK_CSS = ":root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; } body { background: var(--bg); color: var(--text); font-family: sans-serif; }"

@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("usuario_id", user["id"]).execute()
    # Forma estándar y segura de pasar el contexto
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "tarjetas": res.data, "css": DARK_CSS})

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request):
    html = f"<html><style>{DARK_CSS}</style><body><form action='/login' method='post'><input name='username'><input name='password' type='password'><button>Entrar</button></form></body></html>"
    return HTMLResponse(content=html)

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login")

@app.get("/movimientos/nuevo/{tarjeta}", response_class=HTMLResponse)
async def n_mov(request: Request, tarjeta: str):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("movimientos").select("*").eq("tarjeta", tarjeta).eq("usuario_id", user["id"]).order("id", desc=True).limit(5).execute()
    return templates.TemplateResponse("registrar_movimiento.html", {"request": request, "nombre_tarjeta": tarjeta, "movimientos": res.data, "css": DARK_CSS})

@app.post("/movimientos/guardar")
async def g_mov(request: Request, tarjeta_nombre: str = Form(...), concepto: str = Form(...), monto: float = Form(...), tipo_movimiento: str = Form(...), fecha: str = Form(...)):
    user = request.session.get("user")
    monto_f = monto * -1 if tipo_movimiento == 'abono' else monto
    supabase.table("movimientos").insert({"tarjeta": tarjeta_nombre, "concepto": concepto, "monto": monto_f, "fecha": fecha, "usuario_id": user["id"], "tipo": tipo_movimiento}).execute()
    return RedirectResponse(f"/movimientos/nuevo/{tarjeta_nombre}", status_code=303)
