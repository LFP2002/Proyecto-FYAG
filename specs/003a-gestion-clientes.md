# SPEC-003A — Gestión de clientes

## Referencia

- Dependencia funcional: TFYAG-008 — Crear módulo de clientes.
- Dependencia de: TFYAG-012 — Crear módulo de presupuestos.
- Módulo Django: `apps.comercial`.
- Persistencia: PostgreSQL.
- Prioridad: Alta.

## Objetivo

Implementar la gestión backend de clientes de FYAG, proporcionando una
fuente de datos consistente y segura que posteriormente permita asociar
cada presupuesto a un cliente válido.

La información de clientes será persistida en PostgreSQL.

Cliente será la raíz del dominio comercial en `backend/apps/comercial/`.

### Alcance de esta etapa SDD

Esta etapa implementa los validadores de RUT, el modelo persistente `Cliente`,
sus invariantes Python/PostgreSQL y sus pruebas. La migración inicial es
`comercial/0001_initial.py`, generada por Django.
La migración `0002_remove_cliente_cliente_identificacion_coherente_and_more`
refuerza el tipo documental extranjero como `Upper(Trim(...))`, conservando
la unicidad condicional y las demás ramas de identificación.
Serializers, permisos, servicios, views, URLs, API e integración con presupuestos
quedan para etapas posteriores. La API no está implementada.

No se permitirá eliminación física de clientes desde la API.

## Entidad Cliente

La entidad almacena:

- id
- tipo_cliente
- tipo_identificacion
- numero_identificacion
- pais_identificacion
- tipo_documento_extranjero
- nombre_legal
- nombre_contacto
- correo
- telefono
- activo
- creado_en
- actualizado_en

### id

Clave primaria generada por Django mediante `BigAutoField`.

### Tipos de campos implementados

| Campo | Tipo y opciones |
| --- | --- |
| `id` | `BigAutoField`, clave primaria implícita. |
| `tipo_cliente` | `CharField(7)`, obligatorio, `TipoCliente.choices`. |
| `tipo_identificacion` | `CharField(20)`, obligatorio, `TipoIdentificacion.choices`. |
| `numero_identificacion` | `CharField(100)`, `null=True`, `blank=True`. |
| `pais_identificacion` | `CharField(2)`, `null=True`, `blank=True`. |
| `tipo_documento_extranjero` | `CharField(50)`, `null=True`, `blank=True`. |
| `nombre_legal` | `CharField(200)`, obligatorio, sin unicidad. |
| `nombre_contacto` | `CharField(200)`, `blank=True`, default `""`, no nullable. |
| `correo` | `EmailField(254)`, `blank=True`, default `""`, no nullable. |
| `telefono` | `CharField(50)`, `blank=True`, default `""`, no nullable. |
| `activo` | `BooleanField`, default `True`. |
| `creado_en` | `DateTimeField(auto_now_add=True)`. |
| `actualizado_en` | `DateTimeField(auto_now=True)`. |

`__str__` devuelve únicamente `nombre_legal`.

## Tipo de cliente

`tipo_cliente` tendrá exactamente los siguientes valores:

- `PERSONA`
- `EMPRESA`

El sistema permite registrar tanto personas como empresas. Las reglas de
identificación flexible se conservan para ambos tipos de cliente.

## Identificación del cliente

El registro de un cliente no dependerá obligatoriamente de disponer de un
RUT chileno.

`tipo_identificacion` tendrá exactamente los siguientes valores como contrato de dominio:

- `RUT`
- `DOCUMENTO_EXTRANJERO`
- `SIN_IDENTIFICACION`

### RUT

Cuando `tipo_identificacion = RUT`:

- `numero_identificacion` es obligatorio;
- debe corresponder a un RUT chileno válido;
- se validará mediante módulo 11;
- podrá recibirse con o sin puntos;
- podrá recibirse con guion o continuo sin puntos, interpretando el último carácter como DV;
- se almacenará sin puntos y con guion;
- el dígito verificador K se almacenará en mayúscula;
- el RUT normalizado deberá ser único.

`pais_identificacion` y `tipo_documento_extranjero` deben ser `None`.
Se rechazan datos extranjeros contradictorios, incluso strings vacíos;
no se borran silenciosamente para convertir la combinación en válida.

