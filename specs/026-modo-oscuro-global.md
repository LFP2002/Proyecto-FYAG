# SPEC-026 — Modo claro/oscuro global y contraste por rol

## 1. Objetivo

Definir el selector de modo claro/oscuro del frontend FYAG y eliminar superficies blancas o textos de bajo contraste cuando se activa el modo oscuro. El tema aplica a todas las páginas y roles autenticados sin ocultar, transformar ni modificar datos del negocio.

## 2. Alcance funcional

- Selector persistente disponible en la barra superior; alterna entre claro y oscuro y expone su estado mediante `aria-pressed` y etiqueta accesible.
- Modo claro se mantiene como opción predeterminada si no existe preferencia guardada. La elección del tema se conserva en `localStorage` con la clave `fyag.theme` y valores permitidos `light` o `dark`.
- El tema oscuro se activa mediante `data-fyag-theme="dark"` en el elemento raíz. El rol autenticado se refleja en `data-fyag-role` solo para seleccionar acentos visuales; no cambia permisos, navegación ni datos.
- Roles cubiertos: Gerencia, Administrativo / Finanzas, Supervisor de Obras, Técnico, Administrador de TI y Bodeguero.
- El CSS de tema debe cargarse después de los estilos de las páginas para sobreescribir colores claros explícitos sin alterar las reglas del modo claro.

## 3. Reglas visuales

- Usar superficies oscuras diferenciadas para fondo, panel, controles, filas y hover; conservar bordes visibles y estados de foco.
- Mantener contraste legible en títulos, etiquetas, cifras, texto auxiliar, placeholders, paginación y estados vacíos.
- Mantener los tonos semánticos de estados (éxito, advertencia, error e información), adaptando fondo y texto a la paleta oscura.
- Aplicar las reglas a tarjetas compartidas, métricas, filtros, toolbars, tablas HTML, filas CSS personalizadas, formularios, diálogos, gráficos y contenido de chat.
- Cubrir componentes con color explícito en sus hojas de página, incluyendo Usuarios y roles, Mermas, Inventario, Egresos, Auditoría, Dashboard, Comercial, Obras, Alertas, Cobranzas y Reportes.
- En componentes de Inventario, conservar distinción visual de iconos y acentos mientras las filas de atención y resumen de mermas usan superficies oscuras.
- Ningún override oscuro se aplica sin el atributo de tema oscuro; el modo claro conserva su presentación existente.

## 4. Seguridad y persistencia

- Solo se persisten preferencias visuales no sensibles: tamaño de letra existente y tema `light`/`dark`.
- No guardar tokens, credenciales, datos de sesión ni información de negocio en almacenamiento local.
- Cambiar tema o rol visual no ejecuta escrituras de negocio, no modifica respuestas de API y no altera autorización.

## 5. Verificación

- Prueba de UI verifica alternancia claro/oscuro, persistencia local y atributo visual del rol autenticado.
- Prueba de CSS verifica carga final del tema, contraste de filtros y fechas, tablas, métricas, estados vacíos, Inventario, Usuarios y Auditoría.
- Ejecutar `npm test` y `npm run build` desde `frontend`; revisar capturas de páginas y roles en ambos temas antes de integrar.
- El build debe completar. Las advertencias preexistentes de tamaño de bundle se registran aparte y no se consideran validación visual.

## 6. Estado de implementación

Implementado en frontend: selector persistente, atributos de tema/rol, paleta oscura con acentos por rol y overrides compartidos para tarjetas, tablas, filtros, formularios, gráficos y estados vacíos. Incluye cobertura específica de superficies observadas en Dashboard, Egresos, Inventario, Usuarios y Mermas. Build y pruebas específicas de tema ejecutadas; la suite completa debe ejecutarse antes de integrar. No implica despliegue ni merge.
