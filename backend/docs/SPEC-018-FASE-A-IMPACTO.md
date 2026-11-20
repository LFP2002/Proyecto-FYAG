# SPEC-018 — Fase A: auditoría de impacto y decisiones previas

Fecha: 20-11-2026. **Antecedente de auditoría estática anterior a implementación.**
Este documento no ratifica parámetros productivos ni modifica SPEC históricas.

**Actualización posterior:** el responsable autorizó expresamente continuar la
Fase A para desarrollo/QA, con credencial temporal de 24 horas, desafío de
5 minutos y entrega manual exclusivamente entre cuentas sintéticas QA. Ambos
TTL son configurables y **NO RATIFICADOS PARA PRODUCCIÓN**. Los bloqueos iniciales
que siguen se conservan como historial, no como pendientes de la autorización
de QA. Estado de código, contratos y pruebas en
`SPEC-018-FASE-A-IMPLEMENTACION.md` y `SPEC-018-FASE-A-CONTRATO.md`.

## Punto de partida verificado

- Rama: `feature/backend-018-seguridad-credenciales`.
- HEAD inicial: `9b34a10ca413ce9d64632d9a0cd63fbce83d71b6`.
- `main` local: `1df5da1bffa57c7fe83b4f16adb2ca6b48a71a23`.
- Árbol inicialmente limpio; sin cambios ajenos que reconciliar.
- Revisadas SPEC-018, 002A/002B, 006/006B/006C; modelo, servicios, serializers,
  vistas, autenticación, permisos, migraciones 0004/0005 y pruebas existentes;
  settings, runner documental, compose QA, AuthContext, cliente auth y Usuarios.
- No se han iniciado servicios, modificado bases, aplicado migraciones ni cambiado
  TLS. No se ha hecho commit, push, merge ni modificación del PR documental #45.

## Decisiones que impiden cerrar el contrato previo a implementación

SPEC-018 §§5.1.6, 7 y 12 exige fijar vencimiento y canal antes de implementar.
La instrucción de Fase A autoriza **300 segundos configurables para el desafío,
provisionales de QA y NO RATIFICADOS**, pero no fija el vencimiento de la
credencial temporal (distinto del desafío) ni el canal permitido TI → titular.

Se requiere decisión expresa sobre:

1. TTL de credencial temporal. La SPEC propone 24 horas, pendiente de ratificación.
   No asumir que 300 segundos de desafío equivale a 300 segundos de credencial,
   ni introducir credenciales sin expiración por omisión.
2. Canal de entrega al titular. La respuesta excepcional HTTPS al TI está definida;
   no define por sí misma cómo TI entrega el secreto al usuario. No asumir email,
   SMS ni chat. Para QA puede autorizarse entrega manual exclusivamente entre
   identidades sintéticas, sin aprobar un canal productivo.

Hasta resolverlos, no se modifica el contrato ejecutable ni se publica código.
Bloqueos escalonados, umbrales, recuperación institucional de única TI y frontend
completo permanecen expresamente fuera de esta fase.

## Incompatibilidades exactas y garantías que deben conservarse

| Superficie actual | Impacto de Fase A | Garantía a preservar |
| --- | --- | --- |
| `CrearUsuarioSerializer.password` y `crear_usuario` exigen clave de TI | Rechazar `password` con 400; generación CSPRNG de al menos 128 bits, hash Django y respuesta excepcional separada | Alta inactiva, contrato estricto, rol persistido, unicidad y evento transaccional |
| `LoginSerializer.validate` siempre emite JWT tras validar usuario activo | Bifurcar antes de emitir tokens: temporal solo obtiene desafío restringido | Credenciales inválidas/inactivas con 401 genérico, normalización email y revalidación bajo lock |
| `validar_sesion` valida actividad, versión y hash | Añadir denegación por estado de credencial no personal | No basta con bloquear frontend; JWT y refresh deben revalidar estado SQL |
| `establecer_clave` permite una nueva clave elegida por TI | Cerrar ruta heredada con transición documentada; no mantener bypass | Motivo, prohibición de autooperación, control TI persistido y revocación |
| `cambiar_clave_propia` presupone sesión normal | Mantener contrato 204 y clave anterior; no sustituye primer cambio | Lock de usuario, hash, incremento de versión, auditoría y nuevo login |
| `editar_usuario` revoca por correo efectivo | Desafíos quedan obsoletos al cambiar versión; no-op no revoca | SPEC-006C, correo normalizado, sin cambios retroactivos |
| `UsuarioEvento.tipo` tiene longitud 24 y constraint de catálogo cerrado | Ampliación aditiva de longitud/catálogo para eventos nuevos | No truncar `CREACION_CREDENCIAL_TEMPORAL`; conservar eventos anteriores y PROTECT |
| Snapshots de auditoría y serializer filtran campos | Nuevos eventos de credencial deben tener snapshots vacíos | Ninguna clave, hash, desafío o JWT en auditoría, GET, logs o errores |
| Pruebas administrativas envían `password` y esperan login operativo tras activar | Actualizar expectativas sustituidas y añadir negativas específicas | No eliminar pruebas de roles, última TI/Gerencia, dependencias y sesiones |
| `frontend/src/auth/client.js` espera `access` y llama a `/me/` en cada login exitoso | Futuro estado restringido independiente de sesión autenticada | No llamar `/me/`, refresh ni negocio con desafío; secretos solo en memoria |
| `Usuarios.jsx` envía password en alta y nueva_clave a establecer-clave | Integración posterior deberá quitar ambos flujos y usar exposición única/reset | No reintentar escrituras inciertas ni recuperar secretos por GET |

