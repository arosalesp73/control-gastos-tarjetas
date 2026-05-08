import io
import os
import pandas as pd
import httpx
import threading
import time
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "12345"))
templates = Jinja2Templates(directory="templates")

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
"""

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

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

# --- MÓDULO: REPORTES ---
@app.get("/reportes", response_class=HTMLResponse)
async def rep_ui(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("reportes.html", {"request": request, "tarjetas": res.data, "css": DARK_CSS})

@app.get("/reportes/excel")
@app.get("/descargar_reporte")
async def generar_excel(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("movimientos").select("*").eq("usuario_id", user["id"]).execute()
    if not res.data: return RedirectResponse("/reportes")
    
    df = pd.DataFrame(res.data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Movimientos')
    output.seek(0)
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=reporte_{user['username']}.xlsx"}
    )

# --- MÓDULO: USUARIOS ---
@app.get("/admin/usuarios", response_class=HTMLResponse)
async def panel_usuarios(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    res = supabase.table("usuarios").select("*").execute()
    return templates.TemplateResponse("usuarios.html", {"request": request, "user": user, "lista_usuarios": res.data, "css": DARK_CSS})

@app.post("/admin/crear_usuario")
async def c_usuario(request: Request, nuevo_username: str = Form(...), nuevo_password: str = Form(...), nuevo_role: str = Form(...)):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    supabase.table("usuarios").insert({"username": nuevo_username, "password": nuevo_password, "role": nuevo_role}).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

# --- MÓDULO: TARJETAS ---
@app.get("/tarjetas/nueva", response_class=HTMLResponse)
async def f_nueva(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("nueva_tarjeta.html", {"request": request, "user": user, "css": DARK_CSS})

@app.post("/tarjetas/guardar")
async def g_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    supabase.table("tarjetas").insert({"nombre_tarjeta": nombre_tarjeta, "usuario_id": user["id"], "dia_corte": dia_corte, "dia_pago": dia_pago}).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/tarjetas/editar/{nombre}", response_class=HTMLResponse)
async def f_editar(request: Request, nombre: str):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("editar_tarjeta.html", {"request": request, "tarjeta": res.data[0], "css": DARK_CSS})

@app.post("/tarjetas/actualizar")
async def actualizar_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...), id_tarjeta: int = Form(None), id: int = Form(None)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    target_id = id_tarjeta if id_tarjeta is not None else id
    supabase.table("tarjetas").update({"nombre_tarjeta": nombre_tarjeta, "dia_corte": dia_corte, "dia_pago": dia_pago}).eq("id", target_id).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/tarjetas/eliminar/{nombre}")
async def e_tarjeta(request: Request, nombre: str):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    supabase.table("movimientos").delete().eq("tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    supabase.table("tarjetas").delete().eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)

# --- MÓDULO: MOVIMIENTOS ---
@app.get("/movimientos/nuevo/{tarjeta}", response_class=HTMLResponse)
async def n_mov(request: Request, tarjeta: str):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("movimientos").select("*").eq("tarjeta", tarjeta).eq("usuario_id", user["id"]).order("id", desc=True).limit(5).execute()
    return templates.TemplateResponse("registrar_movimiento.html", {"request": request, "nombre_tarjeta": tarjeta, "movimientos": res.data, "css": DARK_CSS})

@app.post("/movimientos/guardar")
async def g_mov(request: Request, tarjeta_nombre: str = Form(...), concepto: str = Form(...), monto: float = Form(...), tipo_movimiento: str = Form(...), fecha: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    monto_f = monto * -1 if tipo_movimiento == 'abono' else monto
    supabase.table("movimientos").insert({"tarjeta": tarjeta_nombre, "concepto": concepto, "monto": monto_f, "fecha": fecha, "usuario_id": user["id"], "tipo": tipo_movimiento}).execute()
    return RedirectResponse(f"/movimientos/nuevo/{tarjeta_nombre}", status_code=303)
