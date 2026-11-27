# Arquitectura vigente de FYAG

FYAG registra operaciones comerciales, obras, inventario, cuentas y finanzas. Registra documentos tributarios externos y pagos informados: no emite DTE ni ejecuta cobros o transferencias.

## Componentes y límites

| Componente | Responsabilidad |
| --- | --- |
| React/Vite | SPA, navegación y vistas por rol. Ocultar una acción en la interfaz no sustituye la autorización del backend. |
| Nginx + Django/DRF/Channels | Nginx sirve SPA y termina TLS; reenvía API y `/ws/chat/` por un socket Unix privado a Daphne. Un origen para SPA, API y WSS; solo Nginx publica puertos en Compose productivo. |
| PostgreSQL | Datos de negocio, autorización persistida, auditoría, sesiones y mensajes Chat. Web, migraciones, CLI de seguridad y workers tienen identidades distintas. |
| MongoDB + volúmenes privados | MongoDB conserva metadatos/proyecciones documentales; bytes de evidencias, adjuntos y Chat tienen volúmenes separados y no se sirven como estáticos. ClamAV inspecciona adjuntos por red privada. |
| Redis seguridad / Redis Chat | Seguridad usa autenticación, TLS y AOF para límites y trabajo efímero de correo; Redis Chat separado solo lleva avisos transitorios. Lectura y descarga de Chat pasan por autorización REST. Ningún Redis se restaura desde la copia. |
| Workers | Alertas, Documentos y Adjuntos reconciliados por ciclos; correo opt-in mediante overlay SMTP; purga automática de Chat opt-in mediante perfil y autorización explícita. |

Las escrituras SQL, Mongo y de archivos no constituyen una única transacción. Los módulos usan sus propias compensaciones y reconciliadores; verificar referencias e inventarios antes de reabrir tras un incidente. Las guardas de `live` y `ready` no validan esas invariantes.

## Seguridad y entornos

- **Desarrollo** y **QA aislado** tienen servicios, perfiles y datos propios. No combinar sus Compose con producción ni importar secretos o certificados de laboratorio.
- **Producción** es de un nodo: sin réplicas, failover ni recuperación a un instante posterior al corte. Nginx sustituye la IP reenviada por la del peer de transporte; una topología con terminación TLS externa, balanceador o NAT requiere revalidar el diseño, no confiar en cabeceras de clientes.
- Primera TI solo en instalación nunca inicializada, recuperación por correo verificado y recuperación excepcional TI por CLI son caminos distintos. Los bloqueos productivos requieren [habilitación formal](../backend/docs/SPEC-027-BLOQUEOS.md); el perfil QA C2 no es un sustituto. El acceso previo a un logout normal puede seguir vigente hasta expirar.
- Los contratos HTTP se consultan por alcance en el [índice OpenAPI](../backend/docs/openapi/README.md). La [guía de infraestructura](INFRAESTRUCTURA-PRODUCCION.md) define instalación, secretos y rotación; los runbooks de [respaldo](RESPALDO-RESTAURACION.md) y [retención](RETENCION-CHAT.md) definen recuperación sin reapertura automática.
