import io
import time
import threading
import json
import os
from flask import Flask, jsonify, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
import requests

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE GREEN API (WHATSAPP)
# ==========================================
ID_INSTANCE = "710722782905"
API_TOKEN_INSTANCE = "085f2d211be547b9a9377b0021c03faf845beb16436644748b"

def formatear_telefono(telefono):
    """Limpia y formatea el número para WhatsApp a prueba de fallos (Ej: Paraguay 595...)"""
    tel_limpio = "".join(filter(str.isdigit, str(telefono)))
    if len(tel_limpio) == 10 and tel_limpio.startswith("0"):
        tel_limpio = "595" + tel_limpio[1:]
    elif len(tel_limpio) == 9 and tel_limpio.startswith("9"):
        tel_limpio = "595" + tel_limpio
    return tel_limpio

def enviar_mensaje_whatsapp(telefono, texto):
    def tarea():
        tel_formateado = formatear_telefono(telefono)
        url = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
        payload = {"chatId": f"{tel_formateado}@c.us", "message": texto}
        try:
            res = requests.post(url, json=payload)
            print(f"📤 Respuesta sendMessage: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Error enviando mensaje Green API: {e}")
    threading.Thread(target=tarea).start()

def enviar_imagen_whatsapp(telefono, url_imagen, caption):
    def tarea():
        tel_formateado = formatear_telefono(telefono)
        url = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendFileByUrl/{API_TOKEN_INSTANCE}"
        url_imagen_segura = url_imagen.replace("http://", "https://")
        payload = {
            "chatId": f"{tel_formateado}@c.us",
            "urlFile": url_imagen_segura,
            "fileName": "ticket_vifran.png",
            "caption": caption,
        }
        try:
            res = requests.post(url, json=payload)
            print(f"📤 Respuesta sendFileByUrl: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Error enviando imagen Green API: {e}")
    threading.Thread(target=tarea).start()

def enviar_ticket_directo(telefono, boleto_id, host_url, caption):
    def tarea():
        tel_formateado = formatear_telefono(telefono)
        
        url_txt = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
        try:
            requests.post(url_txt, json={"chatId": f"{tel_formateado}@c.us", "message": "✅ *¡Pago verificado!* Generando tu boleto oficial con QR..."})
        except Exception as e:
            print(f"❌ Error enviando aviso previo: {e}")
        
        output = crear_imagen_boleto_memoria(boleto_id, host_url)
        if not output:
            print("❌ Error: No se pudo generar la imagen del ticket en memoria.")
            return
        
        url_up = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendFileByUpload/{API_TOKEN_INSTANCE}"
        payload = {'chatId': f"{tel_formateado}@c.us", 'caption': caption}
        files = [('file', (f'ticket_{boleto_id}.png', output.getvalue(), 'image/png'))]
        
        try:
            res = requests.post(url_up, data=payload, files=files)
            print(f"📤 Respuesta sendFileByUpload (Ticket): {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Error subiendo ticket directamente: {e}")
            
    threading.Thread(target=tarea).start()


# ==========================================
# BASE DE DATOS Y PERSISTENCIA EN DISCO
# ==========================================
ARCHIVO_DATOS = "datos_vifran.json"

sorteos_db = [{
    "id": 1,
    "titulo": "Sorteo de 4 iPhones (15 Pro Max, 14 Pro Max, 13 Pro Max y 11)",
    "precio": 10000,
    "limite_boletos": 1000,
    "estado": "Activo",
    "imagen_nombre": "flyer_sorteo.jpg",
}]

boletos_db = []
clientes_db = {}  # {telefono: {"nombre": ..., "cedula": ...}}
contador_boletos_por_sorteo = {1: 1}
lote_contador = 1

lotes_pendientes = {}    
numeros_liberados = {}  

SESIONES_WHATSAPP = {}

ADMIN_USERS = {
    "patriciafranco": "Vifran2026*Secure$",
    "edgarfranco": "Vifran2026*Secure$",
}

