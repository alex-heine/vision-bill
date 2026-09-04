\set ON_ERROR_STOP on

-- Run as the role that owns the Alembic-created tables. These are NOLOGIN
-- privilege groups; grant one of them to a separately-created LOGIN role.
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vision_bill_runtime') THEN
        CREATE ROLE vision_bill_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'vision_bill_readonly') THEN
        CREATE ROLE vision_bill_readonly NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END
$roles$;

GRANT CONNECT ON DATABASE :"database_name" TO vision_bill_runtime, vision_bill_readonly;
GRANT USAGE ON SCHEMA public TO vision_bill_runtime, vision_bill_readonly;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
    TO vision_bill_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO vision_bill_readonly;

-- These defaults apply to future objects created by the role running this
-- file, so execute it as the same owner used by Alembic migrations.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vision_bill_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO vision_bill_readonly;

-- UUIDs currently avoid sequences, but this keeps future identity columns
-- usable by the runtime role without broad schema privileges.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO vision_bill_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO vision_bill_runtime;
