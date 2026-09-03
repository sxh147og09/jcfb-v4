-- JCFB V4 DISPOSABLE LOCAL ROLE BOOTSTRAP
-- This file is mounted only into the repository-local disposable PostgreSQL
-- container during first-time database initialization. It is not a V4
-- migration, is not a Supabase/Production patch, and must never be applied to
-- a provider-managed target.
--
-- Candidate 0001 verifies this pre-existing compatibility role and fails
-- closed if it is missing or does not have the platform-equivalent BYPASSRLS
-- capability. The migration itself never creates or alters service_role.
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
