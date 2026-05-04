import io
import os
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import pandas as pd
from supabase import create_client, Client

app = FastAPI()
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
async def index(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    is_admin = user.get("role") == "admin"
    admin_btn = '<a class="nav-link" onclick="tab(\'admin\')">Panel Admin</a>' if is_admin else ""

    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
        <style>{DARK_CSS}</style>
    </head>
    <body>
        <div class="nav-custom">
            <a id="link-reg" class="nav-link active" onclick="tab('reg')">Registro</a>
            <a id="link-rep" class="nav-link" onclick="tab('rep')">Reportes</a>
            {admin_btn}
            <a class="nav-link" href="/logout" style="color:var(--danger)">Salir</a>
        </div>

        <div class="container">
            <div id="reg" class="content">
                <div class="card">
                    <h3>Hola, {user['username']}</h3>
                    <form action="/guardar" method="post">
                        <label>Tipo de movimiento:</label>
                        <select name="tipo" class="form-control">
                            <option value="compra">Compra (Resta saldo -)</option>
                            <option value="abono">Abono (Suma saldo +)</option>
                        </select>
                        <input type="text" name="concepto" placeholder="Concepto" class="form-control" required>
                        <input type="number" step="0.01" name="monto" placeholder="Monto" class="form-control" required>
                        <input type="date" name="fecha" class="form-control" value="{datetime.now().strftime('%Y-%m-%d')}">
                        <button class="btn-main">Guardar Movimiento</button>
                    </form>
                </div>
            </div>

            <div id="rep" class="content" style="display:none">
                <div class="card">
                    <h3>Descargar Excel</h3>
                    <form action="/descargar" method="get">
                        <label>Desde:</label>
                        <input type="date" name="inicio" class="form-control" required>
                        <label>Hasta:</label>
                        <input type="date" name="fin" class="form-control" required>
                        <button class="btn-main" style="background:var(--success)">Generar Reporte</button>
                    </form>
                </div>
            </div>

            <div id="admin" class="content" style="display:none">
                <div class="card">
                    <h3>Gestión de Usuarios</h3>
                    <form action="/admin/crear" method="post">
                        <input type="text" name="new_user" placeholder="Nuevo Usuario" class="form-control" required>
                        <input type="password" name="new_pass" placeholder="Contraseña" class="form-control" required>
                        <button class="btn-main">Crear Cuenta Familiar</button>
                    </form>
                </div>
            </div>
        </div>

        <script>
            function tab(id) {{
                document.querySelectorAll('.content').forEach(c => c.style.display = 'none');
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                document.getElementById(id).style.display = 'block';
                document.getElementById('link-' + id.substring(0,3)).classList.add('active');
            }}
        </script>
    </body>
    </html>
    """

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
async def guardar(monto: float = Form(...), concepto: str = Form(...), fecha: str = Form(...), tipo: str = Form(...), user=Depends(get_current_user)):
    final_monto = abs(monto) if tipo == "compra" else -abs(monto)
    supabase.table("movimientos").insert({{
        "concepto": concepto, "monto": final_monto, "fecha": fecha, "usuario_id": user["id"]
    }}).execute()
    return RedirectResponse("/", status_code=303)

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
