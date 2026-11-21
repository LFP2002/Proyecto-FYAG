"""Original y eventos inmutables; proyección y autorización confirmadas al commit."""
from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


SQL = r"""
CREATE FUNCTION fyag_solicitud_error() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Solicitud incompatible con su origen o estado'
 USING ERRCODE='23514', CONSTRAINT='inv_sol_integridad';
END; $$;

CREATE FUNCTION fyag_solicitud_raiz(obra bigint) RETURNS void LANGUAGE plpgsql AS $$
DECLARE presupuesto bigint; estado text;
BEGIN
 SELECT presupuesto_id INTO presupuesto FROM obras_obra WHERE id=obra;
 IF presupuesto IS NULL THEN PERFORM fyag_solicitud_error(); END IF;
 PERFORM 1 FROM comercial_presupuesto WHERE id=presupuesto FOR UPDATE;
 SELECT o.estado INTO estado FROM obras_obra o WHERE id=obra FOR UPDATE;
 IF estado NOT IN ('EN_PROCESO','SUSPENDIDA') THEN PERFORM fyag_solicitud_error(); END IF;
END; $$;

CREATE FUNCTION fyag_solicitud_original() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE unidad_actual text; activo_actual boolean;
BEGIN
 IF TG_OP='DELETE' THEN PERFORM fyag_solicitud_error(); END IF;
 IF TG_OP='UPDATE' THEN
   IF pg_trigger_depth()<2 OR OLD.estado<>'PENDIENTE' OR NEW.estado='PENDIENTE'
     OR (to_jsonb(NEW)-ARRAY['estado','cantidad_aprobada','motivo_decision','decidido_por_id','decidido_en','autorizacion_id'])
       IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['estado','cantidad_aprobada','motivo_decision','decidido_por_id','decidido_en','autorizacion_id'])
   THEN PERFORM fyag_solicitud_error(); END IF;
   RETURN NEW;
 END IF;
 IF NEW.estado<>'PENDIENTE' THEN PERFORM fyag_solicitud_error(); END IF;
 PERFORM fyag_solicitud_raiz(NEW.obra_id);
 PERFORM 1 FROM obras_obraparticipante WHERE obra_id=NEW.obra_id AND tecnico_id=NEW.solicitante_id AND activo FOR UPDATE;
 IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.solicitante_id AND is_active AND rol='TECNICO')
 THEN PERFORM fyag_solicitud_error(); END IF;
 SELECT unidad, a.activo INTO unidad_actual, activo_actual FROM inventario_articuloinventario a WHERE id=NEW.articulo_id FOR UPDATE;
 IF activo_actual IS DISTINCT FROM true OR unidad_actual IS DISTINCT FROM NEW.unidad THEN PERFORM fyag_solicitud_error(); END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_solicitud_original BEFORE INSERT OR UPDATE OR DELETE ON inventario_solicitudmaterialobra
FOR EACH ROW EXECUTE FUNCTION fyag_solicitud_original();

CREATE FUNCTION fyag_solicitud_evento() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s inventario_solicitudmaterialobra; op inventario_operacionmaterial;
 unidad_actual text; activo_actual boolean;
BEGIN
 SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.solicitud_id;
 IF s.id IS NULL THEN PERFORM fyag_solicitud_error(); END IF;
 PERFORM fyag_solicitud_raiz(s.obra_id);
 SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.solicitud_id FOR UPDATE;
 IF NEW.tipo='CREACION' THEN
   IF s.estado<>'PENDIENTE' OR NEW.actor_id<>s.solicitante_id OR NEW.clave_idempotencia<>s.clave_idempotencia
      OR NEW.huella<>s.huella OR NEW.motivo<>s.justificacion OR NEW.creado_en<>s.creado_en
   THEN PERFORM fyag_solicitud_error(); END IF;
   RETURN NEW;
 END IF;
 IF s.estado<>'PENDIENTE' OR NEW.clave_idempotencia=s.clave_idempotencia
    OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.actor_id AND is_active AND rol='SUPERVISOR_OBRAS')
 THEN PERFORM fyag_solicitud_error(); END IF;
 IF NEW.tipo='APROBACION' THEN
   PERFORM 1 FROM obras_obraparticipante WHERE obra_id=s.obra_id AND tecnico_id=s.solicitante_id AND activo FOR UPDATE;
   IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=s.solicitante_id AND is_active AND rol='TECNICO')
   THEN PERFORM fyag_solicitud_error(); END IF;
   SELECT unidad, a.activo INTO unidad_actual, activo_actual FROM inventario_articuloinventario a WHERE id=s.articulo_id FOR UPDATE;
   IF activo_actual IS DISTINCT FROM true OR unidad_actual IS DISTINCT FROM s.unidad THEN PERFORM fyag_solicitud_error(); END IF;
   SELECT * INTO op FROM inventario_operacionmaterial WHERE id=NEW.autorizacion_id;
   IF op.id IS NULL OR op.tipo<>'AUTORIZACION_ENTREGA' OR op.solicitud_material_id IS DISTINCT FROM s.id
      OR op.obra_id<>s.obra_id OR op.articulo_id<>s.articulo_id OR op.unidad<>s.unidad OR op.cantidad<>NEW.cantidad_aprobada
      OR NEW.cantidad_aprobada>s.cantidad_solicitada OR op.actor_id<>NEW.actor_id
      OR op.clave_idempotencia IN (s.clave_idempotencia, NEW.clave_idempotencia) OR op.motivo<>NEW.motivo
   THEN PERFORM fyag_solicitud_error(); END IF;
 ELSIF NEW.tipo<>'RECHAZO' THEN PERFORM fyag_solicitud_error(); END IF;
 UPDATE inventario_solicitudmaterialobra SET estado=CASE WHEN NEW.tipo='APROBACION' THEN 'APROBADA' ELSE 'RECHAZADA' END,
   cantidad_aprobada=NEW.cantidad_aprobada, motivo_decision=NEW.motivo, decidido_por_id=NEW.actor_id,
   decidido_en=NEW.creado_en, autorizacion_id=NEW.autorizacion_id WHERE id=s.id;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_solicitud_evento BEFORE INSERT ON inventario_solicitudmaterialevento
FOR EACH ROW EXECUTE FUNCTION fyag_solicitud_evento();
CREATE TRIGGER fyag_solicitud_evento_inmutable BEFORE UPDATE OR DELETE ON inventario_solicitudmaterialevento
FOR EACH ROW EXECUTE FUNCTION fyag_inventario_no_mutar();

CREATE FUNCTION fyag_solicitud_autorizacion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s inventario_solicitudmaterialobra;
BEGIN
 IF NEW.solicitud_material_id IS NULL THEN RETURN NEW; END IF;
 SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.solicitud_material_id;
 IF s.id IS NULL THEN PERFORM fyag_solicitud_error(); END IF;
 PERFORM fyag_solicitud_raiz(s.obra_id);
 SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.solicitud_material_id FOR UPDATE;
 PERFORM 1 FROM obras_obraparticipante WHERE obra_id=s.obra_id AND tecnico_id=s.solicitante_id AND activo FOR UPDATE;
 IF NOT FOUND OR s.estado<>'PENDIENTE' OR NEW.tipo<>'AUTORIZACION_ENTREGA'
    OR NEW.obra_id IS DISTINCT FROM s.obra_id OR NEW.articulo_id<>s.articulo_id OR NEW.unidad<>s.unidad
    OR NEW.cantidad>s.cantidad_solicitada OR NEW.clave_idempotencia=s.clave_idempotencia
 THEN PERFORM fyag_solicitud_error(); END IF;
 RETURN NEW;
END; $$;
-- Nombre anterior al trigger fyag_material_validar: raíz/solicitud/participante
-- se adquieren antes del artículo también para INSERT SQL directo enlazado.
CREATE TRIGGER fyag_c1_autorizacion BEFORE INSERT ON inventario_operacionmaterial
FOR EACH ROW EXECUTE FUNCTION fyag_solicitud_autorizacion();

CREATE FUNCTION fyag_solicitud_confirmar() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s inventario_solicitudmaterialobra; e inventario_solicitudmaterialevento;
 op inventario_operacionmaterial; total bigint; decisiones bigint;
BEGIN
 IF TG_TABLE_NAME='inventario_operacionmaterial' THEN
   IF NEW.solicitud_material_id IS NULL THEN RETURN NEW; END IF;
   SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.solicitud_material_id;
 ELSIF TG_TABLE_NAME='inventario_solicitudmaterialevento' THEN
   SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.solicitud_id;
 ELSE
   SELECT * INTO s FROM inventario_solicitudmaterialobra WHERE id=NEW.id;
 END IF;
 SELECT count(*) INTO total FROM inventario_solicitudmaterialevento WHERE solicitud_id=s.id AND tipo='CREACION'
   AND clave_idempotencia=s.clave_idempotencia AND huella=s.huella AND actor_id=s.solicitante_id
   AND motivo=s.justificacion AND creado_en=s.creado_en;
 IF total<>1 THEN PERFORM fyag_solicitud_error(); END IF;
 SELECT count(*) INTO decisiones FROM inventario_solicitudmaterialevento WHERE solicitud_id=s.id AND tipo<>'CREACION';
 SELECT count(*) INTO total FROM inventario_operacionmaterial WHERE solicitud_material_id=s.id;
 IF s.estado='PENDIENTE' THEN
   IF decisiones<>0 OR total<>0 THEN PERFORM fyag_solicitud_error(); END IF;
 ELSE
   SELECT * INTO e FROM inventario_solicitudmaterialevento WHERE solicitud_id=s.id AND tipo<>'CREACION';
   IF decisiones<>1 OR e.actor_id IS DISTINCT FROM s.decidido_por_id OR e.motivo IS DISTINCT FROM s.motivo_decision
      OR e.creado_en IS DISTINCT FROM s.decidido_en OR e.cantidad_aprobada IS DISTINCT FROM s.cantidad_aprobada
      OR e.autorizacion_id IS DISTINCT FROM s.autorizacion_id THEN PERFORM fyag_solicitud_error(); END IF;
   IF s.estado='APROBADA' THEN
     SELECT * INTO op FROM inventario_operacionmaterial WHERE id=s.autorizacion_id;
     IF e.tipo<>'APROBACION' OR total<>1 OR op.solicitud_material_id IS DISTINCT FROM s.id
        OR op.actor_id<>s.decidido_por_id OR op.tipo<>'AUTORIZACION_ENTREGA'
        OR op.cantidad<>s.cantidad_aprobada OR op.obra_id<>s.obra_id OR op.articulo_id<>s.articulo_id OR op.unidad<>s.unidad
        OR op.clave_idempotencia IN (e.clave_idempotencia,s.clave_idempotencia)
     THEN PERFORM fyag_solicitud_error(); END IF;
   ELSIF e.tipo<>'RECHAZO' OR total<>0 THEN PERFORM fyag_solicitud_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fyag_solicitud_confirmar AFTER INSERT OR UPDATE ON inventario_solicitudmaterialobra
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_solicitud_confirmar();
CREATE CONSTRAINT TRIGGER fyag_solicitud_confirmar_evento AFTER INSERT ON inventario_solicitudmaterialevento
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_solicitud_confirmar();
CREATE CONSTRAINT TRIGGER fyag_solicitud_confirmar_autorizacion AFTER INSERT ON inventario_operacionmaterial
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_solicitud_confirmar();
"""

