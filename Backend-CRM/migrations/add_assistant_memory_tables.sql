-- Orbit derived memory (app/modules/assistant/memory).
-- Two tables with opposite lifecycles:
--   assistant_turn   : short-TTL RAW buffer the nightly distiller reads (pruned by retention).
--   assistant_memory : capped (~40/user) DERIVED, PHI-stripped items loaded at session open.
-- Parity with the SQLAlchemy models; init_db's create_all also creates these in dev.

-- RAW turn buffer (rolling retention; NOT a permanent transcript) --------------
CREATE TABLE IF NOT EXISTS assistant_turn (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL,               -- 'user' | 'assistant'
    text TEXT NOT NULL,
    source_conversation_id UUID,             -- cascade delete of derived memory
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_assistant_turn_user_id ON assistant_turn (user_id);
CREATE INDEX IF NOT EXISTS ix_assistant_turn_created_at ON assistant_turn (created_at);
CREATE INDEX IF NOT EXISTS ix_assistant_turn_user_created ON assistant_turn (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_assistant_turn_source_conversation_id ON assistant_turn (source_conversation_id);

-- DERIVED memory (bounded per user; PHI-free by construction) ------------------
CREATE TABLE IF NOT EXISTS assistant_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    type VARCHAR(16) NOT NULL,               -- preference | pattern | context
    text VARCHAR(500) NOT NULL,
    salience DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    hits INTEGER NOT NULL DEFAULT 1,
    ref_study_id VARCHAR(255),               -- re-validated vs entitlements at load
    source_turn_id UUID,
    source_conversation_id UUID,
    excluded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_assistant_memory_user_id ON assistant_memory (user_id);
CREATE INDEX IF NOT EXISTS ix_assistant_memory_user_salience ON assistant_memory (user_id, salience);
CREATE INDEX IF NOT EXISTS ix_assistant_memory_source_conversation_id ON assistant_memory (source_conversation_id);
