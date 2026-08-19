-- Migration: add amendment_of_id to agreements table
-- Supports amendment/amendment-chain tracking (self-referential FK).

ALTER TABLE agreements
  ADD COLUMN IF NOT EXISTS amendment_of_id UUID REFERENCES agreements(id) ON DELETE SET NULL;
