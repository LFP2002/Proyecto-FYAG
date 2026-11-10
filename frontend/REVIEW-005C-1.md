# Revisión técnica — SPEC-005C-1

Rama: `feature/frontend-005c-obras`. Implementación frontend, sin commits, push ni PR.

## Alcance

- G/S/AF: listado y detalle reales de Obras; T: `/api/obras/mis-obras/` y detalle
  limitado por membresía activa en Django. No se deduce membresía del responsable.
- Filtros **del servidor**: estado, cliente/responsable/categoría por ID, programación
  desde/hasta y orden. Aplicar/limpiar vuelve a página 1; actualizar mantiene la
  consulta. Colecciones e historiales usan páginas DRF de 25, sin seguir URLs externas.
- S: alta desde la proyección de presupuestos disponibles de Obras; categorías activas
  y técnicos disponibles paginados. Descripción operativa nueva, independiente de
  Comercial. PATCH parcial, cambio de responsable por acción dedicada, inicio,
  suspensión y reanudación con motivo. Sin cancelar ni finalizar.
- G/S: participantes y sus historiales, distinguiendo PK de miembro y PK de técnico,
  activos/históricos, responsable y origen de registro. S asigna/reactiva y desasigna
  con motivo, respetando guardias del backend. No se consulta ni implementa Turnos.
- G: alta/renombre/activación/desactivación e historial de categorías. S: consulta;
  AF/T no montan el catálogo ni solicitan sus endpoints.
- AF: proyección mínima explícita; no descripción libre, auditoría ni participantes.
  Ninguna ficha operativa muestra importes comerciales o costos.
- Pestañas permitidas de turnos/evidencia, gastos, costos y finalización muestran
  únicamente **Pendiente de integración frontend** para 005C-2/3. Esas API existen
  en Django; no se presentan como inexistentes ni se ejecutan desde esta entrega.
- Resto de módulos sin integrar conserva `PendingIntegration`.

## Seguridad y contratos

Se reutilizan `useAuth().request`, `createScope` y el hook de solicitudes seguras
de 005B (`useCommercial`, alias `useOperational`), sin otro cliente HTTP, tokens ni
almacenamiento. Cada ficha se monta por identidad/rol/PK; sus scopes cancelan y
descartan respuestas al navegar o cerrar sesión. Los formularios no actualizan
estados optimistamente ni repiten escrituras por red, timeout, 5xx o 409.

El único cambio a `auth/client.js` amplía la lista de **campos públicos saneados**
de errores 400/409 de Obras/categorías y reconoce `sin_cambios`. Era necesario para
no descartar errores de `presupuesto`, `categoria_servicio`, `tecnico_responsable`,
`fecha_programada`, `nombre`, etc. No cambia JWT/CSRF, refresh, epoch ni logout.

Después de escribir se releen ficha y colecciones relacionadas autorizadas. Si la
relectura falla, se informa sincronización pendiente y se bloquean nuevas escrituras
hasta actualizar. El formulario se conserva cuando corresponde. Reconsultar no
repite la operación. Una pérdida de acceso al detalle de T retira la ficha anterior.

Se verificaron serializers, permisos, servicios y pruebas 004A/004B-1. No fue
necesario inventar contratos. Los encabezados históricos de las SPEC-004/004B no
describen el estado actual de todos los bloques. En categorías el serializer permite
motivo omitido/vacío, pero los **cambios efectivos** requieren motivo en el servicio;
la UI sigue esta última regla. Las categorías históricas inactivas no se reenvían
en PATCH si no cambian.

## Prueba E2E con cuentas reales (pendiente de revisión humana)

No se crearon usuarios ni se guardaron credenciales. Se necesitan cuentas existentes
G, S, AF y T y datos de prueba controlados. Los tests automatizados montan componentes
con respuestas controladas; no certifican el recorrido completo en navegador/BD.

1. Iniciar Docker y Vite según `README.md`.
2. **G:** entrar a Obras → Categorías de servicio. Crear una categoría, renombrarla
   con motivo, desactivarla/reactivarla y comprobar su historial. No debe poder crear
   Obras ni cambiar estados, responsable o participantes.
3. **S:** preparar mediante Comercial, con sus roles reales, un presupuesto aceptado
   por cliente y todavía sin Obra. En Obras → Nueva obra, elegir ese presupuesto,
   categoría activa, descripción operativa y fecha opcional. Si se asigna técnico,
   indicar motivo. Verificar el nuevo código/PK y persistencia tras F5. El presupuesto
   utilizado debe desaparecer de los disponibles; no crear otro para eludir el guard.
4. **S:** editar descripción/fecha con motivo; cambiar responsable mediante su acción.
   Iniciar, suspender y reanudar. Comprobar que el inicio real no cambia al reanudar.
   Un turno abierto en datos preparados puede bloquear suspensión o baja: mostrar el
   409, actualizar y no reenviar automáticamente. Esta entrega no inicia/cierra turnos.
