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

DARK_CSS = ":root { --bg: #0e0e1a; --surface: #181828; --accent: #6c63ff; --text: #e0e0f0; } body { background: var(--bg); color: var(--text); font-family: sans-serif; margin: 0; padding: 20px; }"

# --- RUTAS DE NAVEGACIÓN PRINCIPAL ---

@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    try:
        user = request.session.get("user")
        if not user:
            return RedirectResponse(url="/login")

        # Traemos las tarjetas con las nuevas columnas
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
        print(f"Error en inicio: {e}")
        return HTMLResponse(content=f"Error de sistema: {str(e)}", status_code=500)

# --- SISTEMA DE AUTENTICACIÓN ---

@app.get("/login", response_class=HTMLResponse)
async def login_ui(request: Request, error: str = None):
    err = f'<p style="color:red">{error}</p>' if error else ""
    return f"<html><head><style>{DARK_CSS}</style></head><body><div class='card'><h2>Login</h2>{err}<form action='/login' method='post'><input name='username' placeholder='Usuario' required><br><input name='password' type='password' placeholder='Pass' required><br><button>Entrar</button></form></div></body></html>"

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    res = supabase.table("usuarios").select("*").eq("username", username).eq("password", password).execute()
    if res.data:
        request.session["user"] = res.data[0]
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/login?error=Error", status_code=303)

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
async def guardar_tarjeta(
    request: Request, 
    nombre_tarjeta: str = Form(...),
    dia_corte: int = Form(...),
    dia_pago: int = Form(...)
):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")

    try:
        supabase.table("tarjetas").insert({
            "nombre_tarjeta": nombre_tarjeta.strip(),
            "usuario_id": user["id"],
            "dia_corte": dia_corte,
            "dia_pago": dia_pago
        }).execute()
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        print(f"Error al guardar tarjeta: {e}")
        return HTMLResponse(content=f"Error al guardar tarjeta: {str(e)}", status_code=500)

@app.get("/tarjetas/eliminar/{nombre_tarjeta}")
async def eliminar_tarjeta(request: Request, nombre_tarjeta: str):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")

    try:
        # 1. Borramos los movimientos asociados a esa tarjeta y usuario
        supabase.table("movimientos")\
            .delete()\
            .eq("tarjeta", nombre_tarjeta)\
            .eq("usuario_id", user["id"])\
            .execute()

        # 2. Borramos la tarjeta
        supabase.table("tarjetas")\
            .delete()\
            .eq("nombre_tarjeta", nombre_tarjeta)\
            .eq("usuario_id", user["id"])\
            .execute()
        
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        print(f"Error al eliminar tarjeta: {e}")
        return HTMLResponse(content=f"Error al eliminar: {str(e)}", status_code=500)
        
# --- GESTIÓN DE MOVIMIENTOS (COMPRAS Y ABONOS) ---

@app.get("/movimientos/nuevo/{tarjeta_nombre}", response_class=HTMLResponse)
async def nuevo_movimiento(request: Request, tarjeta_nombre: str):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")

    try:
        # Cambiamos "fecha" por "id" para un orden de registro real (Pila)
        res = supabase.table("movimientos")\
            .select("*")\
            .eq("tarjeta", tarjeta_nombre)\
            .eq("usuario_id", user["id"])\
            .order("id", desc=True)\
            .limit(5)\
            .execute()
        
        movimientos = res.data
        
        template = templates.get_template("registrar_movimiento.html")
        return HTMLResponse(content=template.render({
            "request": request,
            "nombre_tarjeta": tarjeta_nombre,
            "movimientos": movimientos,
            "css": DARK_CSS
        }))
    except Exception as e:
        print(f"Error: {e}")
        return HTMLResponse(content=f"Error al cargar: {str(e)}", status_code=500)
        
@app.post("/movimientos/guardar")
async def guardar_movimiento(
    request: Request,
    tarjeta_nombre: str = Form(...),
    concepto: str = Form(...),
    monto: float = Form(...),
    tipo_movimiento: str = Form(...), 
    fecha: str = Form(...)
):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login", status_code=303)

    # El monto se guarda negativo si es un abono para facilitar cálculos
    monto_final = monto * -1 if tipo_movimiento == 'abono' else monto

    try:
        supabase.table("movimientos").insert({
            "tarjeta": tarjeta_nombre.strip(),
            "concepto": concepto,
            "monto": monto_final,
            "fecha": fecha,
            "usuario_id": user["id"],
            "tipo": tipo_movimiento
        }).execute()
        
        # Redirigimos a la misma pantalla para ver el registro actualizado
        return RedirectResponse(url=f"/movimientos/nuevo/{tarjeta_nombre}", status_code=303)
    except Exception as e:
        print(f"Error al guardar movimiento: {e}")
        return HTMLResponse(content=f"Error al registrar: {str(e)}", status_code=500)

