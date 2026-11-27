# SPEC-027 — Primera cuenta TI por web

Solo para instalaciones que nunca tuvieron usuarios. Aplicar `usuarios.0014_version_desafio_correo` y `usuarios.0015_autorizacion_instalacion` mediante el procedimiento aprobado. El asistente funciona con PostgreSQL y Redis de seguridad; SMTP es opcional y la verificación sigue siendo voluntaria. No usar este procedimiento para recuperar una TI en una instalación usada.

1. Con aprobación fuera de banda de dos personas, el operador autorizado abre una terminal privada sin grabación. En Compose local, por ejemplo:
   ```bash
   docker compose exec backend python manage.py emitir_clave_instalacion --operador operador-ti --referencia CAMBIO-027
   ```
   En Compose productivo, usar el proyecto, archivo de entorno y overlays del backend, pero ejecutar en el servicio efímero de seguridad (sin `-T`):
   ```bash
   docker compose … run --rm --no-deps operaciones_seguridad python -m config.security_cli emitir_clave_instalacion --operador operador-ti --referencia CAMBIO-027
   ```
   Usar ese mismo servicio para la alternativa `crear_primera_ti`.
   `--operador` y `--referencia` son identificadores no secretos. La clave de 256 bits se muestra una vez, vence en 30 minutos y queda almacenada solo por digest. Si se pierde, caduca o se sospecha exposición, volver a ejecutar el comando: la clave anterior queda invalidada. No ponerla en URLs, argumentos, registros ni archivos compartidos.
2. Entregar la clave por un canal privado autorizado. El responsable abre FYAG en su origen habitual, usando HTTPS fuera de QA local. FYAG consulta `GET /api/auth/setup/estado/` antes de mostrar el login o restaurar una sesión. Si `pendiente` es `true`, abre `/configuracion-inicial`. Introducir nombre, apellidos, usuario, correo, contraseña, confirmación y clave. No se elige rol.
3. Tras confirmar el alta (`201`), FYAG muestra el login en `/`. Iniciar sesión manualmente: el alta no crea ni restaura una sesión, ni exige cambiar la contraseña personal. Confirmar el enlace si llega; si SMTP falla, el alta no se revierte. Solicitar reenvío según la [guía de verificación](SPEC-027-VERIFICACION.md), sin intentar reabrir la instalación.

Si `pendiente` es `false`, la entrada habitual conserva su flujo de autenticación, incluida la restauración de una sesión existente; una visita directa a `/configuracion-inicial` vuelve al login. Los cambios de ruta reemplazan la entrada actual del historial. Durante la consulta se muestra un estado de carga; si vence el plazo de 10 s, falla la conexión o la respuesta no es válida, pulsar **Reintentar**. Un fallo nunca habilita el login ni el asistente. Las rutas públicas de recuperación y verificación permanecen accesibles directamente.

La pantalla de comprobación y el asistente ofrecen tema claro/oscuro y cuatro tamaños de letra (100 %, 112,5 %, 125 % y 137,5 %). La redirección no concede autorización: PostgreSQL sigue siendo la autoridad sobre la inicialización y el backend valida y consume la clave de un solo uso al crear la primera TI.

La CLI interactiva `crear_primera_ti` sigue siendo una alternativa autorizada para instalaciones nuevas; usa el mismo mutex y también invalida la clave web al crear la cuenta. Las inserciones externas marcan la instalación y limpian cualquier autorización pendiente. SQL registra emisión y renovación con operador/referencia, y la inicialización con el tipo de autoridad, sin contraseñas, claves, digests ni cuerpos HTTP.

**QA:** usar una instalación desechable, direcciones `.test` y Mailpit privado. La [colección Postman](postman/SPEC-027-setup.postman_collection.json) requiere cookie jar y variables locales y privadas `clave_qa` y `password_qa`; limpiarlas y no exportarlas ni ejecutar la colección contra datos institucionales. El [contrato OpenAPI](openapi/SPEC-027-setup-v1.yaml) recoge el estado, CSRF, límites y respuestas.

**Validación dirigida de la entrada automática:** [`frontend/qa/spec027-setup-browser.cjs`](../../frontend/qa/spec027-setup-browser.cjs) se ejecuta desde la raíz con `node` y Playwright/Firefox disponibles en el entorno QA. Usa Firefox real y respuestas API controladas para verificar carga sin login, reintento tras error de red/503/respuesta inválida, redirecciones sin bucle, alta sin sesión y login manual, restauración habitual, rutas públicas y 32 combinaciones de ancho/tema/escala (1440, 768, 390 y 320 px). La suite `apps.usuarios.tests.test_setup_web_027` verifica el comportamiento real del backend con PostgreSQL y Redis en QA; las pruebas de este cambio no requirieron Mailpit ni validan una activación institucional.
