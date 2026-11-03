import sqlite3
import os
import io
import time
import threading
import json
from flask import Flask, jsonify, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
import requests
import shutil

app = Flask(__name__)

ID_INSTANCE = "710722782905"
API_TOKEN_INSTANCE = "085f2d211be547b9a9377b0021c03faf845beb16436644748b"

def formatear_telefono(telefono):
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
            requests.post(url, json=payload)
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
            requests.post(url, json=payload)
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
        if not output: return
        
        url_up = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendFileByUpload/{API_TOKEN_INSTANCE}"
        payload = {'chatId': f"{tel_formateado}@c.us", 'caption': caption}
        files = [('file', (f'ticket_{boleto_id}.png', output.getvalue(), 'image/png'))]
        
        try:
            requests.post(url_up, data=payload, files=files)
        except Exception as e:
            print(f"❌ Error subiendo ticket directamente: {e}")
            
    threading.Thread(target=tarea).start()

CARPETA_DISCO = "/varidata"
CARPETA_LOCAL = "."

if os.path.exists(CARPETA_DISCO):
    CARPETA_DATOS = CARPETA_DISCO
else:
    CARPETA_DATOS = CARPETA_LOCAL
    try:
        os.makedirs(CARPETA_DISCO, exist_ok=True)
        if os.path.exists(CARPETA_DISCO):
            CARPETA_DATOS = CARPETA_DISCO
    except:
        pass

DB_PATH = os.path.join(CARPETA_DATOS, "sorteos.db")
BACKUP_PATH = os.path.join(CARPETA_LOCAL, "sorteos_respaldo.db")

print(f"📂 [VIFRAN DB] Ruta principal: {os.path.abspath(DB_PATH)}")

def respaldar_base_datos():
    try:
        if os.path.exists(DB_PATH) and DB_PATH != BACKUP_PATH:
            shutil.copy2(DB_PATH, BACKUP_PATH)
    except Exception as e:
        print(f"⚠️ Error al respaldar DB: {e}")

