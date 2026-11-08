# Frontend FYAG — sesión real (005A)

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

Las pruebas usan el runner nativo de Node, sin nuevas dependencias. Verifican el
cliente y los estados de sesión con respuestas HTTP controladas, concurrencia,
renderizado de componentes React y contratos de UI/fuentes; no sustituyen una
prueba E2E en navegador.

`npm run preview` solo sirve el build: para desplegarlo se requiere un servidor
same-origin que encamine `/api` a Django. No es un proxy de producción.

## Alcance

Solo autenticación está conectada. Los módulos de negocio muestran un aviso de
integración pendiente, sin registros ni escrituras simuladas. Los prototipos
anteriores no se montan. Clientes, Presupuestos, Obras y Finanzas requieren sus
propias integraciones posteriores; los menús no otorgan permisos del backend.