@app.get("/movimientos/editar/{movimiento_id}", response_class=HTMLResponse)
async def editar_movimiento_ui(request: Request, movimiento_id: int):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    
    res = supabase.table("movimientos").select("*").eq("id", movimiento_id).eq("usuario_id", user["id"]).execute()
    if not res.data:
        return HTMLResponse("Movimiento no encontrado", status_code=404)
    
    movimiento = res.data[0]
    template = templates.get_template("editar_movimiento.html")
    return HTMLResponse(content=template.render({"request": request, "movimiento": movimiento, "css": DARK_CSS}))

@app.post("/movimientos/actualizar")
async def actualizar_movimiento(
    request: Request,
    id: int = Form(...),
    concepto: str = Form(...),
    monto: float = Form(...),
    fecha: str = Form(...),
    tarjeta: str = Form(...)
):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")

    try:
        supabase.table("movimientos").update({
            "concepto": concepto,
            "monto": monto,
            "fecha": fecha
        }).eq("id", id).eq("usuario_id", user["id"]).execute()
        
        return RedirectResponse(url=f"/movimientos/nuevo/{tarjeta}", status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"Error al actualizar: {str(e)}", status_code=500)

# --- ADMINISTRACIÓN DE USUARIOS ---

@app.get("/admin/usuarios", response_class=HTMLResponse)
async def gestionar_usuarios(request: Request):
    try:
        user = request.session.get("user")
        if not user or user.get("role") != 'admin':
            return RedirectResponse(url="/")

        todos_los_usuarios = supabase.table("usuarios").select("*").execute().data

        template = templates.get_template("usuarios.html")
        return HTMLResponse(content=template.render({
            "request": request,
            "user": user,
            "lista_usuarios": todos_los_usuarios,
            "css": DARK_CSS
        }))
    except Exception as e:
        return HTMLResponse(content=f"Error al cargar usuarios: {str(e)}", status_code=500)

@app.post("/admin/crear_usuario")
async def crear_usuario(
    request: Request,
    nuevo_username: str = Form(...),
    nuevo_password: str = Form(...),
    nuevo_role: str = Form(...)
):
    try:
        user = request.session.get("user")
        if not user or user.get("role") != 'admin':
            return RedirectResponse(url="/", status_code=303)

        supabase.table("usuarios").insert({
            "username": nuevo_username,
            "password": nuevo_password,
            "role": nuevo_role
        }).execute()

        return RedirectResponse(url="/admin/usuarios", status_code=303)
    except Exception as e:
        print(f"Error al crear usuario: {e}")
        return HTMLResponse(content=f"Error al crear usuario: {str(e)}", status_code=500)

# --- GENERACIÓN DE REPORTES ---

@app.get("/reportes")
async def descargar_reporte(request: Request):
    user = request.session.get("user")
    if not user: 
        return RedirectResponse(url="/login")

    try:
        # 1. Obtener todos los movimientos del usuario ordenados por fecha
        res = supabase.table("movimientos")\
            .select("*")\
            .eq("usuario_id", user["id"])\
            .order("fecha", desc=True)\
            .execute()
        
        if not res.data:
            return HTMLResponse("No hay movimientos registrados para generar el reporte.")

        # 2. Crear un DataFrame de Pandas con los datos
        df = pd.DataFrame(res.data)
        
        # 3. Limpiar y renombrar columnas para el usuario
        # Seleccionamos solo lo que nos sirve para el Excel
        columnas_interes = ['fecha', 'tarjeta', 'concepto', 'tipo', 'monto']
        df = df[columnas_interes]
        
        # Renombramos para que el Excel se vea profesional
        df.columns = ['Fecha', 'Tarjeta', 'Concepto', 'Tipo', 'Monto ($)']

        # 4. Generar el Excel en un "archivo virtual" en memoria
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Mis Movimientos')
        
        output.seek(0) # Regresamos al inicio del archivo virtual
        
        # 5. Configurar el nombre del archivo con la fecha de hoy
        fecha_str = datetime.now().strftime("%d-%m-%Y")
        nombre_archivo = f"Reporte_Gastos_{fecha_str}.xlsx"

        return StreamingResponse(
            output, 
            headers={'Content-Disposition': f'attachment; filename="{nombre_archivo}"'},
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        print(f"Error al generar reporte: {e}")
        return HTMLResponse(content=f"Error al generar Excel: {str(e)}", status_code=500)
