# Manual de implementación de FYAG

## 1. Propósito y alcance

Este manual describe cómo preparar una instalación controlada del frontend y backend de FYAG, configurar sus dependencias, verificarla y operarla con respaldos y controles de seguridad.

**Importante:** `compose.yaml` es el entorno local de desarrollo del repositorio: monta el código backend, publica puertos de base de datos para uso local y la aplicación usa Daphne. No es una receta de producción. Este repositorio no incluye un despliegue productivo certificado, terminación TLS, provisión de secretos ni un servicio frontend dentro de Compose. Antes de producción, el equipo de infraestructura debe aprobar y documentar esos componentes.

FYAG administra operaciones empresariales y registra documentos/pagos informados externamente. No emite DTE ni procesa transferencias o cobros en línea.

## 2. Arquitectura

- **Frontend:** React y Vite; se compila como archivos estáticos. El acceso a la API se enruta bajo `/api/`.
- **Backend:** Django REST Framework servido por Daphne/ASGI; WebSocket del chat y API HTTP.
- **PostgreSQL:** datos transaccionales, usuarios, operaciones y auditoría.
- **MongoDB:** metadatos documentales y anotaciones; no es la autoridad de usuarios ni almacena los archivos privados.
- **Volúmenes privados:** evidencias, adjuntos y archivos del chat; deben persistir y tener respaldo coordinado.
- **Redis:** transporte efímero de mensajes del chat; no se considera almacenamiento permanente.
- **ClamAV:** análisis de archivos adjuntos; si no está disponible, el backend debe rechazar nuevas cargas.
- **Procesos de reconciliación:** mantienen metadatos documentales, adjuntos y alertas conforme a sus contratos.

## 3. Requisitos previos

Para desarrollo local se requiere Git, Docker con Compose, Node.js/npm y acceso a los puertos configurados en `.env`. Para producción se requiere además una plataforma operada por la empresa para contenedores/procesos, PostgreSQL y MongoDB, almacenamiento persistente, Redis, ClamAV, proxy TLS, monitoreo y gestión de secretos.

Dimensionar CPU, memoria, conexiones, almacenamiento, retención y concurrencia con el responsable de infraestructura. El Compose de desarrollo limita ClamAV y Redis para una máquina local; no usar esos límites como sizing productivo.

## 4. Preparación local de desarrollo

1. Clonar el repositorio y entrar en su raíz.
2. Copiar `.env.example` a `.env` local. Reemplazar **todos** los valores `CAMBIAR_*` con secretos aleatorios independientes. No commitear `.env`, enviarlo por correo ni pegar secretos en tickets.
3. Mantener `DJANGO_DEBUG=True` solo en el entorno local. Definir hosts y orígenes de desarrollo exactos; no usar `*` para CORS ni CSRF.
4. Mantener puertos PostgreSQL y MongoDB enlazados a loopback como en la configuración local. No exponer Redis, ClamAV ni puertos de bases a redes públicas.
5. Verificar que Docker tenga memoria suficiente para PostgreSQL, MongoDB y ClamAV.

Variables principales se describen en `.env.example`: Django/JWT, PostgreSQL, MongoDB, credenciales de QA, Redis, archivos privados y ClamAV. No reutilizar secretos entre aplicaciones ni entre desarrollo, QA y producción.

## 5. Arranque y comprobación local

Desde la raíz:

```bash
docker compose config --quiet
docker compose up --pull always -d --build
```

`docker compose up --pull always` puede usarse para solicitar imágenes actualizadas antes de iniciar; revise y apruebe cambios de imágenes en el entorno correspondiente.

Comprobar servicios y migraciones:

```bash
docker compose ps
docker compose logs --tail 100 backend migraciones postgres mongodb redis clamav
```

Esperar que `migraciones` termine correctamente y que PostgreSQL, MongoDB, Redis y ClamAV indiquen salud disponible. Revisar los logs ante fallos; no repetir migraciones destructivas ni eliminar volúmenes para ocultar un problema.

Iniciar el frontend en otra terminal:

```bash
cd frontend
npm ci
npm run dev
```

