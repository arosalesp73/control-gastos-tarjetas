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

# --- GENERACIÓN DE REPORTES FILTRADOS ---

@app.get("/reportes", response_class=HTMLResponse)
async def configurar_reporte_ui(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")
    
    # Traemos las tarjetas del usuario para el selector
    tarjetas = supabase.table("tarjetas").select("nombre_tarjeta").eq("usuario_id", user["id"]).execute().data
    
    template = templates.get_template("reportes.html")
    return HTMLResponse(content=template.render({"request": request, "tarjetas": tarjetas, "css": DARK_CSS}))

@app.get("/reportes/generar")
async def generar_reporte_excel(
    request: Request,
    tarjeta: str,
    fecha_inicio: str,
    fecha_fin: str
):
    user = request.session.get("user")
    if not user: return RedirectResponse(url="/login")

    try:
        query = supabase.table("movimientos").select("*")\
            .eq("usuario_id", user["id"])\
            .gte("fecha", fecha_inicio)\
            .lte("fecha", fecha_fin)

        if tarjeta != "TODAS":
            query = query.eq("tarjeta", tarjeta)

        res = query.order("id", desc=True).execute()

        if not res.data:
            return HTMLResponse("No hay movimientos en este rango de fechas.")

        df = pd.DataFrame(res.data)
        df = df[['fecha', 'tarjeta', 'concepto', 'tipo', 'monto']]
        df.columns = ['Fecha', 'Tarjeta', 'Concepto', 'Tipo', 'Monto']

        output = io.BytesIO()
        # Creamos el Excel con un formato más avanzado
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Reporte')
            
            workbook = writer.book
            worksheet = writer.sheets['Reporte']

            # 1. Definimos el formato de moneda ($#,##0.00)
            formato_moneda = '$#,##0.00'
            
            # 2. Aplicar formato a la columna E (Monto) y ajustar anchos
            # Las columnas en Excel son: A(Fecha), B(Tarjeta), C(Concepto), D(Tipo), E(Monto)
            for row in range(2, len(df) + 2):  # Empezamos en la fila 2 por el encabezado
                celda_monto = worksheet.cell(row=row, column=5)
                celda_monto.number_format = formato_moneda

            # 3. Ajustar automáticamente el ancho de las columnas para que no se corten
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value) or "") for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = length + 5

        output.seek(0)

        tag_tarjeta = tarjeta.replace(" ", "_") if tarjeta != "TODAS" else "GENERAL"
        nombre_final = f"Reporte_{tag_tarjeta}_{fecha_inicio}_al_{fecha_fin}.xlsx"

        return StreamingResponse(
            output,
            headers={'Content-Disposition': f'attachment; filename="{nombre_final}"'},
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        print(f"Error en reporte: {e}")
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)
