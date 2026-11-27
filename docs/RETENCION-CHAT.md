# AUD-027 — Retención y purga de Chat

Cada mensaje recibe `vence_en` al publicarse: 30 días por defecto, `FYAG_CHAT_RETENCION_DIAS` entre 1 y 90. Cambiar la configuración afecta a mensajes nuevos, no recalcula vencimientos históricos. La API excluye los caducados aunque aún haya trabajo de mantenimiento; no sirve sus adjuntos. El recibo de idempotencia del mensaje caducado conserva autor, conversación y clave de operación, sin cuerpo, hash del contenido ni referencia al mensaje; un reintento de ese acto no republica el mensaje.

## Operación con Compose productivo

La purga automática está apagada. Activar el perfil `chat-mantenimiento` **y** fijar `FYAG_CHAT_PURGA_AUTORIZADA=CONFIRMADA` únicamente tras la autorización institucional. El perfil por sí solo no autoriza el worker. La cadencia predeterminada es 3.600 s (`FYAG_CHAT_PURGA_INTERVALO`). Mantener alertas sobre ciclos incompletos, edad del último éxito y espacio libre. No compartir la cuenta SQL con web ni conceder permisos adicionales.

Antes de una intervención, desde el proyecto y entorno correctos, inspeccionar sin escribir; solo tras autorización ejecutar un ciclo puntual:

```sh
docker compose … run --rm --no-deps chat_purgador python manage.py purgar_chat --dry-run
docker compose … run --rm --no-deps chat_purgador python manage.py purgar_chat --once
```

`--lote` admite 1–1000 (250 por defecto) y acota las transacciones, no el número total de filas de un ciclo. `--dry-run` solo consulta SQL: no adquiere locks de fila ni inspecciona o modifica archivos; los retiros nuevos que una purga generaría aún no existen en su recuento. El JSON contiene corte UTC y registros `identificados`, `eliminados`, `pendientes` y `fallidos` por tipo. Las reservas se contabilizan como `transferidas` a `RETIRAR`; su borrado final se cuenta en `retiros`. Los fallidos aún presentes se incluyen en pendientes. El recuento inicial y el final son observaciones distintas si hay concurrencia, no una suma contable. `staging` solo se informa en ejecución real, y cuenta referencias publicadas encontradas en el directorio temporal.

Un ciclo `pendiente` o `fallido` sale distinto de cero y no actualiza la salud del worker como éxito. El recorrido avanza por claves: un lock ocupado o un archivo malo no impide visitar los siguientes lotes. Se preserva la tumba SQL hasta retirar y sincronizar los archivos; una interrupción entre retiro físico y commit se recupera al reintentar. Si el ciclo falla, revisar PostgreSQL, permisos y espacio del almacén privado; corregir la causa y repetir con la misma identidad. No borrar a mano recibos ni directorios de producción. Las entradas de staging sin recibo reconocido quedan fuera de la purga automática y requieren revisión; no son un permiso para eliminar archivos arbitrarios.

## Restauración y copias históricas

[AUD-023](RESPALDO-RESTAURACION.md) ejecuta una purga puntual, sin activar la programación, después de restaurar SQL y archivos y **antes de reabrir**. Usa el reloj del destino, por lo que también retira mensajes que caducaron entre el corte y la recuperación. Si falla o quedan pendientes, mantener el destino aislado. La restauración con imágenes previas sin esta versión del comando falla cerrada: mantener el destino aislado y planificar la actualización validada y la purga con la versión vigente antes de admitir tráfico. La herramienta no reescribe ni purga respaldos ya hechos.

Las copias históricas pueden contener mensajes y archivos ya eliminados del sistema activo. Aplicar el acceso restringido y cifrado de AUD-023. La caducidad de Chat no autoriza a reescribir, destruir o decidir por cuenta propia la retención de copias, incluidas las sujetas a conservación legal. Aprobar esa política por separado.
