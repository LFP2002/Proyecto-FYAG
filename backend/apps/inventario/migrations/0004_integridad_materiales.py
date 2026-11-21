"""019B: libro físico firmado, valoración secuencial y enlace económico al commit."""
from django.db import migrations


SQL = r"""
LOCK TABLE inventario_articuloinventario, inventario_movimientoinventario IN SHARE ROW EXCLUSIVE MODE;
INSERT INTO inventario_estadovaloracion
 (articulo_id, saldo_historico, ultimo_movimiento_historico, corte_en, saldo_valorado, promedio)
 SELECT e.articulo_id, e.saldo, (SELECT max(id) FROM inventario_movimientoinventario m WHERE m.articulo_id=e.articulo_id),
        statement_timestamp(), 0, NULL FROM inventario_existenciainventario e;

CREATE FUNCTION fyag_material_error() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Operacion de materiales incompatible con su origen o estado'
 USING ERRCODE='23514', CONSTRAINT='inv_019b_integridad';
END; $$;

CREATE OR REPLACE FUNCTION fyag_inventario_existencia_inicial() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO inventario_existenciainventario (articulo_id,saldo) VALUES (NEW.id,0);
 INSERT INTO inventario_estadovaloracion
 (articulo_id,saldo_historico,ultimo_movimiento_historico,corte_en,saldo_valorado,promedio)
 VALUES (NEW.id,0,NULL,statement_timestamp(),0,NULL);
 RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fyag_inventario_conciliar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual numeric; libro numeric;
BEGIN
 IF TG_OP='UPDATE' AND NEW.articulo_id IS DISTINCT FROM OLD.articulo_id THEN
   PERFORM fyag_material_error();
 END IF;
 SELECT saldo INTO actual FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id;
 SELECT COALESCE(sum(CASE WHEN tipo='SALIDA' THEN -cantidad ELSE cantidad END),0)
 INTO libro FROM inventario_movimientoinventario WHERE articulo_id=NEW.articulo_id;
 IF actual IS NULL OR actual IS DISTINCT FROM libro THEN PERFORM fyag_material_error(); END IF;
 RETURN NEW;
END; $$;

CREATE OR REPLACE FUNCTION fyag_inventario_aplicar_ingreso() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE disponible numeric; habilitado boolean; op inventario_operacionmaterial;
BEGIN
 -- 019A nunca adquiere después locks de Obras. Para 019B la operación ya
 -- bloqueó Presupuesto/Obra ANTES de llegar a este trigger físico.
 SELECT activo INTO habilitado FROM inventario_articuloinventario WHERE id=NEW.articulo_id FOR UPDATE;
 SELECT saldo INTO disponible FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id FOR UPDATE;
 IF disponible IS NULL OR NEW.saldo_anterior IS DISTINCT FROM disponible OR
    NEW.saldo_posterior IS DISTINCT FROM (disponible + CASE WHEN NEW.tipo='SALIDA' THEN -NEW.cantidad ELSE NEW.cantidad END)
 THEN PERFORM fyag_material_error(); END IF;
 IF NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.actor_id AND is_active AND rol='BODEGUERO')
 THEN PERFORM fyag_material_error(); END IF;
 IF NEW.tipo <> 'DEVOLUCION' AND habilitado IS DISTINCT FROM true THEN PERFORM fyag_material_error(); END IF;
 IF NEW.tipo <> 'INGRESO' THEN
   SELECT * INTO op FROM inventario_operacionmaterial WHERE id=NEW.operacion_id;
   IF op.id IS NULL OR op.tipo <> (CASE WHEN NEW.tipo='SALIDA' THEN 'ENTREGA' ELSE 'DEVOLUCION' END)
      OR op.articulo_id<>NEW.articulo_id OR op.cantidad<>NEW.cantidad OR op.actor_id<>NEW.actor_id
      OR op.clave_idempotencia<>NEW.clave_idempotencia OR op.referencia<>NEW.referencia OR op.motivo<>NEW.motivo
   THEN PERFORM fyag_material_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;

CREATE FUNCTION fyag_material_proteger_estado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR pg_trigger_depth()<2 OR
    (NEW.articulo_id,NEW.saldo_historico,NEW.ultimo_movimiento_historico,NEW.corte_en)
    IS DISTINCT FROM (OLD.articulo_id,OLD.saldo_historico,OLD.ultimo_movimiento_historico,OLD.corte_en)
 THEN PERFORM fyag_material_error(); END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_material_estado BEFORE UPDATE OR DELETE ON inventario_estadovaloracion
FOR EACH ROW EXECUTE FUNCTION fyag_material_proteger_estado();

CREATE FUNCTION fyag_material_operacion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE a inventario_articuloinventario; v inventario_estadovaloracion;
 p inventario_operacionmaterial; original inventario_operacionmaterial;
 ingreso inventario_movimientoinventario; g obras_gastoobra;
 presupuesto bigint; estado text; rol_actor text; total numeric; fisico numeric;
 saldo_nuevo numeric; promedio_nuevo numeric; numerador numeric;
BEGIN
 IF NEW.referencia='' OR NEW.motivo='' OR NEW.referencia<>btrim(NEW.referencia) OR NEW.motivo<>btrim(NEW.motivo)
 THEN PERFORM fyag_material_error(); END IF;
 SELECT rol INTO rol_actor FROM usuarios_usuario WHERE id=NEW.actor_id AND is_active;
 IF NEW.tipo IN ('AUTORIZACION_ENTREGA','AUTORIZACION_DEVOLUCION') THEN
   IF rol_actor IS DISTINCT FROM 'SUPERVISOR_OBRAS' THEN PERFORM fyag_material_error(); END IF;
 ELSIF NEW.tipo IN ('ENTREGA','DEVOLUCION') THEN
   IF rol_actor IS DISTINCT FROM 'BODEGUERO' THEN PERFORM fyag_material_error(); END IF;
 ELSE
   IF rol_actor IS DISTINCT FROM 'ADMINISTRATIVO_FINANZAS' THEN PERFORM fyag_material_error(); END IF;
 END IF;
 IF NEW.tipo IN ('VALORIZACION','REGULARIZACION') THEN
   IF NEW.obra_id IS NOT NULL OR NEW.autorizacion_id IS NOT NULL OR NEW.entrega_id IS NOT NULL OR NEW.gasto_id IS NOT NULL
   THEN PERFORM fyag_material_error(); END IF;
 ELSE
   SELECT presupuesto_id INTO presupuesto FROM obras_obra WHERE id=NEW.obra_id;
   IF presupuesto IS NULL THEN PERFORM fyag_material_error(); END IF;
   PERFORM 1 FROM comercial_presupuesto WHERE id=presupuesto FOR UPDATE;
   SELECT o.estado INTO estado FROM obras_obra o WHERE id=NEW.obra_id FOR UPDATE;
   IF estado NOT IN ('EN_PROCESO','SUSPENDIDA') OR NEW.ingreso_id IS NOT NULL THEN PERFORM fyag_material_error(); END IF;
 END IF;
 PERFORM 1 FROM inventario_operacionmaterial WHERE id IN (NEW.autorizacion_id,NEW.entrega_id) ORDER BY id FOR UPDATE;
 SELECT * INTO p FROM inventario_operacionmaterial WHERE id=NEW.autorizacion_id;
 SELECT * INTO original FROM inventario_operacionmaterial WHERE id=NEW.entrega_id;
 SELECT * INTO a FROM inventario_articuloinventario WHERE id=NEW.articulo_id FOR UPDATE;
 SELECT saldo INTO fisico FROM inventario_existenciainventario WHERE articulo_id=NEW.articulo_id FOR UPDATE;
 SELECT * INTO v FROM inventario_estadovaloracion WHERE articulo_id=NEW.articulo_id FOR UPDATE;
 IF a.id IS NULL OR v.articulo_id IS NULL OR NEW.unidad<>a.unidad THEN PERFORM fyag_material_error(); END IF;
 IF NOT a.activo AND NEW.tipo NOT IN ('DEVOLUCION','VALORIZACION','REGULARIZACION') THEN PERFORM fyag_material_error(); END IF;
 IF NEW.tipo='AUTORIZACION_ENTREGA' THEN
   IF NEW.autorizacion_id IS NOT NULL OR NEW.entrega_id IS NOT NULL OR NEW.gasto_id IS NOT NULL THEN PERFORM fyag_material_error(); END IF;
 ELSIF NEW.tipo='ENTREGA' THEN
   IF p.id IS NULL OR p.tipo<>'AUTORIZACION_ENTREGA' OR p.obra_id<>NEW.obra_id OR p.articulo_id<>NEW.articulo_id
      OR NEW.entrega_id IS NOT NULL OR NEW.gasto_id IS NULL THEN PERFORM fyag_material_error(); END IF;
   SELECT COALESCE(sum(cantidad),0) INTO total FROM inventario_operacionmaterial WHERE autorizacion_id=p.id AND tipo='ENTREGA';
   IF total+NEW.cantidad>p.cantidad OR fisico<NEW.cantidad OR fisico<>v.saldo_valorado THEN PERFORM fyag_material_error(); END IF;
   SELECT * INTO g FROM obras_gastoobra WHERE id=NEW.gasto_id FOR UPDATE;
   IF g.id IS NULL OR g.origen<>'BODEGA_019B' OR g.tipo<>'MATERIAL' OR NOT g.vigente OR g.obra_id<>NEW.obra_id
     OR g.registrado_por_id<>NEW.actor_id OR g.cantidad<>NEW.cantidad OR g.unidad<>NEW.unidad
     OR g.costo_unitario_neto IS DISTINCT FROM v.promedio OR NEW.costo_unitario_neto IS DISTINCT FROM v.promedio
     OR g.cantidad_devuelta<>0 THEN PERFORM fyag_material_error(); END IF;
 ELSIF NEW.tipo IN ('AUTORIZACION_DEVOLUCION','DEVOLUCION') THEN
   IF original.id IS NULL OR original.tipo<>'ENTREGA' OR original.obra_id<>NEW.obra_id OR original.articulo_id<>NEW.articulo_id
      OR NEW.gasto_id IS NOT NULL THEN PERFORM fyag_material_error(); END IF;
   IF NEW.tipo='AUTORIZACION_DEVOLUCION' THEN
     IF NEW.autorizacion_id IS NOT NULL THEN PERFORM fyag_material_error(); END IF;
     SELECT COALESCE(sum(cantidad),0) INTO total FROM inventario_operacionmaterial WHERE entrega_id=original.id AND tipo='AUTORIZACION_DEVOLUCION';
     IF total+NEW.cantidad>original.cantidad THEN PERFORM fyag_material_error(); END IF;
   ELSE
     IF p.id IS NULL OR p.tipo<>'AUTORIZACION_DEVOLUCION' OR p.entrega_id<>original.id
        OR NEW.costo_unitario_neto IS DISTINCT FROM original.costo_unitario_neto THEN PERFORM fyag_material_error(); END IF;
     SELECT COALESCE(sum(cantidad),0) INTO total FROM inventario_operacionmaterial WHERE autorizacion_id=p.id AND tipo='DEVOLUCION';
     IF total+NEW.cantidad>p.cantidad OR fisico+NEW.cantidad>999999999.999 THEN PERFORM fyag_material_error(); END IF;
   END IF;
 ELSIF NEW.tipo='REGULARIZACION' THEN
   IF v.saldo_historico<=0 OR NEW.cantidad<>v.saldo_historico OR NEW.ingreso_id IS NOT NULL
      OR EXISTS (SELECT 1 FROM inventario_operacionmaterial WHERE articulo_id=a.id AND tipo IN ('VALORIZACION','REGULARIZACION'))
   THEN PERFORM fyag_material_error(); END IF;
 ELSE
   SELECT * INTO ingreso FROM inventario_movimientoinventario WHERE id=NEW.ingreso_id;
   IF ingreso.id IS NULL OR ingreso.tipo<>'INGRESO' OR ingreso.articulo_id<>a.id OR ingreso.cantidad<>NEW.cantidad
      OR ingreso.id<=COALESCE(v.ultimo_movimiento_historico,0)
      OR (v.saldo_historico>0 AND NOT EXISTS (SELECT 1 FROM inventario_operacionmaterial WHERE articulo_id=a.id AND tipo='REGULARIZACION'))
      OR EXISTS (SELECT 1 FROM inventario_movimientoinventario m WHERE m.articulo_id=a.id AND m.tipo='INGRESO'
        AND m.id>COALESCE(v.ultimo_movimiento_historico,0) AND m.id<ingreso.id
        AND NOT EXISTS (SELECT 1 FROM inventario_operacionmaterial op WHERE op.ingreso_id=m.id))
   THEN PERFORM fyag_material_error(); END IF;
 END IF;
 IF NEW.tipo IN ('AUTORIZACION_ENTREGA','AUTORIZACION_DEVOLUCION') THEN
   IF NEW.costo_unitario_neto IS NOT NULL OR NEW.saldo_valorado_anterior IS NOT NULL OR NEW.saldo_valorado_posterior IS NOT NULL
      OR NEW.promedio_anterior IS NOT NULL OR NEW.promedio_posterior IS NOT NULL THEN PERFORM fyag_material_error(); END IF;
 ELSE
   IF NEW.costo_unitario_neto IS NULL THEN PERFORM fyag_material_error(); END IF;
   IF NEW.tipo='ENTREGA' THEN
     saldo_nuevo:=v.saldo_valorado-NEW.cantidad;
     promedio_nuevo:=CASE WHEN saldo_nuevo=0 THEN NULL ELSE v.promedio END;
   ELSE
     saldo_nuevo:=v.saldo_valorado+NEW.cantidad;
     numerador:=v.saldo_valorado*COALESCE(v.promedio,0)+NEW.cantidad*NEW.costo_unitario_neto;
     promedio_nuevo:=round(numerador/saldo_nuevo,2);
     IF numerador>0 AND promedio_nuevo=0 THEN PERFORM fyag_material_error(); END IF;
   END IF;
   IF NEW.costo_unitario_neto>0 AND round(NEW.cantidad*NEW.costo_unitario_neto,2)=0 THEN PERFORM fyag_material_error(); END IF;
   IF (NEW.saldo_valorado_anterior,NEW.saldo_valorado_posterior,NEW.promedio_anterior,NEW.promedio_posterior)
      IS DISTINCT FROM (v.saldo_valorado,saldo_nuevo,v.promedio,promedio_nuevo) THEN PERFORM fyag_material_error(); END IF;
   UPDATE inventario_estadovaloracion SET saldo_valorado=saldo_nuevo,promedio=promedio_nuevo WHERE articulo_id=a.id;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_material_validar BEFORE INSERT ON inventario_operacionmaterial FOR EACH ROW EXECUTE FUNCTION fyag_material_operacion();
CREATE TRIGGER fyag_material_inmutable BEFORE UPDATE OR DELETE ON inventario_operacionmaterial FOR EACH ROW EXECUTE FUNCTION fyag_inventario_no_mutar();

CREATE FUNCTION fyag_material_gasto() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE presupuesto bigint; estado text; entregado numeric;
BEGIN
 IF TG_OP='DELETE' THEN
   IF OLD.origen='BODEGA_019B' THEN PERFORM fyag_material_error(); END IF;
   RETURN OLD;
 END IF;
 IF NEW.origen NOT IN ('MANUAL','BODEGA_019B') THEN PERFORM fyag_material_error(); END IF;
 IF TG_OP='UPDATE' THEN
   IF NEW.origen<>OLD.origen THEN PERFORM fyag_material_error(); END IF;
   IF OLD.origen='MANUAL' THEN RETURN NEW; END IF;
   IF (to_jsonb(NEW)-'cantidad_devuelta'-'actualizado_en') IS DISTINCT FROM (to_jsonb(OLD)-'cantidad_devuelta'-'actualizado_en')
      OR NEW.cantidad_devuelta<=OLD.cantidad_devuelta THEN PERFORM fyag_material_error(); END IF;
   SELECT COALESCE(sum(d.cantidad),0) INTO entregado FROM inventario_operacionmaterial d
   JOIN inventario_operacionmaterial e ON d.entrega_id=e.id WHERE d.tipo='DEVOLUCION' AND e.gasto_id=NEW.id;
   IF NEW.cantidad_devuelta<>entregado THEN PERFORM fyag_material_error(); END IF;
 ELSIF NEW.origen='BODEGA_019B' THEN
   SELECT presupuesto_id INTO presupuesto FROM obras_obra WHERE id=NEW.obra_id;
   PERFORM 1 FROM comercial_presupuesto WHERE id=presupuesto FOR UPDATE;
   SELECT o.estado INTO estado FROM obras_obra o WHERE id=NEW.obra_id FOR UPDATE;
   IF estado NOT IN ('EN_PROCESO','SUSPENDIDA') OR NEW.tipo<>'MATERIAL' OR NEW.cantidad_devuelta<>0 OR NOT NEW.vigente
      OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.registrado_por_id AND is_active AND rol='BODEGUERO')
   THEN PERFORM fyag_material_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_material_gasto BEFORE INSERT OR UPDATE OR DELETE ON obras_gastoobra FOR EACH ROW EXECUTE FUNCTION fyag_material_gasto();

CREATE FUNCTION fyag_material_confirmar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE op inventario_operacionmaterial; g obras_gastoobra; total numeric; eventos bigint;
BEGIN
 IF TG_TABLE_NAME='obras_gastoobra' THEN
   IF NEW.origen='MANUAL' THEN RETURN NEW; END IF;
   SELECT * INTO op FROM inventario_operacionmaterial WHERE gasto_id=NEW.id AND tipo='ENTREGA';
   IF op.id IS NULL THEN PERFORM fyag_material_error(); END IF;
 ELSE
   SELECT * INTO op FROM inventario_operacionmaterial WHERE id=NEW.id;
 END IF;
 IF op.tipo IN ('ENTREGA','DEVOLUCION') THEN
   IF NOT EXISTS (SELECT 1 FROM inventario_movimientoinventario WHERE operacion_id=op.id) THEN PERFORM fyag_material_error(); END IF;
   SELECT * INTO g FROM obras_gastoobra WHERE id=COALESCE(op.gasto_id,(SELECT gasto_id FROM inventario_operacionmaterial WHERE id=op.entrega_id));
   SELECT count(*) INTO eventos FROM obras_costoobraevento c WHERE c.gasto_id=g.id
    AND c.tipo=CASE WHEN op.tipo='ENTREGA' THEN 'ALTA' ELSE 'DEVOLUCION' END
    AND c.registrado_por_id=op.actor_id AND c.obra_id=op.obra_id
    AND c.datos_nuevos->>'origen'='BODEGA_019B' AND c.datos_nuevos->>'operacion_material'=op.id::text;
   IF eventos<>1 THEN PERFORM fyag_material_error(); END IF;
   SELECT COALESCE(sum(cantidad),0) INTO total FROM inventario_operacionmaterial WHERE tipo='DEVOLUCION' AND entrega_id=COALESCE(op.entrega_id,op.id);
   IF g.cantidad_devuelta<>total OR NOT g.vigente THEN PERFORM fyag_material_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fyag_material_confirmar AFTER INSERT ON inventario_operacionmaterial
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_material_confirmar();
CREATE CONSTRAINT TRIGGER fyag_material_confirmar_gasto AFTER INSERT OR UPDATE ON obras_gastoobra
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_material_confirmar();

CREATE FUNCTION fyag_material_evento() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE g obras_gastoobra; op inventario_operacionmaterial;
BEGIN
 IF TG_OP<>'INSERT' THEN
   IF EXISTS (SELECT 1 FROM obras_gastoobra WHERE id=OLD.gasto_id AND origen='BODEGA_019B') THEN PERFORM fyag_material_error(); END IF;
   IF TG_OP='UPDATE' AND EXISTS (SELECT 1 FROM obras_gastoobra WHERE id=NEW.gasto_id AND origen='BODEGA_019B') THEN PERFORM fyag_material_error(); END IF;
   RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
 END IF;
 SELECT * INTO g FROM obras_gastoobra WHERE id=NEW.gasto_id;
 IF g.origen='BODEGA_019B' THEN
   SELECT * INTO op FROM inventario_operacionmaterial WHERE id=(NEW.datos_nuevos->>'operacion_material')::bigint;
   IF op.id IS NULL OR op.tipo NOT IN ('ENTREGA','DEVOLUCION') OR NEW.datos_nuevos->>'origen' IS DISTINCT FROM 'BODEGA_019B' OR NEW.obra_id<>g.obra_id
      OR NEW.registrado_por_id<>op.actor_id OR NEW.tipo<>(CASE WHEN op.tipo='ENTREGA' THEN 'ALTA' ELSE 'DEVOLUCION' END)
      OR COALESCE(op.gasto_id,(SELECT gasto_id FROM inventario_operacionmaterial WHERE id=op.entrega_id)) IS DISTINCT FROM g.id
   THEN PERFORM fyag_material_error(); END IF;
   IF op.tipo='DEVOLUCION' AND ((NEW.datos_nuevos->'devolucion'->>'cantidad')::numeric IS DISTINCT FROM op.cantidad
       OR (NEW.datos_nuevos->'devolucion'->>'fecha')::date IS NULL
       OR (NEW.datos_nuevos->'devolucion'->>'fecha')::date<g.fecha_gasto)
   THEN PERFORM fyag_material_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_material_evento BEFORE INSERT OR UPDATE OR DELETE ON obras_costoobraevento FOR EACH ROW EXECUTE FUNCTION fyag_material_evento();
CREATE UNIQUE INDEX inv_material_evento_unico ON obras_costoobraevento ((datos_nuevos->>'operacion_material'))
WHERE datos_nuevos->>'origen'='BODEGA_019B' AND gasto_id IS NOT NULL;
"""


