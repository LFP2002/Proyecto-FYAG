from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


SQL = r"""
CREATE FUNCTION fyag_chat_error() RETURNS void LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Estado de chat incompatible' USING ERRCODE='23514', CONSTRAINT='chat_integridad'; END; $$;

CREATE FUNCTION fyag_chat_conversacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN PERFORM fyag_chat_error(); END IF;
 IF NEW.titulo<>btrim(NEW.titulo) OR NEW.titulo ~ '[[:cntrl:]]'
   OR NOT EXISTS (SELECT 1 FROM usuarios_usuario WHERE id=NEW.creador_id AND is_active)
 THEN PERFORM fyag_chat_error(); END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_chat_conversacion BEFORE INSERT OR UPDATE OR DELETE ON chat_conversacionchat FOR EACH ROW EXECUTE FUNCTION fyag_chat_conversacion();

CREATE FUNCTION fyag_chat_miembro() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m chat_mensajechat;
BEGIN
 IF TG_OP='DELETE' THEN PERFORM fyag_chat_error(); END IF;
 PERFORM 1 FROM chat_conversacionchat WHERE id=NEW.conversacion_id FOR UPDATE;
 IF TG_OP='UPDATE' THEN
   IF (to_jsonb(NEW)-'ultimo_leido_mensaje_id') IS DISTINCT FROM (to_jsonb(OLD)-'ultimo_leido_mensaje_id')
     OR NEW.ultimo_leido_mensaje_id IS NULL OR NEW.ultimo_leido_mensaje_id<COALESCE(OLD.ultimo_leido_mensaje_id,0)
   THEN PERFORM fyag_chat_error(); END IF;
   IF NEW.ultimo_leido_mensaje_id IS DISTINCT FROM OLD.ultimo_leido_mensaje_id THEN
     SELECT * INTO m FROM chat_mensajechat WHERE id=NEW.ultimo_leido_mensaje_id AND conversacion_id=NEW.conversacion_id AND vence_en>statement_timestamp();
     IF m.id IS NULL THEN PERFORM fyag_chat_error(); END IF;
   END IF;
 ELSIF EXISTS (SELECT 1 FROM chat_actochat WHERE conversacion_id=NEW.conversacion_id)
   OR NEW.ultimo_leido_mensaje_id IS NOT NULL THEN PERFORM fyag_chat_error();
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_chat_miembro BEFORE INSERT OR UPDATE OR DELETE ON chat_participantechat FOR EACH ROW EXECUTE FUNCTION fyag_chat_miembro();

CREATE FUNCTION fyag_chat_confirmar_miembros() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE c chat_conversacionchat; total bigint;
BEGIN
 IF TG_TABLE_NAME='chat_conversacionchat' THEN SELECT * INTO c FROM chat_conversacionchat WHERE id=NEW.id;
 ELSE SELECT * INTO c FROM chat_conversacionchat WHERE id=NEW.conversacion_id; END IF;
 SELECT count(*) INTO total FROM chat_participantechat WHERE conversacion_id=c.id;
 IF NOT EXISTS (SELECT 1 FROM chat_actochat WHERE conversacion_id=c.id AND accion='CONVERSACION')
   OR NOT EXISTS (SELECT 1 FROM chat_participantechat WHERE conversacion_id=c.id AND usuario_id=c.creador_id)
   OR (c.tipo='GRUPAL' AND total NOT BETWEEN 3 AND 20)
   OR (c.tipo='DIRECTA' AND (total<>2 OR EXISTS (SELECT 1 FROM chat_participantechat WHERE conversacion_id=c.id AND usuario_id NOT IN (c.par_menor_id,c.par_mayor_id))))
 THEN PERFORM fyag_chat_error(); END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fyag_chat_confirmar_conversacion AFTER INSERT ON chat_conversacionchat DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_chat_confirmar_miembros();
CREATE CONSTRAINT TRIGGER fyag_chat_confirmar_miembros AFTER INSERT ON chat_participantechat DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_chat_confirmar_miembros();

CREATE FUNCTION fyag_chat_mensaje() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN PERFORM fyag_chat_error(); END IF;
 IF TG_OP='DELETE' THEN
   PERFORM 1 FROM chat_conversacionchat WHERE id=OLD.conversacion_id FOR UPDATE;
   IF OLD.vence_en>statement_timestamp() THEN PERFORM fyag_chat_error(); END IF;
   UPDATE chat_archivochat SET mensaje_id=NULL,estado='RETIRAR',nombre='',mime='',tamano_bytes=0,sha256='' WHERE mensaje_id=OLD.id;
   UPDATE chat_actochat SET mensaje_id=NULL,caducado=true,huella='' WHERE accion='MENSAJE' AND mensaje_id=OLD.id;
   RETURN OLD;
 END IF;
 PERFORM 1 FROM chat_conversacionchat WHERE id=NEW.conversacion_id FOR UPDATE;
 IF NOT EXISTS (SELECT 1 FROM chat_participantechat WHERE conversacion_id=NEW.conversacion_id AND usuario_id=NEW.autor_id)
   OR NEW.texto<>btrim(NEW.texto) OR NEW.texto ~ '[[:cntrl:]]'
   OR NEW.vence_en-NEW.creado_en NOT BETWEEN interval '1 day' AND interval '90 days'
   OR NOT EXISTS (SELECT 1 FROM usuarios_usuario u JOIN usuarios_seguridadcredencial s ON s.usuario_id=u.id WHERE u.id=NEW.autor_id AND u.is_active AND s.estado='PERSONAL')
 THEN PERFORM fyag_chat_error(); END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_chat_mensaje BEFORE INSERT OR UPDATE OR DELETE ON chat_mensajechat FOR EACH ROW EXECUTE FUNCTION fyag_chat_mensaje();

CREATE FUNCTION fyag_chat_archivo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
   IF OLD.estado<>'RETIRAR' THEN PERFORM fyag_chat_error(); END IF;
   RETURN OLD;
 END IF;
 IF TG_OP='UPDATE' THEN
   IF NEW.clave_interna<>OLD.clave_interna OR NEW.creado_en<>OLD.creado_en
     OR OLD.estado='RETIRAR' OR (OLD.estado='PUBLICADO' AND (pg_trigger_depth()<2 OR NEW.estado<>'RETIRAR' OR NEW.mensaje_id IS NOT NULL))
     OR (OLD.estado='RESERVADO' AND NEW.estado NOT IN ('PUBLICADO','RETIRAR'))
   THEN PERFORM fyag_chat_error(); END IF;
 ELSIF NEW.estado<>'RESERVADO' THEN PERFORM fyag_chat_error(); END IF;
 IF NEW.estado='PUBLICADO' AND EXISTS (SELECT 1 FROM chat_actochat WHERE accion='MENSAJE' AND mensaje_id=NEW.mensaje_id)
 THEN PERFORM fyag_chat_error(); END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_chat_archivo BEFORE INSERT OR UPDATE OR DELETE ON chat_archivochat FOR EACH ROW EXECUTE FUNCTION fyag_chat_archivo();

CREATE FUNCTION fyag_chat_acto() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN
   IF TG_OP='DELETE' OR pg_trigger_depth()<2 OR OLD.accion<>'MENSAJE' OR OLD.caducado
     OR NOT NEW.caducado OR NEW.huella<>'' OR NEW.mensaje_id IS NOT NULL
     OR (to_jsonb(NEW)-ARRAY['mensaje_id','caducado','huella']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['mensaje_id','caducado','huella'])
   THEN PERFORM fyag_chat_error(); END IF;
 ELSE
   IF NEW.caducado OR NEW.huella !~ '^[0-9a-f]{64}$'
     OR NEW.accion NOT IN ('CONVERSACION','MENSAJE')
     OR NOT EXISTS (SELECT 1 FROM chat_participantechat WHERE conversacion_id=NEW.conversacion_id AND usuario_id=NEW.autor_id)
     OR (NEW.accion='CONVERSACION' AND NEW.mensaje_id IS NOT NULL)
     OR (NEW.accion='MENSAJE' AND NOT EXISTS (SELECT 1 FROM chat_mensajechat WHERE id=NEW.mensaje_id AND conversacion_id=NEW.conversacion_id AND autor_id=NEW.autor_id AND clave_idempotencia=NEW.clave AND huella=NEW.huella))
   THEN PERFORM fyag_chat_error(); END IF;
 END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER fyag_chat_acto BEFORE INSERT OR UPDATE OR DELETE ON chat_actochat FOR EACH ROW EXECUTE FUNCTION fyag_chat_acto();

CREATE FUNCTION fyag_chat_confirmar_mensaje() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE m chat_mensajechat;
BEGIN
 SELECT * INTO m FROM chat_mensajechat WHERE id=NEW.id;
 IF m.id IS NULL THEN RETURN NEW; END IF;
 IF (m.texto='' AND NOT EXISTS (SELECT 1 FROM chat_archivochat WHERE mensaje_id=m.id AND estado='PUBLICADO'))
   OR NOT EXISTS (SELECT 1 FROM chat_actochat WHERE mensaje_id=m.id AND accion='MENSAJE' AND NOT caducado)
 THEN PERFORM fyag_chat_error(); END IF;
 RETURN NEW;
END; $$;
CREATE CONSTRAINT TRIGGER fyag_chat_confirmar_mensaje AFTER INSERT ON chat_mensajechat DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fyag_chat_confirmar_mensaje();
"""


