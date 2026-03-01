-- Migration 018: Populate message_count column from JSON data
-- ADR-017: Fix sorting by message_count
--
-- The stored_summaries.message_count column was not being populated
-- during INSERT. This migration extracts the value from summary_json
-- and updates the column for all existing records.

-- Update message_count from JSON for all records where it's NULL or 0
UPDATE stored_summaries
SET message_count = COALESCE(
    CAST(json_extract(summary_json, '$.message_count') AS INTEGER),
    0
)
WHERE message_count IS NULL OR message_count = 0;

-- Also update participant_count from JSON
UPDATE stored_summaries
SET participant_count = COALESCE(
    json_array_length(json_extract(summary_json, '$.participants')),
    0
)
WHERE participant_count IS NULL OR participant_count = 0;
