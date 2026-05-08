-- schema-setup.sql
-- Run this ONCE when setting up a new database, before importing any data.
-- Safe to re-run: all statements use IF NOT EXISTS.

USE `Micro-Surveys`;

-- Prevents duplicate People rows on re-import (ON DUPLICATE KEY UPDATE fires on this constraint)
CREATE UNIQUE INDEX IF NOT EXISTS uniq_people_empl_id ON People (EMPL_ID);
