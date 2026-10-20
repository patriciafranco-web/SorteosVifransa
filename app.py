from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

TASA_USDT_GUARANIES = 7800

sorteos_db = [{
    "id": 1,
    "titulo": "Gran Sorteo: Camioneta 4x4 0km",
    "precio": 50000,
    "estado": "Activo",
}]

boletos_db = []
contador_boletos_por_sorteo = {1: 1}
lote_contador = 1

ADMIN_USER = "admin"
ADMIN_PASSWORD = "vifran2026admin"


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/admin")
def admin_panel():
  return render_template("admin.html")


# --- API PÚBLICA (Solo muestra sorteos ACTIVOS a los clientes) ---
@app.route("/api/sorteos", methods=["GET"])
def obtener_sorteos():
  activos = [s for s in sorteos_db if s["estado"] == "Activo"]
  return jsonify({"sorteos": activos, "tasa_usdt": TASA_USDT_GUARANIES})


@app.route("/api/comprar", methods=["POST"])
def comprar():
  global lote_contador
  data = request.json
  sorteo_id = int(data.get("sorteo_id"))
  nombre = data.get("nombre")
  telefono = data.get("telefono")
  cedula = data.get("cedula")
  cantidad = int(data.get("cantidad", 1))
  metodo_pago = data.get("metodo_pago", "Transferencia / QR")
  detalle_pago = data.get("detalle_pago", "Transferencia Directa")

  if not sorteo_id or not nombre or not telefono or not cedula or cantidad < 1:
    return jsonify({"error": "Todos los campos son obligatorios."}), 400

  sorteo_activo = next(
      (
          s
          for s in sorteos_db
          if s["id"] == sorteo_id and s["estado"] == "Activo"
      ),
      None,
  )
  if not sorteo_activo:
    return (
        jsonify({
            "error": "El sorteo seleccionado ya no está activo para compras."
        }),
        400,
    )

  primer_numero = contador_boletos_por_sorteo.get(sorteo_id, 1)
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
        "metodo_pago": metodo_pago,
        "detalle_pago": detalle_pago,
        "estado": "Pendiente",
        "impreso": False,
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

  for b in resultados:
    s = next(
        (item for item in sorteos_db if item["id"] == b["sorteo_id"]), None
    )
    b["sorteo_titulo"] = s["titulo"] if s else "Sorteo General"

  return jsonify({"encontrado": True, "boletos": resultados}), 200


def verificar_admin(data):
  return (
      data.get("usuario") == ADMIN_USER
      and data.get("password") == ADMIN_PASSWORD
  )


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
  precio = data.get("precio", 0)

  if not titulo:
    return jsonify({"error": "El título es obligatorio"}), 400

  nuevo_id = len(sorteos_db) + 1
  nuevo_sorteo = {
      "id": nuevo_id,
      "titulo": titulo,
      "precio": precio,
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
  for b in boletos_db:
    if b["lote_id"] == lote_id and b["estado"] == "Pendiente":
      b["estado"] = "Aprobado"
      aprobados += 1

  return jsonify({"mensaje": f"¡Lote aprobado con éxito ({aprobados} boletos)!"})


@app.route("/api/pendientes-impresion", methods=["GET"])
def pendientes_impresion():
  pendientes = []
  for b in boletos_db:
    if b["estado"] == "Aprobado" and not b["impreso"]:
      s = next(
          (item for item in sorteos_db if item["id"] == b["sorteo_id"]), None
      )
      boleto_con_titulo = b.copy()
      boleto_con_titulo["sorteo_titulo"] = (
          s["titulo"] if s else "Sorteo Vifran"
      )
      pendientes.append(boleto_con_titulo)
  return jsonify(pendientes)


@app.route("/api/marcar-impreso/<int:boleto_id>/<int:sorteo_id>", methods=["POST"])
def marcar_impreso(boleto_id, sorteo_id):
  for b in boletos_db:
    if b["id"] == boleto_id and b["sorteo_id"] == sorteo_id:
      b["impreso"] = True
      return jsonify({"mensaje": f"Boleto {boleto_id} marcado como impreso"})
  return jsonify({"error": "Boleto no encontrado"}), 404


if __name__ == "__main__":
  app.run(debug=True)