5. **S:** Técnicos → asignar otro T, desasignarlo y reactivarlo con motivo. Comprobar
   que se conserva el PK de miembro, el principal no ofrece baja directa y los eventos
   reflejan actor/fecha y valores reales. Probar filtros activo/inactivo y paginación.
6. **G:** consultar ficha, técnicos e historiales; solo lectura de operación. Administrar
   categorías sigue siendo su capacidad exclusiva; S no ve historial de catálogo.
7. **AF:** ver listado/detalle y filtros; no debe ver descripción libre, auditoría,
   participantes, catálogo ni controles de edición. Costos es solo sección pendiente.
8. **T:** Mis obras debe incluir también membresías adicionales, no solo obras donde
   sea principal. Al desasignarlo como S, actualizar como T: la obra desaparece y el
   detalle deja de ser accesible. No debe haber controles de escritura, participantes,
   categorías, importes ni turnos operativos habilitados.
9. Probar 26 o más registros para navegar páginas reales, filtros de fechas/IDs,
   páginas fuera de rango, F5, cambios de usuario y logout durante solicitudes lentas.
   Revisar que ningún dato anterior ni respuesta tardía vuelva a la sesión siguiente.

## Limitaciones deliberadas

- No se ejecutó E2E en navegador con las cuatro cuentas reales. No se declaran
  comprobadas manualmente la persistencia de estos flujos ni carreras multiusuario.
- Sin implementación 005C-2/3, finalización, contabilidad, porcentajes de avance ni
  descargas de evidencia. No se cambia la política de cookies para facilitar pruebas.
- IDs mayores que `Number.MAX_SAFE_INTEGER` no se aceptan como identificadores
  seguros en React, igual que 005B; no se redondean ni se inventan IDs.
- Las opciones seleccionadas se conservan al paginar; Django revalida elegibilidad
  bajo bloqueo. Una opción pudo cambiar entre lectura y escritura y devolver 400/409.
- CI/PR y revisión visual en dispositivos reales quedan pendientes. No se afirma
  aprobación de un workflow remoto no ejecutado.

## Comandos de validación

### Resultados locales ejecutados

| Verificación | Resultado |
| --- | --- |
| `npm ci` | Correcto; sin cambios de dependencias |
| `npm test` | **128 aprobadas**, 0 fallidas, 0 omitidas; se conservan las 94 anteriores de 005A/005B |
| `npm run build` | Correcto, Vite 6.4.5 |
| `npm audit --omit=dev` | **0 vulnerabilidades** |
| Docker `python manage.py check` | Sin problemas (0 silenciados) |
| Docker `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| Docker `python manage.py test --noinput` | **508 aprobadas**, `OK`, 74.620 s |
| `git diff --check` | Sin errores de whitespace; solo advertencias locales LF/CRLF |

`npm ci` informó que el script postinstall de esbuild fue bloqueado por la política
local de npm. No impidió ninguna prueba ni el build. No se relajó esa política.

### Archivos creados

- `frontend/src/obras/api.js`
- `frontend/src/obras/domain.js`
- `frontend/src/obras/ui.jsx`
- `frontend/src/obras/ObraForm.jsx`
- `frontend/src/obras/ObraDetail.jsx`
- `frontend/src/obras/Categories.jsx`
- `frontend/tests/obras-domain.test.js`
- `frontend/tests/obras-http.test.js`
- `frontend/tests/obras-ui.test.js`
- `frontend/tests/helpers/obras-backend.js` (solo fixtures de prueba)
- `frontend/REVIEW-005C-1.md`

### Archivos modificados

- `frontend/src/app.jsx`
- `frontend/src/auth/client.js` (solo whitelist de errores públicos)
- `frontend/src/data/constants.js`
- `frontend/src/pages/Obras.jsx`
- `frontend/src/pages/TecnicoApp.jsx`
- `frontend/src/styles/pages/obras.css`
- `frontend/tests/auth-ui.test.js`
- `frontend/tests/comercial-ui.test.js`
- `frontend/tests/frontend-contract.test.js`
- `frontend/README.md`

Las expectativas antiguas de placeholders y de ausencia total de solicitudes S/T
se actualizaron para Obras; las prohibiciones de Comercial y los escenarios de
sesión permanecen probados. `backend/scripts/` era trabajo no versionado previo
y se preservó sin modificar ni incluirlo en el ZIP.

```sh
# frontend/
npm ci
npm test
npm run build
npm audit --omit=dev
# raíz del repositorio
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py test --noinput
```

Los resultados exactos se entregan junto con el ZIP de revisión. El ZIP es un
snapshot del frontend (fuentes, pruebas, manifiestos y documentación), sin
`node_modules`, `dist`, `.env`, credenciales reales, archivos privados ni backend.
Para reproducir, extraer y ejecutar los comandos de frontend en `frontend/`.
