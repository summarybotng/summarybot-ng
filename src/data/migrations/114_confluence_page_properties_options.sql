-- ADR-114: Page Properties metadata options
-- Control which fields appear in Page Properties macro and display options

-- Whether to include Page Properties macro at all
ALTER TABLE confluence_settings ADD COLUMN include_page_properties INTEGER DEFAULT 1;

-- Whether to wrap Page Properties in an expander (default true)
ALTER TABLE confluence_settings ADD COLUMN page_properties_in_expander INTEGER DEFAULT 1;

-- Individual property toggles - basic info
ALTER TABLE confluence_settings ADD COLUMN prop_show_channel INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN prop_show_period_start INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN prop_show_period_end INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN prop_show_message_count INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN prop_show_participant_count INTEGER DEFAULT 1;

-- Individual property toggles - summary metadata
ALTER TABLE confluence_settings ADD COLUMN prop_show_summary_type INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN prop_show_perspective INTEGER DEFAULT 0;
ALTER TABLE confluence_settings ADD COLUMN prop_show_granularity INTEGER DEFAULT 1;
ALTER TABLE confluence_settings ADD COLUMN prop_show_source INTEGER DEFAULT 0;
