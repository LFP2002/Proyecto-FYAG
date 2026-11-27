# AUD-023 — Respaldo coordinado y recuperación

`deploy/aud023/backup.py` opera sobre el Compose productivo independiente, no sobre desarrollo. Requiere Python 3.11+, Docker Compose v2, GnuPG y control exclusivo del daemon y los volúmenes durante la ventana. Usar una estación administrativa confiable. No usar un contexto remoto compartido con procesos que puedan iniciar clientes, modificar volúmenes o cambiar imágenes mientras se ejecuta.

## Preparación y respaldo

1. Autorizar la ventana, identificar proyecto, contexto Docker, imágenes y volumen de datos; anunciar el corte. Suspender automatizaciones, clientes externos y accesos de operadores. La herramienta detiene el proxy, web, workers, Redis y demás servicios del proyecto excepto PostgreSQL y MongoDB; rechaza clientes restantes, redes de datos no internas, puertos de los motores publicados, volúmenes personalizados y contenedores activos que monten archivos privados. No sustituye el control administrativo de quien tiene acceso al daemon.
2. Preparar un directorio privado de *staging* en un sistema de archivos cifrado o RAM (modo `0700` en POSIX; ACL equivalente en Windows). Reservar espacio para aproximadamente dos copias sin comprimir, más el cifrado en destino. No usar un directorio sincronizado ni incluir staging en otro respaldo. Preparar un archivo externo de clave de 32 bytes aleatorios en hexadecimal (`0600` o ACL equivalente), bajo custodia separada del respaldo. El destino también debe tener acceso restringido; requiere un filesystem con hard links para publicar atómicamente sin sobrescribir un respaldo previo.
3. Ejecutar desde la revisión aprobada, con el mismo entorno Compose. Añadir `--smtp` si el proyecto usa el overlay SMTP:

   ```sh
   python deploy/aud023/backup.py backup --project fyag-prod --confirm fyag-prod \
      --env /srv/fyag/production.env --archive /respaldo/2026-11-27.gpg \
      --stage /staging/privado --key /custodia/aud023.key
   ```

4. El manifiesto dentro del cifrado contiene corte UTC, versiones exactas, IDs de imágenes, configuración seleccionada, nombres lógicos de secretos, inventarios y SHA-256 de cada componente. PostgreSQL usa `pg_dump` con la identidad de migraciones; no se exportan roles o contraseñas del motor. Mongo usa `mongodump` de la base documental, sin usuarios del motor; herramientas Mongo resuelven la autenticación con el secreto bootstrap ya montado, no por argumentos. Los TAR de evidencias, adjuntos y Chat conservan bytes, rutas, permisos y propietarios; no admiten enlaces simbólicos ni archivos especiales. Los enlaces duros de staging de Chat se representan como archivos regulares. El paquete usa OpenPGP simétrico AES-256 con verificación de integridad; no se debe compartir la clave con quien solo custodia copias. `verify` comprueba descifrado, inventario y hashes sin conectar a Docker (usar `--archive`, `--stage`, `--key`).
5. Aun si el respaldo falla, no se reabre el tráfico automáticamente. Revisar resultado, reactivar los mismos servicios autorizados del origen y verificar salud y colas. Registrar inicio de mantenimiento, corte UTC, publicación, reapertura y referencia de cambio; no transcribir datos, secretos ni errores brutos de motores.

## Restauración aislada

1. Mantener cerrado el ingreso. Preparar un proyecto **nuevo** `fyag-dr-*`, sin contenedores, volúmenes ni redes previos (ni siquiera detenidos), entorno separado y volúmenes Compose estándar. Preparar imágenes exactas del manifiesto y certificados autorizados; las incompatibilidades se ensayan aparte, nunca se fuerzan. Generar secretos SQL/Mongo para el nuevo proyecto y rotar Django, JWT, HMAC de recuperación (si SMTP), Redis y los demás accesos necesarios. No reutilizar el archivo de entorno ni copiar material privado del origen. No ejecutar `up` ni inicializar manualmente el destino antes de `restore`.

   ```sh
   python deploy/aud023/backup.py restore --project fyag-dr-incidente --confirm fyag-dr-incidente \
      --env /srv/fyag/recovery.env --archive /respaldo/2026-11-27.gpg \
      --stage /staging/privado --key /custodia/aud023.key
   ```

