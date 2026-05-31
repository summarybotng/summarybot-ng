-- Migration 115: Extended job tracking fields (ADR-112)
-- Add skip_existing and creation_source for better job visibility

-- Add skip_existing column (defaults to 1/true for backwards compatibility)
ALTER TABLE summary_jobs ADD COLUMN skip_existing INTEGER DEFAULT 1;

-- Add creation_source column to track where jobs were created from
-- Values: 'wizard', 'archive_dialog', 'api', 'scheduled', 'unknown'
ALTER TABLE summary_jobs ADD COLUMN creation_source TEXT DEFAULT 'unknown';
