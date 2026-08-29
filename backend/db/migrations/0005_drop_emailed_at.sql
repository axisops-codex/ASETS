-- =====================================================================
-- ASETS 0005 — drop invoices.emailed_at
--
-- Sending invoices by email was removed: the app shares the PDF through
-- the phone's own share sheet instead, which reaches the client from the
-- practitioner's own address rather than from a server. Nothing sets
-- this column any more, and a column nothing writes is a column someone
-- will one day trust.
-- =====================================================================

SET search_path = asets, public;

ALTER TABLE asets.invoices DROP COLUMN IF EXISTS emailed_at;
