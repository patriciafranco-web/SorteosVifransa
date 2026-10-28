import io
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont
import requests

app = Flask(__name__)

# Configuración inicial de sorteos
sorteos_db = [{
    "id": 1,
    "titulo": "Gran Sorteo: 4 iPhones",
    "precio": 10000,
    "limite_boletos": 1000,
    "estado": "Activo",
}]

boletos_db = []
contador_boletos_por_sorteo = {1: 1}
lote_contador = 1

# Diccionario de credenciales para múltiples administradores
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


@app.route("/api/sorteos", methods=["GET"])
def obtener_sorteos():
  activos = []
  for s in sorteos_db:
    if s["estado"] == "Activo":
      sorteo_info = s.copy()
      activos.append(sorteo_info)
  return jsonify({"sorteos": activos})


@app.route("/api/comprar", methods=["POST"])
def comprar():
  global lote_contador
  data = request.json
  sorteo_id = int(data.get("sorteo_id", 1))
  nombre = data.get("nombre")
  telefono = data.get("telefono")
  cedula = data.get("cedula")
  cantidad = int(data.get("cantidad", 1))
  imagen_comprobante = data.get("imagen_comprobante", "")

  if not nombre or not telefono or not cedula or cantidad < 1:
    return jsonify({"error": "Todos los campos son obligatorios."}), 400

  sorteo_activo = next(
      (s for s in sorteos_db if s["id"] == sorteo_id and s["estado"] == "Activo"),
      None,
  )
  if not sorteo_activo:
    return jsonify({"error": "El sorteo seleccionado ya no está activo."}), 400

  primer_numero = contador_boletos_por_sorteo.get(sorteo_id, 1)
  emitidos_actuales = primer_numero - 1
  if (emitidos_actuales + cantidad) > sorteo_activo["limite_boletos"]:
    return (
        jsonify({
            "error": "No hay suficientes boletos disponibles para esa cantidad."
        }),
        400,
    )

  current_lote = lote_contador
  lote_contador += 1

  nuevos_boletos = []
  for i in range(cantidad):
    num_boleto = primer_numero + i
    nuevo_boleto = {
        "id": num_boleto,
        "sorteo_id": sorteo_id,
        "lote_id": current_lote,
        "nombre": nombre,
        "telefono": telefono,
        "cedula": cedula,
        "cantidad_lote": cantidad,
        "imagen_comprobante": imagen_comprobante,
        "estado": "Pendiente",
        "impreso": False,  # Control para la impresora térmica
    }
    boletos_db.append(nuevo_boleto)
    nuevos_boletos.append(nuevo_boleto)

  contador_boletos_por_sorteo[sorteo_id] = primer_numero + cantidad

  rango_str = (
      f"#{nuevos_boletos[0]['id']}"
      if len(nuevos_boletos) == 1
      else (
          f"#{nuevos_boletos[0]['id']} al #{nuevos_boletos[-1]['id']}"
      )
  )

  return (
      jsonify({
          "mensaje": f"¡Compra de {cantidad} boleto(s) registrada!",
          "rango": rango_str,
      }),
      200,
  )


@app.route("/api/consultar", methods=["POST"])
def consultar():
  data = request.json
  termino = data.get("termino")
  resultados = [
      b for b in boletos_db if b["telefono"] == termino or b["cedula"] == termino
  ]
  if not resultados:
    return (
        jsonify({
            "encontrado": False,
            "mensaje": "No se encontraron boletos con esos datos.",
        }),
        404,
    )
  return jsonify({"encontrado": True, "boletos": resultados}), 200


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


@app.route("/api/admin/crear-sorteo", methods=["POST"])
def admin_crear_sorteo():
  data = request.json
  if not verificar_admin(data):
    return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

  titulo = data.get("titulo")
  precio = int(data.get("precio", 0))
  limite_boletos = int(data.get("limite_boletos", 1000))

  if not titulo:
    return jsonify({"error": "El título es obligatorio"}), 400

  nuevo_id = len(sorteos_db) + 1
  nuevo_sorteo = {
      "id": nuevo_id,
      "titulo": titulo,
      "precio": precio,
      "limite_boletos": limite_boletos,
      "estado": "Activo",
  }
  sorteos_db.append(nuevo_sorteo)
  contador_boletos_por_sorteo[nuevo_id] = 1

  return jsonify({"mensaje": "¡Sorteo creado con éxito!", "sorteo": nuevo_sorteo})


@app.route("/api/admin/finalizar-sorteo/<int:sorteo_id>", methods=["POST"])
def admin_finalizar_sorteo(sorteo_id):
  data = request.json
  if not verificar_admin(data):
    return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

  for s in sorteos_db:
    if s["id"] == sorteo_id:
      s["estado"] = "Finalizado"
      return jsonify(
          {"mensaje": f"Sorteo '{s['titulo']}' finalizado con éxito."}
      )
  return jsonify({"error": "Sorteo no encontrado"}), 404


