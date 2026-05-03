-- ADR-070: Issue Activity Context
-- Add activity logs and error context to issue reports for debugging

ALTER TABLE local_issues ADD COLUMN activity_context TEXT;  -- Formatted activity log
ALTER TABLE local_issues ADD COLUMN error_context TEXT;     -- Error details JSON when reported from Errors page
