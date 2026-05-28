-- Backfill: add public-read RLS policy for statcast_pitching.
--
-- The original create_statcast_pitching migration (20260519120000) created the
-- table and indexes but omitted the RLS enable + policy that every other
-- Statcast table carries.  The policy was documented in SCHEMA.md but never
-- committed to a migration file, so any direct anon-key query against
-- statcast_pitching returns 0 rows (RLS blocks silently).
--
-- This surfaced via the pipeline status page (GET /api/status) which performs
-- a direct anon-key HEAD count on each table.
--
-- ALTER TABLE ... ENABLE ROW LEVEL SECURITY is idempotent.
-- DROP POLICY IF EXISTS + CREATE POLICY is idempotent.

ALTER TABLE public.statcast_pitching ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public can read statcast pitching" ON public.statcast_pitching;

CREATE POLICY "Public can read statcast pitching"
  ON public.statcast_pitching FOR SELECT
  TO anon, authenticated
  USING (true);
