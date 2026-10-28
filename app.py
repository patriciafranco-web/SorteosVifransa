# ==========================================
# WEBHOOK UNIVERSAL Y DE DIAGNÓSTICO (GREEN API)
# ==========================================
@app.route("/api/webhook/whatsapp", methods=["POST"])
def webhook_whatsapp():
  datos = request.json
  print(
      "--- DATOS RECIBIDOS DEL WEBHOOK ---"
  )  # Esto aparecerá en los Logs de Render
  print(datos)

  if not datos:
    return jsonify({"status": "ignored"}), 200

  try:
    senderData = datos.get("senderData", {})
    messageData = datos.get("messageData", {})

    chat_id = senderData.get("chatId", "")
    if not chat_id and "chatData" in datos:
      chat_id = datos.get("chatData", {}).get("chatId", "")

    # Si no viene en senderData, buscamos directo en el nivel raíz del JSON de Green API
    if not chat_id and "sender" in datos:
      chat_id = datos.get("sender", "")

    telefono = chat_id.split("@")[0] if "@" in chat_id else str(chat_id)

    # Extraer texto del mensaje de múltiples formas posibles
    mensaje = ""
    if "textMessageData" in messageData:
      mensaje = messageData["textMessageData"].get("textMessage", "")
    elif "extendedTextMessageData" in messageData:
      mensaje = messageData["extendedTextMessageData"].get("text", "")
    elif "textMessage" in messageData:
      mensaje = messageData.get("textMessage", "")
    elif "messageData" in datos and isinstance(datos["messageData"], str):
      mensaje = datos["messageData"]

    # Si el JSON tiene una estructura distinta, forzamos la lectura del texto principal
    if not mensaje and "typeWebhook" in datos:
      if datos["typeWebhook"] == "incomingMessageReceived":
        # Extraer del cuerpo estándar de Green API
        try:
          mensaje = (
              datos.get("messageData", {})
              .get("textMessageData", {})
              .get("textMessage", "")
          )
        except:
          pass

    # ¡IMPORTANTE PARA LA PRUEBA! Si por alguna razón llegó el webhook pero no extrajo texto,
    # por defecto lo trataremos como un saludo para forzar la respuesta y validar el canal.
    if telefono and not mensaje:
      mensaje = "hola"

    if not telefono:
      return jsonify({"status": "ok"}), 200

    mensaje_lower = mensaje.lower().strip()
    print(f"Teléfono detectado: {telefono} | Mensaje: {mensaje_lower}")

    if telefono not in SESIONES_WHATSAPP:
      SESIONES_WHATSAPP[telefono] = {"paso": "INICIO", "datos": {}}

    sesion = SESIONES_WHATSAPP[telefono]
    paso = sesion["paso"]

    # PASO 1: Saludo inicial y envío del flyer
    if "hola" in mensaje_lower or paso == "INICIO":
      sesion["paso"] = "ESPERANDO_CANTIDAD"
      sorteo = sorteos_db[0]

      url_flyer = request.host_url.rstrip("/") + url_for(
          "static", filename=sorteo["imagen_nombre"]
      )

      caption = (
          f"¡Hola! Bienvenido a *PRO CAR GROUP* 🚗\n\n🏆 *Sorteo:*"
          f" {sorteo['titulo']}\n📅 *Fecha:* 21 de abril, 10:00 p.m.\n💵 *Valor"
          f" del ticket:* Gs. {sorteo['precio']:,}\n\n¿Cuántos boletos te"
          " gustaría reservar hoy?\n*(Responde únicamente con el número, ej:"
          " '2')*"
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

    # PASO 3: Recibir comprobante (simulado)
    elif paso == "ESPERANDO_COMPROBANTE":
      enviar_mensaje_whatsapp(
          telefono,
          "🤖 *Analizando seguridad del comprobante.* Aguardá unos segundos...",
      )

      sesion["paso"] = "CONFIRMAR_DATOS"
      sesion["datos"]["nombre"] = "Edgar Franco"
      sesion["datos"]["cedula"] = "4321212"

      enviar_mensaje_whatsapp(
          telefono,
          "✅ *¡Pago Válido!*\n\n¿Generamos las boletas con tus datos"
          " guardados?\n\n👤 *Titular:* Edgar Franco\n🆔 *CI:*"
          " 4321212\n\n👉 *Respondé SÍ para confirmar o NO para cambiar.*",
      )

    # PASO 4: Confirmación final y envío del ticket con QR
    elif paso == "CONFIRMAR_DATOS" and "si" in mensaje_lower:
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
            f"✨ *¡Venta Completada!*\n\nCLIENTE: {nombre}\nCI:"
            f" {cedula}\nEDICION: {sorteo['titulo']}\nA: Gs."
            f" {sorteo['precio']:,}\nNRO: #{num_str}\n\n🍀 *¡Muchísima suerte para"
            " PRO CAR GROUP!*"
        )
        enviar_imagen_whatsapp(telefono, url_imagen_ticket, caption)

      sesion["paso"] = "INICIO"

  except Exception as e:
    print(f"❌ Error procesando webhook: {e}")

  return jsonify({"status": "ok"}), 200
