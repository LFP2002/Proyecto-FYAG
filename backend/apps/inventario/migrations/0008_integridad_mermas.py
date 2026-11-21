"""019C-2: baja física MB, clasificación MO y retorno serializado por entrega."""
from importlib import import_module

from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


SQL = r"""
CREATE FUNCTION fyag_merma_error() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Merma incompatible con su origen o estado'
 USING ERRCODE='23514', CONSTRAINT='inv_merma_integridad';
END; $$;

CREATE FUNCTION fyag_merma_raiz(m inventario_merma) RETURNS void LANGUAGE plpgsql AS $$
DECLARE presupuesto bigint; estado text;
BEGIN
 IF m.ambito='BODEGA' THEN
   PERFORM 1 FROM inventario_articuloinventario WHERE id=m.articulo_id FOR UPDATE;
   PERFORM 1 FROM inventario_existenciainventario WHERE articulo_id=m.articulo_id FOR UPDATE;
   PERFORM 1 FROM inventario_estadovaloracion WHERE articulo_id=m.articulo_id FOR UPDATE;
 ELSE
   SELECT presupuesto_id INTO presupuesto FROM obras_obra WHERE id=m.obra_id;
   IF presupuesto IS NULL THEN PERFORM fyag_merma_error(); END IF;
   PERFORM 1 FROM comercial_presupuesto WHERE id=presupuesto FOR UPDATE;
   SELECT o.estado INTO estado FROM obras_obra o WHERE id=m.obra_id FOR UPDATE;
   IF estado NOT IN ('EN_PROCESO','SUSPENDIDA') THEN PERFORM fyag_merma_error(); END IF;
   PERFORM 1 FROM inventario_operacionmaterial WHERE id=m.entrega_id FOR UPDATE;
 END IF;
END; $$;

CREATE FUNCTION fyag_merma_original() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e inventario_operacionmaterial; a inventario_articuloinventario; ultimo bigint;
BEGIN
 IF TG_OP='DELETE' THEN PERFORM fyag_merma_error(); END IF;
 IF TG_OP='UPDATE' THEN
   IF pg_trigger_depth()<2 OR OLD.estado<>'PENDIENTE' OR NEW.estado='PENDIENTE'
     OR (to_jsonb(NEW)-ARRAY['estado','decidido_por_id','decidido_en','motivo_decision','operacion_id'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['estado','decidido_por_id','decidido_en','motivo_decision','operacion_id'])
   THEN PERFORM fyag_merma_error(); END IF;
   RETURN NEW;
 END IF;
 IF NEW.estado<>'PENDIENTE' THEN PERFORM fyag_merma_error(); END IF;
 PERFORM fyag_merma_raiz(NEW);
 IF NEW.ambito='BODEGA' THEN
   SELECT * INTO a FROM inventario_articuloinventario WHERE id=NEW.articulo_id;
   SELECT max(id) INTO ultimo FROM inventario_movimientoinventario WHERE articulo_id=NEW.articulo_id;
   IF NOT a.activo OR a.unidad<>NEW.unidad OR NEW.corte_movimiento_id IS DISTINCT FROM ultimo
     OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.informado_por_id AND is_active AND rol='BODEGUERO')
   THEN PERFORM fyag_merma_error(); END IF;
 ELSE
   SELECT * INTO e FROM inventario_operacionmaterial WHERE id=NEW.entrega_id;
   PERFORM 1 FROM obras_obraparticipante WHERE obra_id=NEW.obra_id AND tecnico_id=NEW.informado_por_id AND activo FOR UPDATE;
   IF NOT FOUND OR e.tipo IS DISTINCT FROM 'ENTREGA' OR e.obra_id IS DISTINCT FROM NEW.obra_id
     OR e.articulo_id IS DISTINCT FROM NEW.articulo_id OR e.unidad IS DISTINCT FROM NEW.unidad OR NEW.cantidad>e.cantidad
     OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.informado_por_id AND is_active AND rol='TECNICO')
   THEN PERFORM fyag_merma_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_merma_original BEFORE INSERT OR UPDATE OR DELETE ON inventario_merma
FOR EACH ROW EXECUTE FUNCTION fyag_merma_original();

CREATE FUNCTION fyag_merma_operacion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m inventario_merma; a inventario_articuloinventario; v inventario_estadovaloracion;
 fisico numeric; ultimo bigint; posterior numeric; promedio_nuevo numeric;
BEGIN
 SELECT * INTO m FROM inventario_merma WHERE id=NEW.merma_bodega_id;
 IF m.id IS NULL OR m.ambito<>'BODEGA' THEN PERFORM fyag_merma_error(); END IF;
 PERFORM fyag_merma_raiz(m);
 SELECT * INTO m FROM inventario_merma WHERE id=m.id FOR UPDATE;
 SELECT * INTO a FROM inventario_articuloinventario WHERE id=m.articulo_id;
 SELECT saldo INTO fisico FROM inventario_existenciainventario WHERE articulo_id=m.articulo_id;
 SELECT * INTO v FROM inventario_estadovaloracion WHERE articulo_id=m.articulo_id;
 SELECT max(id) INTO ultimo FROM inventario_movimientoinventario WHERE articulo_id=m.articulo_id;
 IF m.estado<>'PENDIENTE' OR NOT a.activo OR NEW.articulo_id<>m.articulo_id OR NEW.unidad<>m.unidad OR NEW.unidad<>a.unidad
   OR NEW.cantidad<>m.cantidad OR fisico<NEW.cantidad OR fisico IS DISTINCT FROM v.saldo_valorado OR v.promedio IS NULL
   OR m.corte_movimiento_id IS DISTINCT FROM ultimo OR NEW.costo_unitario_neto IS DISTINCT FROM v.promedio
   OR NEW.obra_id IS NOT NULL OR NEW.autorizacion_id IS NOT NULL OR NEW.entrega_id IS NOT NULL OR NEW.ingreso_id IS NOT NULL
   OR NEW.gasto_id IS NOT NULL OR NEW.solicitud_material_id IS NOT NULL
   OR NEW.clave_idempotencia=m.clave_idempotencia OR NEW.referencia<>m.referencia
   OR NEW.motivo<>format('Merma de Bodega %s; informante %s',m.id,m.informado_por_id)
   OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.actor_id AND is_active AND rol='ADMINISTRATIVO_FINANZAS')
 THEN PERFORM fyag_merma_error(); END IF;
 posterior:=v.saldo_valorado-NEW.cantidad;
 promedio_nuevo:=CASE WHEN posterior=0 THEN NULL ELSE v.promedio END;
 IF (NEW.saldo_valorado_anterior,NEW.saldo_valorado_posterior,NEW.promedio_anterior,NEW.promedio_posterior)
   IS DISTINCT FROM (v.saldo_valorado,posterior,v.promedio,promedio_nuevo)
   OR (v.promedio>0 AND round(NEW.cantidad*v.promedio,2)=0)
 THEN PERFORM fyag_merma_error(); END IF;
 UPDATE inventario_estadovaloracion SET saldo_valorado=posterior,promedio=promedio_nuevo WHERE articulo_id=m.articulo_id;
 RETURN NEW;
END; $$;
DROP TRIGGER fyag_material_validar ON inventario_operacionmaterial;
CREATE TRIGGER fyag_material_validar BEFORE INSERT ON inventario_operacionmaterial
FOR EACH ROW WHEN (NEW.tipo<>'MERMA') EXECUTE FUNCTION fyag_material_operacion();
CREATE TRIGGER fyag_merma_operacion BEFORE INSERT ON inventario_operacionmaterial
FOR EACH ROW WHEN (NEW.tipo='MERMA') EXECUTE FUNCTION fyag_merma_operacion();

CREATE FUNCTION fyag_merma_movimiento() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE op inventario_operacionmaterial; fisico numeric;
BEGIN
 -- La operación ya posee artículo/existencia/valoración/MB, sin raíces de Obra.
 PERFORM 1 FROM inventario_articuloinventario WHERE id=NEW.articulo_id FOR UPDATE;
 SELECT saldo INTO fisico FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id FOR UPDATE;
 SELECT * INTO op FROM inventario_operacionmaterial WHERE id=NEW.operacion_id;
 IF op.tipo IS DISTINCT FROM 'MERMA' OR NEW.saldo_anterior IS DISTINCT FROM fisico
   OR NEW.saldo_posterior IS DISTINCT FROM fisico-NEW.cantidad
   OR (NEW.articulo_id,NEW.cantidad,NEW.actor_id,NEW.clave_idempotencia,NEW.referencia,NEW.motivo)
     IS DISTINCT FROM (op.articulo_id,op.cantidad,op.actor_id,op.clave_idempotencia,op.referencia,op.motivo)
 THEN PERFORM fyag_merma_error(); END IF;
 RETURN NEW;
END; $$;
DROP TRIGGER fyag_inventario_validar_ingreso ON inventario_movimientoinventario;
CREATE TRIGGER fyag_inventario_validar_ingreso BEFORE INSERT ON inventario_movimientoinventario
FOR EACH ROW WHEN (NEW.tipo<>'MERMA') EXECUTE FUNCTION fyag_inventario_aplicar_ingreso();
CREATE TRIGGER fyag_merma_movimiento BEFORE INSERT ON inventario_movimientoinventario
FOR EACH ROW WHEN (NEW.tipo='MERMA') EXECUTE FUNCTION fyag_merma_movimiento();
CREATE OR REPLACE FUNCTION fyag_inventario_conciliar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual numeric; libro numeric;
BEGIN
 IF TG_OP='UPDATE' AND NEW.articulo_id IS DISTINCT FROM OLD.articulo_id THEN PERFORM fyag_merma_error(); END IF;
 SELECT saldo INTO actual FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id;
 SELECT COALESCE(sum(CASE WHEN tipo IN ('SALIDA','MERMA') THEN -cantidad ELSE cantidad END),0)
 INTO libro FROM inventario_movimientoinventario WHERE articulo_id=NEW.articulo_id;
 IF actual IS NULL OR actual IS DISTINCT FROM libro THEN PERFORM fyag_merma_error(); END IF;
 RETURN NEW;
END; $$;

CREATE FUNCTION fyag_merma_evento() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m inventario_merma; op inventario_operacionmaterial; e inventario_operacionmaterial;
 perdidas numeric; recibidas numeric;
BEGIN
 SELECT * INTO m FROM inventario_merma WHERE id=NEW.merma_id;
 IF m.id IS NULL THEN PERFORM fyag_merma_error(); END IF;
 PERFORM fyag_merma_raiz(m);
 SELECT * INTO m FROM inventario_merma WHERE id=m.id FOR UPDATE;
 IF m.estado<>'PENDIENTE' THEN PERFORM fyag_merma_error(); END IF;
 IF NEW.tipo='CREACION' THEN
   IF (NEW.actor_id,NEW.motivo,NEW.clave_idempotencia,NEW.huella,NEW.creado_en)
      IS DISTINCT FROM (m.informado_por_id,m.motivo,m.clave_idempotencia,m.huella,m.creado_en)
   THEN PERFORM fyag_merma_error(); END IF;
   RETURN NEW;
 END IF;
 IF NEW.clave_idempotencia=m.clave_idempotencia
   OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.actor_id AND is_active
     AND rol=CASE WHEN m.ambito='BODEGA' THEN 'ADMINISTRATIVO_FINANZAS' ELSE 'SUPERVISOR_OBRAS' END)
 THEN PERFORM fyag_merma_error(); END IF;
 IF NEW.tipo='APROBACION' THEN
   IF m.ambito='BODEGA' THEN
     SELECT * INTO op FROM inventario_operacionmaterial WHERE id=NEW.operacion_id;
     IF op.id IS NULL OR op.tipo<>'MERMA' OR op.merma_bodega_id IS DISTINCT FROM m.id
       OR op.actor_id<>NEW.actor_id OR op.clave_idempotencia=NEW.clave_idempotencia
       OR NOT EXISTS (SELECT 1 FROM inventario_movimientoinventario WHERE operacion_id=op.id AND tipo='MERMA')
     THEN PERFORM fyag_merma_error(); END IF;
   ELSE
     IF NEW.operacion_id IS NOT NULL THEN PERFORM fyag_merma_error(); END IF;
     PERFORM 1 FROM obras_obraparticipante WHERE obra_id=m.obra_id AND tecnico_id=m.informado_por_id AND activo FOR UPDATE;
     IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=m.informado_por_id AND is_active AND rol='TECNICO')
     THEN PERFORM fyag_merma_error(); END IF;
     SELECT * INTO e FROM inventario_operacionmaterial WHERE id=m.entrega_id;
     IF e.tipo IS DISTINCT FROM 'ENTREGA' OR e.obra_id<>m.obra_id OR e.articulo_id<>m.articulo_id OR e.unidad<>m.unidad
       OR NOT EXISTS (SELECT 1 FROM obras_gastoobra WHERE id=e.gasto_id AND obra_id=m.obra_id AND origen='BODEGA_019B' AND vigente)
     THEN PERFORM fyag_merma_error(); END IF;
     SELECT COALESCE(sum(cantidad),0) INTO perdidas FROM inventario_merma WHERE entrega_id=e.id AND ambito='OBRA' AND estado='APROBADA';
     SELECT COALESCE(sum(cantidad),0) INTO recibidas FROM inventario_operacionmaterial WHERE entrega_id=e.id AND tipo='DEVOLUCION';
     IF perdidas+recibidas+m.cantidad>e.cantidad THEN PERFORM fyag_merma_error(); END IF;
   END IF;
 ELSIF NEW.tipo<>'RECHAZO' OR NEW.operacion_id IS NOT NULL THEN PERFORM fyag_merma_error(); END IF;
 UPDATE inventario_merma SET estado=CASE WHEN NEW.tipo='APROBACION' THEN 'APROBADA' ELSE 'RECHAZADA' END,
   decidido_por_id=NEW.actor_id,decidido_en=NEW.creado_en,motivo_decision=NEW.motivo,operacion_id=NEW.operacion_id WHERE id=m.id;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_merma_evento BEFORE INSERT ON inventario_mermaevento FOR EACH ROW EXECUTE FUNCTION fyag_merma_evento();
CREATE TRIGGER fyag_merma_evento_inmutable BEFORE UPDATE OR DELETE ON inventario_mermaevento FOR EACH ROW EXECUTE FUNCTION fyag_inventario_no_mutar();

CREATE FUNCTION fyag_merma_retorno() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE presupuesto bigint; estado_obra text; e inventario_operacionmaterial; perdidas numeric; total numeric;
BEGIN
 SELECT presupuesto_id INTO presupuesto FROM obras_obra WHERE id=NEW.obra_id;
 IF presupuesto IS NULL THEN PERFORM fyag_merma_error(); END IF;
 PERFORM 1 FROM comercial_presupuesto WHERE id=presupuesto FOR UPDATE;
 SELECT o.estado INTO estado_obra FROM obras_obra o WHERE id=NEW.obra_id FOR UPDATE;
 IF estado_obra NOT IN ('EN_PROCESO','SUSPENDIDA') THEN PERFORM fyag_merma_error(); END IF;
 -- Mismo orden de padres que 019B, siempre antes de artículo/gasto.
 PERFORM 1 FROM inventario_operacionmaterial WHERE id IN (NEW.autorizacion_id,NEW.entrega_id) ORDER BY id FOR UPDATE;
 SELECT * INTO e FROM inventario_operacionmaterial WHERE id=NEW.entrega_id;
 IF e.tipo IS DISTINCT FROM 'ENTREGA' OR e.obra_id<>NEW.obra_id OR e.articulo_id<>NEW.articulo_id THEN PERFORM fyag_merma_error(); END IF;
 SELECT COALESCE(sum(cantidad),0) INTO perdidas FROM inventario_merma WHERE entrega_id=e.id AND ambito='OBRA' AND estado='APROBADA';
 SELECT COALESCE(sum(cantidad),0) INTO total FROM inventario_operacionmaterial WHERE entrega_id=e.id
   AND tipo=CASE WHEN NEW.tipo='DEVOLUCION' THEN 'DEVOLUCION' ELSE 'AUTORIZACION_DEVOLUCION' END;
 IF perdidas+total+NEW.cantidad>e.cantidad THEN PERFORM fyag_merma_error(); END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_c2_retorno BEFORE INSERT ON inventario_operacionmaterial
FOR EACH ROW WHEN (NEW.tipo IN ('AUTORIZACION_DEVOLUCION','DEVOLUCION')) EXECUTE FUNCTION fyag_merma_retorno();

CREATE FUNCTION fyag_merma_confirmar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m inventario_merma; e inventario_mermaevento; op inventario_operacionmaterial; total bigint; decisiones bigint;
BEGIN
 IF TG_TABLE_NAME='inventario_operacionmaterial' THEN
   IF NEW.merma_bodega_id IS NULL THEN RETURN NEW; END IF;
   SELECT * INTO m FROM inventario_merma WHERE id=NEW.merma_bodega_id;
 ELSIF TG_TABLE_NAME='inventario_mermaevento' THEN
   SELECT * INTO m FROM inventario_merma WHERE id=NEW.merma_id;
 ELSE SELECT * INTO m FROM inventario_merma WHERE id=NEW.id;
 END IF;
 SELECT count(*) INTO total FROM inventario_mermaevento WHERE merma_id=m.id AND tipo='CREACION'
   AND actor_id=m.informado_por_id AND motivo=m.motivo AND clave_idempotencia=m.clave_idempotencia AND huella=m.huella AND creado_en=m.creado_en;
 IF total<>1 THEN PERFORM fyag_merma_error(); END IF;
 SELECT count(*) INTO decisiones FROM inventario_mermaevento WHERE merma_id=m.id AND tipo<>'CREACION';
 SELECT count(*) INTO total FROM inventario_operacionmaterial WHERE merma_bodega_id=m.id;
 IF m.estado='PENDIENTE' THEN
   IF decisiones<>0 OR total<>0 THEN PERFORM fyag_merma_error(); END IF;
 ELSE
   SELECT * INTO e FROM inventario_mermaevento WHERE merma_id=m.id AND tipo<>'CREACION';
   IF decisiones<>1 OR (e.actor_id,e.motivo,e.creado_en,e.operacion_id)
     IS DISTINCT FROM (m.decidido_por_id,m.motivo_decision,m.decidido_en,m.operacion_id)
     OR e.tipo<>(CASE WHEN m.estado='APROBADA' THEN 'APROBACION' ELSE 'RECHAZO' END)
   THEN PERFORM fyag_merma_error(); END IF;
   IF m.estado='APROBADA' AND m.ambito='BODEGA' THEN
     SELECT * INTO op FROM inventario_operacionmaterial WHERE id=m.operacion_id;
     IF total<>1 OR op.merma_bodega_id IS DISTINCT FROM m.id OR op.tipo<>'MERMA' OR op.actor_id<>m.decidido_por_id
       OR op.cantidad<>m.cantidad OR op.articulo_id<>m.articulo_id OR op.unidad<>m.unidad
       OR op.clave_idempotencia IN (m.clave_idempotencia,e.clave_idempotencia)
       OR NOT EXISTS (SELECT 1 FROM inventario_movimientoinventario WHERE operacion_id=op.id AND tipo='MERMA')
     THEN PERFORM fyag_merma_error(); END IF;
   ELSIF total<>0 THEN PERFORM fyag_merma_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fyag_merma_confirmar AFTER INSERT OR UPDATE ON inventario_merma
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_merma_confirmar();
CREATE CONSTRAINT TRIGGER fyag_merma_confirmar_evento AFTER INSERT ON inventario_mermaevento
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_merma_confirmar();
CREATE CONSTRAINT TRIGGER fyag_merma_confirmar_operacion AFTER INSERT ON inventario_operacionmaterial
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_merma_confirmar();
"""


