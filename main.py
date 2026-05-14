import io
import os
import pandas as pd
import httpx
import threading
import time
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()

# --- CONFIGURACIÓN DE SESIONES ---
# Usamos una clave secreta para firmar las cookies
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "12345"))

# --- MIDDLEWARE ANTI-CACHE (SEGURIDAD BOTÓN ATRÁS) ---
# Este bloque obliga al navegador a pedir permiso al servidor siempre
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- KEEP ALIVE ---
def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:
        while True:
            try:
                httpx.get(f"{url}/login", timeout=10)
            except:
                pass
            time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

DARK_CSS = """
:root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; } 
body { background: var(--bg); color: var(--text); font-family: sans-serif; margin: 0; }
.card { background: var(--surface); padding: 20px; border-radius: 12px; border: 1px solid #333; }
input, select { width: 100%; padding: 10px; margin-bottom: 10px; border-radius: 5px; border: 1px solid #444; background: #0f0f1a; color: white; }
button { width: 100%; padding: 10px; background: var(--accent); border: none; color: white; border-radius: 5px; cursor: pointer; }
.error-msg { color: #ff5555; background: rgba(255,85,85,0.1); padding: 10px; border-radius: 5px; margin-bottom: 15px; text-align: center; border: 1px solid #ff5555; }
"""

# --- RUTA DE SEGURIDAD (PUERTA TRASERA) ---
@app.get("/instalar-admin-secreto")
async def instalar_admin():
    check = supabase.table("usuarios").select("id").execute()
    if len(check.data) == 0:
        supabase.table("usuarios").insert({
            "username": "alfredo", 
            "password": "admin", 
            "role": "admin"
        }).execute()
        return HTMLResponse("<h1>Admin creado. <a href='/login'>Ir al Login</a></h1>")
    return HTMLResponse("<h1>Acceso denegado. La base ya contiene datos.</h1>")

# --- RUTAS DE NAVEGACIÓN ---
@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "tarjetas": res.data, "css": DARK_CSS})

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    # Si ya tiene sesión, lo mandamos al inicio
    if request.session.get("user"):
        return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request, "css": DARK_CSS, "error": error})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session.clear() # Limpiamos basura previa
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=Usuario+o+contraseña+incorrectos", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session") # Borramos la cookie físicamente
    return response

# --- MÓDULO: REPORTES ---
@app.get("/reportes/generar")
@app.get("/reportes/excel")
async def generar_excel(request: Request, tarjeta: str = "TODAS", fecha_inicio: str = None, fecha_fin: str = None):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    query = supabase.table("movimientos").select("*").eq("usuario_id", user["id"])
    if tarjeta != "TODAS": query = query.eq("tarjeta", tarjeta)
    if fecha_inicio: query = query.gte("fecha", fecha_inicio)
    if fecha_fin: query = query.lte("fecha", fecha_fin)
    res = query.execute()
    if not res.data: return RedirectResponse("/reportes")
    df = pd.DataFrame(res.data)
    df["fecha"] = pd.to_datetime(df["fecha"], errors='coerce')
    df = df.dropna(subset=["fecha"]).sort_values(by="fecha", ascending=True)
    df["fecha_limpia"] = df["fecha"].dt.strftime('%Y-%m-%d')
    df_final = df[["fecha_limpia", "concepto", "monto", "tipo"]].copy()
    df_final.columns = ["Fecha", "Concepto", "Monto", "Tipo"]
    df_final["Monto"] = df_final["Monto"].map("{:.2f}".format)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Mis Gastos')
        worksheet = writer.sheets['Mis Gastos']
        for idx, col in enumerate(df_final.columns):
            max_len = max(df_final[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = max_len
    output.seek(0)
    nombre_archivo = f"Reporte_{tarjeta}.xlsx"
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={nombre_archivo}"})

@app.get("/reportes", response_class=HTMLResponse)
async def rep_ui(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("reportes.html", {"request": request, "tarjetas": res.data, "css": DARK_CSS})

# --- MÓDULO: USUARIOS (SOLO ADMIN) ---
@app.get("/admin/usuarios", response_class=HTMLResponse)
async def
