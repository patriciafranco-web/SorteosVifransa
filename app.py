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

    # Identificar si el usuario envió una imagen (comprobante)
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

    # PASO 2: Recibir cantidad y enviar datos para transferencia
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
          " Gs.*\n\n📂 *Datos para el pago (ueno):*\n🔸 *RUC / Alias:*"
          " 4775796-5\n🔸 *Titular:* Patricia Franco\n\n⏳ Tenés 15 minutos para"
          " enviar la foto del comprobante.",
      )

    # PASO 3: Validación del comprobante (¡Aquí detecta cuando envías la foto!)
    elif paso == "ESPERANDO_COMPROBANTE" and (es_imagen or "comprobante" in mensaje_lower or len(mensaje_lower) > 0):
      enviar_mensaje_whatsapp(
          telefono,
          "🤖 *Analizando comprobante de pago.* Aguardá unos segundos...",
      )

      sesion["paso"] = "CONFIRMAR_DATOS"
      sesion["datos"]["nombre"] = "Patricia Franco"
      sesion["datos"]["cedula"] = "4775796-5"

      enviar_mensaje_whatsapp(
          telefono,
          "✅ *¡Pago Confirmado!*\n\n¿Generamos tus boletas digitales con estos"
          " datos?\n\n👤 *Titular:* Patricia Franco\n🆔 *RUC/CI:*"
          " 4775796-5\n\n👉 *Respondé SÍ para confirmar o NO para cambiar.*",
      )

    # PASO 4: Confirmación final, registro y emisión del ticket con QR
    elif paso == "CONFIRMAR_DATOS" and ("si" in mensaje_lower or "sí" in mensaje_lower):
      enviar_mensaje_whatsapp(
          telefono,
          "🔄 Registrando tu compra y generando boletas. Por favor aguardá...",
      )

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
            "estado": "Aprobado",
            "impreso": False,
        }
        boletos_db.append(nuevo_boleto)

      contador_boletos_por_sorteo[sorteo["id"]] += len(numeros)

      for num_str in numeros:
        url_imagen_ticket = f"{request.host_url.rstrip('/')}/api/ticket-imagen/{int(num_str)}"
        caption = (
            f"✨ *¡Venta Completada - VIFRAN GROUP S.A.!*\n\nCLIENTE:"
            f" {nombre}\nRUC/CI: {cedula}\nEDICION: {sorteo['titulo']}\nA: Gs."
            f" {sorteo['precio']:,}\nNRO: #{num_str}\n\n🍀 *¡Muchísima suerte!*"
        )
        enviar_imagen_whatsapp(telefono, url_imagen_ticket, caption)

      sesion["paso"] = "INICIO"

  except Exception as e:
    print(f"❌ Error procesando webhook: {e}")

  return jsonify({"status": "ok"}), 200
