-- =====================================================================
-- ASETS 0004 — receipt images in the database
--
-- The alternative was an object store, which for a handful of
-- practitioners means another service, another set of credentials,
-- another thing to get wrong on account deletion, and a bill. A receipt
-- photo is ~200 KB and a busy year is a few hundred of them, so the
-- database holds a decade of them comfortably and the images inherit
-- everything the rest of the data already has: row-level security,
-- transactional deletes, and the same backup.
--
-- Revisit this if a user ever passes a few hundred megabytes.
-- =====================================================================

SET search_path = asets, public;

CREATE TABLE asets.receipt_files (
    path         text PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES asets.users(id) ON DELETE CASCADE,
    content_type text NOT NULL DEFAULT 'image/jpeg',
    bytes        bytea NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    -- The app compresses before upload; this is a backstop against a
    -- single row eating the whole database.
    CONSTRAINT receipt_files_size_limit CHECK (octet_length(bytes) <= 8 * 1024 * 1024),
    CONSTRAINT receipt_files_not_empty CHECK (octet_length(bytes) > 0)
);

CREATE INDEX receipt_files_user_idx ON asets.receipt_files (user_id, created_at DESC);

ALTER TABLE asets.receipt_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE asets.receipt_files FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON asets.receipt_files
    USING (user_id = asets.current_user_id())
    WITH CHECK (user_id = asets.current_user_id());

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asets_app') THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON asets.receipt_files TO asets_app;
  END IF;
END
$$;

-- How much space the images are taking, for the operator.
CREATE OR REPLACE VIEW asets.receipt_storage_usage AS
SELECT user_id,
       count(*)                       AS files,
       sum(octet_length(bytes))       AS bytes_used,
       pg_size_pretty(sum(octet_length(bytes))::bigint) AS pretty
  FROM asets.receipt_files
 GROUP BY user_id;