def guardar_datos_disco():
    datos = {
        "sorteos": sorteos_db,
        "boletos": boletos_db,
        "clientes": clientes_db,
        "contador_boletos": contador_boletos_por_sorteo,
        "lote_contador": lote_contador,
        "numeros_liberados": numeros_liberados
    }
    try:
        with open(ARCHIVO_DATOS, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ Error guardando en disco: {e}")

def cargar_datos_disco():
    global sorteos_db, boletos_db, clientes_db, contador_boletos_por_sorteo, lote_contador, numeros_liberados
    if os.path.exists(ARCHIVO_DATOS):
        try:
            with open(ARCHIVO_DATOS, "r", encoding="utf-8") as f:
                datos = json.load(f)
                sorteos_db = datos.get("sorteos", sorteos_db)
                boletos_db = datos.get("boletos", boletos_db)
                clientes_db = datos.get("clientes", {})
                contador_boletos_por_sorteo = {int(k): v for k, v in datos.get("contador_boletos", {1: 1}).items()}
                lote_contador = datos.get("lote_contador", 1)
                numeros_liberados = {int(k): v for k, v in datos.get("numeros_liberados", {})}
                print("✅ Datos cargados exitosamente desde el disco.")
        except Exception as e:
            print(f"❌ Error leyendo datos del disco: {e}")

cargar_datos_disco()


# ==========================================
# CRONJOB LIGERO (RECUPERACIÓN Y EXPIRACIÓN)
# ==========================================
def revisar_lotes_pendientes():
    global boletos_db
    while True:
        time.sleep(60) 
        ahora = time.time()
        lotes_a_eliminar = []

        for lote_id, info in list(lotes_pendientes.items()):
            tiempo_transcurrido = ahora - info['tiempo_reserva']
            
            if tiempo_transcurrido >= 900 and not info['recordatorio_enviado']:
                mensaje = "⏳ ¡Hola! Notamos que tus números siguen reservados pero aún no recibimos tu comprobante.\n\n¿Tuviste algún problema con la transferencia ueno? Si necesitas ayuda o más tiempo, ¡solo respóndenos este mensaje! 🍀"
                enviar_mensaje_whatsapp(info['telefono'], mensaje)
                lotes_pendientes[lote_id]['recordatorio_enviado'] = True
            
            if tiempo_transcurrido >= 7200:
                mensaje = "❌ Tu reserva ha expirado por falta de pago y tus números han sido liberados para otros clientes.\n\nSi aún deseas participar, vuelve a enviar 'hola' para iniciar un nuevo proceso. ¡Te esperamos! ✨"
                enviar_mensaje_whatsapp(info['telefono'], mensaje)
                lotes_a_eliminar.append(lote_id)

        if lotes_a_eliminar:
            for lote_id in lotes_a_eliminar:
                boletos_a_borrar = [b for b in boletos_db if b['lote_id'] == lote_id]
                for b in boletos_a_borrar:
                    s_id = b['sorteo_id']
                    if s_id not in numeros_liberados:
                        numeros_liberados[s_id] = []
                    numeros_liberados[s_id].append(b['id'])
                boletos_db = [b for b in boletos_db if b['lote_id'] != lote_id]
                del lotes_pendientes[lote_id]
            guardar_datos_disco()

hilo_revision = threading.Thread(target=revisar_lotes_pendientes, daemon=True)
hilo_revision.start()


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/admin")
def admin_panel():
    return render_template("admin.html")


# ==========================================
# RUTAS DE COMPRA PÚBLICA (WEB Y CONSULTA)
# ==========================================
@app.route("/api/sorteos", methods=["GET"])
def obtener_sorteos():
    activos = [s for s in sorteos_db if s["estado"] == "Activo"]
    return jsonify({"sorteos": activos})


# Candado de seguridad para asignación concurrente limpia
bloqueo_compra = threading.Lock()

@app.route("/api/comprar", methods=["POST"])
def comprar():
    global lote_contador
    data = request.json
    
    sorteo_id = int(data.get("sorteo_id", 1))
    nombre = data.get("nombre")
    telefono = data.get("telefono")
    cedula = data.get("cedula")
    cantidad = int(data.get("cantidad", 1))
    
    metodo_pago = data.get("metodo_pago", "Transferencia Directa")
    detalle_pago = data.get("detalle_pago", "")
    imagen_comprobante = data.get("imagen_comprobante", "")

    if not nombre or not telefono or not cedula or cantidad < 1:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400

    with bloqueo_compra:
        clientes_db[telefono] = {"nombre": nombre, "cedula": cedula}

        sorteo_activo = next((s for s in sorteos_db if s["id"] == sorteo_id and s["estado"] == "Activo"), None)
        if not sorteo_activo:
            return jsonify({"error": "El sorteo seleccionado ya no está activo."}), 400

        total_activos = len([b for b in boletos_db if b["sorteo_id"] == sorteo_id])
        if (total_activos + cantidad) > sorteo_activo["limite_boletos"]:
            return jsonify({"error": "No hay suficientes boletos disponibles para esa cantidad."}), 400

        current_lote = lote_contador
        lote_contador += 1

        nuevos_boletos_ids = []
        if sorteo_id not in numeros_liberados:
            numeros_liberados[sorteo_id] = []

        for _ in range(cantidad):
            if numeros_liberados[sorteo_id]:
                numeros_liberados[sorteo_id].sort()
                num_boleto = numeros_liberados[sorteo_id].pop(0)
            else:
                num_boleto = contador_boletos_por_sorteo.get(sorteo_id, 1)
                contador_boletos_por_sorteo[sorteo_id] = num_boleto + 1
            nuevos_boletos_ids.append(num_boleto)

        for num_boleto in nuevos_boletos_ids:
            nuevo_boleto = {
                "id": num_boleto,
                "sorteo_id": sorteo_id,
                "lote_id": current_lote,
                "nombre": nombre,
                "telefono": telefono,
                "cedula": cedula,
                "cantidad_lote": cantidad,
                "imagen_comprobante": imagen_comprobante,
                "metodo_pago": metodo_pago,
                "detalle_pago": detalle_pago,
                "estado": "Pendiente",
                "impreso": False,
            }
            boletos_db.append(nuevo_boleto)

        lotes_pendientes[current_lote] = {
            "telefono": telefono,
            "tiempo_reserva": time.time(),
            "recordatorio_enviado": False
        }

        guardar_datos_disco()

    rango_str = (
        f"#{str(nuevos_boletos_ids[0]).zfill(5)}"
        if len(nuevos_boletos_ids) == 1
        else f"#{str(nuevos_boletos_ids[0]).zfill(5)} al #{str(nuevos_boletos_ids[-1]).zfill(5)}"
    )

    return jsonify({
        "mensaje": f"¡Compra de {cantidad} boleto(s) registrada!",
        "rango": rango_str,
        "lote_id": current_lote,
        "boleto": {"id": nuevos_boletos_ids[0]}
    }), 200


@app.route("/api/consultar", methods=["POST"])
def consultar():
    data = request.json
    termino = data.get("termino")
    resultados = [b for b in boletos_db if b["telefono"] == termino or b["cedula"] == termino]
    
    if not resultados:
        return jsonify({"encontrado": False, "mensaje": "No se encontraron boletos."}), 404

    for b in resultados:
        s = next((item for item in sorteos_db if item["id"] == b["sorteo_id"]), None)
        b["sorteo_titulo"] = s["titulo"] if s else "Sorteo General"

    return jsonify({"encontrado": True, "boletos": resultados}), 200


# ==========================================
# WEBHOOK DEL BOT DE WHATSAPP (GREEN API)
# ==========================================
@app.route("/api/webhook/whatsapp", methods=["POST"])
def webhook_whatsapp():
    datos = request.json
    if not datos:
        return jsonify({"status": "ignored"}), 200

    try:
        senderData = datos.get("senderData", {})
        messageData = datos.get("messageData", {})
        chat_id = senderData.get("chatId", "")
        if not chat_id and "chatData" in datos:
            chat_id = datos.get("chatData", {}).get("chatId", "")

        telefono = chat_id.split("@")[0] if "@" in chat_id else str(chat_id)
        tipo_mensaje = messageData.get("typeMessage", "")
        es_imagen = (
            "fileMessageData" in messageData or "imageMessageData" in messageData
            or "jpeg" in tipo_mensaje.lower() or "image" in tipo_mensaje.lower()
        )

        mensaje = ""
        if "textMessageData" in messageData:
            mensaje = messageData["textMessageData"].get("textMessage", "")
        elif "extendedTextMessageData" in messageData:
            mensaje = messageData["extendedTextMessageData"].get("text", "")

        if telefono and not mensaje and not es_imagen:
            mensaje = "hola"
        if not telefono:
            return jsonify({"status": "ok"}), 200

        mensaje_lower = mensaje.lower().strip()

        if telefono not in SESIONES_WHATSAPP:
            SESIONES_WHATSAPP[telefono] = {"paso": "INICIO", "datos": {}}

        sesion = SESIONES_WHATSAPP[telefono]
        paso = sesion["paso"]

        if "hola" in mensaje_lower or paso == "INICIO":
            sesion["paso"] = "ESPERANDO_CANTIDAD"
            sorteo = sorteos_db[0]
            url_flyer = request.host_url.rstrip("/").replace("http://", "https://") + url_for("static", filename="flyer_sorteo.jpg")
            caption = (
                f"¡Hola! Bienvenido a *VIFRAN GROUP S.A.* 🍀\nTu suerte, nuestro compromiso.\n\n"
                f"🏆 *Sorteo:* {sorteo['titulo']}\n💵 *Valor del ticket:* Gs. {sorteo['precio']:,}\n\n"
                "¿Cuántos boletos te gustaría reservar?\n*(Responde únicamente con el número, ej: '2')*"
            )
            enviar_imagen_whatsapp(telefono, url_flyer, caption)

        elif paso == "ESPERANDO_CANTIDAD" and mensaje.isdigit():
            cantidad = int(mensaje)
            sorteo = sorteos_db[0]
            
            total_activos = len([b for b in boletos_db if b["sorteo_id"] == sorteo["id"]])
            if (total_activos + cantidad) > sorteo["limite_boletos"]:
                enviar_mensaje_whatsapp(telefono, "❌ Lo sentimos, no hay suficientes boletos disponibles para esa cantidad.")
                sesion["paso"] = "INICIO"
                return jsonify({"status": "ok"}), 200

            sesion["datos"]["cantidad"] = cantidad
            total = cantidad * sorteo["precio"]

            sesion["paso"] = "ESPERANDO_DATOS_CLIENTE"
            enviar_mensaje_whatsapp(
                telefono,
                f"🎟️ *Cantidad seleccionada:* {cantidad} boleto(s)\nTotal a pagar: *{total:,} Gs.*\n\n"
                "📂 *Datos para el pago (ueno):*\n🔸 *RUC / Alias:* 4775796-5\n🔸 *Titular:* Patricia Franco\n\n"
                "📝 Por favor, escribe tu *Nombre completo* y tu *Cédula/RUC* (Ej: Juan Pérez 1234567)."
            )

        elif paso == "ESPERANDO_DATOS_CLIENTE" and ("," in mensaje or " " in mensaje):
            if "," in mensaje:
                partes = mensaje.split(",")
            else:
                partes = mensaje.rsplit(" ", 1)

            nombre_cliente = partes[0].strip()
            cedula_cliente = partes[1].strip()

            sesion["datos"]["nombre"] = nombre_cliente
            sesion["datos"]["cedula"] = cedula_cliente

            with bloqueo_compra:
                clientes_db[telefono] = {"nombre": nombre_cliente, "cedula": cedula_cliente}

                sorteo = sorteos_db[0]
                cantidad = sesion["datos"]["cantidad"]

                global lote_contador
                current_lote = lote_contador
                lote_contador += 1

                nuevos_boletos_ids = []
                if sorteo["id"] not in numeros_liberados:
                    numeros_liberados[sorteo["id"]] = []

                for _ in range(cantidad):
                    if numeros_liberados[sorteo["id"]]:
                        numeros_liberados[sorteo["id"]].sort()
                        num_boleto = numeros_liberados[sorteo["id"]].pop(0)
                    else:
                        num_boleto = contador_boletos_por_sorteo.get(sorteo["id"], 1)
                        contador_boletos_por_sorteo[sorteo["id"]] = num_boleto + 1
                    nuevos_boletos_ids.append(num_boleto)

                numeros_str = []
                for num_boleto in nuevos_boletos_ids:
                    nuevo_boleto = {
                        "id": num_boleto,
                        "sorteo_id": sorteo["id"],
                        "lote_id": current_lote,
                        "nombre": nombre_cliente,
                        "telefono": telefono,
                        "cedula": cedula_cliente,
                        "cantidad_lote": cantidad,
                        "imagen_comprobante": "",
                        "metodo_pago": "WhatsApp / ueno",
                        "detalle_pago": "Transferencia Directa",
                        "estado": "Pendiente",
                        "impreso": False,
                    }
                    boletos_db.append(nuevo_boleto)
                    numeros_str.append(str(num_boleto).zfill(5))

                sesion["datos"]["lote_id"] = current_lote
                sesion["datos"]["numeros"] = numeros_str

                lotes_pendientes[current_lote] = {
                    "telefono": telefono,
                    "tiempo_reserva": time.time(),
                    "recordatorio_enviado": False
                }

                guardar_datos_disco()

            sesion["paso"] = "ESPERANDO_COMPROBANTE"
            enviar_mensaje_whatsapp(
                telefono,
                f"✅ Datos guardados:\n👤 *Nombre:* {nombre_cliente}\n🆔 *CI/RUC:* {cedula_cliente}\n🎟️ *Tus números:* {', '.join(numeros_str)}\n\n"
                "📸 Ahora, por favor **enviá la foto del comprobante de pago** para finalizar."
            )

        elif paso == "ESPERANDO_COMPROBANTE" and es_imagen:
            file_data = messageData.get("fileMessageData", {})
            download_url = file_data.get("downloadUrl", "")
            current_lote = sesion["datos"].get("lote_id")

            if current_lote:
                with bloqueo_compra:
                    for b in boletos_db:
                        if b["lote_id"] == current_lote:
                            b["imagen_comprobante"] = download_url
                    
                    if current_lote in lotes_pendientes:
                        del lotes_pendientes[current_lote]
                    
                    guardar_datos_disco()

            enviar_mensaje_whatsapp(
                telefono,
                "🔍 *¡Comprobante recibido con éxito!*\n\nUn administrador verificará tu pago y te enviará tu boleto con QR en breve. ¡Muchas gracias!"
            )
            sesion["paso"] = "INICIO"

    except Exception as e:
        print(f"❌ Error procesando webhook: {e}")

    return jsonify({"status": "ok"}), 200


# ==========================================
# GENERADOR DE IMAGEN DIGITAL DE TICKET CON QR
# ==========================================
def crear_imagen_boleto_memoria(boleto_id, host_url):
    boleto = next((b for b in boletos_db if b["id"] == boleto_id), None)
    if not boleto:
        return None

    sorteo_titulo = "Sorteo de 4 iPhones"
    for s in sorteos_db:
        if s["id"] == boleto["sorteo_id"]:
            sorteo_titulo = s["titulo"]
            break

    ancho, alto = 420, 580
    img = Image.new("RGB", (ancho, alto), color="white")
    d = ImageDraw.Draw(img)

    try:
        font_titulo = ImageFont.truetype("arial.ttf", 20)
        font_texto = ImageFont.truetype("arial.ttf", 14)
        font_grande = ImageFont.truetype("arial.ttf", 26)
    except:
        font_titulo = ImageFont.load_default()
        font_texto = ImageFont.load_default()
        font_grande = ImageFont.load_default()

    d.text((ancho / 2, 25), "VIFRAN GROUP S.A.", fill="black", anchor="mm", font=font_titulo)
    d.line([(20, 45), (ancho - 20, 45)], fill="black", width=2)
    d.text((20, 65), f"CLIENTE: {boleto['nombre'].upper()}", fill="black", font=font_texto)
    d.text((20, 90), f"RUC/CI: {boleto['cedula']} | TEL: {boleto['telefono']}", fill="black", font=font_texto)
    d.line([(20, 115), (ancho - 20, 115)], fill="black", width=1)
    d.text((20, 130), f"EDICION: {sorteo_titulo}", fill="black", font=font_texto)
    d.text((20, 155), f"PAGO: {boleto.get('metodo_pago', 'Directo')}", fill="black", font=font_texto)
    d.line([(20, 180), (ancho - 20, 180)], fill="black", width=1)
    d.text((ancho / 2, 210), f"NRO: #{str(boleto['id']).zfill(5)}", fill="black", anchor="mm", font=font_grande)
    d.line([(20, 240), (ancho - 20, 240)], fill="black", width=1)

    url_segura = host_url.rstrip('/').replace("http://", "https://")
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={url_segura}/validar/{boleto['id']}"
    
    try:
        res_qr = requests.get(qr_url)
        if res_qr.status_code == 200:
            qr_img = Image.open(io.BytesIO(res_qr.content)).resize((150, 150))
            img.paste(qr_img, (int((ancho - 150) / 2), 255))
    except Exception:
        pass

    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output

@app.route("/api/ticket-imagen/<int:boleto_id>")
def obtener_ticket_imagen(boleto_id):
    output = crear_imagen_boleto_memoria(boleto_id, request.host_url)
    if not output: return "Boleto no encontrado", 404
    return send_file(output, mimetype="image/png")


# ==========================================
# RUTA PÚBLICA DE VALIDACIÓN DE QR
# ==========================================
@app.route("/validar/<int:boleto_id>")
def validar_boleto_qr(boleto_id):
    boleto = next((b for b in boletos_db if b["id"] == boleto_id), None)
    if not boleto:
        return "<h3>Boleto no encontrado</h3>", 404

    sorteo = next((s for s in sorteos_db if s["id"] == boleto["sorteo_id"]), {"titulo": "Sorteo General", "precio": 10000})
    estado_color = "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" if boleto["estado"] == "Aprobado" else "text-amber-400 bg-amber-500/10 border-amber-500/30"

    return f"""
        <!DOCTYPE html>
        <html lang="es">
        <head><meta charset="UTF-8"><title>Validación de Boleto</title><script src="https://cdn.tailwindcss.com"></script></head>
        <body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4 font-sans">
            <div class="bg-slate-800 p-8 rounded-2xl shadow-2xl border border-slate-700 max-w-md w-full space-y-6">
                <div class="text-center space-y-1 border-b border-slate-700 pb-4">
                    <h1 class="text-xl font-black text-amber-400">VIFRAN GROUP S.A.</h1>
                    <p class="text-xs text-slate-400 uppercase tracking-widest">Certificado Oficial</p>
                </div>
                <div class="space-y-3 text-sm">
                    <div class="bg-slate-900 p-4 rounded-xl border border-slate-700 text-center">
                        <span class="text-xs text-slate-400 block">NÚMERO DE BOLETO</span>
                        <span class="text-3xl font-black text-amber-400">#{str(boleto['id']).zfill(5)}</span>
                    </div>
                    <div><p class="text-xs text-slate-400">Sorteo:</p><p class="font-bold text-white">{sorteo['titulo']}</p></div>
                    <div><p class="text-xs text-slate-400">Comprador:</p><p class="font-bold text-white">{boleto['nombre']}</p></div>
                </div>
                <div class="text-center pt-2">
                    <span class="inline-block px-4 py-1.5 rounded-xl text-xs font-bold border {estado_color}">Estado: {boleto['estado']}</span>
                </div>
            </div>
        </body>
        </html>
    """


# ==========================================
# API DE ADMINISTRACIÓN
# ==========================================
def verificar_admin(data):
    if data.get("usuario") in ADMIN_USERS and ADMIN_USERS[data.get("usuario")] == data.get("password"): 
        return True
    return False

@app.route("/api/admin/datos", methods=["POST"])
def admin_datos():
    if not verificar_admin(request.json): return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    return jsonify({
        "sorteos": sorteos_db, 
        "boletos": boletos_db,
        "total_clientes": len(clientes_db)
    })

@app.route("/api/admin/crear-sorteo", methods=["POST"])
def admin_crear_sorteo():
    data = request.json
    if not verificar_admin(data): return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    if not data.get("titulo"): return jsonify({"error": "El título es obligatorio"}), 400
    
    with bloqueo_compra:
        nuevo_id = len(sorteos_db) + 1
        nuevo_sorteo = {
            "id": nuevo_id, 
            "titulo": data.get("titulo"), 
            "precio": int(data.get("precio", 10000)), 
            "limite_boletos": int(data.get("limite_boletos", 1000)), 
            "estado": "Activo"
        }
        sorteos_db.append(nuevo_sorteo)
        contador_boletos_por_sorteo[nuevo_id] = 1
        guardar_datos_disco()
    return jsonify({"mensaje": "¡Sorteo creado con éxito!", "sorteo": nuevo_sorteo})

@app.route("/api/admin/finalizar-sorteo/<int:sorteo_id>", methods=["POST"])
def admin_finalizar_sorteo(sorteo_id):
    if not verificar_admin(request.json): return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    with bloqueo_compra:
        for s in sorteos_db:
            if s["id"] == sorteo_id:
                s["estado"] = "Finalizado"
                guardar_datos_disco()
                return jsonify({"mensaje": f"Sorteo '{s['titulo']}' finalizado con éxito."})
    return jsonify({"error": "Sorteo no encontrado"}), 404

@app.route("/api/admin/difundir-nuevo-sorteo", methods=["POST"])
def difundir_nuevo_sorteo():
    data = request.json
    if not verificar_admin(data): 
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    
    sorteo_id = data.get("sorteo_id")
    sorteo = next((s for s in sorteos_db if s["id"] == sorteo_id), None)
    if not sorteo:
        return jsonify({"error": "Sorteo no encontrado"}), 404

    mensaje_difusion = (
        f"🚨 *¡NUEVO SORTEO DISPONIBLE EN VIFRAN GROUP S.A.!* 🍀\n\n"
        f"🏆 *Premio:* {sorteo['titulo']}\n"
        f"💵 *Valor por boleto:* Gs. {sorteo['precio']:,}\n\n"
        f"¡Hola! Como ya participaste con nosotros anteriormente, te avisamos antes que nadie. Escríbenos 'hola' para reservar tus números de esta nueva edición. ¡Muchísima suerte! ✨"
    )

    enviados = 0
    for tel in clientes_db.keys():
        enviar_mensaje_whatsapp(tel, mensaje_difusion)
        enviados += 1

    return jsonify({"mensaje": f"¡Difusión enviada con éxito a {enviados} clientes registrados!"}), 200

@app.route("/api/admin/limpiar-pruebas", methods=["POST"])
def limpiar_pruebas():
    data = request.json
    if not verificar_admin(data): 
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    
    with bloqueo_compra:
        global boletos_db, contador_boletos_por_sorteo, lote_contador, numeros_liberados, lotes_pendientes
        boletos_db = []
        contador_boletos_por_sorteo = {s["id"]: 1 for s in sorteos_db}
        lote_contador = 1
        numeros_liberados = {}
        lotes_pendientes = {}
        
        if os.path.exists(ARCHIVO_DATOS):
            try:
                os.remove(ARCHIVO_DATOS)
            except Exception as e:
                print(f"❌ Error al borrar el archivo de datos: {e}")

    return jsonify({"mensaje": "¡Sistema limpiado con éxito! Todas las pruebas fueron eliminadas y los contadores volvieron a cero."}), 200

@app.route("/api/admin/aprobar-lote/<int:lote_id>", methods=["POST"])
def admin_aprobar_lote(lote_id):
    if not verificar_admin(request.json): return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    
    aprobados = 0
    host_actual = request.host_url
    
    with bloqueo_compra:
        for b in boletos_db:
            if b["lote_id"] == lote_id and b["estado"] == "Pendiente":
                b["estado"] = "Aprobado"
                b["impreso"] = False  
                aprobados += 1
                sorteo = next((s for s in sorteos_db if s["id"] == b["sorteo_id"]), sorteos_db[0])
                
                caption = f"✨ *¡Pago Verificado y Boleto Emitido!*\n\nCLIENTE: {b['nombre']}\nRUC/CI: {b['cedula']}\nEDICION: {sorteo['titulo']}\nA: Gs. {sorteo['precio']:,}\nNRO: #{str(b['id']).zfill(5)}\n\n🍀 *¡Muchísima suerte con VIFRAN GROUP S.A.!*"
                enviar_ticket_directo(b['telefono'], b['id'], host_actual, caption)

        if aprobados > 0: 
            guardar_datos_disco()
            return jsonify({"mensaje": f"¡Lote aprobado con éxito ({aprobados} boletos)!"})
    return jsonify({"error": "Lote no encontrado o ya aprobado"}), 404

@app.route("/api/pendientes-impresion", methods=["GET"])
def obtener_pendientes_impresion():
    pendientes, lotes_procesados = [], set()
    with bloqueo_compra:
        for b in boletos_db:
            if b["estado"] == "Aprobado" and not b.get("impreso", False) and b["lote_id"] not in lotes_procesados:
                lotes_procesados.add(b["lote_id"])
                sorteo = next((s for s in sorteos_db if s["id"] == b["sorteo_id"]), sorteos_db[0])
                pendientes.append({"id": b["lote_id"], "sorteo_titulo": sorteo["titulo"], "nombre": b["nombre"], "cedula": b["cedula"], "telefono": b["telefono"], "numeros_asignados": [str(x["id"]).zfill(5) for x in boletos_db if x["lote_id"] == b["lote_id"]]})
    return jsonify(pendientes), 200

@app.route("/api/marcar-impreso/<int:lote_id>", methods=["POST"])
def marcar_como_impreso(lote_id):
    with bloqueo_compra:
        for b in boletos_db:
            if b["lote_id"] == lote_id: b["impreso"] = True
        guardar_datos_disco()
    return jsonify({"status": "success"}), 200

@app.route("/api/reimprimir/<int:boleto_id>", methods=["POST"])
def api_reimprimir(boleto_id):
    data = request.json
    if not verificar_admin(data): 
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
    
    with bloqueo_compra:
        boleto = next((b for b in boletos_db if b["id"] == boleto_id), None)
        if not boleto:
            return jsonify({"error": "Boleto no encontrado"}), 404
        
        boleto["impreso"] = False
        guardar_datos_disco()
    return jsonify({"mensaje": f"Boleto #{boleto_id} reenviado a la impresora con éxito."}), 200

@app.route("/impresion")
def vista_impresion_web():
    return render_template("impresion.html")

if __name__ == "__main__":
    app.run(debug=True)