REVERSE = """
DROP TRIGGER fyag_solicitud_confirmar_autorizacion ON inventario_operacionmaterial;
DROP TRIGGER fyag_solicitud_confirmar_evento ON inventario_solicitudmaterialevento;
DROP TRIGGER fyag_solicitud_confirmar ON inventario_solicitudmaterialobra;
DROP TRIGGER fyag_c1_autorizacion ON inventario_operacionmaterial;
DROP TRIGGER fyag_solicitud_evento_inmutable ON inventario_solicitudmaterialevento;
DROP TRIGGER fyag_solicitud_evento ON inventario_solicitudmaterialevento;
DROP TRIGGER fyag_solicitud_original ON inventario_solicitudmaterialobra;
DROP FUNCTION fyag_solicitud_confirmar(), fyag_solicitud_autorizacion(), fyag_solicitud_evento(), fyag_solicitud_original(), fyag_solicitud_raiz(bigint), fyag_solicitud_error();
"""


def preservar_historia(apps, schema_editor):
    if apps.get_model('inventario', 'SolicitudMaterialObra').objects.using(schema_editor.connection.alias).exists():
        raise IrreversibleError('Hay solicitudes registradas; preservar su historia y autorizaciones.')


class Migration(migrations.Migration):
    dependencies = [('inventario', '0005_solicitudes_materiales')]
    operations = [migrations.RunSQL(SQL, REVERSE), migrations.RunPython(migrations.RunPython.noop, preservar_historia)]
