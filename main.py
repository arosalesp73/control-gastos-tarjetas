import io
import os
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "personal-key-123"))
templates = Jinja2Templates(directory=os.path.join(os.getcwd(), "templates"))

# --- CONEXIÓN SUPABASE ---
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- DISEÑO ---
DARK_CSS = ":root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; } body { background: var(--bg); color: var(--text); font-family: sans-serif; margin: 0; padding: 20px; }"

@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    try:
        # Cargamos el archivo manualmente sin usar el buscador de Jinja2
        with open("templates/index.html", "r") as f:
            contenido = f.read()
        return HTMLResponse(content=contenido)
    except Exception as e:
        return HTMLResponse(content=f"Error de lectura manual: {str(e)}")

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    err = f'<p style="color:red">{error}</p>' if error else ""
    return f"<html><head><style>{DARK_CSS}</style></head><body><div class='card'><h2>Login</h2>{err}<form action='/login' method='post'><input name='username' placeholder='Usuario' required><br><input name='password' type='password' placeholder='Pass' required><br><button>Entrar</button></form></div></body></html>"

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=Error", status_code=303)

@app.post("/guardar")
async def guardar(request: Request, fecha: str = Form(...), tienda: str = Form(...), monto: float = Form(...), tarjeta: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    supabase.table("movimientos").insert({"usuario_id": user["id"], "fecha": fecha, "concepto": tienda, "monto": monto, "tarjeta": tarjeta, "tipo": "gasto"}).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
