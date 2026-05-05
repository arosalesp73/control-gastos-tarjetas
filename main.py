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
templates = Jinja2Templates(directory="templates")
# Usa la variable que configuramos en Render
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "clave-secreta-default"))

# --- CONEXIÓN SUPABASE ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- SEGURIDAD ---
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401)
    return user

# --- DISEÑO ---
DARK_CSS = """
    :root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; --danger: #ff6b6b; --success: #56cf86; }
    body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; padding-bottom: 30px; }
    .nav-custom { background: var(--surface); display: flex; overflow-x: auto; padding: 10px; border-bottom: 1px solid #2a2a45; sticky: top; }
    .nav-link { color: #8080a8; text-decoration: none; padding: 10px; font-size: 0.9rem; white-space: nowrap; cursor: pointer; }
    .nav-link.active { color: var(--accent); font-weight: bold; border-bottom: 2px solid var(--accent); }
    .container { max-width: 500px; margin: auto; padding: 20px; }
    .card { background: var(--surface); border-radius: 15px; padding: 20px; border: 1px solid #2a2a45; margin-bottom: 20px; }
    .form-control { background: #1f1f33; border: 1px solid #2a2a45; color: white; width: 100%; padding: 12px; border-radius: 10px; margin-bottom: 15px; box-sizing: border-box; font-size: 16px; }
    .btn-main { background: var(--accent); color: white; border: none; width: 100%; padding: 15px; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 16px; }
"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)
    
    # Esta es la línea corregida:
    return templates.TemplateResponse(request=request, name="index.html", context={"usuario": user["username"]})
    
@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    # Si recibimos un error en la URL, lo mostramos en un div rojo
    error_html = f'<div style="color: #ff4d4d; margin-bottom: 15px; text-align: center; font-weight: bold;">{error}</div>' if error else ""
    
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>{DARK_CSS}</style>
    </head>
    <body class="container">
        <div class="card">
            <h2 style="text-align:center">Control de Gastos</h2>
            {error_html}
            <form action="/login" method="post">
                <input name="username" class="form-control" placeholder="Usuario" required autocomplete="off">
                <input name="password" type="password" class="form-control" placeholder="Contraseña" required>
                <button class="btn-main">Entrar</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    try:
        # Consulta limpia a Supabase
        res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
        
        if res.data and len(res.data) > 0:
            request.session["user"] = res.data[0]
            return RedirectResponse("/", status_code=303)
        else:
            # Redirige de vuelta al login con un mensaje de error amigable
            return RedirectResponse("/login?error=Usuario+o+clave+incorrectos", status_code=303)
            
    except Exception as e:
        # En caso de error de conexión, también redirige con aviso
        print(f"Error de sistema: {e}")
        return RedirectResponse("/login?error=Error+de+conexion+con+el+servidor", status_code=303)

@app.post("/guardar")
async def guardar(
    request: Request,
    fecha: str = Form(...),
    tienda: str = Form(...),
    monto: float = Form(...),
    tarjeta: str = Form(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=303)

    # Registro en la base de datos con los nuevos nombres
    nuevo_movimiento = {
        "user_id": user["id"],
        "fecha": fecha,
        "establecimiento": tienda, # 'tienda' del HTML viaja a 'establecimiento' en Supabase
        "monto": monto,
        "tarjeta": tarjeta
    }

    supabase.table("movimientos").insert(nuevo_movimiento).execute()
    
    return RedirectResponse("/", status_code=303)
    
# --- AQUI PEGUE EL CODIGO QUE SE SUPONE QUE DESPUES DE CREAR UN USUARIO NUEVO REGRESA A LA PAGINA ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_ui(request: Request, msg: str = None, error: str = None):
    # Verificamos sesión
    user_session = request.session.get("user")
    if not user_session or user_session.get("role") != "admin":
        return RedirectResponse("/login", status_code=303)

    # Preparamos avisos de éxito o error
    alert = ""
    if msg:
        alert = f'<div style="color: #2ecc71; margin-bottom: 15px; text-align: center;">{msg}</div>'
    if error:
        alert = f'<div style="color: #e74c3c; margin-bottom: 15px; text-align: center;">{error}</div>'
    
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>{DARK_CSS}</style>
    </head>
    <body class="container">
        <div class="card">
            <h2 style="text-align:center">Panel de Administración</h2>
            {alert}
            <div style="margin-bottom: 20px;">
                <a href="/" style="color: var(--primary); text-decoration: none;">← Volver al Inicio</a>
            </div>
            
            <form action="/admin/crear" method="post">
                <h3>Crear Nuevo Usuario</h3>
                <input name="new_user" class="form-control" placeholder="Nuevo Usuario" required>
                <input name="new_pass" type="password" class="form-control" placeholder="Contraseña" required>
                <button class="btn-main">Registrar Usuario</button>
            </form>
        </div>
    </body>
    </html>
    """
    # --- AQUI TERMINA EL CODIGO PARA REGRESAR A LA PAGINA DESPUES DE CREAR UN USUARIO NUEVO ---
@app.post("/admin/crear")
async def crear_user(request: Request, new_user: str = Form(...), new_pass: str = Form(...)):
    # Verificamos sesión de admin
    user_session = request.session.get("user")
    if not user_session or user_session.get("role") != "admin":
        return RedirectResponse("/login", status_code=303)

    try:
        # CORRECCIÓN: Quitamos las llaves dobles que causaban el TypeError
        supabase.table("usuarios").insert({
            "username": new_user, 
            "password": new_pass, 
            "role": "user"
        }).execute()
        
        return RedirectResponse("/admin?msg=Usuario+creado+exitosamente", status_code=303)
    except Exception as e:
        print(f"Error al crear usuario: {e}")
        return RedirectResponse(f"/admin?error=Error+al+crear+usuario", status_code=303)

@app.get("/descargar")
async def descargar(inicio: str, fin: str, user=Depends(get_current_user)):
    query = supabase.table("movimientos").select("*").eq("usuario_id", user["id"]).gte("fecha", inicio).lte("fecha", fin)
    res = query.execute()
    
    if not res.data:
        return "No hay datos en ese rango de fechas."

    df = pd.DataFrame(res.data)
    # Limpiamos columnas innecesarias para el reporte
    df = df.drop(columns=['usuario_id'], errors='ignore')
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={{"Content-Disposition": f"attachment; filename=reporte_{user['username']}_{inicio}.xlsx"}})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
