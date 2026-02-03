-- ResearchLab Database Initialization Script
-- This script runs automatically when the PostgreSQL container starts

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Create additional indexes for performance
-- These will be created after tables are initialized by SQLAlchemy

-- Note: The main table creation is handled by SQLAlchemy in the application
-- This script is for additional database setup that can't be done through SQLAlchemy

-- Create a function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- The trigger will be added after table creation by the application