import io
import os
import pandas as pd
import httpx
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

# Middleware de sesión
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "personal-key-123"))

# Configuración de templates
templates = Jinja2Templates(directory="templates")
templates.env.cache = None 

# Conexión Supabase
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"), 
    os.environ.get("SUPABASE_KEY")
)

# --- KEEP ALIVE ---
def self_ping():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:
        try:
            with httpx.Client() as client:
                client.get(f"{url}/login")
        except:
            pass

scheduler = BackgroundScheduler()
scheduler.add_job(self_ping, 'interval', minutes=12)
scheduler.start()

# --- ESTILOS ---
DARK_CSS = """
:root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; --input-bg: #0f0f1a; } 
body { background-color: var(--bg); background-image: url('https://www.transparenttextures.com/patterns/carbon-fibre.png'), linear-gradient(rgba(14, 14, 26, 0.95), rgba(14, 14, 26, 0.95)); background-attachment: fixed; color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding: 0; min-height: 100vh; }
.card { background: var(--surface); padding: 30px; border-radius: 16px; border: 1px solid #333; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
input, select { width: 100%; padding: 14px; border-radius: 10px; border: 1px solid #444; background: var(--input-bg); color: white; margin-bottom: 15px; box-sizing: border-box; font-size: 16px; }
button { width: 100%; padding: 14px; background: var(--accent); border: none; color: white; font-weight: bold; border-radius: 10px; cursor: pointer; font-size: 16px; }
"""

# --- RUTAS ---
@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    tarjetas = supabase.table("tarjetas").select("*").eq("usuario_id", user["id"]).execute().data
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "tarjetas": tarjetas, "css": DARK_CSS})

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    err = f'<div style="color:#ff4e4e; text-align:center; margin-bottom:15px;">⚠️ Acceso denegado</div>' if error else ""
    return f"""<html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>{DARK_CSS}</style></head><body><div style="display:flex; justify-content:center; align-items:center; height:100vh; padding:20px;"><div class="card" style="width:100%; max-width:350px; text-align:center;"><h2>Mis Finanzas</h2>{err}<form action="/login" method="post"><input name="username" placeholder="Usuario" required><input name="password" type="password" placeholder="Contraseña" required><button type="submit">Entrar</button></form></div></div></body></html>"""

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=1", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- TARJETAS ---
@app.get("/tarjetas/nueva")
async def f_tarjeta(request: Request):
    return templates.TemplateResponse("nueva_tarjeta.html", {"request": request, "user": request.session.get("user"), "css": DARK_CSS})

@app.post("/tarjetas/guardar")
async def g_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...)):
    user = request.session.get("user")
    supabase.table("tarjetas").insert({"nombre_tarjeta": nombre_tarjeta, "usuario_id": user["id"], "dia_corte": dia_corte, "dia_pago": dia_pago}).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/tarjetas/eliminar/{nombre}")
async def e_tarjeta(request: Request, nombre: str):
    user = request.session.get("user")
    supabase.table("movimientos").delete().eq("tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    supabase.table("tarjetas").delete().eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/tarjetas/editar/{nombre}")
async def ed_tarjeta_ui(request: Request, nombre: str):
    res = supabase.table("tarjetas").select("*").eq("nombre_tarjeta", nombre).eq("usuario_id", request.session.get("user")["id"]).execute()
    return templates.TemplateResponse("editar_tarjeta.html", {"request": request, "tarjeta": res.data[0], "css": DARK_CSS})

@app.post("/tarjetas/actualizar")
async def a_tarjeta(request: Request, id: int = Form(...), nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...)):
    supabase.table("tarjetas").update({"nombre_tarjeta": nombre_tarjeta, "dia_corte": dia_corte, "dia_pago": dia_pago}).eq("id", id).execute()
    return RedirectResponse("/", status_code=303)

# --- MOVIMIENTOS ---
@app.get("/movimientos/nuevo/{tarjeta}")
async def n_mov(request: Request, tarjeta: str):
    user = request.session.get("user")
    res = supabase.table("movimientos").select("*").eq("tarjeta", tarjeta).eq("usuario_id", user["id"]).order("id", desc=True).limit(5).execute()
    return templates.TemplateResponse("registrar_movimiento.html", {"request": request, "nombre_tarjeta": tarjeta, "movimientos": res.data, "css": DARK_CSS})

@app.post("/movimientos/guardar")
async def g_mov(request: Request, tarjeta_nombre: str = Form(...), concepto: str = Form(...), monto: float = Form(...), tipo_movimiento: str = Form(...), fecha: str = Form(...)):
    monto_f = monto * -1 if tipo_movimiento == 'abono' else monto
    supabase.table("movimientos").insert({"tarjeta": tarjeta_nombre, "concepto": concepto, "monto": monto_f, "fecha": fecha, "usuario_id": request.session.get("user")["id"], "tipo": tipo_movimiento}).execute()
    return RedirectResponse(f"/movimientos/nuevo/{tarjeta_nombre}", status_code=303)

# --- ADMIN ---
@app.get("/admin/usuarios")
async def g_usuarios(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    todos = supabase.table("usuarios").select("*").execute().data
    return templates.TemplateResponse("usuarios.html", {"request": request, "user": user, "lista_usuarios": todos, "css": DARK_CSS})

@app.get("/admin/usuarios/eliminar/{user_id}")
async def el_usuario(request: Request, user_id: int):
    user = request.session.get("user")
    if user and user.get("role") == 'admin' and user_id != user["id"]:
        supabase.table("usuarios").delete().eq("id", user_id).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.get("/admin/usuarios/editar/{user_id}")
async def ed_usuario_ui(request: Request, user_id: int):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    res = supabase.table("usuarios").select("*").eq("id", user_id).execute()
    return templates.TemplateResponse("editar_usuario.html", {"request": request, "u_edit": res.data[0], "css": DARK_CSS})

@app.post("/admin/usuarios/actualizar")
async def ac_usuario(request: Request, id: int = Form(...), username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    supabase.table("usuarios").update({"username": username, "password": password, "role": role}).eq("id", id).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.post("/admin/crear_usuario")
async def c_usuario(request: Request, nuevo_username: str = Form(...), nuevo_password: str = Form(...), nuevo_role: str = Form(...)):
    supabase.table("usuarios").insert({"username": nuevo_username, "password": nuevo_password, "role": nuevo_role}).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

# --- REPORTES ---
@app.get("/reportes")
async def rep_ui(request: Request):
    tarjetas = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", request.session.get("user")["id"]).execute().data
    return templates.TemplateResponse("reportes.html", {"request": request, "tarjetas": tarjetas, "css": DARK_CSS})

@app.get("/reportes/generar")
async def gen_rep(request: Request, tarjeta: str, fecha_inicio: str, fecha_fin: str):
    query = supabase.table("movimientos").select("*").eq("usuario_id", request.session.get("user")["id"]).gte("fecha", fecha_inicio).lte("fecha", fecha_fin)
    if tarjeta != "TODAS": query = query.eq("tarjeta", tarjeta)
    res = query.order("id", asc=True).execute()
    if not res.data: return HTMLResponse("No hay datos")
    df = pd.DataFrame(res.data)[['fecha', 'tarjeta', 'concepto', 'tipo', 'monto']]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return StreamingResponse(output, headers={'Content-Disposition': 'attachment; filename="Reporte.xlsx"'}, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
