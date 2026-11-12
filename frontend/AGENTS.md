# AGENTS.md — Reglas obligatorias para IA y desarrollo del frontend FYAG

> **Ámbito:** todos los archivos y subdirectorios de `frontend/`. Dirigido a cualquier asistente de IA, agente de código o persona que colabore en el frontend. Leer **antes** de proponer, ejecutar o publicar cambios. Estas reglas son parte del proceso de trabajo, no un prompt que autorice tareas por sí solo.

## 1. Responsabilidades, límites y fuentes de verdad

- **Equipo frontend + su IA:** arquitectura y código React/Vite, integración de APIs existentes, UX/UI, accesibilidad, estilos, tests y documentación correspondiente.
- **OpenCode:** implementación del backend Django/DRF/PostgreSQL y sus pruebas; el frontend no modifica backend por iniciativa propia.
- **Responsable del proyecto:** aprueba alcance, decisiones de negocio, especificaciones, publicación y **cada merge**.
- **Revisión externa:** puede auditar specs, código, GitHub Actions y pruebas. No sustituye la autorización del responsable.
- **Fuentes de verdad:** `specs/` para el contrato aprobado; código/serializers/OpenAPI del backend **integrado en `main`** para el comportamiento disponible; `frontend/src/auth/` para el protocolo actual de sesión. Los prototipos, capturas, mocks, ramas sin integrar y textos históricos **no** prueban que un endpoint exista.
- Ante ambigüedad o contradicción entre SPEC, API real y seguridad: **detenerse, informar con evidencia y solicitar definición**, no improvisar contratos, permisos o reglas.
- Excepción mínima al ámbito frontend: crear o actualizar la **SPEC de frontend en `specs/`**, mediante el flujo documental indicado. No modificar `backend/`, modelos, migraciones, `compose.yaml`, permisos, workflows ni configuración global sin aprobación explícita y coordinación con el propietario.

## 2. Prohibiciones absolutas para la IA

1. **NO ejecutar merge, squash, rebase sobre `main`, cherry-pick a `main`, push a `main` ni cierre/eliminación de ramas o PR sin autorización expresa del responsable.** Que el CI esté verde NO equivale a autorización.
2. **NO comenzar una funcionalidad sin una SPEC aprobada**. No inventar una API para hacer coincidir el frontend ni reinterpretar reglas de negocio existentes.
3. **NO editar código backend, base de datos, autenticación del servidor ni configuración de infraestructura** para resolver unilateralmente un problema de frontend.
4. **NO subir archivos `.env`, contraseñas, tokens, cookies, claves, datos personales reales, volcados de base de datos, capturas sensibles, certificados, archivos privados o artefactos generados.** No utilizar `git add -A` sin inspeccionar el staging.
5. **NO guardar JWT access/refresh, CSRF, contraseñas ni identificadores de sesión sensibles en `localStorage`, `sessionStorage`, IndexedDB, querystrings, logs o variables públicas `VITE_*`.** No trasladar refresh fuera de su cookie HttpOnly.
6. **NO quitar ni debilitar CSRF, CORS, comprobación de origen, HTTPS, política de cookies, validación del servidor, expiración/rotación de tokens ni control de permisos** para hacer pasar un flujo.
7. **NO calcular en React precios, impuestos, saldos, costos, rentabilidad, aprobación, vigencia o estados del negocio** cuando son responsabilidad de Django. Mostrar exactamente los datos y estados contractuales.
8. **NO mostrar mocks, métricas fijas, datos de prueba o mensajes de éxito como si fueran información productiva**. Un módulo sin API integrada debe marcarse como integración pendiente.
9. **NO exponer enlaces directos a evidencias privadas ni construir URLs de descarga con tokens**. Utilizar el endpoint autorizado y transporte de archivos prescrito por su SPEC.
10. **NO editar o borrar tests para ocultar fallos**, declarar pruebas que no se ejecutaron, inventar resultados de CI/Postman o introducir soluciones que solo funcionen con una cuenta privilegiada.
11. **NO hacer cambios masivos, refactors ajenos, renombrados, nuevas dependencias o cambios al diseño fuera de alcance** sin explicitar el motivo y obtener aprobación.
12. **NO hacer commit, push ni abrir PR automáticamente cuando el encargo solo pide análisis, SPEC o informe**. Respetar la etapa de autorización indicada por el responsable.

