# Proyecto FYAG

## Integración continua

El workflow **Backend CI** se ejecuta en los pull requests hacia `main` y los
pushes a `main` cuando cambian archivos del backend, `compose.yaml`, `.env.example`
o el propio workflow.

Utiliza Python 3.13.18 y un PostgreSQL 18 limpio con datos exclusivos de CI para:

1. Ejecutar `python manage.py check`.
2. Verificar migraciones con `python manage.py makemigrations --check --dry-run`.
3. Aplicar las migraciones mediante `python manage.py migrate --noinput`.
4. Ejecutar la suite completa con `python manage.py test`.

No levanta MongoDB porque las funcionalidades y pruebas actuales no dependen
de este servicio. Este workflow valida el backend; no realiza despliegues.