## Diseño propuesto, aún no implementado

- Estado de seguridad PostgreSQL 1:1 por usuario: PERSONAL, INICIAL o RECUPERACION.
  `is_active` conserva exclusivamente actividad administrativa. INICIAL y
  RECUPERACION implican cambio obligatorio y vencimiento temporal; PERSONAL no.
  Constraints deben impedir combinaciones imposibles de estado y vencimiento.
- Migración aditiva posterior a `usuarios.0005_administrador_ti`. Cuentas previas
  conservan hash, actividad, rol, versión, relaciones e historial; quedan PERSONAL.
  No generar cuentas ni credenciales en migraciones. Probar ascenso desde 0005.
- Desafío opaco CSPRNG, dominio distinto a JWT; persistir solo digest, identidad,
  versión, expiración y consumo en PostgreSQL. No aceptarlo como Bearer ni en
  refresh. Una emisión posterior debe invalidar los desafíos anteriores aplicables.
- Fijar OpenAPI de Fase A antes de código, incluyendo nombres exactos de campos,
  respuesta temporal diferenciada sin access/refresh, errores genéricos y cierre de
  establecer-clave. No presentar este diseño preliminar como API ya disponible.
- Primer cambio: CSRF efectivo; bloquear usuario y luego estado/desafío en orden
  uniforme; comprobar actividad, estado, digest, TTL, versión y consumo; rechazar
  la misma clave temporal y aplicar validadores Django. Hash nuevo, consumo,
  estado PERSONAL, incremento de versión y evento en una única transacción.
  No iniciar sesión automáticamente; exigir login nuevo.
- Reset TI: mutex administrativo existente → usuarios por PK → estado/desafíos.
  TI activo/persistido y versión vigente bajo lock; motivo; prohibición de reset
  propio; no reactivar, alterar roles ni tocar asignaciones. Rotar credencial,
  invalidar desafíos/sesiones y auditar en la misma transacción. Solo una
  credencial resultante debe permanecer utilizable ante resets concurrentes.
- Login y refresh ya bloquean la fila de usuario. Conservar ese punto común de
  serialización con reset/cambio/correo; jamás adquirir mutex administrativo
  después de un lock de usuario desde autenticación. No bloquear Obras/Finanzas.
- Mantener JWT corto, CHECK_REVOKE_TOKEN, sesion_version, rotación/blacklist,
  refresh HttpOnly/Secure/Strict/path existente, CSRF y throttles. Ningún desafío
  debe generar OutstandingToken operativo. Añadir no-store a respuestas secretas,
  protección de variables sensibles en informes de excepción y tests de filtrado.
- Un reset confirmado invalida tokens anteriores. Si login/refresh confirma antes
  de un reset solapado, puede responder, pero sus tokens deben quedar inválidos
  después del reset; no prometer atomicidad entre commit SQL y entrega HTTP.

## Plan de verificación, no resultados

1. `manage.py check` y `makemigrations --check --dry-run`.
2. Tests de usuarios/autenticación y migración sobre PostgreSQL QA real.
3. Carreras con conexiones independientes, barreras y bloqueo PostgreSQL observado,
   siguiendo `test_concurrencia_006.py`, sin sustituir por SQLite o sleeps:
   primer cambio doble; emisión/consumo y expiración; reset/login y reset/refresh
   en ambos órdenes; reset/reset; cambio propio/revocación; correo/primer cambio.
4. Pruebas de permisos por cada rol, flags Django sin TI, no enumeración, CSRF,
   lectura sin secretos, auditoría y rollback completo si falla el evento.
5. Suite backend completa con `DocumentalTestRunner` existente, Mongo QA autenticado
   separado y ClamAV exclusivo. Compose standalone con proyecto nuevo, secretos
   externos y sin volúmenes principales ni puertos host; nunca combinar con compose
   principal ni ejecutar `down -v`.
6. OpenAPI coherente, contrato frontend exacto, diff --check y escaneo de secretos.
   Registrar resultados reales; solo entonces considerar commit/push a la rama
   autorizada. No atribuir las 874 pruebas históricas a una ejecución de Fase A.

## Estado de esta auditoría

Solo se ha creado este informe de impacto. No hay endpoints ni migraciones nuevos,
no se han ejecutado tests de esta fase y SPEC-018 no se declara implementada.
Pendiente autorización de TTL temporal y canal de entrega antes de continuar.

### Hallazgo posterior de integración SQL

La primera regresión completa de implementación encontró siete presupuestos SQL
incumplidos por leer el estado 1:1 en una segunda consulta. La corrección propuesta
precarga `seguridad_credencial` al autenticar JWT y en las revalidaciones existentes
de `apps.documentos.permissions` y `apps.adjuntos.permissions`, sin alterar RBAC,
sin locks adicionales y sin relajar límites de tests. El estado debe provenir de
la misma lectura SQL del usuario, nunca de claims o de un cache entre peticiones.
Resultados efectivos de las repeticiones en el informe de implementación.
