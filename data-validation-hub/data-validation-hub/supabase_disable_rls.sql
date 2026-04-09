-- ============================================================================
-- DISABILITA RLS sulle tabelle target (solo per POC)
-- Esegui nel SQL Editor di Supabase
-- ============================================================================

ALTER TABLE dim_stores     DISABLE ROW LEVEL SECURITY;
ALTER TABLE dim_customers  DISABLE ROW LEVEL SECURITY;
ALTER TABLE dim_products   DISABLE ROW LEVEL SECURITY;
ALTER TABLE fact_sales     DISABLE ROW LEVEL SECURITY;

-- Oppure, se preferisci mantenere RLS attivo, crea una policy permissiva:
--
-- CREATE POLICY "allow_all_inserts" ON dim_stores     FOR ALL USING (true) WITH CHECK (true);
-- CREATE POLICY "allow_all_inserts" ON dim_customers  FOR ALL USING (true) WITH CHECK (true);
-- CREATE POLICY "allow_all_inserts" ON dim_products   FOR ALL USING (true) WITH CHECK (true);
-- CREATE POLICY "allow_all_inserts" ON fact_sales     FOR ALL USING (true) WITH CHECK (true);
