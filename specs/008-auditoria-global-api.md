# SPEC-008 — Auditoría global de solo lectura

**Estado: especificada, NO implementada.** Contrato propuesto para la API de Django/DRF. Su implementación corresponde a los compañeros del backend, mediante PR independiente.

## Fuente de verdad y alcance
Auditoría existente en PostgreSQL: PresupuestoEvento; ObraEvento, ObraParticipanteEvento, CategoriaServicioEvento, TurnoObraEvento y CostoObraEvento; FinanzasEvento; UsuarioEvento. La nueva capa consolida eventos de fuentes reales sin duplicar ni reescribir históricos ni alterar servicios de negocio. Cliente no dispone de historial equivalente: no fingir auditoría exhaustiva de Clientes. Tampoco hay historial general de logins. MongoDB no es requisito de esta fase: una proyección futura exige diseño y reconciliación independientes.

## Matriz de acceso
- GERENCIA: eventos de Comercial, Obras y Finanzas; no eventos de gestión de Usuarios.
- SUPERVISOR_OBRAS: eventos de Obras, incluidas fuentes operativas y costos ya autorizados.
- ADMINISTRATIVO_FINANZAS: únicamente eventos públicos de Finanzas; sin evidencia ni detalle técnico.
- ADMINISTRADOR_TI: exclusivamente UsuarioEvento; sin información de negocio.
- TECNICO: sin auditoría global; mantiene las lecturas propias permitidas por APIs operativas.

No habilitar accesos por is_staff, is_superuser ni claims del navegador. Verificar rol activo persistido y versión de sesión. Respetar la proyección y visibilidad del serializer de cada dominio.

## Endpoint obligatorio
GET /api/auditoria/eventos/

Filtros opcionales y estrictos: modulo (COMERCIAL/OBRAS/FINANZAS/USUARIOS, sujeto al rol), tipo, actor (id positivo), recurso_tipo, recurso_id (requiere recurso_tipo), desde y hasta (YYYY-MM-DD, días civiles de Santiago; default últimos 30, rango máximo 366 días), limit (1–50, default 25), cursor (opaco y vinculado a identidad, filtros y corte). Rechazar parámetros desconocidos o repetidos.

Respuesta JSON de ejemplo **sintético**:

~~~json
{
  "results": [{
    "id": "OBRAS:OBRA:72:215",
    "modulo": "OBRAS",
    "recurso_tipo": "OBRA",
    "recurso_id": 72,
    "evento_id": 215,
    "tipo": "CAMBIO_ESTADO",
    "actor": 9,
    "motivo": "Suspensión solicitada",
    "creado_en": "2026-11-11T18:30:00-03:00",
    "datos_anteriores": {"estado": "EN_PROCESO"},
    "datos_nuevos": {"estado": "SUSPENDIDA"}
  }],
  "next_cursor": null,
  "has_more": false,
  "fecha_corte": "2026-11-11T18:32:00-03:00",
  "zona_horaria": "America/Santiago"
}
~~~

La clave id es compuesta para evitar colisiones de PK entre fuentes; no constituye autorización. Orden descendente por creado_en, con desempate estable por modulo/recurso/evento. Cursor paginado sin cargar todos los eventos a memoria; un cursor alterado o incompatible debe responder 400. Al paginar, fijar corte de lectura y evitar duplicados o saltos por escrituras concurrentes. Snapshot permitido por lista blanca de la fuente; excluir password, hashes, tokens, secretos y evidencia privada.

## Criterios verificables
- 200 con results vacíos; 400 parámetros inválidos, 401 no autenticado, 403 roles denegados, 405 mutaciones.
- Confirmar que TI no puede extraer negocios y Gerencia no puede leer eventos de Usuarios, incluso con flags Django.
- Rechazar filtros de recursos no autorizados sin filtrar su existencia.
- Pruebas de solapamiento temporal, paginación/cursor, cambio de rol, eventos concurrentes y acceso multifuente sobre PostgreSQL real.
- Documentar cobertura parcial de fuentes. GET no crea datos, no cambia ni borra registros de auditoría.
- Entregar OpenAPI/contratos de ejemplos, Backend CI y Postman (positivo, negativo, RBAC) antes de habilitar frontend.
