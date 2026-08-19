-- Orbit live evals: append-only score store (parity with
-- app/modules/assistant/live_eval/models.py — init_db's create_all also
-- creates this on fresh envs; this file is for existing databases).
--
-- ALCOA+ contract: rows are INSERT-only. The application exposes no update or
-- delete path; corrections are new rows. Do not add UPDATE/DELETE grants for
-- app roles beyond what the shared connection already has.

CREATE TABLE IF NOT EXISTS live_eval_scores (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id VARCHAR(255) NOT NULL,
    session_id VARCHAR(255) NOT NULL,
    message_preview VARCHAR(300) NOT NULL DEFAULT '',
    answer_preview VARCHAR(500) NOT NULL DEFAULT '',
    scored_mode VARCHAR(32) NOT NULL,
    judge_model VARCHAR(64),
    overall_passed BOOLEAN NOT NULL,
    metrics JSON NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS ix_live_eval_scores_created
    ON live_eval_scores (created_at);
CREATE INDEX IF NOT EXISTS ix_live_eval_scores_user_created
    ON live_eval_scores (user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_live_eval_scores_user_id
    ON live_eval_scores (user_id);
