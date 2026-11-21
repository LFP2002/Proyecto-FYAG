# SPEC-018C C2 — contrato futuro para equipo frontend

> Histórico de diseño C1. La integración posterior C2, **solo QA y apagada por
> defecto**, se documenta en [contrato de consumo C2](SPEC-018C-C2-CONSUMO.md).
> Implementa perfil QA 401 genérico; las propuestas 423 siguientes no se activan.

**PROPUESTA, NO IMPLEMENTADA NI CONSUMIBLE TODAVÍA.** C1 solo aporta persistencia
y motor aislado. Mantener consumo actual de [Fase A](SPEC-018-FASE-A-CONTRATO.md).
No inferir que hay 423, endpoints nuevos, campos de bloqueo o recuperación C2.
Los umbrales 5/15 min, 15/60/240 min y cuarto ciclo en 24 h están ratificados;
no están ratificadas las siguientes decisiones de comunicación/operación.

Artefacto OpenAPI 3.1 de diseño:
[SPEC-018C-C2-propuesta.json](openapi/SPEC-018C-C2-propuesta.json), con `paths` vacío
y operaciones candidatas en extensión x-futuro, para no declarar rutas implementadas.
No sustituye ni cambia el OpenAPI vigente SPEC-018A-v1.json.

| Operación candidata C2 | Propuesta, sujeta a cierre de seguridad |
| --- | --- |
| POST `/api/auth/login/` | 401 genérico actual para clave incorrecta/inexistente/inactiva/NO_DISPONIBLE. Solo tras verificar clave correcta, evaluar si se acepta 423 bloqueo_temporal con disponible_desde o solicitar_ti. Alternativa: conservar 401 y canal institucional. No emitir JWT/refresh/desafío cuando se deniegue. |
| GET `/api/usuarios/` y `/{id}/` | Solo TI, eventual estado_acceso y bloqueado_hasta nullable. No exponer contadores sensibles en `/me/` ni negocio. Estado NO_DISPONIBLE no equivale a NORMAL. |
| POST `/api/usuarios/{id}/restablecer-clave/` | Solo TI activo, vigente y autorizado, cuenta ajena, motivo y verificación institucional del titular. Liberar bloqueo únicamente con reemisión confirmada, revocación/auditoría atómicas; no activar is_active. Respuesta excepcional con temporal como Fase A, sin sesión automática. |
| `/desbloquear-seguridad/` | No implementado; no recomendar desbloqueo simple de REQUIERE_TI. Exige decisión separada. |

Mientras no se ratifique 423, el equipo frontend **no debe depender de él**.
Contrato final debe fijar ejemplos, schemas, errores, permisos, headers, paginación,
idempotencia y comportamiento ante estado ausente antes de integrar pantallas.
No devolver información diferenciada de bloqueo antes de verificar suficientemente
identidad: conocer email no debe permitir enumerar cuentas.

Preservar JWT access solo en memoria, cookie refresh HttpOnly/Secure/Strict/path
`/api/auth/`, CSRF rotado y header vigente para login/refresh/logout/primer cambio;
CORS explícito con credentials no habilita cookies cross-site Strict. TI usa Bearer
válido; flags staff/superuser no conceden TI. Sin cambios en cinco roles.

Cliente futuro: no almacenar contraseñas, desafíos o tokens en storage/URL/logs.
No recalcular permisos o desbloqueo usando reloj local; servidor decide vencimiento.
429 no significa contraseña incorrecta ni un ciclo. No repetir automáticamente
alta/reset/cambio ante red/5xx; reconciliar resultado incierto. Descartar respuestas
tardías al cambiar identidad. Definir qué ocurre con access ya emitidos según
decisión C2; C1 no garantiza su denegación por bloqueo.

QA C2/C3 pendiente: Postman local con cuentas sintéticas y plan de recuperación TI;
navegador real para cookies, CORS/CSRF, navegación atrás y limpieza de memoria.
No escribir pruebas destructivas contra una única TI institucional ni publicar
colecciones que activen bloqueo definitivo por defecto.
