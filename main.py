import io
import os
import pandas as pd
import httpx
import threading
import time
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "12345"))
templates = Jinja2Templates(directory="templates")

supabase: Client = create_client(os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY"))

# --- NUEVA LÓGICA KEEP-ALIVE (MÁS AGRESIVA) ---
def keep_alive():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:
        while True:
            try:
                # Ping cada 10 minutos para evitar el sueño de 15m de Render
                httpx.get(f"{url}/login", timeout=10)
            except:
                pass
            time.sleep(600)

# Iniciamos el ping en un hilo separado
threading.Thread(target=keep_alive, daemon=True).start()

DARK_CSS = ":root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; } body { background: var(--bg); color: var(--text); font-family: sans-serif; }"

# --- RUTAS DE NAVEGACIÓN ---
@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "tarjetas": res.data, "css": DARK_CSS})

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "css": DARK_CSS})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login")

# --- MÓDULO: EXCEL (MÚLTIPLES RUTAS PARA EVITAR 404) ---
@app.get("/reportes/excel")
@app.get("/descargar_reporte")
@app.get("/reporte_excel")
async def generar_excel(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    res = supabase.table("movimientos").select("*").eq("usuario_id", user["id"]).execute()
    if not res.data: return RedirectResponse("/")
        
    df = pd.DataFrame(res.data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=reporte.xlsx"}
    )

# --- MÓDULO: ADMINISTRACIÓN Y USUARIOS ---
@app.get("/admin/usuarios", response_class=HTMLResponse)
async def panel_usuarios(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    res = supabase.table("usuarios").select("*").execute()
    return templates.TemplateResponse("usuarios.html", {"request": request, "user": user, "lista_usuarios": res.data, "css": DARK_CSS})

@app.post("/admin/crear_usuario")
async def c_usuario(request: Request, nuevo_username: str = Form(...), nuevo_password: str = Form(...), nuevo_role: str = Form(...)):
    supabase.table("usuarios").insert({"username": nuevo_username, "password": nuevo_password, "role": nuevo_role}).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

# --- TARJETAS ---
@app.get("/tarjetas/nueva", response_class=HTMLResponse)
async def f_nueva(request: Request):
    return templates.TemplateResponse("nueva_tarjeta.html", {"request": request, "user": request.session.get("user"), "css": DARK_CSS})

@app.post("/tarjetas/guardar")
async def g_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...)):
    user = request.session.get("user")
    supabase.table("tarjetas").insert({"nombre_tarjeta": nombre_tarjeta, "usuario_id": user["id"], "dia_corte": dia_corte, "dia_pago": dia_pago}).execute()
    return RedirectResponse("/", status_code=303)

# ... (Mantener el resto de funciones de editar/eliminar igual)
