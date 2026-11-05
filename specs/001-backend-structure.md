# SPEC-001 — Estructura modular del backend

## Objetivo

Crear la estructura inicial del backend de Proyecto Beta FYAG utilizando Django REST Framework, separando las responsabilidades del sistema en módulos relacionados con el dominio definido durante la etapa de diseño.

## Alcance

Se crearán las siguientes aplicaciones Django:

- usuarios
- comercial
- obras
- finanzas
- auditoria
- alertas
- dashboard
- reportes

## Responsabilidades

### usuarios
Autenticación, usuarios, roles, permisos y control de acceso.

### comercial
Clientes, contactos de clientes y presupuestos.

### obras
Obras, categorías de servicio, costos y reglas operativas.

### finanzas
Facturas, pagos y seguimiento de cobranza.

### auditoria
Registro y trazabilidad de operaciones relevantes.

### alertas
Evaluación y registro de alertas asociadas a desviaciones.

### dashboard
Consultas e indicadores utilizados por el Dashboard Gerencial.

### reportes
Generación y exportación de reportes.

## Estructura esperada

Cada módulo deberá quedar preparado para contener:

- models.py
- serializers.py
- views.py
- services.py
- permissions.py
- urls.py
- admin.py
- migrations/
- tests/

## Fuera de alcance

En esta especificación no se implementarán:

- modelos de negocio;
- endpoints;
- JWT;
- permisos específicos;
- conexión de MongoDB;
- lógica de rentabilidad;
- alertas;
- CRUD.

## Criterios de aceptación

- Existe el paquete `backend/apps/`.
- Existen las ocho aplicaciones definidas.
- Todas las aplicaciones están registradas en Django.
- `python manage.py check` finaliza sin errores.
- No se implementa todavía lógica de negocio.