Se rechazarán cuerpos vacíos, no numéricos o compuestos únicamente por ceros,
DV vacío o distinto de `0-9`/`K`, múltiples guiones, caracteres arbitrarios y
formatos ambiguos. Solo se aceptan dígitos ASCII. Los puntos, si se usan,
deben separar grupos de miles del cuerpo (primer grupo de uno a tres dígitos,
seguido de grupos de tres); no pueden aparecer en el DV. Se permiten espacios
exteriores, pero no interiores. No se impondrá una longitud de cuerpo adicional.

Si el RUT contiene puntos, debe contener también guion separando explícitamente
el DV. Los únicos estilos permitidos son `12.345.678-5`, `12345678-5` y
`123456785`. El formato continuo sin guion solo admite dígitos ASCII en el cuerpo
y un último carácter `0-9` o `K/k` como DV. Se rechazan `12.345.6785` y `1.2345`.

Los ceros a la izquierda utilizados como relleno de formato no forman parte de
la representación canónica del RUT y serán eliminados, después de validar que
el cuerpo sea numérico. Un cuerpo compuesto únicamente por ceros sigue siendo
inválido y se rechaza mediante `ValidationError`; nunca se devuelve un cuerpo vacío.
El DV se valida contra el cuerpo canónico resultante. Por ejemplo, `637985-4`
y `00637985-4` representan el mismo RUT y se normalizan a `637985-4`;
`00012345678-5` se normaliza a `12345678-5`.

Normalizar no implica validar la coincidencia del DV: el cuerpo `637985` tiene
DV `0` según módulo 11. Las dos variantes con `-4` anteriores se normalizan,
pero `validar_rut` las rechaza; `637985-0` y `00637985-0` sí son válidas y
devuelven `637985-0`.

Ejemplo:

Entrada:

`12.345.678-5`

Persistencia:

`12345678-5`

Las entradas `12345678-5` y `123456785` producen también `12345678-5`.

### Documento extranjero

Cuando `tipo_identificacion = DOCUMENTO_EXTRANJERO`:

- `numero_identificacion` es obligatorio;
- `pais_identificacion` es obligatorio;
- `tipo_documento_extranjero` es obligatorio;
- no se aplicará validación de RUT chileno;
- el sistema deberá impedir duplicados de la misma combinación de país,
  tipo de documento y número.

No se asumirá que todos los países utilizan el mismo formato documental.
No se aplicará módulo 11 ni una regex restrictiva basada en documentos chilenos.
Las validaciones específicas por país quedan fuera de esta etapa.

El país se normaliza con `strip().upper()` y debe tener exactamente dos letras
ASCII mayúsculas. No se comprueba su existencia en ISO 3166.
`tipo_documento_extranjero` representa una categoría documental y se normaliza
con `strip().upper()`: `" dni "` pasa a `"DNI"` y `" pasaporte "` a `"PASAPORTE"`.
El número extranjero se normaliza solo con `strip`, preservando su case en esta
etapa, sin asumir reglas universales por país.

### Sin identificación

Cuando `tipo_identificacion = SIN_IDENTIFICACION`:

- `numero_identificacion` deberá ser null;
- `pais_identificacion` deberá ser null;
- `tipo_documento_extranjero` deberá ser null.

Esta modalidad permitirá registrar clientes cuya identificación todavía no
esté disponible.

No se utilizarán números ficticios para representar clientes sin
identificación.

Se permiten múltiples clientes sin identificación, sin usar RUT genéricos.
La identificación pendiente podrá completarse posteriormente modificando el cliente.

### nombre_legal

- obligatorio;
- debe ser un string;
- no puede ser una cadena vacía tras aplicar `strip`;
- no puede contener únicamente espacios;
- se conservan mayúsculas/minúsculas ingresadas;
- se eliminan espacios exteriores.

Cuando `tipo_cliente = EMPRESA`, representa la razón social de la empresa.
Cuando `tipo_cliente = PERSONA`, representa el nombre legal/completo de la persona.

### nombre_contacto

Nombre de la persona de contacto principal.

Puede quedar vacío cuando el cliente aún no tenga un contacto individual
definido.

Es opcional y se aplica `strip`.

Para una empresa puede representar al contacto comercial principal, sin ser
obligatorio. Para una persona puede quedar vacío. No se exige `nombre_contacto`
en función del tipo de cliente.

### correo

Correo principal de contacto.

Reglas:

- formato de correo válido;
- normalizado a minúsculas;
- aplicar `strip` y validar formato solo si existe;
- puede quedar vacío si existe teléfono.

