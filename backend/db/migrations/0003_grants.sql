-- =====================================================================
-- ASETS 0003 — runtime privileges
--
-- Migrations run as the database administrator (Cloud SQL only lets the
-- admin user CREATE EXTENSION, so that is unavoidable for 0001). The
-- application never uses that account: it connects as asets_app, which
-- holds DML only, cannot touch the schema, and is bound by row-level
-- security — FORCE ROW LEVEL SECURITY in 0001/0002 means even the table
-- owner is fenced, so a mistake in the deploy role is not a data leak.
--
-- Guarded by a role-exists check so a throwaway test cluster can run the
-- migrations without provisioning the role first.
-- =====================================================================

SET search_path = asets, public;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asets_app') THEN
    RAISE NOTICE 'role asets_app does not exist — skipping grants';
    RETURN;
  END IF;

  GRANT USAGE ON SCHEMA asets TO asets_app;

  -- Everything the app writes.
  GRANT SELECT, INSERT, UPDATE, DELETE ON
      asets.users,
      asets.user_services,
      asets.clients,
      asets.invoices,
      asets.invoice_items,
      asets.expenses,
      asets.hmrc_oauth_states,
      asets.hmrc_connections,
      asets.hmrc_submissions
    TO asets_app;

  -- Reference data is read-only at runtime; it changes by migration.
  GRANT SELECT ON asets.expense_categories TO asets_app;

  GRANT EXECUTE ON FUNCTION asets.current_user_id() TO asets_app;

  -- Nothing the app can do should ever create objects.
  REVOKE CREATE ON SCHEMA asets FROM asets_app;
END
$$;

-- Future tables default to the same posture.
ALTER DEFAULT PRIVILEGES IN SCHEMA asets
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO asets_app;
