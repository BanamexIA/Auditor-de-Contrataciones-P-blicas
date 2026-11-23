\set ON_ERROR_STOP on
-- Correo de cada usuario: enlaza la cuenta de Cognito (pool que inicia sesión con correo)
-- con audit.usuarios. El nombre de usuario legible sigue siendo el que registra la bitácora.

BEGIN;

ALTER TABLE audit.usuarios ADD COLUMN IF NOT EXISTS email TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'usuarios_email_valido') THEN
        ALTER TABLE audit.usuarios
            ADD CONSTRAINT usuarios_email_valido
            CHECK (email IS NULL OR (email = lower(email) AND email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_unico ON audit.usuarios (email) WHERE email IS NOT NULL;

COMMENT ON COLUMN audit.usuarios.email IS
'Correo (minúsculas) con el que la persona entra por Cognito. Opcional; único si existe.';

COMMIT;
