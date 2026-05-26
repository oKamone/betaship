-- betashipスキーマの権限付与
-- Supabase SQL Editor で一度だけ実行してください

GRANT USAGE ON SCHEMA betaship TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA betaship TO postgres, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA betaship TO authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA betaship TO anon;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA betaship TO postgres, anon, authenticated, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA betaship
  GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA betaship
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA betaship
  GRANT EXECUTE ON FUNCTIONS TO postgres, anon, authenticated, service_role;