@app.route("/api/admin/aprobar-lote/<int:lote_id>", methods=["POST"])
def admin_aprobar_lote(lote_id):
  data = request.json
  if not verificar_admin(data):
    return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

  aprobados = 0
  telefono_cliente = None

  for b in boletos_db:
    if b["lote_id"] == lote_id and b["estado"] == "Pendiente":
      b["estado"] = "Aprobado"
      aprobados += 1
      telefono_cliente = b["telefono"]

  # Si se aprobaron boletos, enviamos automáticamente el ticket por WhatsApp al cliente
  if aprobados > 0 and telefono_cliente:
    boletos_lote = [b for b in boletos_db if b["lote_id"] == lote_id]
    for boleto in boletos_lote:
      # URL de la imagen digital del ticket con QR
      url_imagen = (
          f"https://sorteosvifransa.onrender.com/api/ticket-imagen/{boleto['id']}"
      )
      caption = (
          f"✨ *¡Venta Completada!*\n\nTu número de boleto asignado es:"
          f" *#{str(boleto['id']).zfill(4)}*\n\n¡Muchísima suerte! 🍀"
      )
      enviar_imagen_por_whatsapp(telefono_cliente, url_imagen, caption)

  return jsonify({"mensaje": f"¡Lote aprobado con éxito ({aprobados} boletos)!"})


# ==========================================
# GENERADOR DE IMAGEN DIGITAL DE TICKET (WHATSAPP)
# ==========================================
@app.route("/api/ticket-imagen/<int:boleto_id>")
def obtener_ticket_imagen(boleto_id):
  boleto = next((b for b in boletos_db if b["id"] == boleto_id), None)
  if not boleto:
    return "Boleto no encontrado", 404

  # Buscar el título del sorteo
  sorteo_titulo = "Sorteo Vifran"
  for s in sorteos_db:
    if s["id"] == boleto["sorteo_id"]:
      sorteo_titulo = s["titulo"]
      break

  # Crear imagen en blanco para el ticket digital (ancho 400px)
  ancho, alto = 400, 520
  img = Image.new("RGB", (ancho, alto), color="white")
  d = ImageDraw.Draw(img)

  try:
    font_titulo = ImageFont.truetype("arial.ttf", 18)
    font_texto = ImageFont.truetype("arial.ttf", 13)
    font_grande = ImageFont.truetype("arial.ttf", 22)
  except:
    font_titulo = ImageFont.load_default()
    font_texto = ImageFont.load_default()
    font_grande = ImageFont.load_default()

  # Dibujar datos en la imagen
  d.text((ancho / 2, 20), "SORTEOS VIFRAN GROUP", fill="black", anchor="mm")
  d.line([(20, 40), (ancho - 20, 40)], fill="black", width=1)

  d.text((20, 55), f"Sorteo: {sorteo_titulo}", fill="black", font=font_texto)
  d.text((20, 80), f"Cliente: {boleto['nombre']}", fill="black", font=font_texto)
  d.text(
      (20, 105),
      f"CI: {boleto['cedula']} | Cel: {boleto['telefono']}",
      fill="black",
      font=font_texto,
  )

  d.line([(20, 130), (ancho - 20, 130)], fill="black", width=1)
  d.text(
      (ancho / 2, 155),
      f"NRO: #{str(boleto['id']).zfill(4)}",
      fill="black",
      anchor="mm",
      font=font_grande,
  )
  d.line([(20, 180), (ancho - 20, 180)], fill="black", width=1)

  # Descargar el QR real generado por API para incluirlo en la imagen de WhatsApp
  qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=https://sorteosvifransa.onrender.com/validar/{boleto['id']}"
  try:
    res_qr = requests.get(qr_url)
    if res_qr.status_code == 200:
      qr_img = Image.open(io.BytesIO(res_qr.content)).resize((130, 130))
      img.paste(qr_img, (int((ancho - 130) / 2), 195))
  except Exception:
    pass

  d.text(
      (ancho / 2, 350),
      "¡MUCHA SUERTE!",
      fill="black",
      anchor="mm",
      font=font_texto,
  )
  d.text(
      (ancho / 2, 375),
      "Gracias por participar.",
      fill="black",
      anchor="mm",
      font=font_texto,
  )

  output = io.BytesIO()
  img.save(output, format="PNG")
  output.seek(0)
  return send_file(output, mimetype="image/png")


def enviar_imagen_por_whatsapp(telefono, url_imagen, caption):
  # Conecta con tu proveedor de WhatsApp (ej. Evolution API / Meta)
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
    print(f"Error al enviar WhatsApp: {e}")


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
          x["id"] for x in boletos_db if x["lote_id"] == b["lote_id"]
      ]

      sorteo_titulo = "Sorteo Vifran"
      precio_boleto = 10000
      for s in sorteos_db:
        if s["id"] == b["sorteo_id"]:
          sorteo_titulo = s["titulo"]
          precio_boleto = s["precio"]
          break

      total_pagado = len(numeros_del_lote) * precio_boleto

      pendientes.append({
          "id": b["lote_id"],
          "sorteo_id": b["sorteo_id"],
          "sorteo_titulo": sorteo_titulo,
          "nombre": b["nombre"],
          "cedula": b["cedula"],
          "telefono": b["telefono"],
          "valor_boleto": f"{precio_boleto:,}".replace(",", "."),
          "total_pagado": f"{total_pagado:,}".replace(",", "."),
          "metodo_pago": "Efectivo / Transferencia",
          "vendedor": "Administración",
          "fecha_venta": "Reciente",
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
