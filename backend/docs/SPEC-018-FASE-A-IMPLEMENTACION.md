# SPEC-018 — Fase A backend: implementación y validación

Fecha: 20-11-2026. Rama exclusiva `feature/backend-018-seguridad-credenciales`.
Base local verificada: `9b34a10ca413ce9d64632d9a0cd63fbce83d71b6`.
**SPEC-018 NO está completada:** frontend y política de bloqueos escalonados
siguen pendientes. No autoriza despliegue, merge ni modificación del PR #45.

**Revisión posterior del commit `242abcb`:** se confirmó un fail-open al considerar
PERSONAL un registro de seguridad ausente. La corrección elimina esa equivalencia
y requiere un estado SQL presente/coherente; ver
[hallazgo, migración 0007 y resultados nuevos](SPEC-018-FAIL-CLOSED.md).
Los resultados de 918 pruebas indicados más abajo pertenecen a la entrega anterior,
no se atribuyen automáticamente a esta corrección.

## Autorización y alcance

El responsable autorizó expresamente en conversación:

- Credencial temporal: **24 horas** desde generación, configurable, reloj servidor.
- Desafío: **5 minutos**, configurable, nunca más allá del vencimiento temporal.
- Ambos valores **NO RATIFICADOS PARA PRODUCCIÓN**, exclusivos desarrollo/QA.
- Entrega exclusivamente manual entre cuentas sintéticas QA; sin email/chat/SMS.
- Credencial vencida no permite login; exige reemisión TI.

Se implementan backend, migración aditiva, pruebas y contrato frontend/OpenAPI.
No se cambian roles, inventario, negocio ni umbrales de bloqueo. SPEC históricas
permanecen intactas; la autorización posterior se documenta aquí, no se inventa
una aprobación retrospectiva de la propuesta original.

## Persistencia y compatibilidad

Migración nueva `usuarios.0006_seguridad_credenciales`:

- Tabla 1:1 `SeguridadCredencial`, estados PERSONAL / INICIAL / RECUPERACION.
  `is_active` conserva exclusivamente su significado administrativo.
- Constraints de estado, fechas, digest/versión y vencimiento de desafío; digest
  SHA256 único de desafío aleatorio de 256 bits. Sin desafíos en texto claro SQL.
- Estado PERSONAL para cuentas existentes mediante inserciones por lotes; ningún
  cambio de usuario, hash, rol, versión, actividad, relaciones ni evento histórico.
   La equivalencia inicial de creaciones internas sin fila a PERSONAL fue retirada
   por insegura en la revisión posterior. Toda cuenta nueva requiere estado explícito;
   ausencia o incoherencia deniegan acceso. Bootstrap TI se conserva bajo ese control.
- Ampliación del catálogo y longitud de UsuarioEvento: nuevos tipos
  CREACION_CREDENCIAL_TEMPORAL, REEMISION y CAMBIO_INICIAL. Eventos de credenciales
  sin snapshots; el alta conserva además CREACION administrativo existente.

Cambio contractual deliberado: POST usuarios ya no acepta password; devuelve
credencial generada una vez. `establecer-clave` está retirado (409), no es una
alternativa para elegir clave ajena. React antiguo requerirá la integración
descrita en el contrato; no se afirma compatibilidad de su formulario de alta.

## Autenticación, sesiones y seguridad

- Login temporal solo emite desafío opaco restringido, sin JWT operativo ni
  OutstandingToken. Elimina refresh anterior del navegador y rota CSRF.
- Primer cambio exige CSRF y JSON estricto, validadores Django y clave distinta
  de la temporal; consume desafío y cambia hash/estado/versión/evento atómicamente.
  Sin sesión automática: nuevo login obligatorio.
- Reset por TI activo/persistido, versión vigente, motivo y cuenta ajena; mutex
  administrativo existente → usuarios por PK → seguridad. No reactiva ni cambia
  roles/asignaciones. La última credencial emitida reemplaza las anteriores.
- Login/refresh/cambio/correo se serializan sobre el lock Usuario existente;
  no adquieren mutex después de usuario ni locks de Obras/Finanzas. Reset posterior
  invalida también tokens que un login/refresh solapado confirmó antes.
- JWT y refresh verifican estado PERSONAL además de actividad, versión y hash;
  incluso tokens generados artificialmente para una temporal son rechazados.
- Mantiene última TI/Gerencia, dependencias de técnicos, flags sin privilegios,
  normalización y revocación de correo SPEC-006C, JWT en memoria y refresh
  HttpOnly/Secure/Strict/path existente. No se modifica confianza TLS Windows.
- La lectura JWT integra el estado 1:1 en la consulta de usuario. Las revalidaciones
  de permisos de Documentos y Adjuntos incorporan únicamente el mismo precargado;
  no cambian sus roles ni reglas de negocio. Evita una consulta adicional por
  autenticación/revalidación y conserva los presupuestos SQL existentes.
- Sin logs de cuerpos o secretos; respuesta excepcional no-store/no-cache;
  variables sensibles protegidas, reporter y logger Django de errores de rutas
  sensibles omiten locales/valores de excepción para evitar filtración indirecta.
  Proxy/APM externos no están configurados por esta fase y deben excluir cuerpos,
  cookies, Authorization y respuestas secretas antes de cualquier despliegue.
- Throttle de IP existente de refresh se reutiliza en primer cambio; no añade
  política de bloqueo ni contador de intentos. No reintentar resets automáticamente.

## Contratos y frontend pendiente

- [Contrato exacto de integración](SPEC-018-FASE-A-CONTRATO.md).
- [OpenAPI 018A v1](openapi/SPEC-018A-v1.json).
- [Auditoría inicial de impacto](SPEC-018-FASE-A-IMPACTO.md).

