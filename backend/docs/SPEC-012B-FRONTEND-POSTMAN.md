# Integración frontend y pruebas Postman — SPEC-012B

## Frontend (guía, no implementación)

- Autenticar con JWT versionado vigente. Nunca usar usuario Mongo ni scanner.
- Obtener ID de Obra/DocumentoCobro de las APIs existentes, sin inventar adjuntos
  desde `referencia_respaldo`. Respetar matriz de roles, pero el backend es autoridad.
- Crear `FormData`; `append('archivo', file)` una vez; nombre_visible opcional.
  No fijar Content-Type manualmente: el navegador agrega boundary.
- Generar UUID para Idempotency-Key por intención de carga. Conservarlo junto con
  los mismos bytes/nombre al reintentar por timeout; no regenerarlo automáticamente.
  Nueva intención/archivo usa UUID distinto. 201 y 200 son éxito con mismo contrato.
- No predecir rutas físicas o públicas. Descargar con Authorization desde endpoint;
  usar Blob temporal y revocar su object URL. No cachear bytes/token en almacenamiento
  persistente del navegador. Content-Disposition es solo presentación saneada.
- Listado/detalle son SQL. Notas pueden responder 409 pendiente; mostrar estado y
  reintentar con espera acotada. Mongo/scanner 503 no vuelve inválido el listado.
- PATCH usa revisión devuelta por GET; 409 CAS requiere recargar y decisión humana,
  no sobrescribir silenciosamente. No enviar campos técnicos, HTML, PII o OCR.
- 413/422 requieren otro archivo; 401 nueva sesión; 403/404 no reintentar en bucle.
  No mostrar mensajes internos ni prometer que un PDF firmado fue autenticado.

## Postman importable

Importar `postman/SPEC-012B.postman_collection.json`. Configurar `base_url`, `token`,
`obra_id`, `documento_id`, `adjunto_id` e `idempotency_key` (UUID canónico manual).
Usar exclusivamente datos/usuarios QA. Importar JSON/ZIP NO transfiere archivos ni
resuelve rutas: abrir cada POST → Body → form-data → `archivo` tipo **File** y
seleccionar manualmente un PDF/JPEG/PNG local real. No añadir Content-Type manual.

1. AF: seleccionar PDF de factura VIGENTE, POST 201; guardar ID. Repetir misma key,
   bytes y nombre => 200 mismo ID; cambiar contenido/key conservada => 409.
2. Supervisor: seleccionar PNG/JPEG de Obra EN_PROCESO; POST 201, listado 200,
   detalle sin hash/clave, descarga attachment con cabeceras privadas. Comprobar
   que imagen descargada no conserva EXIF; PDF descargado conserva bytes originales.
3. Consultar notas: 409 hasta reconciliación; ejecutar worker/pasada, GET 200.
   PATCH revision=0 con descripción técnica => 200/revision=1; repetir 0 => 409.
4. Gerencia lee ambos tipos, POST/PATCH 403. AF no accede a informes, Supervisor
   no accede a facturas, TI no accede a ninguno aunque sea staff/superuser.
5. Técnico miembro activo sube solo EN_PROCESO; desasignado pierde GET/descarga/notas
   y replay (404), incluso de archivos propios. Token revocado/expirado => 401.
6. PDF cifrado/activo, SVG/ZIP/HTML disfrazados, truncados y MIME falso => rechazo.
   No ejecutar malware real. EICAR inocuo se prueba en suite automatizada aislada.
7. En QA aislado, scanner detenido => nuevas cargas 503, descarga existente 200.
   Mongo detenido => notas 503, subida/listado/descarga operativos. Recuperar Mongo
   y reconciliar dos veces, comprobar notas/revisión intactas.
8. Revertir documento por API financiera de QA: descarga histórica funciona,
   nueva carga 409, importes/folio/pagos no cambian por operar adjuntos.

Registrar por ejecución fecha, entorno aislado, rol, request/HTTP esperado/real,
UUID e ID (sin token ni archivo privado). No interpretar esta guía o la colección
importada como una ejecución de Postman aprobada.
