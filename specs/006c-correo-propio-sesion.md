# SPEC-006C — Coherencia de sesión tras cambio del correo propio

**Estado:** corrección implementada en rama `feature/006c-sesion-correo-propio-specs`, **pendiente de CI y validación Postman en entorno local**; no fusionada en `main` hasta completar revisión. Complementa SPEC-006B sin migraciones y sin crear un nuevo endpoint.

## Problema reproducible

Una TI puede editar su propia cuenta con `PATCH /api/usuarios/{id}/`. Cuando cambia `email`, `services_usuarios.editar_usuario` incrementa `sesion_version` y la API responde 200 con correo confirmado. Access y refresh previos se vuelven 401 de inmediato. La vista React antigua intentaba una relectura autenticada después del PATCH; esto generaba un error de sesión y podía ocultar la confirmación visible del correo actualizado.

## Reglas contractuales

1. **Backend prevalece.** `PATCH` de perfil sólo admite campos previstos en SPEC-006B. Cambiar correo propio es permitido a TI autenticada; normalizar con trim/minúsculas y validar formato/duplicados.
2. **Revocación exacta.** Si el correo confirmado difiere del persistido previamente, incrementar una vez `sesion_version`, registrar evento `EDICION` con actor/objetivo y snapshots de correo; access anterior y refresh anterior reciben 401. El login con correo antiguo deja de funcionar; el nuevo requiere el mismo password salvo modificación independiente.
3. **Idempotencia de perfil.** Enviar correo idéntico tras normalización no revoca, no incrementa versión ni crea evento. Cambiar exclusivamente nombre/alias tampoco revoca sesión.
4. **UX de identidad.** Si la respuesta 200 del PATCH indica que **la propia** dirección de acceso cambió, React debe descartar access y usuario localmente, mostrar el login y un aviso de cambio confirmado. No intentar relectura posterior, refresh ni logout con sesión ya invalidada; el frontend no debe afirmar revocación remota si el PATCH no fue confirmado.
5. **Errores y conciliación.** Respuestas 400/409 no anuncian éxito ni invalidan sesión deliberadamente; fallos de red/5xx se consideran resultado incierto. No reenviar automáticamente PATCH: reconsultar o reautenticar según estado. La misma política de abortar y descartar respuestas tardías de SPEC-005A se mantiene.
6. **Confidencialidad.** Ningún aviso, log, test o archivo Postman expondrá contraseñas, tokens, hashes, cookies ni configuración privada. No se guarda sesión en localStorage/sessionStorage. Se preserva `SameSite=Strict` en producción.

## Pruebas de aceptación

- Django/PostgreSQL: cambio de correo propio TI retorna 200 y versión aumenta una vez; auditoría exacta; /me y refresh antiguos 401; login con correo viejo 401 y correo nuevo 200; no-op no altera eventos ni JWT.
- React: formulario de correo propio confirmado → login con mensaje, sin reconsultar historial ni intentar refresh; actualización de otro atributo mantiene sesión; limpieza de contraseña y cierre ante cambio de identidad.
- Postman: colección secuencial con variables desechables, identidad TI de prueba y usuario técnico temporal; pruebas negativas de campos prohibidos, duplicados, accesos indebidos y último TI/Gerencia. **Evitar modificar correo del único TI institucional** en ejecución automática: el cambio propio se verifica mediante una segunda cuenta TI temporal autorizada, con restauración de datos al finalizar o eliminación lógica según política.
- CI: ejecutar `manage.py check`, `makemigrations --check --dry-run`, suite Django/PostgreSQL, pruebas React y build. Estados registrados sólo tras resultados reales.

## Despliegue, recuperación y rollback

Migración de datos: **ninguna**. Cambios acotados a frontend y tests backend. No alterar `auth` ni reglas de negocio. Si la UI o red falla después de un cambio confirmado, autenticarse nuevamente usando el correo actualizado. Si se desconoce la cuenta o el correo, TI autorizada debe seguir el proceso institucional de recuperación; nunca rebootstrap por CLI ni deshabilitar RBAC. El despliegue independiente de React/API debe cumplir CORS/CSRF y cookies same-site. Actualizar el estado a integrado únicamente después de PR, CI y revisión.
