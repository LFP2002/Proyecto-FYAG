# Instrucciones para OpenCode — Implementación SPEC-008 Auditoría global

**Uso:** el responsable del proyecto copia estas instrucciones a OpenCode cuando autorice el inicio de programación. ChatGPT preparó el contrato y hará revisión técnica; **OpenCode es el implementador**. El equipo frontend no debe modificar backend ni inventar endpoints.

## Prompt listo para OpenCode

Actúa como ingeniero de software senior especializado en Django 5.x, Django REST Framework, PostgreSQL y seguridad de APIs. Trabaja sobre el repositorio **Proyecto-FYAG**, a partir de la rama `main` actualizada, respetando el flujo de Git y los commits/PR descriptivos exigidos por el responsable del proyecto.

### Objetivo

Implementar exclusivamente **SPEC-008 — Auditoría global federada**, utilizando el contrato vigente en `specs/008-auditoria-global-api.md` dentro de la rama documental `docs/spec-008-011-contratos-backend-restantes` o su versión ya fusionada en `main`. **Antes de programar, confirma si el documento está en main; si no, inspecciona la rama documental, sin modificarla ni declarar aprobado el PR #26.** Lee `specs/008-011-mapa-backend-pendiente.md`, `specs/006b-administrador-ti.md`, `backend/config/urls.py`, los modelos/serializers/permissions de `apps.comercial`, `apps.obras`, `apps.finanzas`, `apps.usuarios` y el CI existente.

No toques SPEC-009/010/011 ni la integración React: este incremento es **solo backend**.

### Pasos de trabajo requeridos

**Fase 1 — Auditoría de contratos y plan (SIN editar código):**
1. Comprueba los ocho modelos evento existentes y los campos reales de PK de recurso, actor, tipo, fecha y snapshots. PresupuestoEvento NO tiene campo `tipo`: derivarlo de estados; Costos y Finanzas usan FK tipadas, nunca confundir sus PK con ID de Obra.
2. Revisa por rol qué campos de cada fuente ya son visibles bajo permisos del backend. Compara con los serializers existentes; selecciona una whitelist mínima. Señala cualquier discrepancia concreta con SPEC-008.
3. Estudia la paginación federada que funcione con PostgreSQL real sin cargar todas las filas, el orden de desempate, y la semántica de consistencia documentada (no prometer snapshot SQL perfecto entre requests).
4. Presenta plan de archivos, alternativas y trade-offs de cursor/seguridad/rendimiento, matriz de pruebas y puntos de riesgo. **Detente para revisión del plan si hay contradicciones materiales con la SPEC. No inventes contratos.**

**Fase 2 — Implementación local (solo después del plan):**
5. Crear una rama propia `feature/backend-008-auditoria-global` desde `main` actualizado. No programar en `main` ni en `docs/spec-008-011-contratos-backend-restantes`.
6. Implementar solo `GET /api/auditoria/eventos/` con autenticación versionada DRF, RBAC por fuente y recurso, filtros estrictos, proyección sin secretos, respuesta JSON con schema exacto y cursor firmado con fecha_corte, identidad/rol y PK watermarks.
7. Crear adaptadores desacoplados por fuente, capa de servicio orquestadora, serializador público, permisos explícitos y rutas en `apps.auditoria/urls.py` y `backend/config/urls.py`. **Sin migraciones por defecto ni reescritura de servicios de otros dominios.**
8. Reutilizar los modelos/evaluaciones existentes; hacer consultas ORM de PostgreSQL acotadas y evitar N+1. Timestamps de rango en `America/Santiago`, inclusive en días civiles incluso con DST.
9. Entregar `tests` en `apps.auditoria.tests`: oito fuentes, eventos presupuesto con tipo derivado, refs tipadas, whitelists por rol, JWT revocado, cursores manipulados, filtros y métodos denegados, colisiones de fechas, paginación federada/concurrencia y ausencia de writes en GET. Testear con PostgreSQL real; prohibido “simular” carreras con SQLite o sleeps.
10. Los errores deben ser predecibles 400/401/403/405, sin exponer SQL ni permisos. Auditoría de usuarios solo TI, G nunca obtiene cuentas; AF solo Finanzas; S solo Obras; Técnico sin acceso global.
11. No añadir paquetes ni índices sin necesidad demostrada y justificación. Si detectas que un requisito del documento es técnicamente inviable, documentar la contradicción con solución mínima y **solicitar revisión antes de cambiar el contrato**.

**Fase 3 — Verificaciones y entrega para revisión:**
12. Ejecutar y copiar los resultados reales de:
    - `docker compose exec backend python manage.py check`
    - `docker compose exec backend python manage.py makemigrations --check --dry-run`
    - `docker compose exec backend python manage.py migrate --noinput` (solo ambiente de prueba)
    - `docker compose exec backend python manage.py test apps.auditoria`
    - `docker compose exec backend python manage.py test`
    - Si la configuración de Compose del repositorio requiere rutas o nombres distintos, identificarlos sin inventar comandos.
13. Hacer revisión del diff y de los permisos: secretos, PII, SQL sin index, orden, memoria, cursor, serialización, contratos y compatibilidad.
14. Entregar un **informe de revisión previo al commit**, con: listado de archivos modificados, decisiones arquitectónicas, ejemplos JSON reales de test, tablas de resultados reales, riesgos residuales, cobertura exacta de ocho fuentes, filtros admitidos y cómo hacer rollback. **No hacer commit, push ni PR hasta que el usuario y ChatGPT revisen el informe**. No fusionar nada.
15. Tras autorización, proponer commits atómicos y descriptivos y un PR con: motivación, implementación, impacto API/migraciones, decisiones de seguridad, tests, CI y checklist. Describir solo lo realmente ejecutado; no afirmar CI/Postman antes de que pasen.
16. Una vez revisados cambios y CI, ChatGPT preparará y entregará al usuario una **suite Postman completa importable**, sin secretos, con rutas positivas, negativas, filtros, permisos de cinco roles, cursores y regresión, para que él la ejecute y comunique Passed/Failed. No autoaprobar pruebas de Postman.

### Límites explícitos

- No modificar frontend. Tus compañeros de interfaz solo consumirán la API establecida.
- No introducir MongoDB, un modelo global de eventos duplicados o escrituras a través de GET.
- No debilitar CORS, CSRF, JWT/refresh, control de sesión, ni permisos existentes.
- No exponer snapshots crudos de `JSONField`, fotos privadas, contraseñas, hashes, tokens, información ajena ni tarifas restringidas.
- No afirmar que existe cobertura histórica de Clientes o logs de autenticación que todavía no se guardan.
- No declarar SPEC-008 implementada hasta que backend, CI y Postman se revisen y el PR sea fusionado de manera autorizada.
- Si el responsable mantiene la fase “solo diseño”, ejecutar **únicamente Fase 1** y esperar instrucción explícita para programar.

## Entregable esperado del primer contacto

Un diagnóstico de viabilidad y plan de implementación para SPEC-008: fuentes exactas y autorización, validaciones, paginación/cursor, archivos a cambiar, nuevas pruebas, riesgos y preguntas **solo si existen conflictos materiales**. No producir código antes de acordar el plan.
