# README — Terminal WhatsApp (Chat básico asíncrono)

## 1. Descripción

Aplicación de chat en terminal tipo “WhatsApp” con comunicación **asíncrona**, usando:

* **2 conexiones TCP simultáneas por cliente**

  * Puerto **666**: envío de mensajes (outbound)
  * Puerto **999**: recepción de actualizaciones / mensajes (inbound)
* Persistencia mediante **archivos de texto/JSON**:

  * Historial local por conversación (cliente) en `data/client_history/`
  * Historial de servidor por pareja + mensajes pendientes en `data/server_history/` y `data/pending.json`
  * El cliente persiste el último timestamp procesado (`lastTsSeen`) para evitar duplicados tras reinicios y garantizar consistencia en la descarga incremental de UPDATE.

* Gestión de concurrencia con **threads + locks/semaphores**, con `acquire()` / `release()` explícitos.

---

## 2. Requisitos del enunciado implementados

* Comunicación asíncrona: hilo de envío + hilo de recepción en el cliente.
* 2 puertos (666/999) según especificación.
* Comandos del cliente:

  * `@usuario` → cambia el chat activo y muestra conversación
  * `@lista` → lista conversaciones y mensajes pendientes
  * `@salir` → cierra sesión
* No se imprimen mensajes mientras se espera input: los mensajes se guardan y se visualizan al abrir/refrescar conversación.
* Persistencia local y en servidor.
* Gestión de mensajes pendientes (usuarios desconectados).
* Sincronización con OK/KO (ACK) en mensajes y listados.
* Estados de mensajes:

  - `ENVIADO`: mensaje almacenado localmente (incluye cola offline si el servidor no responde)
  - `ENTREGADO`: el receptor ha recibido el mensaje (actualización enviada al emisor mediante UPDATE)
  - `LEIDO`: el receptor ha abierto/refrescado la conversación (READ → evento LEIDO)

---

## 3. Estructura del proyecto

* `server.py` → servidor TCP (puertos 666 y 999)
* `client.py` → cliente en terminal
* `protocol.py` → parser/generador del protocolo de mensajes
* `makeUsers.py` → generación de usuarios (si se usa)
* Carpeta `data/`:

  * `data/client_history/` → historiales locales por conversación (**cliente**).
    - Cada cliente guarda su propio historial en ficheros `<yo>_<peer>.json`
    - Ejemplo (cliente `paula`): `data/client_history/paula_lucia.json`

  * `data/server_history/` → historial de conversaciones en el **servidor** (un único fichero por pareja).
    - Ejemplo: `data/server_history/lucia_paula.json` (o `paula_lucia.json`, según cuál se crease primero)

  * `data/pending.json` → mensajes pendientes almacenados por el servidor (usuarios desconectados o sin ACK).

  * `data/state/` → estado persistente del cliente:
    - `lastts_<usuario>.txt` (JSON) con `{"lastTs": ...}` para evitar reprocesar UPDATE tras reinicios.

  * `data/tmp/` → cola offline del cliente:
    - `tmp_<usuario>.txt` con mensajes que no se pudieron enviar al servidor (se reintenta al reconectar).

---

## 4. Protocolo y funcionamiento

### Puerto 666 (cliente → servidor)

* Envío de `MSG;...`
* Respuesta servidor: `OK` / `KO`
* Si el servidor no responde / está caído:

  - el cliente guarda el mensaje en `data/tmp/tmp_<usuario>.txt`
  - estado local `ENVIADO`
  - reintenta envío al reconectar

### Puerto 999 (cliente ← servidor)

* `LIST`: listado de conversaciones con pendientes
* `UPDATE`: actualización periódica (polling)
  - Incluye mensajes nuevos **y también mensajes pendientes del servidor** (reintentos hasta recibir ACK).
  - Incluye eventos de estado (`ENTREGADO`, `LEIDO`)
  - El cliente confirma cada línea recibida con `OK` (ACK).
  - Polling: la frecuencia de consulta al servidor es configurable mediante POLL_INTERVAL_SECONDS (en src/client.py). El cliente envía UPDATE cuando han transcurrido POLL_INTERVAL_SECONDS segundos desde el último polling (por defecto: 1s).


---

## 5. Ejecución

### 5.1 Servidor

En una terminal desde la raíz:

```bash
python src/server.py
```

### 5.2 Cliente

En otra terminal (una por usuario):

```bash
python src/client.py
```

---

## 6. Comandos del cliente

Una vez autenticado:

* `@usuario` → abrir chat con ese usuario
* `@lista` → listar chats abiertos y pendientes
* Pulsar **Enter en blanco** → refrescar conversación actual
* `@salir` → cerrar sesión

---

## 7. Pruebas recomendadas (rápidas)

1. Conectar 2 clientes (ej. Paula y Lucía) y enviar mensajes.
2. Enviar mensajes a un usuario desconectado:

   * comprobar `@lista` (pendientes)
   * conectar receptor y verificar entrega.
3. Apagar el servidor durante el envío:

   * cliente guarda en `tmp_<usuario>.txt`
   * reiniciar servidor
   * cliente reenvía automáticamente al reconectar.
4. LEIDO:

   * abrir chat (`@usuario`) en el receptor
   * comprobar que el emisor recibe actualización de `LEIDO`.

---

## 8. Credenciales

**Usuarios disponibles:**

* Usuario: `@paula`  Contraseña: `paula`
* Usuario: `@lucia`  Contraseña: `lucia`
* Usuario: `@roberto`  Contraseña: `roberto`