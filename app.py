from flask import Flask, jsonify, render_template, render_template_string, request

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
  for b in boletos_db:
    if b["lote_id"] == lote_id and b["estado"] == "Pendiente":
      b["estado"] = "Aprobado"
      aprobados += 1

  return jsonify({"mensaje": f"¡Lote aprobado con éxito ({aprobados} boletos)!"})


# ==========================================
# RUTAS NUEVAS PARA LA IMPRESIÓN WEB AUTOMÁTICA
# ==========================================


@app.route("/api/pendientes-impresion", methods=["GET"])
def obtener_pendientes_impresion():
  pendientes = []
  for b in boletos_db:
    # Si el boleto está aprobado pero aún no se imprimió
    if b["estado"] == "Aprobado" and not b.get("impreso", False):
      # Buscar el título del sorteo correspondiente
      sorteo_titulo = "Sorteo Vifran"
      for s in sorteos_db:
        if s["id"] == b["sorteo_id"]:
          sorteo_titulo = s["titulo"]
          break

      pendientes.append({
          "id": b["id"],
          "sorteo_id": b["sorteo_id"],
          "sorteo_titulo": sorteo_titulo,
          "nombre": b["nombre"],
          "cedula": b["cedula"],
          "telefono": b["telefono"],
      })
  return jsonify(pendientes), 200


@app.route("/api/marcar-impreso/<int:boleto_id>", methods=["POST"])
def marcar_como_impreso(boleto_id):
  for b in boletos_db:
    if b["id"] == boleto_id:
      b["impreso"] = True
  return jsonify({"status": "success"}), 200


@app.route("/impresion")
def vista_impresion_web():
  return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Impresión Automática - Sorteos Vifran</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 30px; background: #f4f4f4; }
                .card { background: white; padding: 20px; border-radius: 8px; max-width: 400px; margin: 0 auto; box-shadow: 0px 2px 10px rgba(0,0,0,0.1); }
                .ticket { font-family: monospace; text-align: left; border: 1px dashed #333; padding: 15px; margin-top: 15px; background: #fff; }
                @media print {
                    body { background: none; padding: 0; }
                    .no-print { display: none; }
                    .ticket { border: none; margin: 0; padding: 0; width: 100%; }
                }
            </style>
        </head>
        <body>
            <div class="card no-print">
                <h2>🖨️ Sistema de Impresión Vifran</h2>
                <p>Mantén esta pestaña abierta en Google Chrome.</p>
                <div id="status" style="color: #27ae60; font-weight: bold;">🟢 Conectado y esperando tickets...</div>
            </div>
            
            <div id="ticket-container"></div>

            <script>
                async function verificarPendientes() {
                    try {
                        let res = await fetch('/api/pendientes-impresion');
                        if (res.ok) {
                            let pendientes = await res.json();
                            for (let boleto of pendientes) {
                                mostrarEImprimir(boleto);
                                await fetch(`/api/marcar-impreso/${boleto.id}`, { method: 'POST' });
                            }
                        }
                    } catch (e) {
                        document.getElementById('status').innerText = "🔴 Reconectando con el servidor...";
                    }
                }

                function mostrarEImprimir(boleto) {
                    let container = document.getElementById('ticket-container');
                    container.innerHTML = `
                        <div class="ticket">
                            <h3 style="text-align:center; margin:0;">SORTEOS VIFRAN S.A.</h3>
                            <p style="text-align:center; margin:5px 0;">--------------------------------</p>
                            <p><b>Sorteo:</b> ${boleto.sorteo_titulo || 'Sorteo'}</p>
                            <p><b>Boleto N°:</b> #${String(boleto.id).padStart(4, '0')}</p>
                            <p><b>Cliente:</b> ${boleto.nombre}</p>
                            <p><b>Cédula:</b> ${boleto.cedula}</p>
                            <p><b>Teléfono:</b> ${boleto.telefono}</p>
                            <p style="text-align:center; margin:5px 0;">--------------------------------</p>
                            <p style="text-align:center; margin:0;"><b>LISTO PARA EL BAUL</b></p>
                        </div>
                    `;
                    window.print();
                }

                setInterval(verificarPendientes, 4000);
            </script>
        </body>
        </html>
    """)


if __name__ == "__main__":
  app.run(debug=True)