Abrir la URL local que Vite indique, normalmente `http://localhost:5173`. El proxy de Vite envía `/api/` al backend local configurado en `frontend/vite.config.js`. Si cambia el origen, alinear el proxy con `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, CORS y la lista permitida del WebSocket; no relajar validaciones.

Verificaciones de desarrollo:

```bash
cd frontend
npm test
npm run build
cd ..
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
```

El build genera `frontend/dist/`; publicar ese directorio solo mediante la canalización aprobada de la empresa. Una compilación exitosa no equivale a aprobación funcional, seguridad o despliegue.

## 6. Aprovisionamiento inicial y cuentas

No hay cuentas demo ni selector de roles. El acceso se realiza con cuentas institucionales creadas y autorizadas por TI. Las operaciones de administración de cuentas están restringidas a Administrador de TI y se registran en auditoría.

Antes de incorporar usuarios:

- confirmar procedimiento corporativo de identidad, correo y entrega inicial de credenciales;
- usar credenciales temporales únicamente si el proceso institucional las habilita y exigir el cambio inicial;
- entregar credenciales por canal privado aprobado; no compartirlas en el manual, Git, capturas o logs;
- confirmar al menos una cuenta TI y las cuentas de continuidad empresarial según las reglas de backend;
- validar cada persona con su responsable y rol mínimo necesario.

El superusuario de Django no debe convertirse en cuenta diaria de negocio. No crear usuarios mediante fixtures o scripts improvisados en producción.

## 7. Consideraciones para producción

La puesta en producción requiere una implementación separada revisada por Seguridad e Infraestructura:

1. Ejecutar el frontend compilado en alojamiento estático corporativo detrás de TLS confiable.
2. Publicar backend ASGI detrás de proxy inverso TLS confiable, con WebSocket y encabezados/origen configurados explícitamente.
3. Mantener `DJANGO_DEBUG=False`; definir `DJANGO_SECRET_KEY`, `JWT_SIGNING_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` y CORS por entorno y con mínimos privilegios.
4. Usar PostgreSQL y MongoDB con autenticación, red privada, cuentas de aplicación restringidas y cifrado/controles de acceso corporativos.
5. Proveer Redis privado y autenticado. No guardar ahí datos que deban ser permanentes.
6. Proveer almacenamiento persistente, cifrado, permisos mínimos y cuota/alertas para evidencias, adjuntos y chat.
7. Instalar y monitorear ClamAV y las actualizaciones de firmas. Una falla debe impedir nuevas cargas, no desactivar el antivirus.
8. Ejecutar migraciones como paso controlado de liberación, con ventana, respaldo probado y plan de reversión compatible con cambios de esquema.
9. Levantar los reconciliadores requeridos como procesos supervisados. Definir política de reinicios, alertas y comprobación de retraso.
10. No incluir `.env`, claves, certificados privados, bases, backups ni archivos de usuarios en imágenes o artefactos.

No se deben copiar literalmente a producción los puertos publicados, límites, volúmenes bind, imágenes o credenciales del Compose local. La confianza TLS de producción debe validarse sin excepciones de navegador.

## 8. Actualizaciones, respaldo y recuperación

Antes de actualizar:

- identificar versión/commit y revisar migraciones y cambios de contrato;
- detener o coordinar escrituras según el plan de mantenimiento;
- respaldar PostgreSQL, metadatos MongoDB y volúmenes de archivos desde un punto coordinado;
- guardar manifiestos de integridad y comprobar restauración en un entorno aislado;
- no versionar los respaldos ni almacenarlos en ubicaciones públicas.

Para una restauración, usar un entorno nuevo y restaurar PostgreSQL, MongoDB y archivos del mismo punto de consistencia. Ejecutar checks, reconciliadores y verificaciones de descarga/metadata autorizadas. No usar `docker compose down -v`, borrar volúmenes ni reinicializar bases como método de diagnóstico. Consultar los procedimientos específicos de `database/README.md` y `backend/docs/SPEC-012B-OPERACION.md`.

## 9. Operación y soporte

- Revisar `docker compose ps` y los logs de servicios con incidentes.
- En errores de login, revisar conectividad, cookies/CSRF, reloj de sistema y logs saneados; nunca registrar contraseñas, JWT ni contenido documental.
- En fallos de adjuntos, comprobar ClamAV, espacio, permisos y logs de scanner antes de reintentar.
- Ante retraso de documentos, adjuntos o alertas, comprobar el proceso reconciliador y el estado de las dependencias; no editar directamente Mongo para reparar estados.
- Registrar fecha/hora, usuario afectado, módulo, ID no sensible y correlación de la solicitud. Escalar incidentes de datos o acceso a Seguridad/DBA.

## 10. QA separado

`compose.premerge-qa.yaml` crea un laboratorio aislado, efímero y destinado a pruebas. Sus bases usan almacenamiento temporal; reiniciarlo puede perder datos QA. Nunca combinarlo con `compose.yaml`, apuntarlo a servicios institucionales o tratarlo como respaldo. Seguir su procedimiento documentado y usar solo datos y cuentas sintéticas.
