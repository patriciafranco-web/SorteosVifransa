import io
from flask import Flask, jsonify, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
import requests

app = Flask(__name__)

# Configuración inicial de sorteos
sorteos_db = [{
    "id": 1,
    "titulo": "S10 Más exclusiva del Py",
    "precio": 10000,
    "limite_boletos": 1000,
    "estado": "Activo",
    "imagen_nombre": (
        "flyer_sorteo.png"  # Nombre del archivo en la carpeta static
    ),
}]

boletos_db = []
contador_boletos_por_sorteo = {1: 1}
lote_contador = 1

# Memoria temporal para la conversación del bot de WhatsApp de cada cliente
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
# WEBHOOK DEL BOT DE WHATSAPP
# ==========================================
@app.route("/api/webhook/whatsapp", methods=["POST"])
def webhook_whatsapp():
  datos = request.json
  telefono = datos.get("telefono")
  mensaje = datos.get("mensaje", "").strip()
  tiene_imagen = datos.get("imagen_enviada", False)

  if not telefono:
    return jsonify({"error": "Falta el teléfono"}), 400

  if telefono not in SESIONES_WHATSAPP:
    SESIONES_WHATSAPP[telefono] = {"paso": "INICIO", "datos": {}}

  sesion = SESIONES_WHATSAPP[telefono]
  paso = sesion["paso"]

  # PASO 1: Saludo inicial y envío del flyer desde la carpeta static
  if "hola" in mensaje.lower() or paso == "INICIO":
    sesion["paso"] = "ESPERANDO_CANTIDAD"
    sorteo = sorteos_db[0]

    # URL pública absoluta del flyer ubicado en static/
    url_flyer = request.host_url.rstrip("/") + url_for(
        "static", filename=sorteo["imagen_nombre"]
    )

    caption = (
        f"¡Hola! Bienvenido a *PRO CAR GROUP* eas 🚗\n\n🏆 *Sorteo:*"
        f" {sorteo['titulo']}\n📅 *Fecha:* 21 de abril, 10:00 p.m.\n💵 *Valor del"
        f" ticket:* Gs. {sorteo['precio']:,}\n\n¿Cuántos boletos te gustaría"
        " reservar hoy?\n*(Responde únicamente con el número, ej: '2')*"
    )

    enviar_imagen_whatsapp(telefono, url_flyer, caption)

  # PASO 2: Recibir cantidad y mostrar datos bancarios
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

    sesion["paso"] = "ESPERANDO_COMPROBANTE"
    enviar_mensaje_whatsapp(
        telefono,
        f"🎟️ *¡Números Reservados!*\n\nSorteo: {sorteo['titulo']}\nTus números:"
        f" {', '.join(numeros_asignados)}\nTotal a pagar: *{total:,}"
        " Gs.*\n\n📂 *Datos para el pago:*\n🔸 *Alias / RUC:*"
        " 80148499-5\n🔸 *Titular:* PRO CAR GROUP\n\n⏳ Tenés 15 minutos para"
        " enviar la foto del comprobante.",
    )

  # PASO 3: Recibir comprobante (foto)
  elif paso == "ESPERANDO_COMPROBANTE" or tiene_imagen:
    enviar_mensaje_whatsapp(
        telefono, "🤖 *Analizando seguridad del comprobante.* Aguardá unos segundos..."
    )

    sesion["paso"] = "CONFIRMAR_DATOS"
    sesion["datos"]["nombre"] = "Edgar Franco"
    sesion["datos"]["cedula"] = "4321212"

    enviar_mensaje_whatsapp(
        telefono,
        "✅ *¡Pago Valido!*\n\n¿Generamos las boletas con tus datos"
        " guardados?\n\n👤 *Titular:* Edgar Franco\n🆔 *CI:*"
        " 4321212\n\n👉 *Respondé SÍ para confirmar o NO para cambiar.*",
    )

  # PASO 4: Confirmación final y envío del ticket con QR
  elif paso == "CONFIRMAR_DATOS" and "si" in mensaje.lower():
    enviar_mensaje_whatsapp(
        telefono, "🔄 Registrando tu compra y generando boletas. Por favor aguardá..."
    )

    sorteo = sorteos_db[0]
    numeros = sesion["datos"]["numeros"]
    nombre = sesion["datos"]["nombre"]
    cedula = sesion["datos"]["cedula"]
    telefono_cliente = telefono

    current_lote = lote_contador
    globals()["lote_contador"] += 1

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
          "estado": "Aprobado",
          "impreso": False,  # Esto activa automáticamente la impresora de Ariel
      }
      boletos_db.append(nuevo_boleto)

    contador_boletos_por_sorteo[sorteo["id"]] += len(numeros)

    for num_str in numeros:
      url_imagen_ticket = f"{request.host_url.rstrip('/')}/api/ticket-imagen/{int(num_str)}"
      caption = (
          f"✨ *¡Venta Completada!*\n\nCLIENTE: {nombre}\nCI:"
          f" {cedula}\nEDICION: {sorteo['titulo']}\nA: Gs."
          f" {sorteo['precio']:,}\nNRO: #{num_str}\n\n🍀 *¡Muchísima suerte para"
          " PRO CAR GROUP!*"
      )
      enviar_imagen_whatsapp(telefono, url_imagen_ticket, caption)

    sesion["paso"] = "INICIO"

  return jsonify({"status": "ok"}), 200


def enviar_mensaje_whatsapp(telefono, texto):
  api_url = "https://tu-api-de-whatsapp.com/message/sendText"
  headers = {"apikey": "TU_TOKEN_SECRETO"}
  payload = {"number": telefono, "text": texto}
  try:
    requests.post(api_url, json=payload, headers=headers)
  except Exception as e:
    print(f"Error enviando texto WhatsApp: {e}")


def enviar_imagen_whatsapp(telefono, url_imagen, caption):
  api_url = "https://tu-api-de-whatsapp.com/message/sendMedia"
  headers = {"apikey": "TU_TOKEN_SECRETO"}
  payload = {
      "number": telefono,
      "mediatype": "image",
      "media": url_imagen,
      "caption": caption,
  }
  try:
    requests.post(api_url, json=payload, headers=headers)
  except Exception as e:
    print(f"Error enviando imagen WhatsApp: {e}")


# ==========================================
# GENERADOR DE IMAGEN DIGITAL DE TICKET
# ==========================================
@app.route("/api/ticket-imagen/<int:boleto_id>")
def obtener_ticket_imagen(boleto_id):
  boleto = next((b for b in boletos_db if b["id"] == boleto_id), None)
  if not boleto:
    return "Boleto no encontrado", 404

  sorteo_titulo = "S10 Más exclusiva del Py"
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
      "PRO CAR GROUP",
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
      f"CI: {boleto['cedula']} | TEL: {boleto['telefono']}",
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
# RUTAS DE IMPRESIÓN WEB AUTOMÁTICA (ARIEL)
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
          "sorteo_titulo": "S10 Más exclusiva del Py",
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
