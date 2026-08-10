import io
import os
import pandas as pd
import httpx
import threading
import time
import urllib.parse
import hashlib
import secrets
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURACIÓN DE SESIONES ---
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "12345"))

# --- FUNCIONES DE CONTRASEÑA SEGURA (COMPATIBLES) ---
def generar_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
    return f"{salt}${pwd_hash}"

def verificar_password(password: str, stored_hash: str) -> bool:
    try:
        if "$" not in stored_hash:
            return password == stored_hash
        salt, pwd_hash = stored_hash.split('$')
        verificar = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        return verificar == pwd_hash
    except:
        return False

@app.get("/arreglar-pass")
async def arreglar_pass():
    password_hash = generar_hash("admin")
    supabase.table("usuarios").update({"password": password_hash}).eq("username", "alfredo").execute()
    return HTMLResponse("<h1>Contraseña actualizada correctamente. <a href='/login'>Ir al Login</a></h1>")

# --- MIDDLEWARE ANTI-CACHE ---
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

@app.get("/instalar-admin-secreto", response_class=HTMLResponse)
async def instalar_admin():
    check = supabase.table("usuarios").select("id").execute()
    if len(check.data) == 0:
        password_hash = generar_hash("admin")
        supabase.table("usuarios").insert({
            "username": "alfredo", 
            "password": password_hash, 
            "role": "admin"
        }).execute()
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Admin Creado</title><style>{DARK_CSS}</style><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
                <h2 style="color: #4ecca3; margin-top: 0;">✨ ¡Admin Creado!</h2>
                <p style="color: #bbb; font-size: 0.95em;">Se ha configurado el usuario administrador correctamente.</p>
                <a href="/login" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Ir al Login</a>
            </div>
        </body>
        </html>
        """)
    
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Acceso Denegado</title><style>{DARK_CSS}</style><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
        <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
            <h2 style="color: #ff5555; margin-top: 0;">⚠️ Acceso Denegado</h2>
            <p style="color: #bbb; font-size: 0.95em;">El administrador ya se encuentra registrado en el sistema.</p>
            <a href="/login" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Ir al Login</a>
        </div>
    </body>
    </html>
    """, status_code=403)

@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "tarjetas": res.data, "css": DARK_CSS})

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    if request.session.get("user"): return RedirectResponse("/")
    return templates.TemplateResponse("login.html", {"request": request, "css": DARK_CSS, "error": error})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).execute()
    if res.data:
        usuario = res.data[0]
        if verificar_password(password, usuario["password"]):
            request.session.clear()
            request.session["user"] = usuario
            return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=Usuario+o+contraseña+incorrectos", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response

@app.get("/reportes", response_class=HTMLResponse)
async def rep_ui(request: Request, response: Response, error: str = None):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("reportes.html", {"request": request, "tarjetas": res.data, "css": DARK_CSS, "error": error})

