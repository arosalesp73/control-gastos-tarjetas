import io
import os
import pandas as pd
import httpx
import asyncio
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException, Depends
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

# --- LÓGICA PARA EVITAR REPOSO (KEEP ALIVE) ---

def self_ping():
    """Función que hace una petición a la propia app para mantenerla despierta"""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if url:
        try:
            # Usamos httpx para hacer un ping rápido a la pantalla de login
            with httpx.Client() as client:
                client.get(f"{url}/login")
                print(f"Ping de auto-despertado exitoso a las {datetime.now()}")
        except Exception as e:
            print(f"Error en self-ping: {e}")

# Configuramos el programador para que corra cada 12 minutos
scheduler = BackgroundScheduler()
scheduler.add_job(self_ping, 'interval', minutes=12)
scheduler.start()

# --- CONFIGURACIÓN VISUAL ---

DARK_CSS = """
:root { 
    --bg: #0e0e1a; 
    --surface: #181828; 
    --accent: #6c63ff; 
    --text: #e0e0f0; 
    --input-bg: #0f0f1a;
} 
body { 
    background-color: var(--bg); 
    background-image: url('https://www.transparenttextures.com/patterns/carbon-fibre.png'), 
                      linear-gradient(rgba(14, 14, 26, 0.95), rgba(14, 14, 26, 0.95));
    background-attachment: fixed;
    color: var(--text); 
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
    margin: 0; 
    padding: 0;
    min-height: 100vh;
}
.card { 
    background: var(--surface); 
    padding: 30px; 
    border-radius: 16px; 
    border: 1px solid #333; 
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}
input { 
    width: 100%; padding: 14px; border-radius: 10px; border: 1px solid #444; 
    background: var(--input-bg); color: white; margin-bottom: 15px; box-sizing: border-box; 
    font-size: 16px; 
}
button { 
    width: 100%; padding: 14px; background: var(--accent); border: none; 
    color: white; font-weight: bold; border-radius: 10px; cursor: pointer; 
    font-size: 16px; transition: opacity 0.2s;
}
button:hover { opacity: 0.9; }
"""

# --- RUTAS DE NAVEGACIÓN PRINCIPAL ---

