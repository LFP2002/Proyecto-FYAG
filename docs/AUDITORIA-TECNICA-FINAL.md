# Auditoría técnica final — plan y registro de evidencia

Base auditada: `87d564bba6d18b274cb7ed009c767e89071b6aec`. Rama local: `fix/auditoria-tecnica-final`. Sin autorización de publicación, merge ni despliegue.

## Orden de trabajo

1. Acordar precedencia y modelo en [SPEC-027](../specs/027-aprovisionamiento-recuperacion-seguridad.md).
2. Verificar guards y reconciliación; preservar orden de locks, probar con PostgreSQL real y fixtures sintéticos.
3. Aislar infraestructura, fijar dependencias efectivas y auditar sin suprimir hallazgos.
4. Integrar correo/verificación, instalación, recuperación y C2/emergencia, con pruebas dirigidas por etapa y sin activar producción.
5. Incorporar UI y contratos. Verificar componentes residuales por consumidores antes de retirar.
6. Validación integral única sobre solución consolidada; no usar resultados históricos como evidencia nueva.

## Registro inicial

- `origin/main` se actualizó por fetch y coincidió con la base auditada. El árbol estaba limpio. Se creó la rama sin mover `main`.
- `crear_primera_ti` ya usa mutex PostgreSQL, pero su predicado solo busca TI (no certifica instalación nunca inicializada ni conjunto vacío de usuarios). C2 existente se restringe a QA y conserva 401 genérico; no se debe reutilizar su excepción de última recuperadora en producción.
- RESULTADOS históricos de 1.451 backend y 316 frontend son referencias, no pruebas de esta rama. La validación de navegador no usará Edge Headless/CDP ni scripts dinámicos PowerShell bloqueados.