React posterior: estado restringido distinto de authenticated, desafío solo en
memoria, sin /me/refresh/negocio; pantalla de cambio inicial; quitar password del
alta y clave elegida de reset; exposición confidencial única y borrado de memoria.
Mantener abortos/scopes, conciliación de escrituras inciertas y SPEC-006C.

## Validación ejecutada

Laboratorio nuevo exclusivo `fyag-spec018-qa-20261120`, compose standalone existente,
PostgreSQL/Mongo en tmpfs, red interna sin puertos host, ClamAV propio y secretos
externos. Runner `DocumentalTestRunner`; Mongo de tests separado de servicios
principales. Migraciones aplicadas únicamente en este laboratorio.

La primera ejecución dirigida detectó un problema de normalización de TextChoices
en llamadas internas de servicio: los snapshots exigen tipos str exactos. Se
corrigió `_role` para devolver str antes de auditar, conservando validación RBAC.
La siguiente ejecución pasó 121 pruebas; no se oculta el intento anterior fallido.
Una ejecución dirigida posterior pasó 123 pruebas en 22.226 s, incluidos contrato
OpenAPI y reporter/logger sin secretos. Después se añadió rechazo ASCII antes de
hashear desafíos, con prueba de JSON con surrogate aislado (400 de serializer o
401 genérico; nunca error de codificación), sin atribuir un defecto público
observado a esa revisión estática de defensa en profundidad.

La primera suite completa ejecutó 917 pruebas en 367.133 s y detectó **7 fallos de
presupuesto SQL** por la consulta adicional del estado de seguridad (Auditoría,
Obras, Dashboard, Documentos y Reportes). Se corrigió la lectura de estado mediante
precargado en la consulta de usuario y sus revalidaciones documentales, **sin
aumentar límites ni modificar las pruebas de rendimiento de esas aplicaciones**.
La repetición dirigida pasó **130/130 en 33.985 s** (Usuarios y los siete casos
afectados); Documentos volvió a 9 consultas y Dashboard resumen a 12. También se
precargó estado en el listado administrativo y se añadió una regresión propia de
25 cuentas por página con presupuesto de cuatro consultas, evitando N+1.
El módulo definitivo, incluida la nueva regresión de listado, pasó **124/124 en
22.402 s**. La versión final reúne **44 pruebas nuevas**, entre ellas 14 carreras
PostgreSQL y una prueba de ascenso 0005 → 0006.

**Regresión completa definitiva: 918/918 pruebas OK en 339.472 s**, salida 0,
sin fallos ni errores; base de tests destruida normalmente. Incluye Usuarios,
autenticación, integridad de migraciones, presupuestos SQL y regresión de todas
las aplicaciones con PostgreSQL/Mongo/ClamAV QA. No se relajan los límites de
consultas anteriores. Código/tests/OpenAPI cotejados con el manifiesto de la
versión sometida a esta ejecución; solo se completa documentación después.

Evidencia externa local: `fyag-spec018-qa-20261120` en el directorio temporal
aprobado de OpenCode: `usuarios-definitivo.log`, `backend-definitivo.log`,
`usuarios-query-regression.log`, manifiestos de fuentes y escaneo prepublicación.
Se conservan también los intentos anteriores fallidos para trazabilidad, sin
incorporar logs, credenciales de infraestructura ni datos del laboratorio a Git.

### Verificaciones complementarias ejecutadas

- `manage.py check`: sin incidencias; `makemigrations --check --dry-run`: sin
  cambios; `migrate --check`: OK en QA. No se ejecutó migrate en servicios principales.
- OpenAPI JSON válido, referencias locales y rutas resolubles, campos de serializers
  y estados comprobados por test automatizado. No se atribuye validación mediante
  un validador externo de OpenAPI no ejecutado.
- Frontend existente, sin modificaciones: `npm ci` OK, **204/204 pruebas OK en
  9794.5481 ms**, build OK en **6.89 s**, 99 módulos. Estos tests utilizan sus
  contratos simulados anteriores; **no acreditan integración React de Fase A**.
- `npm audit --omit=dev --json` y audit completo devolvieron **0 vulnerabilidades /
  salida 0** en esta consulta del 20-11-2026. Lock/dependencias sin cambios; este
  resultado de registro no demuestra un parche de picomatch ni reescribe la
  aceptación temporal/evidencia histórica. No se declara solucionado el advisory.
- Instalación avisó postinstall de esbuild bloqueado por política local; no se
  habilitaron scripts y no impidió test/build.
- Diff --check y escaneo de fuentes sin secretos QA, claves privadas ni artefactos;
  manifiesto externo para comprobar identidad del código probado antes del commit.

## Operación y reversión segura

No aplicar reversión destructiva automática. Ante fallo, detener habilitación del
flujo y preservar hashes/estado/eventos; respaldar PostgreSQL coordinadamente y
decidir un plan revisado antes de retroceder esquema. El código anterior no conoce
el estado temporal: **no es seguro volver a desplegarlo sobre credenciales
temporales existentes**, pues podría emitirles JWT operativo. No borrar filas de
seguridad ni rebajar versiones para recuperar acceso. No usar crear_primera_ti
como recuperación cuando existe TI. Un secreto de respuesta perdido exige reset
TI nuevo; nunca recuperar plaintext ni logs.

Pendientes de producción: ratificar TTL/canal, UX React, bloqueos escalonados,
recuperación de única TI, retención/privacidad de eventos, controles proxy/APM,
TLS confiable y autorización expresa de despliegue. El CI remoto solo podrá
atribuirse a esta fase tras verificar el SHA publicado y sus ejecuciones reales.
