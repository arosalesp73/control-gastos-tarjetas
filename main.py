import io
import os
import pandas as pd
import httpx
import threading
import time
import urllib.parse
from datetime import datetime
from fastapi import FastAPI, Form, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from supabase import create_client, Client

app = FastAPI()

# --- CONFIGURACIÓN DE SESIONES ---
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "12345"))

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
    return HTMLResponse("<h1>Acceso denegado.</h1>")

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
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session.clear()
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=Usuario+o+contraseña+incorrectos", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response

@app.get("/reportes", response_class=HTMLResponse)
async def rep_ui(request: Request):
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
    
    if not res.data: return RedirectResponse("/reportes")
    
    # 1. Crear DataFrame y asegurar orden cronológico
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
        
        # 2. Auto-ajuste de celdas dinámico
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
    
    # 3. Nombre personalizado dinámico con cabecera expuesta para JS
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

@app.get("/reportes/whatsapp")
async def enviar_excel_whatsapp(request: Request, tarjeta: str = "TODAS", fecha_inicio: str = None, fecha_fin: str = None):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    
    # === LIMPIEZA AUTOMÁTICA DE ARCHIVOS VIEJOS ===
    try:
        archivos_en_nube = supabase.storage.from_("reportes").list()
        if archivos_en_nube:
            for archivo in archivos_en_nube:
                # Si el archivo tiene metadatos con fecha de creación
                created_at_str = archivo.get("created_at")
                if created_at_str:
                    # Cortar el string para manejar el formato ISO de Supabase
                    fecha_creacion = pd.to_datetime(created_at_str[:19])
                    horas_vida = (datetime.utcnow() - fecha_creacion).total_seconds() / 3600
                    # Si tiene más de 24 horas, se borra automáticamente
                    if horas_vida > 24:
                        supabase.storage.from_("reportes").remove([archivo["name"]])
    except Exception as e:
        print(f"Error limpiando archivos viejos: {e}")
    # ==============================================

    query = supabase.table("movimientos").select("*").eq("usuario_id", user["id"])
    if tarjeta != "TODAS": query = query.eq("tarjeta", tarjeta)
    if fecha_inicio: query = query.gte("fecha", fecha_inicio)
    if fecha_fin: query = query.lte("fecha", fecha_fin)
    res = query.execute()
    
    if not res.data: return RedirectResponse("/reportes")
    
    # 1. Crear el DataFrame y ordenar cronológicamente
    df = pd.DataFrame(res.data)
    df["fecha"] = pd.to_datetime(df["fecha"], errors='coerce')
    df = df.dropna(subset=["fecha"]).sort_values(by="fecha", ascending=True)
    
    df["fecha_limpia"] = df["fecha"].dt.strftime('%Y-%m-%d')
    df_final = df[["fecha_limpia", "concepto", "monto", "tipo"]].copy()
    df_final.columns = ["Fecha", "Concepto", "Monto", "Tipo"]
    df_final["Monto"] = df_final["Monto"].map("{:.2f}".format)
    
    # 2. Nombre del archivo único para que no se sobreescriba
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"Reporte_{tarjeta}_{timestamp}.xlsx"
    ruta_local = f"/tmp/{nombre_archivo}"
    
    os.makedirs("/tmp", exist_ok=True)
    
    # 3. Crear el Excel con auto-ajuste de columnas
    with pd.ExcelWriter(ruta_local, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Mis Gastos')
        worksheet = writer.sheets['Mis Gastos']
        for col in worksheet.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value: max_len = max(max_len, len(str(cell.value)))
                except: pass
            worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
            
    # 4. Subir a Supabase de forma permanente para que el enlace funcione siempre
    try:
        with open(ruta_local, "rb") as f:
            supabase.storage.from_("reportes").upload(
                path=nombre_archivo,
                file=f,
                file_options={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            )
        
        # 5. Obtener la URL de descarga directa
        url_descarga = supabase.storage.from_("reportes").get_public_url(nombre_archivo)
        
        # Texto formateado para el chat
        texto = f"📊 *Reporte de Gastos Automático*\n\n💳 *Tarjeta:* {tarjeta}\n📅 *Periodo:* Del {fecha_inicio} al {fecha_fin}\n\n📥 *Descargar archivo Excel aquí:* {url_descarga}"
        
        # Redirigir directamente al WhatsApp web/app con el texto completo
        texto_codificado = urllib.parse.quote(texto)
        url_whatsapp = f"https://wa.me/?text={texto_codificado}"
    
        return RedirectResponse(url_whatsapp)
        
    except Exception as e:
        print(f"Error: {e}")
        return RedirectResponse("/reportes")
    finally:
        if os.path.exists(ruta_local):
            os.remove(ruta_local)

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

@app.get("/admin/usuarios/editar/{id}", response_class=HTMLResponse)
async def f_edit_user(request: Request, id: int):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    res = supabase.table("usuarios").select("*").eq("id", id).execute()
    return templates.TemplateResponse("editar_usuario.html", {"request": request, "u_edit": res.data[0], "css": DARK_CSS})

@app.post("/admin/usuarios/actualizar")
async def actualizar_usuario(request: Request, id: int = Form(...), username: str = Form(...), password: str = Form(...), role: str = Form(...)):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    supabase.table("usuarios").update({"username": username, "password": password, "role": role}).eq("id", id).execute()
    return RedirectResponse("/admin/usuarios", status_code=303)

@app.get("/admin/usuarios/eliminar/{id}")
async def e_usuario(request: Request, id: int):
    user = request.session.get("user")
    if not user or user.get("role") != 'admin': return RedirectResponse("/")
    supabase.table("movimientos").delete().eq("usuario_id", id).execute()
    supabase.table("tarjetas").delete().eq("usuario_id", id).execute()
    supabase.table("usuarios").delete().eq("id", id).execute()
    if id == user["id"]:
        request.session.clear()
        return RedirectResponse("/login")
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
async def f_editar(request: Request, nombre: str):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("tarjetas").select("*").eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return templates.TemplateResponse("editar_tarjeta.html", {"request": request, "tarjeta": res.data[0], "css": DARK_CSS})

@app.post("/tarjetas/actualizar")
async def actualizar_tarjeta(request: Request, nombre_tarjeta: str = Form(...), dia_corte: int = Form(...), dia_pago: int = Form(...), id: int = Form(...)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    supabase.table("tarjetas").update({"nombre_tarjeta": nombre_tarjeta, "dia_corte": dia_corte, "dia_pago": dia_pago}).eq("id", id).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/tarjetas/eliminar/{nombre}")
async def e_tarjeta(request: Request, nombre: str):
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    supabase.table("movimientos").delete().eq("tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    supabase.table("tarjetas").delete().eq("nombre_tarjeta", nombre).eq("usuario_id", user["id"]).execute()
    return RedirectResponse("/", status_code=303)

@app.get("/movimientos/nuevo/{tarjeta}", response_class=HTMLResponse)
async def n_mov(request: Request, tarjeta: str, success: bool = False): # Añade success aquí
    user = request.session.get("user")
    if not user: return RedirectResponse("/login")
    res = supabase.table("movimientos").select("*").eq("tarjeta", tarjeta).eq("usuario_id", user["id"]).order("id", desc=True).limit(5).execute()
    
    return templates.TemplateResponse("registrar_movimiento.html", {
        "request": request, 
        "nombre_tarjeta": tarjeta, 
        "movimientos": res.data, 
        "css": DARK_CSS,
        "success": success # Lo pasamos al HTML
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
    
    # Añadimos '?success=true' a la URL para que el HTML sepa que acabamos de guardar
    return RedirectResponse(f"/movimientos/nuevo/{tarjeta_nombre}?success=true", status_code=303)
