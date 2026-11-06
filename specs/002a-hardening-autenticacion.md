# SPEC-002A — Hardening de autenticación y gestión de sesión

## Referencia

Extensión de SPEC-002 — Autenticación e inicio de sesión.

## Objetivo

Endurecer el mecanismo de autenticación JWT del sistema FYAG para reducir la exposición de credenciales de sesión, permitir revocación efectiva y establecer una política explícita de seguridad para los tokens.

## Decisiones de arquitectura

La autenticación se realizará exclusivamente mediante email y contraseña.

- `email` = autenticación / identidad de acceso.
- `username` = alias visible obligatorio, conservado en `AbstractUser`.
- `first_name` + `last_name` = nombre real/completo del trabajador.
- `rol` = autorización y control de acceso.

El sistema no permite autenticación mediante `username`. Se mantienen
`USERNAME_FIELD = "email"` y `REQUIRED_FIELDS = ["username"]`.
Login y `GET /api/auth/me/` devuelven `id`, `username`, `email` y `role`
para que el frontend pueda mostrar el alias.

El access token será entregado al frontend y utilizado mediante el encabezado:

`Authorization: Bearer <token>`

El refresh token no será expuesto al código JavaScript del frontend.

El refresh token será almacenado mediante una cookie con las siguientes propiedades:

- HttpOnly.
- Secure en producción.
- SameSite=Strict.
- Alcance restringido a las rutas de autenticación.

El frontend mantendrá el access token únicamente en memoria.

## Ciclo de sesión

### Login

`POST /api/auth/login/`

Entrada:

```json
{
  "email": "gerencia@gmail.com",
  "password": "contraseña"
}
```

Respuesta:

```json
{
  "access": "token",
  "user": {
    "id": 1,
    "username": "gerencia",
    "email": "gerencia@gmail.com",
    "role": "GERENCIA"
  },
  "csrfToken": "token_csrf_rotado"
}
```

El refresh token será enviado exclusivamente mediante cookie HttpOnly.

Enviar `username` y contraseña sin email devuelve `400 Bad Request`.
Antes del login se obtiene `csrfToken` con `GET /api/auth/csrf/` y se envía
en `X-CSRFToken` junto con la cookie CSRF. Login rota este token; refresh y
logout deben utilizar el token actualizado. Los tres endpoints requieren CSRF.

### Refresh

`POST /api/auth/refresh/`

El backend obtendrá el refresh token desde la cookie HttpOnly.

Si el token es válido:

- se generará un nuevo access token;
- se rotará el refresh token;
- el refresh anterior será incluido en blacklist.

### Logout

`POST /api/auth/logout/`

El backend:

- revocará el refresh token actual;
- eliminará la cookie de refresh;
- impedirá reutilizar el refresh revocado.

## Política JWT

- Access token de corta duración.
- Refresh token limitado a una jornada de trabajo.
- Rotación de refresh tokens habilitada.
- Blacklist de refresh tokens habilitada.
- Cambio de contraseña invalida los JWT emitidos anteriormente.
- Clave de firma JWT independiente de `DJANGO_SECRET_KEY`.
- Algoritmo y emisor definidos explícitamente.

## Protección contra abuso

El endpoint de login tendrá limitación de solicitudes.

La protección en Django será complementada posteriormente mediante rate limiting en el proxy inverso de producción.

## Identidad

El email será el único identificador de autenticación. `username` es un alias
de presentación y no participa en la validación de credenciales.

Los emails deberán normalizarse para evitar diferencias por mayúsculas/minúsculas.

La normalización elimina espacios exteriores y convierte a minúsculas tanto
al guardar el usuario como al recibir el email del login. Se conservan las
restricciones de PostgreSQL para email no vacío, normalizado y rol válido.

No podrán existir dos usuarios con el mismo email lógico.

## Roles

Los roles permitidos serán:

- GERENCIA
- ADMINISTRATIVO_FINANZAS
- SUPERVISOR_OBRAS
- TECNICO

La autorización continuará siendo responsabilidad exclusiva del backend.

El frontend podrá utilizar el rol únicamente para adaptar su interfaz.

## Seguridad de producción

La aplicación deberá desplegarse exclusivamente mediante HTTPS.

Las cookies sensibles deberán utilizar `Secure`.

Las configuraciones de producción deberán contemplar HSTS, redirección HTTPS y encabezados de seguridad.

## Criterios de aceptación

La implementación se considera correcta cuando:

1. El login utiliza email y contraseña.
2. El refresh token no aparece en el cuerpo JSON del login.
3. El refresh token se almacena en cookie HttpOnly.
4. La renovación funciona utilizando la cookie.
5. Un refresh token rotado no puede reutilizarse.
6. Logout elimina y revoca la sesión.
7. Un refresh revocado no puede generar nuevos access tokens.
8. Cambiar la contraseña invalida tokens anteriores.
9. Un JWT alterado es rechazado.
10. Un JWT expirado es rechazado.
11. Los endpoints protegidos rechazan solicitudes no autenticadas.
12. Los intentos excesivos de autenticación son limitados.
13. Existen pruebas automatizadas para el ciclo de sesión.

## Fuera de alcance

Esta especificación no implementa todavía:

- recuperación de contraseña;
- MFA;
- autenticación mediante proveedores externos;
- permisos funcionales de presupuestos;
- permisos de obras;
- permisos financieros.

## Evidencias requeridas

La implementación deberá generar evidencias reproducibles de:

- login válido;
- refresh válido;
- refresh rotado y revocado;
- logout;
- JWT modificado;
- usuario inactivo;
- acceso protegido;
- ejecución completa de pruebas automatizadas.