@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    try:
        user = request.session.get("user")
        if not user:
            return RedirectResponse(url="/login")

        tarjetas = supabase.table("tarjetas")\
            .select("*")\
            .eq("usuario_id", user["id"])\
            .execute().data
        
        template = templates.get_template("index.html")
        return HTMLResponse(content=template.render({
            "request": request,
            "user": user,
            "tarjetas": tarjetas if tarjetas else [],
            "css": DARK_CSS
        }))
    except Exception as e:
        return HTMLResponse(content=f"Error de sistema: {str(e)}", status_code=500)

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    err_html = f'<div style="color:#ff4e4e; margin-bottom:15px; text-align:center; font-size:0.9em; background:rgba(255,78,78,0.1); padding:10px; border-radius:8px;">⚠️ Usuario o contraseña incorrectos</div>' if error else ""
    return f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Login - Control de Gastos</title>
        <style>
            {DARK_CSS}
            .login-container {{ display: flex; justify-content: center; align-items: center; height: 100vh; padding: 20px; box-sizing: border-box; }}
            .login-card {{ width: 100%; max-width: 380px; text-align: center; }}
            .logo-icon {{ font-size: 3.5em; margin-bottom: 15px; display: block; }}
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="card login-card">
                <span class="logo-icon">💳</span>
                <h2 style="margin-bottom: 25px; color: #fff;">Mis Finanzas</h2>
                {err_html}
                <form action="/login" method="post">
                    <input name="username" placeholder="Usuario" required>
                    <input name="password" type="password" placeholder="Contraseña" required>
                    <button type="submit">Entrar al Sistema</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """

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

# --- GESTIÓN DE TARJETAS ---

@app.get("/tarjetas/nueva", response_class=HTMLResponse)
async def formulario_tarjeta(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    template = templates.get_template("nueva_tarjeta.html")
    return HTMLResponse(content=template.render({"request": request, "user": user, "css": DARK_CSS}))

@app.post("/tarjetas/guardar")
async def guardar_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    supabase.table("tarjetas").insert({"nombre_tarjeta": nombre_tarjeta.strip(), "usuario_id": user["id"], "dia_corte": dia_corte, "dia_pago": dia_pago}).execute()
    return RedirectResponse(url="/", status_code=303)

@app.get("/tarjetas/eliminar/{nombre_tarjeta}")
async def eliminar_tarjeta(request: Request, nombre_tarjeta: str):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    supabase.table("movimientos").delete().eq("tarjeta", nombre_tarjeta).eq("usuario_id", user["id"]).execute()
    supabase.table("tarjetas").delete().eq("nombre_tarjeta", nombre_tarjeta).eq("usuario_id", user["id"]).execute()
    return RedirectResponse(url="/", status_code=303)

@app.get("/tarjetas/editar/{nombre_tarjeta}", response_class=HTMLResponse)
async def editar_tarjeta_ui(request: Request, nombre_tarjeta: str):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    res = supabase.table("tarjetas").select("*").eq("nombre_tarjeta", nombre_tarjeta).eq("usuario_id", user["id"]).execute()
    template = templates.get_template("editar_tarjeta.html")
    return HTMLResponse(content=template.render({"request": request, "tarjeta": res.data[0], "css": DARK_CSS}))

@app.post("/tarjetas/actualizar")
async def actualizar_tarjeta(request: Request, id: int = Form(...), nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    supabase.table("tarjetas").update({"nombre_tarjeta": nombre_tarjeta.strip(), "dia_corte": dia_corte, "dia_pago": dia_pago}).eq("id", id).execute()
    return RedirectResponse(url="/", status_code=303)

# --- GESTIÓN DE MOVIMIENTOS ---

@app.get("/movimientos/nuevo/{tarjeta_nombre}", response_class=HTMLResponse)
async def nuevo_movimiento(request: Request, tarjeta_nombre: str):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    res = supabase.table("movimientos").select("*").eq("tarjeta", tarjeta_nombre).eq("usuario_id", user["id"]).order("id", desc=True).limit(5).execute()
    template = templates.get_template("registrar_movimiento.html")
    return HTMLResponse(content=template.render({"request": request, "nombre_tarjeta": tarjeta_nombre, "movimientos": res.data, "css": DARK_CSS}))

@app.post("/movimientos/guardar")
async def guardar_movimiento(request: Request, tarjeta_nombre: str = Form(...), concepto: str = Form(...), monto: float = Form(...), tipo_movimiento: str = Form(...), fecha: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    monto_final = monto * -1 if tipo_movimiento == 'abono' else monto
    supabase.table("movimientos").insert({"tarjeta": tarjeta_nombre.strip(), "concepto": concepto, "monto": monto_final, "fecha": fecha, "usuario_id": user["id"], "tipo": tipo_movimiento}).execute()
    return RedirectResponse(url=f"/movimientos/nuevo/{tarjeta_nombre}", status_code=303)

# --- ADMINISTRACIÓN DE USUARIOS ---

@app.get("/admin/usuarios", response_class=HTMLResponse)
async def gestionar_usuarios(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse(url="/")
    todos = supabase.table("usuarios").select("*").execute().data
    template = templates.get_template("usuarios.html")
    return HTMLResponse(content=template.render({"request": request, "user": user, "lista_usuarios": todos, "css": DARK_CSS}))

@app.post("/admin/crear_usuario")
async def crear_usuario(request: Request, nuevo_username: str = Form(...), nuevo_password: str = Form(...), nuevo_role: str = Form(...)):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse(url="/")
    supabase.table("usuarios").insert({"username": nuevo_username, "password": nuevo_password, "role": nuevo_role}).execute()
    return RedirectResponse(url="/admin/usuarios", status_code=303)

# --- REPORTES ---

@app.get("/reportes", response_class=HTMLResponse)
async def configurar_reporte_ui(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    tarjetas = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", user["id"]).execute().data
    template = templates.get_template("reportes.html")
    return HTMLResponse(content=template.render({"request": request, "tarjetas": tarjetas, "css": DARK_CSS}))

@app.get("/reportes/generar")
async def generar_reporte_excel(request: Request, tarjeta: str, fecha_inicio: str, fecha_fin: str):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    query = supabase.table("movimientos").select("*").eq("usuario_id", user["id"]).gte("fecha", fecha_inicio).lte("fecha", fecha_fin)
    if tarjeta != "TODAS": query = query.eq("tarjeta", tarjeta)
    res = query.order("id", asc=True).execute()
    if not res.data: return HTMLResponse("No hay movimientos.")
    
    df = pd.DataFrame(res.data)[['fecha', 'tarjeta', 'concepto', 'tipo', 'monto']]
    df.columns = ['Fecha', 'Tarjeta', 'Concepto', 'Tipo', 'Monto']
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    output.seek(0)
    return StreamingResponse(output, headers={'Content-Disposition': f'attachment; filename="Reporte.xlsx"'}, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