## 3. SPEC primero: contrato obligatorio de toda nueva funcionalidad

Antes de programar una función nueva, integración de módulo, cambio significativo de UX, permisos o contrato HTTP:

1. Revisar todas las SPEC relacionadas en `specs/`, la rama `main`, los endpoints reales, las pruebas y las pantallas actuales. No duplicar una SPEC ya existente ni asignar una numeración que colisione.
2. Crear una **SPEC formal versionada en `specs/`** usando la misma estructura, precisión y nivel técnico de `specs/005a-frontend-autenticacion.md`, `specs/005b-frontend-comercial.md` y `specs/005c-frontend-obras.md`. Si la función está cubierta por una SPEC existente, ampliar esa SPEC de manera trazable; no generar documentos redundantes.
3. La SPEC debe contener como mínimo: estado y contexto comprobado, objetivo/alcance y exclusiones, matriz de roles, API exacta (métodos, URLs, parámetros, payload, schemas, errores, paginación), pantallas y estados de UX, seguridad/privacidad, accesibilidad/responsividad, manejo de concurrencia y fallos, arquitectura por componentes, plan de pruebas, criterios de aceptación, riesgos, referencias al código y procedimiento de integración.
4. Distinguir **endpoint existente e integrado** de **endpoint futuro en SPEC de backend**. Si falta un endpoint, comunicarlo al responsable y al equipo backend; no modificar backend para fabricarlo ni construir una versión alternativa en React.
5. Publicar la SPEC en una rama `docs/spec-<id>-frontend-<tema>` mediante PR documental con descripción real y **sin código de la funcionalidad**. Dejar pendiente el merge hasta autorización expresa.
6. **Avisar al responsable que hay una SPEC nueva en GitHub y qué rama debe actualizar en su PC.** Tras merge de documentación autorizado, indicar `git switch main` y `git pull --ff-only origin main`.
7. Solo comenzar el código una vez aprobada e integrada la SPEC y recibido el encargo de implementación. Para errores internos sin cambio funcional, bastará registrar análisis y actualizar la SPEC existente si el contrato se altera; no inventar nuevas SPEC para cada corrección trivial.

La SPEC define el *qué* y los contratos verificables; la implementación decide el *cómo*, respetando esos límites. Ningún asistente puede aprobar su propia SPEC.

## 4. Flujo obligatorio de trabajo con Git y revisión

**Secuencia:** análisis → SPEC → aprobación y merge documental autorizado → rama feature desde `main` actualizado → implementación y pruebas → informe exhaustivo **antes del primer commit/push de código** → revisión del informe → commits descriptivos y push → PR de código → revisión de diff/CI → Postman o E2E cuando aplique → correcciones → merge autorizado.

1. Al iniciar: `git status`, `git branch --show-current`, `git fetch origin`; comprobar si hay trabajo local de otra persona. **No sobrescribir, resetear ni hacer stash del trabajo ajeno sin permiso.**
2. Crear rama `feature/frontend-<spec>-<tema>` desde `origin/main` actualizado. Trabajar únicamente allí; no utilizar `main` ni una rama de backend para desarrollar UI.
3. Limitar cada cambio a una funcionalidad; mantener componentes, servicios HTTP, autenticación, estado de presentación y pruebas separados. Seguir patrones existentes antes de crear capas nuevas.
4. Al terminar desarrollo local, entregar **informe técnico previo a publicación**: alcance real, archivos, decisiones, pantallas, contratos API utilizados, permisos, tests ejecutados con resultados, problemas, riesgos, screenshots de datos no sensibles cuando ayuden y rollback. **Detenerse para revisión.**
5. Solo después de la aprobación del informe, preparar commits convencionales y atómicos con mensajes precisos, p. ej. `feat(frontend): integrar bandeja de alertas con API real`, `test(frontend): cubrir permisos y estados de error`, `docs(spec): actualizar criterios verificados`. No crear commits ficticios para seguir un ejemplo.
6. Hacer push de la feature y abrir PR hacia `main` con propósito, decisiones, diff, contratos, seguridad, pruebas locales, estado CI, riesgos y pasos de validación. **No crear PR de código hasta la revisión previa del informe**.
7. Revisar GitHub Actions reales. Si fallan, corregir sobre la rama; nunca afirmar `passed` a partir de expectativas. Postman, si procede, valida API y no sustituye UI/E2E; el responsable comunica resultados.
8. Solicitar aprobación explícita para cada merge; después de ella, verificar el merge realmente en GitHub, avisar que hay cambios para actualizar localmente y documentar la versión integrada. **Nunca automezclar ni borrar ramas por conveniencia.**
9. No usar `git push --force`, reset destructivo ni cambios de historial compartido salvo autorización expresa y procedimiento acordado. Revisar siempre `git diff --cached` antes de publicar.

