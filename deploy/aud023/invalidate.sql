-- Only after pg_restore into a newly provisioned target, before admitting traffic.
BEGIN;
UPDATE usuarios_usuario u SET sesion_version = sesion_version + 1,
    password = CASE WHEN s.estado IN ('INICIAL', 'RECUPERACION') THEN '!aud023' ELSE u.password END
    FROM usuarios_seguridadcredencial s WHERE u.id = s.usuario_id;
UPDATE usuarios_usuario u SET sesion_version = sesion_version + 1, password = '!aud023'
    WHERE NOT EXISTS (SELECT FROM usuarios_seguridadcredencial s WHERE s.usuario_id = u.id);
UPDATE usuarios_seguridadcredencial SET desafio_digest = NULL, desafio_vence_en = NULL, desafio_version = NULL
    WHERE desafio_digest IS NOT NULL OR desafio_vence_en IS NOT NULL OR desafio_version IS NOT NULL;
UPDATE usuarios_instalacionfyag SET clave_digest = NULL, clave_vence_en = NULL WHERE clave_digest IS NOT NULL;
DELETE FROM usuarios_desafiocorreo;
DELETE FROM usuarios_desafiorecuperacioncorreo;
DELETE FROM django_session;
-- The normal row trigger bars deleting still-valid tickets. The owner discards
-- the entire ephemeral queue on the fresh, offline destination, never in runtime.
TRUNCATE chat_ticketchat;
DELETE FROM chat_canalchat;
DELETE FROM chat_cupochat;
-- Keep security events, persisted access restrictions and outstanding-token history.
COMMIT;
