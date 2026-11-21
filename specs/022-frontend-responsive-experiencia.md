# SPEC-022 — Presentación responsive del frontend FYAG

> **Estado: propuesta descriptiva para revisión y aprobación.** Documenta el trabajo local de presentación y la integración visual de Inventario/solicitudes. La existencia de código y pruebas locales no implica aprobación funcional, merge, despliegue ni validación E2E en un entorno institucional. El archivo `.env.example` ya estaba eliminado en el árbol de trabajo al redactar esta SPEC y queda fuera de alcance.
>
> **Frontera:** cambios exclusivamente en `frontend/` y este contrato. No cambiar roles persistidos, políticas ni endpoints del backend, no alterar otros contratos de negocio y no incluir secretos o datos productivos.

## 1. Objetivo

Ofrecer una interfaz ordenada y usable en móvil, tablet y escritorio, conservando la autoridad de los servicios actuales. Reducir rótulos y repeticiones visuales cuando no aportan contexto; aplicar Bootstrap 5 y Bootstrap Icons; permitir que cada usuario autenticado seleccione tema, tamaño de letra y fuente.

La respuesta del backend sigue siendo la fuente de verdad para identidad, permisos, datos, estados, importes, validaciones e idempotencia. La presentación no calcula ni simula resultados empresariales.

## 2. Alcance implementado localmente

### 2.1 Capa visual compartida y preferencias

- Dependencia `bootstrap-icons`; el punto de entrada carga su hoja de iconos y Bootstrap CSS.
- `BootstrapIcon` es el wrapper de uso común. Navegación y controles de apariencia usan iconos Bootstrap en vez de glifos/paths SVG locales donde ya se integraron.
- Preferencias con valores acotados: tema claro/oscuro, cuatro tamaños legibles y fuentes Sistema, Serif y Humanista.
- La preferencia se guarda en `localStorage` bajo una clave propia de apariencia por ID de usuario; solo contiene tema/fuente/escala. Nunca guardar JWT, refresh token, contraseña, datos de negocio o respuesta de API.
- La interfaz ofrece el selector compacto en la barra superior y el panel de apariencia en navegación; el flujo del Técnico conserva acceso al selector.
- Tema oscuro con tokens CSS, superficies, texto, controles, tablas y estados. Los cambios de escala y fuente se aplican al root y heredan desde allí.
- Los breakpoints existentes del shell mantienen navegación plegable en móvil y rejilla de navegación al abrir el menú.

### 2.2 Orden y adaptación responsive

- La capa compartida usa utilidades Bootstrap para filas, columnas, espacios, alineación, grupos de controles, botones e indicadores.
- Formularios y filtros se distribuyen en rejillas que reducen columnas según ancho disponible.
- Las tablas conservan sus columnas y contratos, usan región desplazable con etiqueta accesible y no deben forzar el viewport completo a desplazamiento horizontal.
- Las tablas de ítems que tienen atributos `data-label` pueden presentarse como tarjetas en pantallas pequeñas; tablas extensas siguen siendo desplazables dentro de su región.
- Clientes elimina el texto de orientación redundante, mantiene la acción de actualizar, y evita volver a repetir nombre legal/estado en los atributos de detalle. Los controles, textos accesibles y acciones existentes se conservan.
- Alertas agrupa sus filtros en un panel Bootstrap plegable, mantiene resumen conciso, lista responsive y detalle/historial bajo demanda. No se altera la matriz ni se infieren acciones desde el cliente.
- Cobranzas agrupa filtros en una rejilla Bootstrap, separa actualización, presenta indicadores en columnas adaptables y reduce rótulos monetarios redundantes en encabezados. No se cambian los schemas financieros ni permisos.
- El resto de páginas comparte las reglas de layout responsivo comunes sin cambios en la lógica de negocio.

### 2.3 Integración visual de Bodega e Inventario

- La navegación reconoce `BODEGUERO`, ya definido por backend; añade el módulo Inventario a los menús de Bodeguero, Supervisor, Gerencia y Administrativo/Finanzas según los endpoints disponibles.
- Inventario presenta las colecciones de artículos, existencias, movimientos, solicitudes, autorizaciones, entregas, devoluciones y valorización con paginación y proyecciones de campos por sección/rol.
- Acciones visibles se limitan en frontend por rol, pero cada operación sigue sujeta a la autorización backend. Los costos no se proyectan en vistas no autorizadas.
- Las solicitudes de Técnico se integran en la ficha de Obra y consultan únicamente el catálogo solicitables y la colección de solicitudes. La creación requiere Técnico y Obra en proceso; Supervisor puede decidir solicitud con motivo e idempotencia, conforme al endpoint existente.
- Las respuestas de inventario usan las rutas bajo `/api/inventario/`; el cliente rechaza enlaces de paginación con filtros/orígenes no permitidos.

## 3. Matriz de interfaz

