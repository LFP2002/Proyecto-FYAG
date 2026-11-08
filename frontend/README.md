# Frontend FYAG — sesión y Comercial reales (005A/005B)

## Desarrollo

1. Desde la raíz: `docker compose up -d` (Django en el puerto 8000).
2. En `frontend/`: `npm ci`, luego `npm run dev`.
3. Abrir la URL de Vite e ingresar con una cuenta interna existente. No hay cuentas
   ni contraseñas precargadas. La gestión de usuarios no se implementa aquí.

Usar Node.js 20 o superior. El proxy `/api` conserva Host y Origin para la
verificación CSRF de Django. No cambiar cookies, omitir CSRF ni agregar claves o
credenciales a variables públicas de Vite. La configuración de desarrollo HTTP
debe ser la existente del backend; producción requiere HTTPS y cookies Secure.

Access se conserva solo en memoria. La recarga intenta refresh mediante la
cookie HttpOnly y confirma la identidad con `/me/`. Login, refresh y logout envían
el token CSRF obtenido de Django; después de login se utiliza el token rotado.
Logout retira inmediatamente el acceso local. Si no puede confirmar la revocación
remota, muestra un aviso y permite volver a intentar el cierre.

## Validación

```sh
npm test
npm run build
```

Las pruebas usan el runner nativo de Node y `react-test-renderer` 18 (solo desarrollo,
para montar formularios y ejecutar sus handlers sin navegador). Verifican el
cliente y los estados de sesión con respuestas HTTP controladas, concurrencia,
renderizado de componentes React y contratos de UI/fuentes; no sustituyen una
prueba E2E en navegador.

`npm run preview` solo sirve el build: para desplegarlo se requiere un servidor
same-origin que encamine `/api` a Django. No es un proxy de producción.

## Alcance

Autenticación, Clientes y Presupuestos están conectados a Django. Los demás
módulos mantienen `PendingIntegration`; no hay escrituras simuladas ni integración
de Obras/Finanzas. Los menús no otorgan permisos del backend.

## Prueba manual con cuentas reales (005B)

No se crean cuentas ni se incluyen credenciales. Se necesitan dos cuentas existentes
con roles `ADMINISTRATIVO_FINANZAS` (AF) y `GERENCIA` (G).

1. AF: entrar en **Clientes**, crear un cliente con RUT válido o documento extranjero
   (país ISO de dos letras y tipo documental), nombre legal y correo o teléfono.
   Probar edición, desactivación/reactivación y transición a **Sin identificación**.
   Recargar para comprobar persistencia. No existe el campo ciudad.
2. AF: **Presupuestos → Nuevo borrador**, seleccionar cliente activo y descripción.
   Agregar una línea (cantidad `0.001`, precio `1250.50`, unidad y orden positivo).
   Neto/subtotales se leen exclusivamente del servidor. Probar editar y eliminar
   líneas y editar cabecera. Un cliente histórico inactivo se puede conservar.
3. AF: **Enviar a Gerencia**, confirmar. No existe envío directo al cliente ni umbral.
4. Cerrar sesión. G: **Presupuestos → Ver presupuesto**, aprobar o rechazar. G no
   tiene controles de creación/edición. Los rechazos exigen motivo.
5. AF: tras aprobación, **Enviar al cliente** y registrar aceptación o rechazo.
   Revisar historial y paginación (25 registros por página); el filtro de estado
   solo filtra la página cargada, no toda la base de datos.
6. AF: anular con motivo solo cuando sea válido. Si Django responde
   `presupuesto_utilizado`, no se anula: mostrar el conflicto y **Reconsultar datos**.
   Esa situación exige datos preparados con una Obra; esta entrega no crea Obras.
7. Desde rechazado/anulado, **Crear revisión** genera un nuevo ID BORRADOR y un
   enlace al origen. Comprobar que el original y su historial se conservan.
8. Probar F5, renovación de sesión, logout y acceso con otra cuenta. S/T no tienen
   acceso general a Comercial. Tras errores de red/timeout/5xx o 409 se bloquean
   escrituras hasta **Reconsultar datos**, sin repetirlas automáticamente. Revisar
   el estado leído y decidir una nueva acción; cancelar formularios obsoletos.

Las solicitudes comerciales se cancelan al desmontar, descartan resultados tardíos
y tienen un timeout de 30 segundos. Un timeout no prueba que Django haya revertido
una escritura: hay que reconsultar. No se ha ejecutado E2E con cuentas reales;
los tests montados usan contratos HTTP controlados, no PostgreSQL real.
