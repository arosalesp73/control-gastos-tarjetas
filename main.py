import io
import os
import pandas as pd
import httpx
import threading
import urllib.parse
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
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
            import time
            time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

DARK_CSS = """
:root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; } 
body { background: var(--bg); color: var(--text); font-family: sans-serif; margin: 0; }
.card { background: var(--surface); padding: 20px; border-radius: 12px; border: 1px solid #333; }
input, select { width: 100%; padding: 10px; margin-bottom: 10px; border-radius: 5px; border: 1px solid #444; background: #0f0f1a; color: white; box-sizing: border-box; }
button { width: 100%; padding: 10px; background: var(--accent); border: none; color: white; border-radius: 5px; cursor: pointer; }
.error-msg { color: #ff5555; background: rgba(255,85,85,0.1); padding: 10px; border-radius: 5px; margin-bottom: 15px; text-align: center; border: 1px solid #ff5555; }
.tab-btn { background: #181828; color: #aaa; border: 1px solid #333; padding: 10px 20px; border-radius: 8px 8px 0 0; cursor: pointer; font-weight: bold; transition: 0.2s; }
.tab-btn.active { background: var(--surface); color: var(--accent); border-bottom: 2px solid var(--accent); }
.tab-content { display: none; }
.tab-content.active { display: block; }
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
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Admin Creado</title><style>""" + DARK_CSS + """</style><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
                <h2 style="color: #4ecca3; margin-top: 0;">✨ ¡Admin Creado!</h2>
                <p style="color: #bbb; font-size: 0.95em;">Se ha configurado el usuario administrador correctamente.</p>
                <a href="/login" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Ir al Login</a>
            </div>
        </body>
        </html>
        """)
    
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head><title>Acceso Denegado</title><style>""" + DARK_CSS + """</style><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
        <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
            <h2 style="color: #ff5555; margin-top: 0;">⚠️ Acceso Denegado</h2>
            <p style="color: #bbb; font-size: 0.95em;">El administrador ya se encuentra registrado en el sistema.</p>
            <a href="/login" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Ir al Login</a>
        </div>
    </body>
    </html>
    """, status_code=403)

@app.get("/registro-inicial", response_class=HTMLResponse)
async def f_registro_inicial(request: Request, error: str = None):
    check = supabase.table("usuarios").select("id").execute()
    if len(check.data) > 0:
        return RedirectResponse("/login", status_code=303)
    
    error_html = f'<div class="error-msg">{error}</div>' if error else ''
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Configuración Inicial</title>
        <style>{DARK_CSS}</style>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
        <div class="card" style="max-width: 400px; width: 90%;">
            <h2 style="color: var(--accent); text-align: center; margin-top: 0;">🚀 Configuración Inicial</h2>
            <p style="color: #bbb; text-align: center; font-size: 0.9em; margin-bottom: 20px;">Crea tu cuenta de administrador para comenzar a usar el sistema.</p>
            {error_html}
            <form action="/registro-inicial" method="post">
                <label>Usuario:</label>
                <input type="text" name="username" required autocomplete="off">
                
                <label>Contraseña:</label>
                <input type="password" name="password" required>
                
                <button type="submit">Crear Cuenta</button>
            </form>
        </div>
    </body>
    </html>
    """)