| Rol | Navegación Inventario | Acciones de UI previstas |
| --- | --- | --- |
| BODEGUERO | Artículos, existencias, movimientos, autorizaciones, entregas y devoluciones | Altas/ingresos y actos físicos según endpoints 019A/019B; sin columnas de costo |
| SUPERVISOR_OBRAS | Existencias, solicitudes, autorizaciones y devoluciones | Aprobar/rechazar solicitudes y autorizar entrega/devolución según permisos backend |
| ADMINISTRATIVO_FINANZAS | Existencias y valorización | Valorar ingresos y regularizar valoración inicial; lectura de valor según endpoint |
| GERENCIA | Lecturas de inventario y solicitudes autorizadas | Solo lectura; importes solo en respuestas autorizadas por backend |
| TECNICO | Mis Obras | Solicitar materiales desde una Obra participante y operativa; sin lectura general de inventario/costos |
| ADMINISTRADOR_TI | Sin módulo de negocio | No se amplía acceso a Inventario |

La matriz documenta visibilidad de interfaz, no sustituye RBAC en servicios. Si la matriz difiere de `permissions.py`, el servidor prevalece; corregir UI para reflejar su contrato y no ampliar acceso mediante cambios frontend.

## 4. Contratos backend que se consumen

Rutas incorporadas en la interfaz, con barra final:

- Base: `/api/inventario/articulos/`, `/existencias/`, `/movimientos/`, `/ingresos/`.
- Operaciones 019B: `/autorizaciones-entrega/`, `/entregas/`, `/autorizaciones-devolucion/`, `/devoluciones/`, `/valorizaciones/`, `/regularizaciones-iniciales/`.
- Solicitudes 019C-1: `/articulos-solicitables/`, `/solicitudes-materiales/`, `/solicitudes-materiales/{id}/`, `/solicitudes-materiales/{id}/decidir/`.
- Listados siguen paginación de 25 y filtros definidos por endpoint. POST usa cargas cerradas con cantidades string decimal y `clave_idempotencia` UUID cuando el contrato la exige.
- No se incluyen rutas de mermas 019C-2, puesto que el backend actual no las expone.

Fuentes contractuales primarias: SPEC-019A, SPEC-019B, SPEC-019C-1, contratos 004/004B y código/rutas/serializers/permissions del backend presente en la rama objetivo.

## 5. Exclusiones y salvaguardas

- No modificar `backend/`, migraciones, modelos, permisos, serializers, OpenAPI ni contratos de negocio.
- No cambiar quién puede aprobar presupuestos, registrar pagos, modificar Obras, categorías, alertas o usuarios.
- No inferir autorizaciones desde navegación, claims JWT, `is_staff` o `is_superuser`; esconder una acción no reemplaza el permiso backend.
- No crear datos, credenciales, inventario de demostración, nombres de artículos, saldos o importes ficticios.
- No implementar UX de mermas 019C-2 hasta que existan endpoints y contrato backend correspondiente.
- Mantener sesión/token fuera de almacenamiento web persistente. Preferencias visuales son la única excepción de persistencia local y se aíslan por cuenta.
- Mantener navegación por teclado, etiquetas de formulario, regiones de tabla accesibles, foco visible, mensajes de error y estados de carga.

## 6. Criterios de aceptación

1. Build de producción de Vite completa sin error.
2. Suite frontend completa pasa; no se rompen pruebas de autenticación, RBAC visual, paginación, escrituras inciertas, finanzas, obras o usuarios.
3. `git diff --check` no informa errores de whitespace.
4. Tema oscuro mantiene contraste legible de texto, encabezados de tabla, filas, controles y estados; tema claro mantiene legibilidad equivalente.
5. Preferencias de apariencia se mantienen por usuario y no incluyen secretos/token/datos de API.
6. A 320–400 px no se desborda el shell; filtros se envuelven y tablas quedan dentro de regiones desplazables accesibles.
7. A 768 px y escritorio el contenido aprovecha rejillas Bootstrap sin solapamiento entre filtros, acciones y tablas.
8. Solicitudes/inventario consumen los endpoints indicados; no muestran costo fuera de las proyecciones autorizadas ni exponen acciones para roles no escritores.
9. Validar manualmente con backend de QA y usuarios de prueba por rol antes de declarar E2E. Build y tests simulados no demuestran por sí solos login con cuentas reales, permisos del servidor, datos cargados ni apariencia en navegadores.

## 7. Verificación local registrada

En el árbol de trabajo se ejecutaron `npm test` (210 pruebas aprobadas), `npm run build` (correcto) y `git diff --check` (sin errores de whitespace). Estas verificaciones no son CI, prueba visual automatizada, E2E autenticado ni aprobación del responsable.

## 8. Entrega y rama

Rama sugerida: `feature/frontend-responsive-bootstrap-icons`.

Incluir únicamente cambios intencionados en `frontend/` y esta SPEC. Revisar y excluir expresamente `.env`, `.env.example` (borrado preexistente en el árbol), `dist/`, archivos de secretos y cualquier cambio ajeno. Crear commit/push solamente después de que el responsable apruebe esta SPEC y el diff final. No hacer merge ni despliegue con esta documentación.
