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

## Inicio de sesión

### Endpoint

POST `/api/auth/login/`

### Entrada

```json
{
  "username": "usuario",
  "password": "contraseña"
}
```

Los campos `username` y `password` son obligatorios.

## Respuesta exitosa

Código HTTP:

`200 OK`

Ejemplo:

```json
{
  "access": "token_de_acceso",
  "refresh": "token_de_actualizacion",
  "user": {
    "id": 1,
    "username": "usuario",
    "role": "GERENCIA"
  }
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

El sistema no deberá indicar si el error corresponde específicamente al nombre de usuario o a la contraseña.

## Usuario inactivo

Un usuario marcado como inactivo no podrá obtener tokens JWT.

La solicitud deberá responder:

`401 Unauthorized`

## Renovación del token

### Endpoint

POST `/api/auth/refresh/`

### Entrada

```json
{
  "refresh": "token_de_actualizacion"
}
```

### Resultado

Si el refresh token es válido, el sistema entregará un nuevo access token.

## Seguridad

- Las contraseñas no se almacenarán en texto plano.
- Se utilizará el sistema de hashing de contraseñas proporcionado por Django.
- JWT será utilizado para autenticar las solicitudes entre React y Django REST.
- Las credenciales deberán validarse exclusivamente en el backend.
- El frontend no determinará los permisos reales del usuario.
- Los endpoints protegidos deberán rechazar solicitudes sin un token válido.
- Las credenciales incorrectas no deberán revelar qué dato fue incorrecto.
- Las claves y configuración sensible deberán mantenerse mediante variables de entorno.

## Criterios de aceptación

La especificación se considera implementada cuando:

1. Existe un modelo de usuario con rol.
2. Se encuentran disponibles los cuatro roles definidos.
3. Un usuario activo con credenciales correctas puede iniciar sesión.
4. El login devuelve access token y refresh token.
5. La respuesta incluye información básica del usuario y su rol.
6. Una contraseña incorrecta genera `401 Unauthorized`.
7. Un usuario inexistente genera `401 Unauthorized`.
8. Un usuario inactivo no puede iniciar sesión.
9. Un refresh token válido permite obtener un nuevo access token.
10. Django valida correctamente los JWT utilizados en endpoints protegidos.
11. Existen pruebas automatizadas para los principales casos de autenticación.

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