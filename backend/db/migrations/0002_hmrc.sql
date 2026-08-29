-- =====================================================================
-- ASETS 0002 — HMRC Making Tax Digital (Income Tax Self Assessment)
--
-- Three concerns, three tables:
--   oauth_states  short-lived PKCE state for the authorisation redirect
--   connections   one live grant per user (tokens encrypted app-side)
--   submissions   an append-only record of everything we sent HMRC
--
-- Tokens and the National Insurance number are stored as bytea: the
-- application encrypts them with Fernet before they ever reach the
-- database, so a database dump discloses neither.
-- =====================================================================

SET search_path = asets, public;

CREATE TYPE asets.hmrc_submission_type AS ENUM (
    'quarterly_update',
    'annual_summary',
    'final_declaration',
    'trigger_calculation',
    'retrieve_calculation',
    'retrieve_obligations',
    'retrieve_businesses'
);

CREATE TYPE asets.hmrc_submission_status AS ENUM (
    'pending',    -- request built, outcome not yet known
    'accepted',   -- HMRC returned 2xx
    'rejected',   -- HMRC returned 4xx (business or validation failure)
    'error'       -- transport failure or 5xx
);

-- ---------------------------------------------------------------------
-- hmrc_oauth_states — one row per authorisation attempt
-- ---------------------------------------------------------------------
CREATE TABLE asets.hmrc_oauth_states (
    state         text PRIMARY KEY,
    user_id       uuid NOT NULL REFERENCES asets.users(id) ON DELETE CASCADE,
    code_verifier text NOT NULL,
    redirect_uri  text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    used_at       timestamptz,
    CONSTRAINT hmrc_oauth_states_window CHECK (expires_at > created_at)
);
CREATE INDEX hmrc_oauth_states_expiry_idx ON asets.hmrc_oauth_states (expires_at);

-- ---------------------------------------------------------------------
-- hmrc_connections — the live grant
-- ---------------------------------------------------------------------
CREATE TABLE asets.hmrc_connections (
    user_id             uuid PRIMARY KEY REFERENCES asets.users(id) ON DELETE CASCADE,
    nino_encrypted      bytea,
    business_id         text,
    business_type       text,
    accounting_type     text,
    access_token        bytea NOT NULL,
    refresh_token       bytea NOT NULL,
    access_expires_at   timestamptz NOT NULL,
    scopes              text[] NOT NULL DEFAULT '{}',
    environment         text NOT NULL DEFAULT 'sandbox',
    connected_at        timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    last_error          text,
    CONSTRAINT hmrc_connections_env CHECK (environment IN ('sandbox', 'production'))
);
CREATE TRIGGER hmrc_connections_touch BEFORE UPDATE ON asets.hmrc_connections
  FOR EACH ROW EXECUTE FUNCTION asets.touch_updated_at();

-- ---------------------------------------------------------------------
-- hmrc_submissions — the audit trail
--
-- If HMRC ever asks "what did your software send, and when", this table
-- is the answer. Rows may be completed once (pending -> final) and are
-- immutable after that; nothing may ever delete one.
-- ---------------------------------------------------------------------
CREATE TABLE asets.hmrc_submissions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES asets.users(id) ON DELETE CASCADE,
    submission_type asets.hmrc_submission_type NOT NULL,
    status          asets.hmrc_submission_status NOT NULL DEFAULT 'pending',
    tax_year        text,
    business_id     text,
    period_start    date,
    period_end      date,
    endpoint        text NOT NULL,
    correlation_id  text,
    receipt_id      text,
    http_status     integer,
    request_payload jsonb,
    response_payload jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz,
    CONSTRAINT hmrc_submissions_tax_year_shape
        CHECK (tax_year IS NULL OR tax_year ~ '^[0-9]{4}-[0-9]{2}$'),
    CONSTRAINT hmrc_submissions_period_order
        CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start)
);
CREATE INDEX hmrc_submissions_user_idx ON asets.hmrc_submissions (user_id, created_at DESC);
CREATE INDEX hmrc_submissions_period_idx ON asets.hmrc_submissions (user_id, tax_year, period_start);

-- Append-only, with one deliberate exception: erasing an account must
-- really erase it (we promise that in the privacy policy). The deletion
-- routine opts in explicitly by setting asets.allow_audit_purge, so an
-- ordinary DELETE still cannot quietly rewrite history.
CREATE OR REPLACE FUNCTION asets.hmrc_submissions_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF COALESCE(current_setting('asets.allow_audit_purge', true), 'off') = 'on' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'hmrc_submissions is append-only: rows cannot be deleted';
    END IF;
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'hmrc_submission % is final (status=%) and cannot be modified', OLD.id, OLD.status;
    END IF;
    IF NEW.id <> OLD.id OR NEW.user_id <> OLD.user_id
       OR NEW.submission_type <> OLD.submission_type
       OR NEW.request_payload IS DISTINCT FROM OLD.request_payload THEN
        RAISE EXCEPTION 'hmrc_submission % may only be completed, not rewritten', OLD.id;
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER hmrc_submissions_append_only
  BEFORE UPDATE OR DELETE ON asets.hmrc_submissions
  FOR EACH ROW EXECUTE FUNCTION asets.hmrc_submissions_immutable();

-- ---------------------------------------------------------------------
-- Row-level security
--
-- hmrc_oauth_states is excluded on purpose: the OAuth callback arrives
-- with nothing but the state token and has to resolve the user *from*
-- it, so there is no tenant to fence against yet. The state itself is a
-- 32-byte secret and single-use.
-- ---------------------------------------------------------------------
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['hmrc_connections','hmrc_submissions']
  LOOP
    EXECUTE format('ALTER TABLE asets.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE asets.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format($f$
      CREATE POLICY tenant_isolation ON asets.%I
        USING (user_id = asets.current_user_id())
        WITH CHECK (user_id = asets.current_user_id())
    $f$, t);
  END LOOP;
END
$$;
