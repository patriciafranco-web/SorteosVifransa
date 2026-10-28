import io
from flask import Flask, jsonify, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
import requests

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN DE GREEN API (WHATSAPP)
# ==========================================
ID_INSTANCE = "710722782905"
API_TOKEN_INSTANCE = (
    "085f2d211be547b9a9377b0021c03faf845beb16436644748b"
)


def enviar_mensaje_whatsapp(telefono, texto):
  url = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
  payload = {"chatId": f"{telefono}@c.us", "message": texto}
  try:
    res = requests.post(url, json=payload)
    print(f"📤 Respuesta sendMessage: {res.status_code} - {res.text}")
  except Exception as e:
    print(f"❌ Error enviando mensaje Green API: {e}")


def enviar_imagen_whatsapp(telefono, url_imagen, caption):
  url = f"https://7107.api.greenapi.com/waInstance{ID_INSTANCE}/sendFileByUrl/{API_TOKEN_INSTANCE}"
  payload = {
      "chatId": f"{telefono}@c.us",
      "urlFile": url_imagen,
      "fileName": "flyer_sorteo.jpg",
      "caption": caption,
  }
  try:
    res = requests.post(url, json=payload)
    print(f"📤 Respuesta sendFileByUrl: {res.status_code} - {res.text}")
  except Exception as e:
    print(f"❌ Error enviando imagen Green API: {e}")


# ==========================================
# BASE DE DATOS EN MEMORIA (SORTEO VIFRAN)
# ==========================================
sorteos_db = [{
    "id": 1,
    "titulo": "Sorteo de 4 iPhones (15 Pro Max, 14 Pro Max, 13 Pro Max y 11)",
    "precio": 10000,
    "limite_boletos": 1000,
    "estado": "Activo",
    "imagen_nombre": "flyer_sorteo.jpg",
}]

boletos_db = []
contador_boletos_por_sorteo = {1: 1}
lote_contador = 1

SESIONES_WHATSAPP = {}