2. `restore` valida todo el paquete antes de cargar datos. Arranca motores nuevos, comprueba versiones, esquema SQL vacío y colecciones Mongo iniciales vacías. `pg_restore` replica objetos de aplicación como `fyag_sql_migration`, no transfiere dueños ni ACL del origen; se reinstala la matriz AUD-025. `mongorestore` reemplaza únicamente la base documental inicial vacía; conserva validadores, índices y anotaciones. Se verifican conteos Mongo y se comparan los archivos restaurados con el TAR. Si hay un fallo parcial, mantener ese proyecto aislado y preparar **otro proyecto nuevo** para el siguiente intento. La herramienta nunca elimina volúmenes.
3. Redis de seguridad y Redis Chat **no se restauran**: arrancan vacíos, se comprueba `DBSIZE=0` y se vuelven a detener hasta la reapertura autorizada. Se pierden colas pendientes, cuotas, throttles efímeros y presencia; volver a solicitar notificaciones por el camino normal y aplicar control de tráfico durante la reapertura. Se conserva el estado SQL de bloqueos, además del historial. En SQL se incrementan versiones de sesión, se retiran sesiones Django, tickets, leases, cuotas y desafíos de correo o primer cambio, y se limpia una eventual clave pendiente de instalación. Las temporales anteriores dejan de ser utilizables; reemitir solo según la autorización normal o el procedimiento excepcional TI. No se borra la auditoría de seguridad ni el historial de tokens emitidos. Si el origen estaba sin inicializar, se requiere una nueva emisión; si estaba inicializado, no se reabre el asistente.
4. Verificar en el destino: inventarios y referencias SQL ↔ Mongo/archivos, hashes en lectura de aplicación, cuentas y revocación, permisos runtime, auditoría, colas y reconciliadores. Una ventana sin escrituras preserva el corte, pero no corrige inconsistencias o compensaciones pendientes que ya tenía el origen. Cuando se usaban bloqueos productivos, la copia preserva la constancia histórica, no su vigencia: obtener una **nueva** autorización para el destino y registrarla según SPEC-027 antes de arrancar web; no desactivar la guarda. Arrancar servicios autorizados en red privada, validar salud y hacer el cambio de tráfico solo con aprobación independiente.

## Retención y métricas

Propuesta para aprobar institucionalmente: copia diaria de 14 días, semanal de 8 semanas y mensual de 12 meses; priorizar requisitos legales y límites de privacidad. Mantener al menos una copia externa inmutable, comprobaciones de integridad periódicas, segregación de acceso a paquetes y claves, y un simulacro trimestral. Conservar las imágenes, código, esquema y referencias de secretos por todo el plazo de recuperación. No borrar copias durante incidentes, investigaciones o retención legal.

**RPO observado** = hora del incidente simulado menos el corte UTC del último respaldo válido (no la hora de cifrado). **RTO observado** = declaración del incidente hasta servicio autorizado y comprobado; medir aparte el tiempo de restauración offline, validación y reapertura. Medir también la ventana de origen desde retirada hasta reapertura. Los tiempos con una fixture pequeña no son objetivos institucionales ni predicen el costo con volumen real. No hay recuperación a un instante posterior al corte ni replicación continua.

Para repetir el ensayo con datos sintéticos, usar bases `fyag_aud023_source` y `fyag_aud023_target`, entornos separados, puertos de loopback y secretos exclusivos del laboratorio. Con el origen saludable, pasar `deploy/tests/smoke_backup_aud023.py` a `docker compose … exec -T backend python - seed`; tras restaurar y arrancar el destino aislado, pasar el mismo script con `verify`. `deploy/aud023/check_negative.py --synthetic-only CONFIRMED` comprueba negativas usando el paquete de laboratorio y los mismos argumentos de archivo, clave y staging de `verify`.