def get_db():
    if not os.path.exists(DB_PATH) and os.path.exists(BACKUP_PATH):
        try:
            shutil.copy2(BACKUP_PATH, DB_PATH)
            print("🔄 [VIFRAN DB] Base de datos recuperada desde el respaldo espejo.")
        except:
            pass
            
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    if not os.path.exists(DB_PATH) and os.path.exists(BACKUP_PATH):
        try:
            shutil.copy2(BACKUP_PATH, DB_PATH)
        except:
            pass

    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sorteos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            precio INTEGER NOT NULL,
            limite_boletos INTEGER NOT NULL,
            estado TEXT NOT NULL,
            imagen_nombre TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boletos (
            id INTEGER,
            sorteo_id INTEGER,
            lote_id INTEGER,
            nombre TEXT,
            telefono TEXT,
            cedula TEXT,
            cantidad_lote INTEGER,
            imagen_comprobante TEXT,
            metodo_pago TEXT,
            detalle_pago TEXT,
            estado TEXT,
            impreso INTEGER,
            PRIMARY KEY (id, sorteo_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            telefono TEXT PRIMARY KEY,
            nombre TEXT,
            cedula TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config (
            clave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS numeros_liberados (
            sorteo_id INTEGER,
            numero INTEGER,
            PRIMARY KEY (sorteo_id, numero)
        )
    ''')
    
    conn.commit()
    
    cursor.execute('SELECT COUNT(*) FROM sorteos')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO sorteos (id, titulo, precio, limite_boletos, estado, imagen_nombre)
            VALUES (1, 'Sorteo de 4 iPhones (15 Pro Max, 14 Pro Max, 13 Pro Max y 11)', 10000, 2000, 'Activo', 'flyer_sorteo.jpg')
        ''')
    else:
        cursor.execute("UPDATE sorteos SET limite_boletos = 2000 WHERE id = 1")
    
    conn.commit()
        
    cursor.execute("SELECT valor FROM config WHERE clave = 'contador_1'")
    if not cursor.fetchone():
        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('contador_1', '187')")
        conn.commit()

    cursor.execute("SELECT valor FROM config WHERE clave = 'lote_contador'")
    if not cursor.fetchone():
        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('lote_contador', '1')")
        conn.commit()
        
    conn.close()
    respaldar_base_datos()

init_db()

ADMIN_USERS = {
    "patriciafranco": "Vifran2026*Secure$",
    "edgarfranco": "Vifran2026*Secure$",
}

bloqueo_compra = threading.Lock()
SESIONES_WHATSAPP = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/admin")
def admin_panel():
    return render_template("admin.html")

@app.route("/api/sorteos", methods=["GET"])
def obtener_sorteos():
    conn = get_db()
    sorteos = conn.execute("SELECT * FROM sorteos WHERE estado = 'Activo'").fetchall()
    conn.close()
    return jsonify({"sorteos": [dict(s) for s in sorteos]})

@app.route("/api/comprar", methods=["POST"])
def comprar():
    data = request.json
    sorteo_id = int(data.get("sorteo_id", 1))
    nombre = data.get("nombre")
    telefono = data.get("telefono")
    cedula = data.get("cedula")
    cantidad = int(data.get("cantidad", 1))
    metodo_pago = data.get("metodo_pago", "Transferencia Directa")
    detalle_pago = data.get("detalle_pago", "")

    if not nombre or not telefono or not cedula or cantidad < 1:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400

    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO clientes (telefono, nombre, cedula) VALUES (?, ?, ?)", (telefono, nombre, cedula))
        sorteo = cursor.execute("SELECT * FROM sorteos WHERE id = ? AND estado = 'Activo'", (sorteo_id,)).fetchone()
        if not sorteo:
            conn.close()
            return jsonify({"error": "El sorteo seleccionado ya no está activo."}), 400

        total_activos = cursor.execute("SELECT COUNT(*) FROM boletos WHERE sorteo_id = ?", (sorteo_id,)).fetchone()[0]
        if (total_activos + cantidad) > sorteo["limite_boletos"]:
            conn.close()
            return jsonify({"error": "No hay suficientes boletos disponibles para esa cantidad."}), 400

        lote_row = cursor.execute("SELECT valor FROM config WHERE clave = 'lote_contador'").fetchone()
        current_lote = int(lote_row["valor"]) if lote_row else 1
        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('lote_contador', ?)", (str(current_lote + 1),))

        nuevos_boletos_ids = []
        for _ in range(cantidad):
            liberado = cursor.execute("SELECT numero FROM numeros_liberados WHERE sorteo_id = ? ORDER BY numero ASC LIMIT 1", (sorteo_id,)).fetchone()
            if liberado:
                num_boleto = liberado["numero"]
                cursor.execute("DELETE FROM numeros_liberados WHERE sorteo_id = ? AND numero = ?", (sorteo_id, num_boleto))
            else:
                cont_row = cursor.execute("SELECT valor FROM config WHERE clave = ?", (f"contador_{sorteo_id}",)).fetchone()
                num_boleto = int(cont_row["valor"]) if cont_row else 187
                cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (f"contador_{sorteo_id}", str(num_boleto + 1)))
            nuevos_boletos_ids.append(num_boleto)

        for num_boleto in nuevos_boletos_ids:
            cursor.execute('''
                INSERT INTO boletos (id, sorteo_id, lote_id, nombre, telefono, cedula, cantidad_lote, imagen_comprobante, metodo_pago, detalle_pago, estado, impreso)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', 0)
            ''', (num_boleto, sorteo_id, current_lote, nombre, telefono, cedula, cantidad, "", metodo_pago, detalle_pago))

        conn.commit()
        conn.close()
        respaldar_base_datos()

    rango_str = (
        f"#{str(nuevos_boletos_ids[0]).zfill(5)}"
        if len(nuevos_boletos_ids) == 1
        else f"#{str(nuevos_boletos_ids[0]).zfill(5)} al #{str(nuevos_boletos_ids[-1]).zfill(5)}"
    )

    return jsonify({
        "mensaje": f"¡Reserva de {cantidad} boleto(s) registrada con éxito!",
        "rango": rango_str,
        "lote_id": current_lote
    }), 200

@app.route("/api/subir-comprobante", methods=["POST"])
def subir_comprobante():
    data = request.json
    lote_id = data.get("lote_id")
    imagen_comprobante = data.get("imagen_comprobante", "")

    if not lote_id or not imagen_comprobante:
        return jsonify({"error": "Faltan datos del lote o la imagen."}), 400

    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE boletos SET imagen_comprobante = ? WHERE lote_id = ?", (imagen_comprobante, lote_id))
        conn.commit()
        conn.close()
        respaldar_base_datos()

    return jsonify({"mensaje": "¡Comprobante adjuntado correctamente al lote!"}), 200

@app.route("/api/consultar", methods=["POST"])
def consultar():
    data = request.json
    termino = data.get("termino")
    conn = get_db()
    boletos = conn.execute("SELECT * FROM boletos WHERE telefono = ? OR cedula = ? ORDER BY id ASC", (termino, termino)).fetchall()
    
    if not boletos:
        conn.close()
        return jsonify({"encontrado": False, "mensaje": "No se encontraron boletos."}), 404

    resultados = []
    for b in boletos:
        b_dict = dict(b)
        sorteo = conn.execute("SELECT titulo FROM sorteos WHERE id = ?", (b_dict["sorteo_id"],)).fetchone()
        b_dict["sorteo_titulo"] = sorteo["titulo"] if sorteo else "Sorteo General"
        resultados.append(b_dict)
        
    conn.close()
    return jsonify({"encontrado": True, "boletos": resultados}), 200

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

        conn = get_db()
        sorteo = conn.execute("SELECT * FROM sorteos WHERE estado = 'Activo' LIMIT 1").fetchone()
        conn.close()

        if "hola" in mensaje_lower or paso == "INICIO":
            sesion["paso"] = "ESPERANDO_CANTIDAD"
            url_flyer = request.host_url.rstrip("/").replace("http://", "https://") + url_for("static", filename="flyer_sorteo.jpg")
            caption = (
                f"¡Hola! Bienvenido a *VIFRAN GROUP S.A.* 🍀\nTu suerte, nuestro compromiso.\n\n"
                f"🏆 *Sorteo:* {sorteo['titulo'] if sorteo else 'Sorteo'}\n💵 *Valor del ticket:* Gs. {sorteo['precio'] if sorteo else 10000:,}\n\n"
                "¿Cuántos boletos te gustaría reservar?\n*(Responde únicamente con el número, ej: '2')*"
            )
            enviar_imagen_whatsapp(telefono, url_flyer, caption)

        elif paso == "ESPERANDO_CANTIDAD" and mensaje.isdigit():
            cantidad = int(mensaje)
            sesion["datos"]["cantidad"] = cantidad
            total = cantidad * (sorteo['precio'] if sorteo else 10000)

            sesion["paso"] = "ESPERANDO_DATOS_CLIENTE"
            enviar_mensaje_whatsapp(
                telefono,
                f"🎟️ *Cantidad seleccionada:* {cantidad} boleto(s)\nTotal a pagar: *{total:,} Gs.*\n\n"
                "📂 *Datos para el pago (Banco GNB):*\n🔸 *Alias / CI:* 4775796\n🔸 *Titular:* Patricia Franco\n\n"
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
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO clientes (telefono, nombre, cedula) VALUES (?, ?, ?)", (telefono, nombre_cliente, cedula_cliente))
                
                sorteo_id = sorteo["id"] if sorteo else 1
                cantidad = sesion["datos"]["cantidad"]

                lote_row = cursor.execute("SELECT valor FROM config WHERE clave = 'lote_contador'").fetchone()
                current_lote = int(lote_row["valor"]) if lote_row else 1
                cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('lote_contador', ?)", (str(current_lote + 1),))

                nuevos_boletos_ids = []
                for _ in range(cantidad):
                    liberado = cursor.execute("SELECT numero FROM numeros_liberados WHERE sorteo_id = ? ORDER BY numero ASC LIMIT 1", (sorteo_id,)).fetchone()
                    if liberado:
                        num_boleto = liberado["numero"]
                        cursor.execute("DELETE FROM numeros_liberados WHERE sorteo_id = ? AND numero = ?", (sorteo_id, num_boleto))
                    else:
                        cont_row = cursor.execute("SELECT valor FROM config WHERE clave = ?", (f"contador_{sorteo_id}",)).fetchone()
                        num_boleto = int(cont_row["valor"]) if cont_row else 187
                        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (f"contador_{sorteo_id}", str(num_boleto + 1)))
                    nuevos_boletos_ids.append(num_boleto)

                numeros_str = []
                for num_boleto in nuevos_boletos_ids:
                    cursor.execute('''
                        INSERT INTO boletos (id, sorteo_id, lote_id, nombre, telefono, cedula, cantidad_lote, imagen_comprobante, metodo_pago, detalle_pago, estado, impreso)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente', 0)
                    ''', (num_boleto, sorteo_id, current_lote, nombre_cliente, telefono, cedula_cliente, cantidad, "", "WhatsApp / GNB", "Transferencia Directa"))
                    numeros_str.append(str(num_boleto).zfill(5))

                conn.commit()
                conn.close()
                respaldar_base_datos()

            sesion["datos"]["lote_id"] = current_lote
            sesion["datos"]["numeros"] = numeros_str

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
                    conn = get_db()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE boletos SET imagen_comprobante = ? WHERE lote_id = ?", (download_url, current_lote))
                    conn.commit()
                    conn.close()
                    respaldar_base_datos()

            enviar_mensaje_whatsapp(
                telefono,
                "🔍 *¡Comprobante recibido con éxito!*\n\nUn administrador verificará tu pago y te enviará tu boleto con QR en breve. ¡Muchas gracias!"
            )
            sesion["paso"] = "INICIO"

    except Exception as e:
        print(f"❌ Error procesando webhook: {e}")

    return jsonify({"status": "ok"}), 200

def crear_imagen_boleto_memoria(boleto_id, host_url):
    conn = get_db()
    boleto = conn.execute("SELECT * FROM boletos WHERE id = ?", (boleto_id,)).fetchone()
    if not boleto:
        conn.close()
        return None
    sorteo = conn.execute("SELECT titulo FROM sorteos WHERE id = ?", (boleto["sorteo_id"],)).fetchone()
    conn.close()

    sorteo_titulo = sorteo["titulo"] if sorteo else "Sorteo de 4 iPhones"

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
    d.text((20, 155), f"PAGO: {boleto['metodo_pago']}", fill="black", font=font_texto)
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

@app.route("/validar/<int:boleto_id>")
def validar_boleto_qr(boleto_id):
    conn = get_db()
    boleto = conn.execute("SELECT * FROM boletos WHERE id = ?", (boleto_id,)).fetchone()
    if not boleto:
        conn.close()
        return "<h3>Boleto no encontrado</h3>", 404
    sorteo = conn.execute("SELECT * FROM sorteos WHERE id = ?", (boleto["sorteo_id"],)).fetchone()
    conn.close()

    estado_color = "text-emerald-400 bg-emerald-500/10 border-emerald-500/30" if boleto["estado"] == "Aprobado" else "text-amber-400 bg-amber-500/10 border-amber-500/30"

    return f"""
        <!DOCTYPE html>
        <html lang="es">
        <head><meta charset="UTF-8"><title>Validación de Boleto</title><script src="https://cdn.tailwindcss.com"></script></head>
        <body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4 font-sans">
            <div class="bg-slate-800 p-8 rounded-2xl shadow-2xl border border-slate-700 max-w-md w-full space-y-6 text-center">
                <h1 class="text-xl font-black text-amber-400">VIFRAN GROUP S.A.</h1>
                <span class="text-3xl font-black text-amber-400 block">#{str(boleto['id']).zfill(5)}</span>
                <p class="text-sm font-bold">{sorteo['titulo'] if sorteo else 'Sorteo General'}</p>
                <p class="text-xs text-slate-300">Cliente: {boleto['nombre']} (CI: {boleto['cedula']})</p>
                <span class="inline-block px-4 py-1.5 rounded-xl text-xs font-bold border {estado_color}">Estado: {boleto['estado']}</span>
            </div>
        </body>
        </html>
    """

def verificar_admin(data):
    return data.get("usuario") in ADMIN_USERS and ADMIN_USERS[data.get("usuario")] == data.get("password")

@app.route("/api/admin/datos", methods=["POST"])
def admin_datos():
    if not verificar_admin(request.json): return jsonify({"error": "No autorizado"}), 401
    
    with bloqueo_compra:
        conn_fix = get_db()
        sorteos = conn_fix.execute("SELECT * FROM sorteos").fetchall()
        boletos = conn_fix.execute("SELECT * FROM boletos ORDER BY id ASC").fetchall()
        total_clientes = conn_fix.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        conn_fix.close()

    return jsonify({
        "sorteos": [dict(s) for s in sorteos],
        "boletos": [dict(b) for b in boletos],
        "total_clientes": total_clientes
    })

@app.route("/api/admin/crear-sorteo", methods=["POST"])
def admin_crear_sorteo():
    data = request.json
    if not verificar_admin(data): return jsonify({"error": "No autorizado"}), 401
    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sorteos (titulo, precio, limite_boletos, estado, imagen_nombre)
            VALUES (?, ?, ?, 'Activo', 'flyer_sorteo.jpg')
        ''', (data.get("titulo"), int(data.get("precio", 10000)), int(data.get("limite_boletos", 1000))))
        nuevo_id = cursor.lastrowid
        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (f"contador_{nuevo_id}", "187"))
        conn.commit()
        nuevo_sorteo = dict(cursor.execute("SELECT * FROM sorteos WHERE id = ?", (nuevo_id,)).fetchone())
        conn.close()
        respaldar_base_datos()
    return jsonify({"mensaje": "¡Sorteo creado con éxito!", "sorteo": nuevo_sorteo})

@app.route("/api/admin/finalizar-sorteo/<int:sorteo_id>", methods=["POST"])
def admin_finalizar_sorteo(sorteo_id):
    data = request.json
    if not verificar_admin(data): return jsonify({"error": "No autorizado"}), 401
    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE sorteos SET estado = 'Finalizado' WHERE id = ?", (sorteo_id,))
        conn.commit()
        conn.close()
        respaldar_base_datos()
    return jsonify({"mensaje": "¡Sorteo finalizado con éxito!"}), 200

@app.route("/api/admin/agregar-manual", methods=["POST"])
def admin_agregar_manual():
    data = request.json
    if not verificar_admin(data): return jsonify({"error": "No autorizado"}), 401
    
    sorteo_id = int(data.get("sorteo_id", 1))
    nombre = data.get("nombre")
    telefono = data.get("telefono", "0000000000")
    cedula = data.get("cedula", "0000000")
    cantidad = int(data.get("cantidad", 1))
    inicio_personalizado = data.get("inicio_personalizado")

    if not nombre or cantidad < 1:
        return jsonify({"error": "El nombre y la cantidad son obligatorios."}), 400

    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        
        lote_row = cursor.execute("SELECT valor FROM config WHERE clave = 'lote_contador'").fetchone()
        current_lote = int(lote_row["valor"]) if lote_row else 1
        cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('lote_contador', ?)", (str(current_lote + 1),))

        nuevos_boletos_ids = []
        if inicio_personalizado is not None and str(inicio_personalizado).strip() != "":
            num_actual = int(inicio_personalizado)
            for _ in range(cantidad):
                nuevos_boletos_ids.append(num_actual)
                num_actual += 1
        else:
            for _ in range(cantidad):
                liberado = cursor.execute("SELECT numero FROM numeros_liberados WHERE sorteo_id = ? ORDER BY numero ASC LIMIT 1", (sorteo_id,)).fetchone()
                if liberado:
                    num_boleto = liberado["numero"]
                    cursor.execute("DELETE FROM numeros_liberados WHERE sorteo_id = ? AND numero = ?", (sorteo_id, num_boleto))
                else:
                    cont_row = cursor.execute("SELECT valor FROM config WHERE clave = ?", (f"contador_{sorteo_id}",)).fetchone()
                    num_boleto = int(cont_row["valor"]) if cont_row else 187
                    cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (f"contador_{sorteo_id}", str(num_boleto + 1)))
                nuevos_boletos_ids.append(num_boleto)

        max_num = max(nuevos_boletos_ids)
        cont_row = cursor.execute("SELECT valor FROM config WHERE clave = ?", (f"contador_{sorteo_id}",)).fetchone()
        actual_cont = int(cont_row["valor"]) if cont_row else 187
        if max_num >= actual_cont:
            cursor.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (f"contador_{sorteo_id}", str(max_num + 1)))

        for num_boleto in nuevos_boletos_ids:
            estado_inicial = 'Aprobado'
            impreso_inicial = 1

            cursor.execute('''
                INSERT OR REPLACE INTO boletos (id, sorteo_id, lote_id, nombre, telefono, cedula, cantidad_lote, imagen_comprobante, metodo_pago, detalle_pago, estado, impreso)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'Carga Manual', 'Manual (Recuperación)', 'Carga interna', ?, ?)
            ''', (num_boleto, sorteo_id, current_lote, nombre, telefono, cedula, cantidad, estado_inicial, impreso_inicial))

        conn.commit()
        conn.close()
        respaldar_base_datos()

    return jsonify({"mensaje": f"¡{cantidad} boletos agregados manualmente (del #{nuevos_boletos_ids[0]} al #{nuevos_boletos_ids[-1]}) para {nombre}!"}), 200

@app.route("/api/admin/aprobar-lote/<int:lote_id>", methods=["POST"])
def admin_aprobar_lote(lote_id):
    if not verificar_admin(request.json): return jsonify({"error": "No autorizado"}), 401
    host_actual = request.host_url
    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        boletos_lote = cursor.execute("SELECT * FROM boletos WHERE lote_id = ? AND estado = 'Pendiente'", (lote_id,)).fetchall()
        
        if not boletos_lote:
            conn.close()
            return jsonify({"error": "Lote no encontrado o ya aprobado"}), 404

        cursor.execute("UPDATE boletos SET estado = 'Aprobado', impreso = 0 WHERE lote_id = ?", (lote_id,))
        conn.commit()
        conn.close()
        respaldar_base_datos()

        for b in boletos_lote:
            conn2 = get_db()
            sorteo = conn2.execute("SELECT * FROM sorteos WHERE id = ?", (b["sorteo_id"],)).fetchone()
            conn2.close()
            precio = sorteo["precio"] if sorteo else 10000
            titulo = sorteo["titulo"] if sorteo else "Sorteo General"
            caption = f"✨ *¡Pago Verificado y Boleto Emitido!*\n\nCLIENTE: {b['nombre']}\nRUC/CI: {b['cedula']}\nEDICION: {titulo}\nA: Gs. {precio:,}\nNRO: #{str(b['id']).zfill(5)}\n\n🍀 *¡Muchísima suerte con VIFRAN GROUP S.A.!*"
            enviar_ticket_directo(b['telefono'], b['id'], host_actual, caption)

    return jsonify({"mensaje": f"¡Lote aprobado con éxito ({len(boletos_lote)} boletos)!"}), 200

@app.route("/api/admin/eliminar-lote/<int:lote_id>", methods=["POST"])
def admin_eliminar_lote(lote_id):
    data = request.json or {}
    if not verificar_admin(data): return jsonify({"error": "No autorizado"}), 401
    
    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        boletos_a_eliminar = cursor.execute("SELECT * FROM boletos WHERE lote_id = ? AND estado = 'Pendiente'", (lote_id,)).fetchall()
        
        if not boletos_a_eliminar:
            conn.close()
            return jsonify({"error": "Lote no encontrado o ya fue aprobado."}), 404
        
        sorteo_id = boletos_a_eliminar[0]["sorteo_id"]
        for b in boletos_a_eliminar:
            cursor.execute("INSERT OR IGNORE INTO numeros_liberados (sorteo_id, numero) VALUES (?, ?)", (sorteo_id, b["id"]))
            
        cursor.execute("DELETE FROM boletos WHERE lote_id = ? AND estado = 'Pendiente'", (lote_id,))
        conn.commit()
        conn.close()
        respaldar_base_datos()
        
    return jsonify({"mensaje": f"¡Lote #{lote_id} eliminado y números liberados con éxito!"}), 200

@app.route("/api/pendientes-impresion", methods=["GET"])
def obtener_pendientes_impresion():
    conn = get_db()
    boletos_aprobados = conn.execute("SELECT * FROM boletos WHERE estado = 'Aprobado' AND impreso = 0 ORDER BY id ASC").fetchall()
    
    pendientes = []
    lotes_procesados = set()
    for b in boletos_aprobados:
        if b["lote_id"] not in lotes_procesados:
            lotes_procesados.add(b["lote_id"])
            sorteo = conn.execute("SELECT titulo FROM sorteos WHERE id = ?", (b["sorteo_id"],)).fetchone()
            nums = conn.execute("SELECT id FROM boletos WHERE lote_id = ? ORDER BY id ASC", (b["lote_id"],)).fetchall()
            if nums:
                pendientes.append({
                    "id": b["lote_id"],
                    "sorteo_titulo": sorteo["titulo"] if sorteo else "Sorteo General",
                    "nombre": b["nombre"],
                    "cedula": b["cedula"],
                    "telefono": b["telefono"],
                    "numeros_asignados": [str(x["id"]).zfill(5) for x in nums]
                })
    conn.close()
    return jsonify(pendientes), 200

@app.route("/api/marcar-impreso/<int:lote_id>", methods=["POST"])
def marcar_como_impreso(lote_id):
    conn = get_db()
    conn.execute("UPDATE boletos SET impreso = 1 WHERE lote_id = ?", (lote_id,))
    conn.commit()
    conn.close()
    respaldar_base_datos()
    return jsonify({"status": "success"}), 200

@app.route("/api/reimprimir/<int:boleto_id>", methods=["POST"])
def api_reimprimir(boleto_id):
    data = request.json
    if not verificar_admin(data): return jsonify({"error": "No autorizado"}), 401
    conn = get_db()
    conn.execute("UPDATE boletos SET impreso = 0 WHERE id = ?", (boleto_id,))
    conn.commit()
    conn.close()
    respaldar_base_datos()
    return jsonify({"mensaje": f"Boleto #{boleto_id} reenviado a la impresora."}), 200

@app.route("/api/admin/limpiar-pruebas", methods=["POST"])
def limpiar_pruebas():
    data = request.json
    if not verificar_admin(data): return jsonify({"error": "No autorizado"}), 401
    with bloqueo_compra:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM boletos")
        cursor.execute("DELETE FROM numeros_liberados")
        cursor.execute("UPDATE config SET valor = '187' WHERE clave LIKE 'contador_%'")
        cursor.execute("UPDATE config SET valor = '1' WHERE clave = 'lote_contador'")
        conn.commit()
        conn.close()
        respaldar_base_datos()
    return jsonify({"mensaje": "¡Sistema limpiado con éxito!"}), 200

@app.route("/impresion")
def vista_impresion_web():
    return render_template("impresion.html")

if __name__ == "__main__":
    app.run(debug=True)
