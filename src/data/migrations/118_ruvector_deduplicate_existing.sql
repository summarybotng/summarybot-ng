-- ADR-118: Clean up duplicate knowledge units from rolling schedule re-runs
-- This migration removes duplicate KUs that have identical content within the same summary

-- Step 1: Create temp table with duplicates identified (keep oldest by created_at)
CREATE TEMPORARY TABLE IF NOT EXISTS duplicate_ku_ids AS
WITH ranked_units AS (
    SELECT
        id,
        guild_id,
        summary_id,
        content,
        ROW_NUMBER() OVER (
            PARTITION BY guild_id, summary_id, content
            ORDER BY created_at ASC
        ) as rn
    FROM wiki_knowledge_units
    WHERE summary_id IS NOT NULL
)
SELECT id FROM ranked_units WHERE rn > 1;

-- Step 2: Delete edges pointing to/from duplicate units
DELETE FROM wiki_edges
WHERE from_unit_id IN (SELECT id FROM duplicate_ku_ids)
   OR to_unit_id IN (SELECT id FROM duplicate_ku_ids);

-- Step 3: Delete learning signals for duplicate units
DELETE FROM wiki_learning_signals
WHERE unit_id IN (SELECT id FROM duplicate_ku_ids);

-- Step 4: Delete coherence validations for duplicate units
DELETE FROM wiki_coherence_validations
WHERE unit_id IN (SELECT id FROM duplicate_ku_ids);

-- Step 5: Delete the duplicate units
DELETE FROM wiki_knowledge_units
WHERE id IN (SELECT id FROM duplicate_ku_ids);

-- Step 6: Clean up
DROP TABLE IF EXISTS duplicate_ku_ids;