def impedir_reversion(apps, schema_editor):
    from django.db.migrations.exceptions import IrreversibleError
    if apps.get_model('inventario', 'OperacionMaterial').objects.using(schema_editor.connection.alias).exists():
        raise IrreversibleError('El libro 019B contiene historia; no retirar sus tablas ni triggers.')


def restaurar_019a(apps, schema_editor):
    from importlib import import_module
    schema_editor.execute("""
    DROP INDEX IF EXISTS inv_material_evento_unico;
    DROP TRIGGER fyag_material_evento ON obras_costoobraevento;
    DROP TRIGGER fyag_material_confirmar_gasto ON obras_gastoobra;
    DROP TRIGGER fyag_material_confirmar ON inventario_operacionmaterial;
    DROP TRIGGER fyag_material_gasto ON obras_gastoobra;
    DROP TRIGGER fyag_material_inmutable ON inventario_operacionmaterial;
    DROP TRIGGER fyag_material_validar ON inventario_operacionmaterial;
    DROP TRIGGER fyag_material_estado ON inventario_estadovaloracion;
    DROP FUNCTION fyag_material_evento(), fyag_material_confirmar(), fyag_material_gasto(), fyag_material_operacion(), fyag_material_proteger_estado();
    DELETE FROM inventario_estadovaloracion;
    """)
    previa = import_module('apps.inventario.migrations.0002_integridad_libro')
    schema_editor.execute(previa.REVERSE)
    schema_editor.execute(previa.SQL)
    schema_editor.execute('DROP FUNCTION fyag_material_error()')


class Migration(migrations.Migration):
    dependencies = [('inventario', '0003_operaciones_material')]
    operations = [
        migrations.RunSQL(SQL, migrations.RunSQL.noop),
        migrations.RunPython(migrations.RunPython.noop, restaurar_019a),
        migrations.RunPython(migrations.RunPython.noop, impedir_reversion),
    ]