### telefono

Número de contacto.

Puede quedar vacío si existe correo.

Es opcional y se aplica `strip`. No se implementará validación agresiva del
formato ni se asumirá que todos los números son chilenos.

### Regla de contacto

Un cliente deberá disponer de al menos uno de los siguientes:

- correo;
- teléfono.

No se permitirá almacenar un cliente sin ningún mecanismo de contacto.

### activo

Booleano.

Valor inicial:

`True`

Un cliente inactivo:

- conserva su información histórica;
- puede seguir asociado a presupuestos existentes;
- no podrá utilizarse para crear nuevos presupuestos.
- puede volver a activarse sin perder sus relaciones históricas.

## Política de eliminación

No se implementará `DELETE` físico para clientes.

Cuando un cliente deje de operar con FYAG deberá utilizarse desactivación
lógica mediante:

`activo = False`

Esto protege:

- integridad referencial;
- trazabilidad;
- presupuestos históricos;
- obras históricas;
- información financiera.

## Normalización

Antes de persistir:

- RUT → formato canónico sin puntos ni ceros iniciales, con guion;
- DV `K` → mayúscula;
- correo → trim + minúsculas;
- nombre legal → trim, conservando mayúsculas/minúsculas;
- nombre de contacto → trim;
- teléfono → trim.

La validación no dependerá exclusivamente del frontend.

### Validación del modelo y persistencia

`_normalizar()` comparte el tratamiento de strings entre `clean_fields()` y
`clean()`. La normalización precede a las validaciones de longitud y email.
`clean()` valida nombre legal, contacto e identificación, asocia los errores a
campos y ejecuta `validar_rut()` para almacenar el RUT canónico. Los campos
nullable no convierten strings vacíos en `None`: los datos contradictorios se
rechazan, especialmente en `SIN_IDENTIFICACION`.

`save()` ejecuta `full_clean(validate_unique=False, validate_constraints=False)`:
valida campos y reglas de dominio, y deja la resolución final de constraints y
unicidad a PostgreSQL, también ante concurrencia. Un `full_clean()` explícito
con sus parámetros por defecto comprueba además los constraints de Django.
No se añade manager de borrado lógico ni operaciones de presupuestos.

### Constraints implementados en PostgreSQL

| Nombre | Invariante |
| --- | --- |
| `cliente_tipo_valido` | Solo `PERSONA` o `EMPRESA`. |
| `cliente_identificacion_valida` | Solo las tres identificaciones definidas. |
| `cliente_nombre_normalizado` | Nombre no vacío e igual a `Trim(nombre_legal)`. |
| `cliente_contacto_obligatorio` | Correo o teléfono no vacío. |
| `cliente_contacto_normalizado` | Correo igual a `Lower(Trim(correo))`; teléfono y contacto iguales a su `Trim`. |
| `cliente_identificacion_coherente` | Combinación de campos según el tipo de identificación. |
| `cliente_rut_unico` | Unicidad de número condicionada a `tipo_identificacion = RUT`. |
| `cliente_documento_unico` | Unicidad de país + tipo documental + número condicionada a documento extranjero. |

El check de coherencia exige para RUT número no NULL y formato
`^[1-9][0-9]*-[0-9K]$`, con ambos campos extranjeros NULL. Para documento
extranjero exige los tres campos no NULL, número y tipo no vacíos, número igual
a su `Trim`, tipo igual a `Upper(Trim(tipo_documento_extranjero))` y país con
formato `^[A-Z]{2}$`. Para `SIN_IDENTIFICACION` exige
los tres campos exactamente NULL. Las comprobaciones explícitas de NULL evitan
que el valor SQL UNKNOWN permita combinaciones incompletas.

No hay unicidad de nombre ni de clientes sin identificación. La unicidad
documental conserva la distinción de mayúsculas/minúsculas del número, pero
las categorías `DNI`, `dni` y `Dni` convergen a `DNI` antes de persistir por
la vía normal. Se mantiene la unicidad por país + tipo + número. No se inventan
reglas de equivalencia específicas por país.

`bulk_create()` y `QuerySet.update()` omiten validación Python, pero mantienen
los constraints de PostgreSQL. La validación matemática de módulo 11 y el
formato de email permanecen en Python; no se implementan en SQL. `Trim` de
PostgreSQL elimina espacios ordinarios, mientras que `strip()` de Python cubre
también otros blancos: las operaciones directas deben respetar la normalización
de aplicación. Las pruebas de base de datos usan `IntegrityError` dentro de
`transaction.atomic()` y comprueban los constraints reales.