def restaurar(apps, schema_editor):
    if apps.get_model('inventario', 'Merma').objects.using(schema_editor.connection.alias).exists():
        raise IrreversibleError('Hay historia de mermas; no retirar sus tablas, tipos o validación.')
    schema_editor.execute('''
    DROP TRIGGER fyag_merma_confirmar_operacion ON inventario_operacionmaterial;
    DROP TRIGGER fyag_merma_confirmar_evento ON inventario_mermaevento;
    DROP TRIGGER fyag_merma_confirmar ON inventario_merma;
    DROP TRIGGER fyag_c2_retorno ON inventario_operacionmaterial;
    DROP TRIGGER fyag_merma_evento_inmutable ON inventario_mermaevento;
    DROP TRIGGER fyag_merma_evento ON inventario_mermaevento;
    DROP TRIGGER fyag_merma_movimiento ON inventario_movimientoinventario;
    DROP TRIGGER fyag_merma_operacion ON inventario_operacionmaterial;
    DROP TRIGGER fyag_merma_original ON inventario_merma;
    DROP TRIGGER fyag_material_validar ON inventario_operacionmaterial;
    DROP TRIGGER fyag_inventario_validar_ingreso ON inventario_movimientoinventario;
    CREATE TRIGGER fyag_material_validar BEFORE INSERT ON inventario_operacionmaterial FOR EACH ROW EXECUTE FUNCTION fyag_material_operacion();
    CREATE TRIGGER fyag_inventario_validar_ingreso BEFORE INSERT ON inventario_movimientoinventario FOR EACH ROW EXECUTE FUNCTION fyag_inventario_aplicar_ingreso();
    ''')
    anterior = import_module('apps.inventario.migrations.0004_integridad_materiales').SQL
    inicio = anterior.index('CREATE OR REPLACE FUNCTION fyag_inventario_conciliar()')
    fin = anterior.index('CREATE OR REPLACE FUNCTION fyag_inventario_aplicar_ingreso()')
    schema_editor.execute(anterior[inicio:fin])
    schema_editor.execute('DROP FUNCTION fyag_merma_confirmar(), fyag_merma_retorno(), fyag_merma_evento(), fyag_merma_movimiento(), fyag_merma_operacion(), fyag_merma_original(), fyag_merma_raiz(inventario_merma), fyag_merma_error()')


class Migration(migrations.Migration):
    dependencies = [('inventario', '0007_mermas')]
    operations = [migrations.RunSQL(SQL, migrations.RunSQL.noop), migrations.RunPython(migrations.RunPython.noop, restaurar)]