ADMIN_USERS = {
    "patriciafranco": "Vifran2026*Secure$",
    "edgarfranco": "Vifran2026*Secure$",
}


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/admin")
def admin_panel():
  return render_template("admin.html")


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
        "fileMessageData" in messageData
        or "imageMessageData" in messageData
        or "jpeg" in tipo_mensaje.lower()
        or "image" in tipo_mensaje.lower()
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
    print(
        f"📩 Mensaje de {telefono} | Texto: {mensaje_lower} | Es imagen:"
        f" {es_imagen} | Paso actual:"
        f" {SESIONES_WHATSAPP.get(telefono, {}).get('paso', 'INICIO')}"
    )

    if telefono not in SESIONES_WHATSAPP:
      SESIONES_WHATSAPP[telefono] = {"paso": "INICIO", "datos": {}}

    sesion = SESIONES_WHATSAPP[telefono]
    paso = sesion["paso"]

    # PASO 1: Saludo inicial y envío del flyer oficial
    if "hola" in mensaje_lower or paso == "INICIO":
      sesion["paso"] = "ESPERANDO_CANTIDAD"
      sorteo = sorteos_db[0]

      url_flyer = request.host_url.rstrip("/") + url_for(
          "static", filename="flyer_sorteo.jpg"
      )

      caption = (
          f"¡Hola! Bienvenido a *VIFRAN GROUP S.A.* 🍀\nTu suerte, nuestro"
          f" compromiso.\n\n🏆 *Sorteo:* {sorteo['titulo']}\n💵 *Valor del"
          f" ticket:* Gs. {sorteo['precio']:,}\n\n¿Cuántos boletos te gustaría"
          " reservar?\n*(Responde únicamente con el número, ej: '2')*"
      )

      enviar_imagen_whatsapp(telefono, url_flyer, caption)

    # PASO 2: Recibir cantidad, reservar números y pedir comprobante
    elif paso == "ESPERANDO_CANTIDAD" and mensaje.isdigit():
      cantidad = int(mensaje)
      sesion["datos"]["cantidad"] = cantidad
      sorteo = sorteos_db[0]
      total = cantidad * sorteo["precio"]

      primer_num = contador_boletos_por_sorteo.get(sorteo["id"], 1)
      numeros_asignados = [
          str(primer_num + i).zfill(5) for i in range(cantidad)
      ]
      sesion["datos"]["numeros"] = numeros_asignados

      sesion["paso"] = "ESPERANDO_DATOS_CLIENTE"
      enviar_mensaje_whatsapp(
          telefono,
          f"🎟️ *¡Números Reservados!*\n\nSorteo: {sorteo['titulo']}\nTus números:"
          f" {', '.join(numeros_asignados)}\nTotal a pagar: *{total:,}"
          " Gs.*\n\n📂 *Datos para el pago (ueno):*\n🔸 *RUC / Alias:*"
          " 4775796-5\n🔸 *Titular:* Patricia Franco\n\n📝 Por favor, escribe tu"
          " *Nombre completo* y tu *Cédula/RUC* separados por una coma (Ej: Juan"
          " Pérez, 1234567).",
      )

    # PASO 3: Recibir Nombre y Cédula del cliente
    elif paso == "ESPERANDO_DATOS_CLIENTE" and "," in mensaje:
      partes = mensaje.split(",")
      nombre_cliente = partes[0].strip()
      cedula_cliente = partes[1].strip()

      sesion["datos"]["nombre"] = nombre_cliente
      sesion["datos"]["cedula"] = cedula_cliente

      sesion["paso"] = "ESPERANDO_COMPROBANTE"
      enviar_mensaje_whatsapp(
          telefono,
          f"✅ Datos guardados:\n👤 *Nombre:* {nombre_cliente}\n🆔"
          f" *CI/RUC:* {cedula_cliente}\n\n📸 Ahora, por favor **enviá la foto"
          " del comprobante de pago** para que el equipo lo verifique.",
      )

    # PASO 4: Recibir comprobante (Foto), guardar como PENDIENTE y avisar al admin
    elif paso == "ESPERANDO_COMPROBANTE" and es_imagen:
      sorteo = sorteos_db[0]
      numeros = sesion["datos"]["numeros"]
      nombre = sesion["datos"]["nombre"]
      cedula = sesion["datos"]["cedula"]
      telefono_cliente = telefono

      global lote_contador
      current_lote = lote_contador
      lote_contador += 1

      for num_str in numeros:
        num_int = int(num_str)
        nuevo_boleto = {
            "id": num_int,
            "sorteo_id": sorteo["id"],
            "lote_id": current_lote,
            "nombre": nombre,
            "telefono": telefono_cliente,
            "cedula": cedula,
            "cantidad_lote": len(numeros),
            "estado": "Pendiente",  # Queda pendiente hasta que el admin apruebe
            "impreso": False,
        }
        boletos_db.append(nuevo_boleto)

      contador_boletos_por_sorteo[sorteo["id"]] += len(numeros)

      enviar_mensaje_whatsapp(
          telefono,
          "🔍 *¡Comprobante recibido con éxito!*\n\nUn administrador de VIFRAN"
          " GROUP S.A. verificará tu pago y te enviará tus boletos y códigos"
          " QR en breve. ¡Muchas gracias!",
      )

      # Reiniciar sesión para futuros mensajes
      sesion["paso"] = "INICIO"

  except Exception as e:
    print(f"❌ Error procesando webhook: {e}")

  return jsonify({"status": "ok"}), 200


# ==========================================
# GENERADOR DE IMAGEN DIGITAL DE TICKET
# ==========================================
@app.route("/api/ticket-imagen/<int:boleto_id>")
def obtener_ticket_imagen(boleto_id):
  boleto = next((b for b in boletos_db if b["id"] == boleto_id), None)
  if not boleto:
    return "Boleto no encontrado", 404

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

  d.text(
      (ancho / 2, 25),
      "VIFRAN GROUP S.A.",
      fill="black",
      anchor="mm",
      font=font_titulo,
  )
  d.line([(20, 45), (ancho - 20, 45)], fill="black", width=2)

  d.text(
      (20, 65), f"CLIENTE: {boleto['nombre'].upper()}", fill="black", font=font_texto
  )
  d.text(
      (20, 90),
      f"RUC/CI: {boleto['cedula']} | TEL: {boleto['telefono']}",
      fill="black",
      font=font_texto,
  )
  d.line([(20, 115), (ancho - 20, 115)], fill="black", width=1)

  d.text((20, 130), f"EDICION: {sorteo_titulo}", fill="black", font=font_texto)
  d.text((20, 155), "A: 10.000 Gs.", fill="black", font=font_texto)

  d.line([(20, 180), (ancho - 20, 180)], fill="black", width=1)
  d.text(
      (ancho / 2, 210),
      f"NRO: #{str(boleto['id']).zfill(5)}",
      fill="black",
      anchor="mm",
      font=font_grande,
  )
  d.line([(20, 240), (ancho - 20, 240)], fill="black", width=1)

  qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={request.host_url.rstrip('/')}/validar/{boleto['id']}"
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
  return send_file(output, mimetype="image/png")