## Permisos

### GERENCIA

Puede:

- listar clientes;
- consultar clientes;
- crear clientes;
- modificar clientes;
- activar clientes;
- desactivar clientes.

### ADMINISTRATIVO_FINANZAS

Puede:

- listar clientes;
- consultar clientes;
- crear clientes;
- modificar clientes;
- activar clientes;
- desactivar clientes.

### SUPERVISOR_OBRAS

No accede al módulo general de clientes.

La información estrictamente necesaria del cliente podrá ser expuesta
posteriormente mediante las obras que tenga autorizadas.

### TECNICO

No accede al módulo general de clientes.

La información estrictamente necesaria podrá mostrarse posteriormente dentro
de sus obras asignadas.

Ningún rol podrá eliminar físicamente clientes desde la API.

## Arquitectura futura

| Archivo | Responsabilidad |
| --- | --- |
| `models.py` | Persistencia, constraints e invariantes estructurales. |
| `validators.py` | Normalización y validación de RUT; validaciones reutilizables de identificación. |
| `serializers.py` | Contrato HTTP, validaciones de entrada e invariantes cruzadas. |
| `permissions.py` | Autorización según rol. |
| `services.py` | Operaciones de negocio, activación/desactivación y futuras operaciones transaccionales. |
| `views.py` | Transporte HTTP, sin lógica de negocio compleja. |
| `urls.py` | Rutas. |
| `tests/` | Pruebas separadas por responsabilidad. |

## Seguridad e integridad

- Todas las rutas futuras de clientes requerirán JWT.
- Django validará siempre la autorización; React no determina permisos reales.
- Nunca se confiará en un rol enviado por el frontend ni en validaciones exclusivamente visuales.
- No habrá eliminación física desde la API.
- Las reglas importantes se reforzarán en aplicación y PostgreSQL cuando corresponda,
  incluyendo unicidad de RUT y de la combinación documental extranjera.
- Los errores API no deberán revelar trazas internas.

## Relación futura con Presupuesto

Presupuesto tendrá una relación real con Cliente mediante ForeignKey.
Solo clientes activos podrán seleccionarse al crear nuevos presupuestos.
Un cliente `SIN_IDENTIFICACION` puede existir y no se prohíbe todavía su
participación en un presupuesto. El momento exacto en que la identificación
tributaria/documental será obligatoria se definirá en SPEC-003B o en el módulo
financiero; esta especificación no introduce esa regla.

## Contrato de validadores de RUT

Funciones puras, sin acceso a base de datos ni dependencias externas. Los errores
se comunican con `django.core.exceptions.ValidationError`.

- `normalizar_rut(value)`: exige string, aplica `strip`, valida estructura,
  elimina puntos y ceros iniciales del cuerpo, convierte DV a mayúscula y
  devuelve `CUERPO-DV`.
  No verifica la coincidencia matemática del DV.
- `calcular_dv_rut(cuerpo)`: exige cuerpo string de dígitos ASCII, no vacío
  ni compuesto solo por ceros. Recorre de derecha a izquierda con factores
  cíclicos 2, 3, 4, 5, 6, 7; calcula `11 - (suma % 11)` y devuelve
  `"0"` para 11, `"K"` para 10 o el dígito restante como string.
- `validar_rut(value)`: normaliza, calcula y compara el DV; devuelve el RUT
  canónico si coincide y lanza `ValidationError` si no coincide. Nunca booleano.

## Verificación de esta etapa

Pruebas unitarias sin base de datos para formatos aceptados, espacios exteriores,
DV K, módulo 11, DV incorrecto y entradas inválidas o ambiguas.
También debe pasar la suite completa existente, sin cambios en autenticación.

```bash
python manage.py check
python manage.py test apps.comercial.tests.test_cliente_validators
python manage.py test apps.comercial.tests.test_cliente_model
python manage.py test apps.comercial.tests
python manage.py test
python manage.py makemigrations --check --dry-run
```

La migración inicial se genera con `python manage.py makemigrations comercial`
y se aplica con `python manage.py migrate`. Después, la comprobación con
`makemigrations --check --dry-run` debe indicar que no hay cambios pendientes.
