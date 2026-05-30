-- ADR-113: Confluence Section Configuration
-- Adds per-guild toggle options for Confluence publishing sections and labels

-- Section toggle options (defaults: summary, key_points, action_items ON; participants OFF)
ALTER TABLE confluence_settings ADD COLUMN include_summary INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN include_key_points INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN include_action_items INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN include_participants INTEGER DEFAULT 0;

-- Label configuration
ALTER TABLE confluence_settings ADD COLUMN include_labels INTEGER DEFAULT 1;