@app.get("/reportes/generar")
@app.get("/reportes/excel")
async def generar_excel(request: Request, tarjeta: str = "TODAS", fecha_inicio: str = None, fecha_fin: str = None):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    try:
        query = supabase.table("movimientos").select("*").eq("usuario_id", user["id"])
        if tarjeta != "TODAS": query = query.eq("tarjeta", tarjeta)
        if fecha_inicio: query = query.gte("fecha", fecha_inicio)
        if fecha_fin: query = query.lte("fecha", fecha_fin)
        res = query.execute()
        
        if not res.data: 
            return RedirectResponse(f"/reportes?error=No+hay+registros+en+esas+fechas+para+esta+tarjeta", status_code=303)
        
        df = pd.DataFrame(res.data)
        df["fecha"] = pd.to_datetime(df["fecha"], errors='coerce')
        df = df.dropna(subset=["fecha"]).sort_values(by="fecha", ascending=True)
        
        if df.empty:
            return RedirectResponse(f"/reportes?error=No+hay+registros+válidos.", status_code=303)
        
        df["fecha_limpia"] = df["fecha"].dt.strftime('%Y-%m-%d')
        df_final = df[["fecha_limpia", "concepto", "monto", "tipo"]].copy()
        df_final.columns = ["Fecha", "Concepto", "Monto", "Tipo"]
        df_final["Monto"] = df_final["Monto"].map("{:.2f}".format)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False, sheet_name='Mis Gastos')
            worksheet = writer.sheets['Mis Gastos']
            
            for col in worksheet.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value:
                            max_len = max(max_len, len(str(cell.value)))
                    except:
                        pass
                worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
                
        output.seek(0)
        
        fecha_hoy = datetime.now().strftime("%d-%m-%Y")
        nombre_archivo = f"Reporte_{tarjeta}_{fecha_hoy}.xlsx"
        
        return StreamingResponse(
            output, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={nombre_archivo}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except Exception as e:
        return RedirectResponse(f"/reportes?error=Error:+{urllib.parse.quote(str(e))}", status_code=303)
        
@app.get("/admin/usuarios", response_class=HTMLResponse)
async def panel_usuarios(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    if user.get("role") != 'admin':
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head><title>Acceso Denegado</title><style>{DARK_CSS}</style><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
                <h2 style="color: #ff5555; margin-top: 0;">⚠️ Acceso Denegado</h2>
                <p style="color: #bbb; font-size: 0.95em;">No tienes los privilegios de administrador necesarios para ver esta sección.</p>
                <a href="/" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Volver al Inicio</a>
            </div>
        </body>
        </html>
        """, status_code=403)
    res = supabase.table("usuarios").select("*").execute()
    return templates.TemplateResponse("usuarios.html", {"request": request, "user": user, "lista_usuarios": res.data, "css": DARK_CSS})

@app.post("/admin/crear_usuario")
async def c_usuario(request: Request, nuevo_username: str = Form(...), nuevo_password: str = Form(...), nuevo_role: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    if user.get("role") != 'admin':
        return HTMLResponse("<h1>403 - Acceso Denegado</h1>", status_code=403)
    password_hash = generar_hash(nuevo_password)
    supabase.table("usuarios").insert({"username": nuevo_username, "password": password_hash, "role": nuevo_role}).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.get("/admin/usuarios/editar/{id}", response_class=HTMLResponse)
async def f_edit_user(request: Request, id: int):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    if user.get("role") != 'admin':
        return HTMLResponse("<h1>403 - Acceso Denegado</h1>", status_code=403)
    res = supabase.table("usuarios").select("*").eq("id", id).execute()
    return templates.TemplateResponse("editar_usuario.html", {"request": request, "u_edit": res.data[0], "css": DARK_CSS})

@app.post("/admin/usuarios/actualizar")
async def actualizar_usuario(request: Request, id: int = Form(...), username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    if user.get("role") != 'admin':
        return HTMLResponse("<h1>403 - Acceso Denegado</h1>", status_code=403)
    password_hash = generar_hash(password)
    supabase.table("usuarios").update({"username": username, "password": password_hash, "role": role}).eq("id", id).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.post("/admin/usuarios/eliminar/{id}")
async def e_usuario(request: Request, id: int):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    if user.get("role") != 'admin':
        return HTMLResponse("<h1>403 - Acceso Denegado</h1>", status_code=403)
    
    supabase.table("movimientos").delete().eq("usuario_id", id).execute()
    supabase.table("tarjetas").delete().eq("usuario_id", id).execute()
    supabase.table("usuarios").delete().eq("id", id).execute()
    
    if id == user["id"]:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
        
    return RedirectResponse("/admin/usuarios", status_code=303)

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
async def f_editar(request: Request, nombre: str, error: str = None):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("editar_tarjeta.html", {"request": request, "tarjeta": res.data[0], "css": DARK_CSS, "error": error})

@app.post("/tarjetas/actualizar")
async def actualizar_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...), id: int = Form(...), password: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    res_user = supabase.table("usuarios").select("password").eq("id", user["id"]).execute()
    if not res_user.data or not verificar_password(password, res_user.data[0]["password"]):
        return RedirectResponse(f"/tarjetas/editar/{urllib.parse.quote(nombre_tarjeta)}?error=Contraseña+incorrecta", status_code=303)

    supabase.table("tarjetas").update({"nombre_tarjeta": nombre_tarjeta, "dia_corte": dia_corte, "dia_pago": dia_pago}).eq("id", id).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/tarjetas/confirmar-eliminar/{nombre}", response_class=HTMLResponse)
async def confirmar_eliminar_tarjeta(request: Request, nombre: str, error: str = None):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    res = supabase.table("tarjetas").select("*").eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    if not res.data:
        return RedirectResponse("/")
        
    return templates.TemplateResponse("confirmar_eliminar_tarjeta.html", {
        "request": request, 
        "tarjeta": res.data[0], 
        "css": DARK_CSS, 
        "error": error
    })

@app.post("/tarjetas/eliminar/{nombre}")
async def e_tarjeta(request: Request, nombre: str, password: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    res_user = supabase.table("usuarios").select("password").eq("id", user["id"]).execute()
    if not res_user.data or not verificar_password(password, res_user.data[0]["password"]):
        return RedirectResponse(f"/tarjetas/confirmar-eliminar/{urllib.parse.quote(nombre)}?error=Contraseña+incorrecta", status_code=303)

    supabase.table("movimientos").delete().eq("tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    supabase.table("tarjetas").delete().eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)
    
@app.get("/movimientos/nuevo/{tarjeta}", response_class=HTMLResponse)
async def n_mov(request: Request, tarjeta: str, success: bool = False):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("movimientos").select("*").eq("tarjeta", tarjeta).eq("usuario_id", user["id"]).order("id", desc=True).limit(5).execute()
    
    return templates.TemplateResponse("registrar_movimiento.html", {
        "request": request, 
        "nombre_tarjeta": tarjeta, 
        "movimientos": res.data, 
        "css": DARK_CSS,
        "success": success
    })

@app.post("/movimientos/guardar")
async def g_mov(request: Request, tarjeta_nombre: str = Form(...), concepto: str = Form(...), monto: float = Form(...), tipo_movimiento: str = Form(...), fecha: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    monto_f = monto * -1 if tipo_movimiento == 'abono' else monto
    supabase.table("movimientos").insert({
        "tarjeta": tarjeta_nombre, 
        "concepto": concepto, 
        "monto": monto_f, 
        "fecha": fecha, 
        "usuario_id": user["id"], 
        "tipo": tipo_movimiento
    }).execute()
    
    return RedirectResponse(f"/movimientos/nuevo/{tarjeta_nombre}?success=true", status_code=303)

@app.get("/movimientos/editar/{id}", response_class=HTMLResponse)
async def f_editar_mov(request: Request, id: int, error: str = None):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("movimientos").select("*").eq("id", id).eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("editar_movimiento.html", {"request": request, "mov": res.data[0], "css": DARK_CSS, "error": error})

@app.post("/movimientos/actualizar")
async def actualizar_mov(request: Request, id: int = Form(...), concepto: str = Form(...), monto: float = Form(...), tipo_movimiento: str = Form(...), fecha: str = Form(...), tarjeta: str = Form(...), password: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    res_user = supabase.table("usuarios").select("password").eq("id", user["id"]).execute()
    if not res_user.data or not verificar_password(password, res_user.data[0]["password"]):
        return RedirectResponse(f"/movimientos/editar/{id}?error=Contraseña+incorrecta", status_code=303)
    
    monto_f = monto * -1 if tipo_movimiento == 'abono' else monto
    
    supabase.table("movimientos").update({
        "concepto": concepto, 
        "monto": monto_f, 
        "fecha": fecha, 
        "tipo": tipo_movimiento
    }).eq("id", id).eq("usuario_id", user["id"]).execute()
    
    return RedirectResponse(f"/movimientos/nuevo/{tarjeta}", status_code=303)
