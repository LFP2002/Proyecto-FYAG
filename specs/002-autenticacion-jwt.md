# SPEC-002 — Autenticación e inicio de sesión

## Referencia

- Tarea: TFYAG-006
- Funcionalidad: Crear inicio de sesión del sistema.
- Módulo: Usuarios y control de acceso.
- Prioridad: Alta.

## Objetivo

Implementar el mecanismo de autenticación del sistema FYAG mediante Django REST Framework y JSON Web Tokens (JWT).

El sistema debe permitir que un usuario registrado ingrese sus credenciales y obtenga tokens que le permitan realizar solicitudes autenticadas a la API.

## Roles del sistema

Los usuarios podrán pertenecer a uno de los siguientes roles:

- GERENCIA
- ADMINISTRATIVO_FINANZAS
- SUPERVISOR_OBRAS
- TECNICO

El rol deberá almacenarse en el usuario y posteriormente será utilizado por el backend para controlar el acceso a las funcionalidades del sistema.

El frontend podrá utilizar el rol para adaptar la interfaz, pero la autorización real siempre deberá ser validada por Django.

## Modelo de usuario

Se utilizará un usuario personalizado de Django basado en `AbstractUser`.

Además de los atributos propios de Django, deberá incorporar:

- rol

El campo `rol` solo podrá contener uno de los roles definidos por el sistema.

El email constituye el único identificador utilizado para autenticación.
El campo `username` se conserva exclusivamente como alias o nombre corto visible
del usuario dentro de la aplicación. El sistema no permite autenticación mediante
`username`.

- `email`: autenticación / identidad de acceso, único y normalizado a minúsculas.
- `username`: alias visible obligatorio, heredado de `AbstractUser`.
- `first_name` + `last_name`: nombre real/completo del trabajador.
- `rol`: autorización y control de acceso.

Se mantienen `USERNAME_FIELD = "email"` y `REQUIRED_FIELDS = ["username"]`,
así como las restricciones de PostgreSQL de email no vacío, normalizado y rol válido.

## Inicio de sesión

### Endpoint

POST `/api/auth/login/`

### Entrada

```json
{
  "email": "usuario@dominio.cl",
  "password": "contraseña"
}
```

Los campos `email` y `password` son obligatorios. El email recibido se normaliza
eliminando espacios exteriores y convirtiéndolo a minúsculas. Enviar únicamente
`username` y `password` devuelve `400 Bad Request` por falta de `email`.

Antes del login, obtener el token CSRF mediante `GET /api/auth/csrf/` y enviarlo
en `X-CSRFToken`, junto con la cookie CSRF. Login, refresh y logout requieren CSRF.

## Respuesta exitosa

Código HTTP:

`200 OK`

Ejemplo:

```json
{
  "access": "token_de_acceso",
  "user": {
    "id": 1,
    "username": "Lucas",
    "email": "usuario@dominio.cl",
    "role": "GERENCIA"
  },
  "csrfToken": "token_csrf_rotado"
}
```

El refresh token se entrega exclusivamente mediante la cookie `fyag_refresh`,
HttpOnly, SameSite=Strict, Secure en producción y con path `/api/auth/`.
No aparece en el JSON. El login rota el token CSRF; las siguientes solicitudes
deben utilizar el nuevo `csrfToken`.

## Perfil actual

`GET /api/auth/me/`, con `Authorization: Bearer <access>`, devuelve:

```json
{
  "id": 1,
  "username": "Lucas",
  "email": "usuario@dominio.cl",
  "role": "GERENCIA"
}
```

## Credenciales incorrectas

Si el usuario no existe o la contraseña es incorrecta:

`401 Unauthorized`

Respuesta:

```json
{
  "detail": "Credenciales inválidas."
}
```

El sistema no deberá indicar si el error corresponde específicamente al email o a la contraseña.

## Usuario inactivo

Un usuario marcado como inactivo no podrá obtener tokens JWT.

La solicitud deberá responder:

`401 Unauthorized`

## Renovación del token

### Endpoint

POST `/api/auth/refresh/`

### Entrada

```json
{}
```

### Resultado

El refresh token se lee exclusivamente desde la cookie HttpOnly. Si es válido,
el sistema entrega `{"access": "token_de_acceso"}`, rota la cookie de refresh
e incluye el refresh anterior en blacklist. No devuelve refresh en JSON.

`POST /api/auth/logout/` revoca el refresh actual, elimina su cookie y devuelve
`204 No Content`.

## Seguridad

- Las contraseñas no se almacenarán en texto plano.
- Se utilizará el sistema de hashing de contraseñas proporcionado por Django.
- JWT será utilizado para autenticar las solicitudes entre React y Django REST.
- Las credenciales deberán validarse exclusivamente en el backend.
- El frontend no determinará los permisos reales del usuario.
- Los endpoints protegidos deberán rechazar solicitudes sin un token válido.
- Las credenciales incorrectas no deberán revelar qué dato fue incorrecto.
- Las claves y configuración sensible deberán mantenerse mediante variables de entorno.
- La clave `JWT_SIGNING_KEY` es independiente de `DJANGO_SECRET_KEY`.
- Se mantienen CSRF, rate limiting, rotación y blacklist de refresh tokens.
- Los JWT expirados o manipulados son rechazados.

## Criterios de aceptación

La especificación se considera implementada cuando:

1. Existe un modelo de usuario con rol.
2. Se encuentran disponibles los cuatro roles definidos.
3. Un usuario activo con credenciales correctas puede iniciar sesión.
4. El login devuelve access token en JSON y refresh token exclusivamente en cookie HttpOnly.
5. Login y perfil incluyen `id`, `username`, `email` y `role`.
6. Una contraseña incorrecta genera `401 Unauthorized`.
7. Un usuario inexistente genera `401 Unauthorized`.
8. Un usuario inactivo no puede iniciar sesión.
9. Un refresh token válido permite obtener un nuevo access token.
10. Django valida correctamente los JWT utilizados en endpoints protegidos.
11. Existen pruebas automatizadas para los principales casos de autenticación.
12. El login solo admite email como identificador; username no permite autenticarse.

## Fuera de alcance

Esta especificación no implementará todavía:

- gestión completa de usuarios;
- creación de usuarios desde React;
- recuperación de contraseña;
- cambio de contraseña;
- permisos específicos de presupuestos;
- permisos específicos de obras;
- permisos financieros;
- autenticación de clientes externos;
- autenticación con Google, Microsoft u otros proveedores;
- interfaz de login en React.

## Dependencias

- Django.
- Django REST Framework.
- Simple JWT.
- PostgreSQL.
- Estructura base del backend.

## Resultado esperado

Al finalizar esta especificación, el backend deberá disponer de una autenticación JWT funcional que pueda ser utilizada posteriormente por React y por los módulos protegidos del sistema FYAG.

## Estado de implementación

Implementada y validada.

Resultados:

- Autenticación por email y contraseña: OK.
- Generación de access token y refresh token: OK.
- Renovación de access token: OK.
- Endpoint protegido con JWT: OK.
- Rechazo de solicitudes sin JWT: OK.
- Rechazo de credenciales incorrectas: OK.
- Rechazo de usuarios inactivos: OK.
- Pruebas automatizadas de autenticación, sesión e integridad: ejecutar
  `python manage.py test apps.usuarios` y `python manage.py test`.
