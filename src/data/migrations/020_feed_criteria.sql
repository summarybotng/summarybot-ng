-- Migration 020: Add criteria column to feed_configs for ADR-037
-- Created: 2026-04-04

-- Add criteria column for storing filter criteria as JSON
ALTER TABLE feed_configs ADD COLUMN criteria TEXT;

-- Update schema version
INSERT INTO schema_version (version, applied_at, description)
VALUES (20, datetime('now'), 'Add criteria column to feed_configs for ADR-037 filter support');
