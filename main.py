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

@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request):
    try:
        user = request.session.get("user")
        if not user:
            return RedirectResponse(url="/login")

        # FILTRO DE PRIVACIDAD: Solo traemos las tarjetas que pertenecen al usuario logueado
        tarjetas = supabase.table("tarjetas")\
            .select("*")\
            .eq("usuario_id", user["id"])\
            .execute().data
        
        template = templates.get_template("index.html")
        content = template.render({
            "request": request,
            "user": user,
            "tarjetas": tarjetas if tarjetas else [],
            "css": DARK_CSS
        })
        return HTMLResponse(content=content)
    except Exception as e:
        print(f"Error en inicio: {e}")
        return HTMLResponse(content=f"Error de sistema: {str(e)}", status_code=500)

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

@app.post("/agregar")
async def agregar_gasto(
    request: Request, 
    concepto: str = Form(...), 
    monto: float = Form(...), 
    tarjeta_id: str = Form(...) # Este valor vendrá del <select>
):
    try:
        user = request.session.get("user")
        if not user: return RedirectResponse("/login")

        nuevo_movimiento = {
            "usuario_id": user["id"],
            "concepto": concepto,
            "monto": monto,
            "tarjeta": tarjeta_id, # En tu tabla es la columna 'tarjeta' (text)
            "tipo": "gasto",       # Agregamos el tipo que pide tu tabla
            "fecha": datetime.now().date().isoformat() # Solo la fecha como pide tu campo 'date'
        }
        
        supabase.table("movimientos").insert(nuevo_movimiento).execute()
        return RedirectResponse(url="/", status_code=303)
        
    except Exception as e:
        print(f"Error: {e}")
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)
        
@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")

@app.get("/admin/usuarios", response_class=HTMLResponse)
async def gestionar_usuarios(request: Request):
    try:
        user = request.session.get("user")
        # Seguridad: Si no es admin, lo mandamos al inicio
        if not user or user.get("role") != 'admin':
            return RedirectResponse(url="/")

        # Traemos a todos los usuarios de la base de datos
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

        # Insertamos el nuevo usuario sin la columna email
        supabase.table("usuarios").insert({
            "username": nuevo_username,
            "password": nuevo_password,
            "role": nuevo_role
        }).execute()

        return RedirectResponse(url="/admin/usuarios", status_code=303)
    except Exception as e:
        print(f"Error al crear usuario: {e}")
        return HTMLResponse(content=f"Error al crear usuario: {str(e)}", status_code=500)

# 1. Ruta para ver el formulario de nueva tarjeta
@app.get("/tarjetas/nueva", response_class=HTMLResponse)
async def formulario_tarjeta(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")
    
    template = templates.get_template("nueva_tarjeta.html")
    return HTMLResponse(content=template.render({"request": request, "user": user, "css": DARK_CSS}))

# 2. Ruta para procesar el guardado de la tarjeta
@app.post("/tarjetas/guardar")
async def guardar_tarjeta(request: Request, nombre_tarjeta: str = Form(...)):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login")

    try:
        # Guardamos la tarjeta ligada al ID del usuario actual
        supabase.table("tarjetas").insert({
            "nombre_tarjeta": nombre_tarjeta,
            "usuario_id": user["id"]
        }).execute()
        
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"Error al guardar tarjeta: {str(e)}", status_code=500)

@app.post("/gastos/guardar")
async def guardar_gasto(
    request: Request,
    tarjeta_id: int = Form(...),
    concepto: str = Form(...),
    monto: float = Form(...),
    fecha: str = Form(...)
):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    try:
        # Insertamos el gasto en la tabla 'gastos'
        supabase.table("gastos").insert({
            "tarjeta_id": tarjeta_id,
            "concepto": concepto,
            "monto": monto,
            "fecha": fecha,
            "usuario_id": user["id"]
        }).execute()
        
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        print(f"Error al guardar gasto: {e}")
        return HTMLResponse(content=f"Error al registrar gasto: {str(e)}", status_code=500)