# ==========================================
# API DE ADMINISTRACIÓN (PANEL ADMIN)
# ==========================================
def verificar_admin(data):
  usuario = data.get("usuario")
  password = data.get("password")
  if usuario in ADMIN_USERS and ADMIN_USERS[usuario] == password:
    return True
  return False


@app.route("/api/admin/datos", methods=["POST"])
def admin_datos():
  data = request.json
  if not verificar_admin(data):
    return jsonify({"error": "Usuario o contraseña incorrectos"}), 401
  return jsonify({"sorteos": sorteos_db, "boletos": boletos_db})


@app.route("/api/admin/aprobar/<int:boleto_id>", methods=["POST"])
def admin_aprobar(boleto_id):
  data = request.json
  if not verificar_admin(data):
    return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

  sorteo_id = data.get("sorteo_id")

  for b in boletos_db:
    if b["id"] == boleto_id and b["sorteo_id"] == sorteo_id:
      b["estado"] = "Aprobado"

      # Enviar boleto digital con QR por WhatsApp automáticamente al cliente
      telefono = b["telefono"]
      nombre = b["nombre"]
      cedula = b["cedula"]
      sorteo = sorteos_db[0]
      url_imagen_ticket = (
          f"{request.host_url.rstrip('/')}/api/ticket-imagen/{b['id']}"
      )
      caption = (
          f"✨ *¡Pago Verificado y Boleto Emitido!*\n\nCLIENTE: {nombre}\nRUC/CI:"
          f" {cedula}\nEDICION: {sorteo['titulo']}\nA: Gs."
          f" {sorteo['precio']:,}\nNRO: #{str(b['id']).zfill(5)}\n\n🍀"
          f" *¡Muchísima suerte con VIFRAN GROUP S.A.!*"
      )
      enviar_imagen_whatsapp(telefono, url_imagen_ticket, caption)

      return jsonify({"mensaje": f"Boleto #{boleto_id} aprobado y enviado."})

  return jsonify({"error": "Boleto no encontrado"}), 404


# ==========================================
# RUTAS DE IMPRESIÓN WEB AUTOMÁTICA
# ==========================================
@app.route("/api/pendientes-impresion", methods=["GET"])
def obtener_pendientes_impresion():
  pendientes = []
  lotes_procesados = set()

  for b in boletos_db:
    if (
        b["estado"] == "Aprobado"
        and not b.get("impreso", False)
        and b["lote_id"] not in lotes_procesados
    ):
      lotes_procesados.add(b["lote_id"])
      numeros_del_lote = [
          str(x["id"]).zfill(5)
          for x in boletos_db
          if x["lote_id"] == b["lote_id"]
      ]

      pendientes.append({
          "id": b["lote_id"],
          "sorteo_titulo": "Sorteo de 4 iPhones",
          "nombre": b["nombre"],
          "cedula": b["cedula"],
          "telefono": b["telefono"],
          "numeros_asignados": numeros_del_lote,
      })

  return jsonify(pendientes), 200


@app.route("/api/marcar-impreso/<int:lote_id>", methods=["POST"])
def marcar_como_impreso(lote_id):
  for b in boletos_db:
    if b["lote_id"] == lote_id:
      b["impreso"] = True
  return jsonify({"status": "success"}), 200


@app.route("/impresion")
def vista_impresion_web():
  return render_template("impresion.html")


if __name__ == "__main__":
  app.run(debug=True)
