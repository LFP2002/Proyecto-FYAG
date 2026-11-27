# SPEC-027 — Primera cuenta TI por web

Solo para instalaciones que nunca tuvieron usuarios. Aplicar `usuarios.0014_version_desafio_correo` y `usuarios.0015_autorizacion_instalacion` mediante el procedimiento aprobado. El asistente funciona con PostgreSQL y Redis de seguridad; SMTP es opcional y la verificación sigue siendo voluntaria. No usar este procedimiento para recuperar una TI en una instalación usada.

1. Con aprobación fuera de banda de dos personas, el operador autorizado abre una terminal privada sin grabación. En Compose local, por ejemplo:
   ```bash
   docker compose exec backend python manage.py emitir_clave_instalacion --operador operador-ti --referencia CAMBIO-027
   ```
   `--operador` y `--referencia` son identificadores no secretos. La clave de 256 bits se muestra una vez, vence en 30 minutos y queda almacenada solo por digest. Si se pierde, caduca o se sospecha exposición, volver a ejecutar el comando: la clave anterior queda invalidada. No ponerla en URLs, argumentos, registros ni archivos compartidos.
2. Entregar la clave por un canal privado autorizado. El responsable abre `/configuracion-inicial` en el origen de FYAG, usando HTTPS fuera de QA local. Introduce nombre, apellidos, usuario, correo, contraseña, confirmación y clave. No elige rol.
3. Iniciar sesión manualmente. El alta no crea sesión ni exige cambiar la contraseña personal. Confirmar el enlace si llega; si SMTP falla, el alta no se revierte. Solicitar reenvío según la [guía de verificación](SPEC-027-VERIFICACION.md), sin intentar reabrir la instalación.

La CLI interactiva `crear_primera_ti` sigue siendo una alternativa autorizada para instalaciones nuevas; usa el mismo mutex y también invalida la clave web al crear la cuenta. Las inserciones externas marcan la instalación y limpian cualquier autorización pendiente. SQL registra emisión y renovación con operador/referencia, y la inicialización con el tipo de autoridad, sin contraseñas, claves, digests ni cuerpos HTTP.

**QA:** usar una instalación desechable, direcciones `.test` y Mailpit privado. La [colección Postman](postman/SPEC-027-setup.postman_collection.json) requiere cookie jar y variables locales y privadas `clave_qa` y `password_qa`; limpiarlas y no exportarlas ni ejecutar la colección contra datos institucionales. El [contrato OpenAPI](openapi/SPEC-027-setup-v1.yaml) recoge el estado, CSRF, límites y respuestas.