## 5. Integración con Django y contratos del backend

- Usar `/api/...` y el cliente HTTP/autenticación existentes, incluidos `frontend/src/auth/client.js`, `AuthContext.jsx` y `frontend/vite.config.js`; no inventar un segundo sistema de autenticación o permisos.
- El proxy Vite de desarrollo conserva Host y Origin por CSRF. No cambiar `changeOrigin` para ocultar errores ni abrir CORS a todos. En producción se requiere infraestructura HTTPS y una configuración explícitamente aprobada.
- El backend es autoridad para rol, acciones permitidas, estados, validaciones y cálculos. Las restricciones visuales del menú son experiencia de usuario, **no seguridad**. Nunca mostrar información restringida aunque llegue por error en una API.
- Emplear schemas estrictos, validación de forma de respuesta y filtros/paginación reales; no asumir que el backend devuelve listas completas ni que un dato es no nulo sin respaldo de SPEC.
- Preservar IDs/códigos y valores decimales exactos como strings cuando lo define el backend; **no convertir dinero a Number para recalcularlo** ni confundir importes netos y brutos.
- Separar estado cargando/vacío/error/sin permiso/datos obsoletos; no presentar respuesta desactualizada como confirmación de una mutación.
- En `401` usar el flujo de restauración/refresh propio del cliente; en `403` mostrar falta de permiso sin escalar; en `404` no revelar recursos; en `409` volver a consultar y exigir nueva decisión del usuario. Un timeout o error de red **no prueba** que la escritura se haya revertido: reconsultar antes de cualquier repetición.
- Cancelar solicitudes al desmontar o cambiar de sección y descartar respuestas tardías; prevenir duplicados por doble clic. No reintentar silenciosamente POST/PATCH/DELETE salvo que el contrato documente expresamente idempotencia.
- Fotografías y exportaciones: validar tipo/tamaño según SPEC; no copiar URLs internas o identificadores de almacenamiento. Descargas autenticadas mediante cliente compatible con Blob cuando la API lo exija; nunca Bearer en querystring.

## 6. Seguridad de sesión, privacidad y entradas de usuario

- **Access JWT solo en memoria** del cliente existente; refresh exclusivamente por cookie HttpOnly gestionada por Django. El cierre de sesión debe invalidar inmediatamente el estado local. Respetar `sesion_version` y el flujo de cambio de correo propio que revoca la sesión.
- Peticiones de login, refresh y logout respetan CSRF, incluido token rotado tras login. No leer cookies HttpOnly con JavaScript ni crear bypass del control CSRF.
- No registrar en consola, reportes, capturas de PR ni errores tokens, passwords, cookies, header `Authorization`, RUT, cuentas personales, fotografías privadas o payloads sensibles. Usar datos sintéticos, seudónimos y IDs no identificables en documentación.
- Evitar HTML dinámico sin saneamiento; no usar `dangerouslySetInnerHTML` con datos de servidor, `eval`, scripts externos ni `target="_blank"` sin protecciones cuando correspondan. Preferir escape estándar de React y validación de URL/origen confiable.
- No incorporar secretos en `VITE_*`, ya que terminan expuestos en el bundle público. `frontend/.env` es **local e ignorado**; no volver a versionarlo. Usar archivos `.env.example` sin valores reales cuando se acuerde una nueva variable.
- Analizar dependencias nuevas por necesidad, mantenimiento, versión y superficie de ataque. No añadir librerías arbitrarias para resolver cuestiones que cubre React/Vite/Bootstrap existente.
- No crear rutas UI privilegiadas accesibles por suposiciones de usuario. Revalidar sesión y permisos al cambiar la cuenta, y limpiar datos sensibles tras logout o invalidación.