@app.post("/registro-inicial")
async def g_registro_inicial(username: str = Form(...), password: str = Form(...)):
    check = supabase.table("usuarios").select("id").execute()
    if len(check.data) > 0:
        return RedirectResponse("/login", status_code=303)
    
    password_hash = generar_hash(password)
    supabase.table("usuarios").insert({
        "username": username,
        "password": password_hash,
        "role": "admin",
        "tipo_acceso": "basico"
    }).execute()
    
    return RedirectResponse("/login", status_code=303)

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
            if usuario.get("role") != "admin" and usuario.get("fecha_expiracion"):
                exp_date = datetime.fromisoformat(usuario["fecha_expiracion"].replace("Z", "+00:00").split("+")[0])
                if datetime.now() > exp_date:
                    return HTMLResponse(f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>Cuenta Expirada</title>
                        <style>{DARK_CSS}</style>
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    </head>
                    <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
                        <div class="card" style="max-width: 440px; width: 90%; text-align: center;">
                            <h2 style="color: #ff5555; margin-top: 0;">⚠️ Tu cuenta ha expirado</h2>
                            <p style="color: #bbb; font-size: 0.9em; line-height: 1.4; margin-bottom: 12px;">
                                Tu licencia ha vencido. Descarga tu respaldo en Excel o realiza tu pago y envíanos el comprobante.
                            </p>
                            <form action="/respaldo-datos" method="post" style="text-align: left;">
                                <label style="font-size: 0.85em;">Confirma tu Usuario:</label>
                                <input type="text" name="username" value="{username}" required autocomplete="off">
                                
                                <label style="font-size: 0.85em;">Confirma tu Contraseña:</label>
                                <input type="password" name="password" required>
                                
                                <button type="submit" style="margin-top: 4px;">📥 Descargar Respaldo (Excel)</button>
                            </form>
                            
                            <div style="margin-top: 12px; padding: 10px; background: rgba(108,99,255,0.08); border-radius: 8px; border: 1px solid var(--accent); text-align: left;">
                                <p style="margin: 0 0 4px 0; font-size: 0.85em; color: #fff; font-weight: bold; text-align: center;">💳 Precios de Renovación:</p>
                                <ul style="margin: 0 0 8px 0; padding-left: 16px; font-size: 0.8em; color: #ccc; line-height: 1.3;">
                                    <li><b>1 Año:</b> $120 MXN</li>
                                    <li><b>2 Años:</b> $200 MXN <span style="color: #4ecca3;">(Oferta)</span></li>
                                    <li><b>3 Años:</b> $300 MXN <span style="color: #4ecca3;">(Ahorro)</span></li>
                                </ul>
                                
                                <div style="display: flex; align-items: center; margin-bottom: 4px;">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4ecca3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px; flex-shrink: 0;"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>
                                    <span style="font-size: 0.8em; color: #ddd;"><b>Banco:</b> BBVA</span>
                                </div>

                                <div style="display: flex; align-items: center; margin-bottom: 8px;">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4ecca3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px; flex-shrink: 0;"><rect x="2" y="5" width="20" height="14" rx="2"></rect><line x1="2" y1="10" x2="22" y2="10"></line></svg>
                                    <span style="font-size: 0.8em; color: #ddd; word-break: break-all;"><b>CLABE:</b> <span style="color: #4ecca3; font-family: monospace; font-size: 1.1em; font-weight: bold; letter-spacing: 0.5px;">012180015723536440</span></span>
                                </div>

                                <div style="background: rgba(37,211,102,0.1); padding: 8px; border-radius: 6px; border: 1px solid rgba(37,211,102,0.3); text-align: center;">
                                    <p style="margin: 0 0 4px 0; font-size: 0.78em; color: #ddd;">Realiza tu depósito y envía tu comprobante indicando tu usuario:</p>
                                    <div style="display: flex; align-items: center; justify-content: center;">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="#25D366" style="margin-right: 6px; flex-shrink: 0;"><path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448l-6.305 1.654zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.198-.198.347-.764.967-.937 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.124-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"/></svg>
                                        <a href="https://wa.me/52523121073276" target="_blank" style="color: #25D366; font-weight: bold; text-decoration: none; font-size: 0.85em;">WhatsApp: +52 312 107 3276</a>
                                    </div>
                                </div>
                            </div>

                            <a href="/login" style="display: block; margin-top: 12px; color: var(--accent); text-decoration: none; font-size: 0.85em;">← Volver al Login</a>
                        </div>
                    </body>
                    </html>
                    """)
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
async def rep_ui(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("reportes.html", {"request": request, "tarjetas": res.data, "css": DARK_CSS})

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
    
    if not res.data: 
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Sin registros</title>
            <style>{DARK_CSS}</style>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
                <h2 style="color: #ffcc00;">📊 Sin movimientos</h2>
                <p style="color: #bbb;">No se encontraron registros para el periodo seleccionado.</p>
                <a href="/reportes" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Volver a Reportes</a>
            </div>
        </body>
        </html>
        """)

    df = pd.DataFrame(res.data)
    df["fecha"] = pd.to_datetime(df["fecha"], errors='coerce')
    df = df.dropna(subset=["fecha"]).sort_values(by="fecha", ascending=True)
    
    if df.empty:
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Sin registros</title>
            <style>{DARK_CSS}</style>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div class="card" style="max-width: 400px; width: 90%; text-align: center;">
                <h2 style="color: #ffcc00;">📊 Sin movimientos</h2>
                <p style="color: #bbb;">No se encontraron registros válidos para el periodo seleccionado.</p>
                <a href="/reportes" style="display: block; margin-top: 20px; padding: 10px; background: var(--accent); color: white; text-decoration: none; border-radius: 5px;">Volver a Reportes</a>
            </div>
        </body>
        </html>
        """)
    
    df["fecha_limpia"] = df["fecha"].dt.strftime('%Y-%m-%d')
    df_final = df[["fecha_limpia", "concepto", "monto", "tipo"]].copy()
    df_final.columns = ["Fecha", "Concepto", "Monto", "Tipo"]
    df_final["Monto"] = df_final["Monto"].astype(float).round(2)
    
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
                except: pass
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
    
    res_usuarios = supabase.table("usuarios").select("*").execute()
    res_codigos = supabase.table("codigos_invitacion").select("*").execute()
    
    usuarios_html = ""
    for u in res_usuarios.data:
        f_exp = u.get('fecha_expiracion')
        if u.get('role') == 'admin':
            exp_info = "<span style='color: #aaa; font-size: 0.85em;'>Acceso Ilimitado (Admin)</span>"
        elif not f_exp:
            exp_info = "<span style='color: #4ecca3; font-size: 0.85em;'>Acceso Ilimitado (Sin caducidad)</span>"
        else:
            exp_info = f"<span style='color: #4ecca3; font-size: 0.85em;'>Expira: {f_exp[:10]}</span>"
        
        renovacion_form = ""
        if u.get('role') != 'admin':
            renovacion_form = f"""
            <form action="/admin/usuarios/renovar" method="post" style="display: flex; gap: 8px; margin-top: 10px; align-items: center; background: rgba(108,99,255,0.05); padding: 8px; border-radius: 6px; border: 1px solid #333;">
                <input type="hidden" name="id" value="{u['id']}">
                <select name="anios" style="margin: 0; padding: 6px; font-size: 0.85em; width: 110px;">
                    <option value="1">1 Año ($120)</option>
                    <option value="2">2 Años ($200)</option>
                    <option value="3">3 Años ($300)</option>
                </select>
                <button type="submit" style="margin: 0; padding: 6px 12px; font-size: 0.85em; background: #25d366; width: auto; font-weight: bold;">⚡ Renovar</button>
            </form>
            """

        usuarios_html += f"""
        <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid #333; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <b style="font-size: 1.1em; color: white;">{u['username']}</b> <span style="color: #888; font-size: 0.85em;">(Rol: {u['role']})</span><br>
                {exp_info}
                {renovacion_form}
            </div>
            <div style="display: flex; gap: 8px;">
                <a href="/admin/usuarios/editar/{u['id']}" style="background: var(--accent); color: white; padding: 6px 12px; border-radius: 5px; text-decoration: none; font-size: 0.85em; display: flex; align-items: center;">✏️ Editar</a>
                <form action="/admin/usuarios/eliminar/{u['id']}" method="post" style="margin: 0;" onsubmit="return confirm('¿Estás seguro de eliminar este usuario?');">
                    <button type="submit" style="background: #ff5555; padding: 6px 12px; font-size: 0.85em; margin: 0;">🗑️ Eliminar</button>
                </form>
            </div>
        </div>
        """

    codigos_html = ""
    for c in res_codigos.data:
        estado_color = "#ff5555" if c['usado'] else "#4ecca3"
        estado_texto = "Usado" if c['usado'] else "Disponible"
        codigos_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #333; font-family: monospace; color: #fff;">{c['codigo']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #333; color: {estado_color}; font-weight: bold;">{estado_texto}</td>
        </tr>
        """

    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Panel de Administración</title>
        <style>{DARK_CSS}</style>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script>
            function switchTab(evt, tabId) {{
                var contents = document.getElementsByClassName("tab-content");
                for (var i = 0; i < contents.length; i++) {{
                    contents[i].classList.remove("active");
                }}
                var buttons = document.getElementsByClassName("tab-btn");
                for (var i = 0; i < buttons.length; i++) {{
                    buttons[i].classList.remove("active");
                }}
                document.getElementById(tabId).classList.add("active");
                evt.currentTarget.classList.add("active");
            }}
        </script>
    </head>
    <body style="padding: 20px; max-width: 800px; margin: 0 auto;">
        <a href="/" style="color: var(--accent); text-decoration: none; font-weight: bold; display: inline-block; margin-bottom: 20px;">← Volver al Inicio</a>
        
        <h2 style="color: #fff; margin-top: 0; margin-bottom: 20px;">⚙️ Panel de Administración</h2>

        <!-- Menú de Pestañas -->
        <div style="display: flex; gap: 5px; border-bottom: 1px solid #333; margin-bottom: 20px; flex-wrap: wrap;">
            <button class="tab-btn active" onclick="switchTab(event, 'tab-usuarios')">👥 Usuarios y Licencias</button>
            <button class="tab-btn" onclick="switchTab(event, 'tab-crear')">➕ Crear Usuario</button>
            <button class="tab-btn" onclick="switchTab(event, 'tab-codigos')">🎟️ Códigos de Invitación</button>
        </div>

        <!-- Pestaña 1: Usuarios y Licencias -->
        <div id="tab-usuarios" class="tab-content active">
            <div class="card">
                <h3 style="margin-top: 0; color: var(--accent);">👥 Gestión de Usuarios y Licencias</h3>
                <div style="margin-top: 15px;">
                    {usuarios_html}
                </div>
            </div>
        </div>

        <!-- Pestaña 2: Crear Usuario -->
        <div id="tab-crear" class="tab-content">
            <div class="card">
                <h3 style="margin-top: 0; color: var(--accent);">➕ Crear Nuevo Usuario Directo (Sin Caducidad)</h3>
                <form action="/admin/crear_usuario" method="post">
                    <label style="font-size: 0.9em;">Usuario:</label>
                    <input type="text" name="nuevo_username" required autocomplete="off">
                    
                    <label style="font-size: 0.9em;">Contraseña:</label>
                    <input type="password" name="nuevo_password" required>
                    
                    <label style="font-size: 0.9em;">Rol:</label>
                    <select name="nuevo_role">
                        <option value="usuario">Usuario Estándar (Sin Caducidad)</option>
                        <option value="admin">Administrador</option>
                    </select>
                    
                    <button type="submit" style="margin-top: 10px;">Registrar Usuario</button>
                </form>
            </div>
        </div>

        <!-- Pestaña 3: Códigos de Invitación -->
        <div id="tab-codigos" class="tab-content">
            <div class="card">
                <h3 style="margin-top: 0; color: var(--accent);">🎟️ Códigos de Invitación</h3>
                <form action="/admin/codigos/generar" method="post" style="margin-bottom: 15px;">
                    <button type="submit" style="max-width: 250px;">Generar Nuevo Código</button>
                </form>
                <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9em;">
                    <thead>
                        <tr style="border-bottom: 2px solid #444; color: #aaa;">
                            <th style="padding: 8px;">Código</th>
                            <th style="padding: 8px;">Estado</th>
                        </tr>
                    </thead>
                    <tbody>
                        {codigos_html if codigos_html else '<tr><td colspan="2" style="padding: 10px; color: #888; text-align: center;">No hay códigos generados</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """)

@app.post("/admin/usuarios/renovar")
async def admin_renovar_licencia(request: Request, id: int = Form(...), anios: int = Form(...)):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin':
        return RedirectResponse("/login", status_code=303)
    
    res = supabase.table("usuarios").select("fecha_expiracion").eq("id", id).execute()
    if res.data:
        u_info = res.data[0]
        base_date = datetime.now()
        current_exp = u_info.get("fecha_expiracion")
        if current_exp:
            try:
                exp_dt = datetime.fromisoformat(current_exp.replace("Z", "+00:00").split("+")[0])
                if exp_dt > base_date:
                    base_date = exp_dt
            except:
                pass
        
        nueva_exp = (base_date + timedelta(days=365 * anios)).isoformat()
        supabase.table("usuarios").update({"fecha_expiracion": nueva_exp}).eq("id", id).execute()
        
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.post("/admin/crear_usuario")
async def c_usuario(request: Request, nuevo_username: str = Form(...), nuevo_password: str = Form(...), nuevo_role: str = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    if user.get("role") != 'admin':
        return HTMLResponse("<h1>403 - Acceso Denegado</h1>", status_code=403)
    password_hash = generar_hash(nuevo_password)
    supabase.table("usuarios").insert({
        "username": nuevo_username, 
        "password": password_hash, 
        "role": nuevo_role,
        "fecha_expiracion": None
    }).execute()
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

@app.get("/registro", response_class=HTMLResponse)
async def registro_usuario_ui(request: Request, error: str = None):
    if request.session.get("user"): 
        return RedirectResponse("/")
    return templates.TemplateResponse("registro_usuario.html", {"request": request, "css": DARK_CSS, "error": error})

@app.post("/registro")
async def registro_usuario_guardar(username: str = Form(...), password: str = Form(...), codigo_invitacion: str = Form(...)):
    val_codigo = supabase.table("codigos_invitacion").select("*").eq("codigo", codigo_invitacion).execute()
    
    if not val_codigo.data:
        return RedirectResponse("/registro?error=El+codigo+de+invitacion+no+existe", status_code=303)
    
    codigo_info = val_codigo.data[0]
    if codigo_info["usado"]:
        return RedirectResponse("/registro?error=Este+codigo+ya+fue+utilizado+anteriormente", status_code=303)

    check = supabase.table("usuarios").select("id").eq("username", username).execute()
    if check.data:
        return RedirectResponse("/registro?error=El+nombre+de+usuario+ya+está+ocupado", status_code=303)
    
    fecha_expiracion = (datetime.now() + timedelta(days=365)).isoformat()
    
    password_hash = generar_hash(password)
    supabase.table("usuarios").insert({
        "username": username,
        "password": password_hash,
        "role": "usuario",
        "tipo_acceso": "basico",
        "fecha_expiracion": fecha_expiracion
    }).execute()
    
    supabase.table("codigos_invitacion").update({"usado": True}).eq("id", codigo_info["id"]).execute()
    
    return RedirectResponse("/login?error=Cuenta+creada+exitosamente.+Inicia+sesión", status_code=303)

@app.api_route("/admin/codigos/generar", methods=["GET", "POST"])
async def generar_codigo_invitacion(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin':
        return RedirectResponse("/login", status_code=303)
    
    nuevo_codigo = f"TDC-{secrets.token_hex(3).upper()}"
    
    supabase.table("codigos_invitacion").insert({
        "codigo": nuevo_codigo,
        "usado": False
    }).execute()
    
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.post("/respaldo-datos")
async def descargar_respaldo(username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).execute()
    if not res.data or not verificar_password(password, res.data[0]["password"]):
        return HTMLResponse("<h1>Credenciales incorrectas. <a href='/login'>Volver al Login</a></h1>", status_code=403)
    
    usuario = res.data[0]
    
    res_tarjetas = supabase.table("tarjetas").select("*").eq("usuario_id", usuario["id"]).execute()
    res_movimientos = supabase.table("movimientos").select("*").eq("usuario_id", usuario["id"]).execute()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if res_tarjetas.data:
            df_tarjetas = pd.DataFrame(res_tarjetas.data)
            df_tarjetas.to_excel(writer, index=False, sheet_name='Mis Tarjetas')
        else:
            pd.DataFrame(columns=["nombre_tarjeta", "dia_corte", "dia_pago"]).to_excel(writer, index=False, sheet_name='Mis Tarjetas')
            
        if res_movimientos.data:
            df_movs = pd.DataFrame(res_movimientos.data)
            df_movs.to_excel(writer, index=False, sheet_name='Mis Movimientos')
        else:
            pd.DataFrame(columns=["tarjeta", "concepto", "monto", "fecha", "tipo"]).to_excel(writer, index=False, sheet_name='Mis Movimientos')
            
    output.seek(0)
    nombre_archivo = f"Respaldo_{usuario['username']}.xlsx"
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={nombre_archivo}",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )
