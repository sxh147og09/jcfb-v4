-- JCFB V4 DISPOSABLE LOCAL ROLE BOOTSTRAP
-- This file is mounted only into the repository-local disposable PostgreSQL
-- container during first-time database initialization. It is not a V4
-- migration, is not a Supabase/Production patch, and must never be applied to
-- a provider-managed target.
--
-- Supabase Production exposes pgcrypto from the provider-owned `extensions`
-- schema. The disposable target mirrors that placement before candidate 0001
-- runs; its database-level search_path also makes extension-owned UUID helpers
-- resolvable by the frozen candidate SQL without changing that SQL.
--
-- Candidate 0001 verifies this pre-existing compatibility role and fails
-- closed if it is missing or does not have the platform-equivalent BYPASSRLS
-- capability. The migration itself never creates or alters service_role.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

DO $$
BEGIN
  EXECUTE format(
    'ALTER DATABASE %I SET search_path = "$user", public, extensions',
    current_database()
  );
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
      FROM pg_catalog.pg_roles
     WHERE rolname = 'service_role'
  ) THEN
    CREATE ROLE service_role
      NOLOGIN
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT
      NOREPLICATION
      BYPASSRLS;
  END IF;
END;
$$;

-- Provider-managed extension schemas are usable by the controlled server-side
-- role, while anonymous/public roles remain unable to resolve extension
-- functions.  The runtime role simulation inherits this capability through
-- service_role; no public.digest alias or extension relocation is created.
GRANT USAGE ON SCHEMA extensions TO service_role;