## 7. Calidad de UI, accesibilidad y rendimiento

- Mantener diseño coherente, legible y adaptable; verificar al menos 320, 375, 768 y 1024 px. No romper navegación ni barras móviles.
- Controles con etiquetas accesibles, foco visible, navegación por teclado, Escape cuando proceda, `aria-current`/ `aria-expanded` cuando corresponda; feedback claro de carga, error y confirmación. Prohibido agregar botones que aparenten funcionar pero no tienen acción.
- Evitar tablas que desborden móviles, errores visuales de porcentajes, superposición de modales, acciones duplicadas, indicadores sin fuente real, estados de carga infinitos y pantallas vacías silenciosas.
- No introducir renders o requests redundantes, consultas N+1 en cliente, cachés de PII persistentes o carga masiva de resultados ignorando paginación.
- Reutilizar componentes y tokens visuales existentes cuando sean útiles; cambios de diseño sustanciales requieren aprobación de alcance, sin reescribir lógica de dominio por estética.

## 8. Pruebas y evidencia obligatoria

Para cualquier cambio de código frontend, ejecutar desde `frontend/`:

    npm ci
    npm test
    npm run build

`npm ci` se necesita al preparar dependencias o al cambiar `package-lock.json`; en iteraciones sucesivas sin cambios, pueden bastar `npm test` y `npm run build`. El repositorio utiliza runner nativo de Node para pruebas actuales y workflow `.github/workflows/frontend-ci.yml`.

Añadir pruebas según el cambio: autenticación y expiración, roles G/AF/S/T/TI, cliente HTTP, respuestas válidas/inválidas, `400/401/403/404/409/5xx`, tiempos de espera, concurrencia, estados UI, paginación, render, permisos, navegación móvil y regresiones de módulos previos. Validar manualmente flujo real con cuentas de **desarrollo** cuando aplique. Las pruebas con mocks verifican lógica de frontend; no demuestran que exista una API backend. **No atribuir a Postman pruebas E2E de interfaz.**

En el informe diferenciar `ejecutado y aprobado`, `ejecutado y fallido` y `no ejecutado`. La falta de pruebas nunca se convierte en éxito por redacción.

## 9. Preparación local y referencias

Desde la raíz del repositorio, con Docker Desktop y entorno configurado, el backend de desarrollo se levanta mediante:

    docker compose up -d

Desde `frontend/`, con Node.js 20+:

    npm ci
    npm run dev

Vite escucha normalmente en `http://localhost:5173`; backend local en `http://localhost:8000`, proxy de `/api` ya definido. Para detener contenedores: `docker compose down`, **sin `-v`** salvo autorización expresa (eliminaría datos persistidos).

Archivos relevantes: `frontend/src/app.jsx`, `frontend/src/auth/`, `frontend/src/pages/`, `frontend/src/components/`, `frontend/tests/`, `frontend/vite.config.js`, `specs/005a-frontend-autenticacion.md`, `specs/005b-frontend-comercial.md`, `specs/005c-frontend-obras.md`. `frontend/REVIEW-005C-1.md` es **informe histórico**, no descripción automática del estado actual del producto.

No asumir que el frontend tiene integrados los módulos solo porque la API está lista: consultar `frontend/src/app.jsx`, las rutas actuales y las SPEC correspondientes.

## 10. Formato obligatorio de respuesta de la IA

Antes de tocar archivos: indicar qué SPEC se aplica, alcance exacto, estado de backend y archivos que piensa modificar. Si falta SPEC aprobada, **entregar primero la SPEC y detener la programación**.

Después de implementar, pero **antes de commit/push**, entregar un informe de revisión que incluya: alcance, archivos cambiados, contratos, consideraciones de seguridad, decisiones de UX, pruebas con resultados verificables, riesgos, impacto y pendientes. Detenerse y pedir autorización para publicar.

Tras commit/push, comunicar SHA, enlace del PR y estado real de CI; no realizar merge sin una autorización posterior explícita. Cuando se suban o integren SPEC o código, informar qué rama debe actualizar el responsable en su PC.

**Regla final:** ante la duda, conservar el trabajo ajeno, respetar el backend, proteger la información y solicitar una decisión documentada antes de realizar cambios irreversibles.