def reversa(apps, editor):
    if apps.get_model('chat', 'ConversacionChat').objects.using(editor.connection.alias).exists() or apps.get_model('chat', 'ArchivoChat').objects.using(editor.connection.alias).exists():
        raise IrreversibleError('Hay historia u objetos de chat pendientes; preservar tablas y referencias de retiro.')
    editor.execute('''
    DROP TRIGGER fyag_chat_confirmar_mensaje ON chat_mensajechat;
    DROP TRIGGER fyag_chat_acto ON chat_actochat;
    DROP TRIGGER fyag_chat_archivo ON chat_archivochat;
    DROP TRIGGER fyag_chat_mensaje ON chat_mensajechat;
    DROP TRIGGER fyag_chat_confirmar_miembros ON chat_participantechat;
    DROP TRIGGER fyag_chat_confirmar_conversacion ON chat_conversacionchat;
    DROP TRIGGER fyag_chat_miembro ON chat_participantechat;
    DROP TRIGGER fyag_chat_conversacion ON chat_conversacionchat;
    DROP FUNCTION fyag_chat_confirmar_mensaje(),fyag_chat_acto(),fyag_chat_archivo(),fyag_chat_mensaje(),fyag_chat_confirmar_miembros(),fyag_chat_miembro(),fyag_chat_conversacion(),fyag_chat_error();
    ''')


class Migration(migrations.Migration):
    dependencies = [('chat', '0001_initial')]
    operations = [migrations.RunSQL(SQL, migrations.RunSQL.noop), migrations.RunPython(migrations.RunPython.noop, reversa)]
