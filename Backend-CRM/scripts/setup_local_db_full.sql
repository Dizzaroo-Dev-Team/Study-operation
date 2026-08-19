-- =====================================================================
-- setup_local_db_full.sql  —  ONE-PASTE LOCAL DB BOOTSTRAP
--
-- Caveman talk:
--   Big rock = Neon (cloud DB).
--   Small rock = your laptop DB.
--   This script make small rock look like big rock + sprinkle seed acorns.
--   You paste, you press Enter, you done.
--
-- HOW TO RUN (pick one):
--   psql:    psql -v ON_ERROR_STOP=1 -d crm_local -f scripts/setup_local_db_full.sql
--   pgAdmin: open this file in Query Tool against your local DB, hit Run (F5).
--   DBeaver: open in SQL Editor, target your local DB, Execute Script (Alt+X).
--
-- Pure SQL — no psql meta-commands (\set, \i, \echo). Works in any client.
--
-- WHAT YOU NEED FIRST:
--   1. A local Postgres 15+ instance up.
--   2. A target database already created. Example:
--        CREATE DATABASE crm_local;
--   3. Connected to that database (NOT to "postgres").
--
-- WHAT THIS SCRIPT DOES:
--   1. Enables pgcrypto (for gen_random_uuid()).
--   2. Creates all ENUM types.
--   3. Creates all core tables, indexes, constraints, foreign keys.
--   4. Creates site-budgeting tables + columns (from migrations).
--   5. Seeds master data: cost elements, factor types.
--
-- WHAT THIS SCRIPT DOES NOT DO:
--   - Does NOT copy customer / transactional data from Neon.
--   - Does NOT touch MongoDB collections (feasibility, etc).
--   - Does NOT auto-create the database — you do that first.
--
-- RE-RUNNABLE? Yes, mostly:
--   - Tables / indexes / FKs use IF NOT EXISTS guards or DO blocks.
--   - Seeds use ON CONFLICT DO NOTHING.
--   - If you want a HARD WIPE, uncomment the DROP SCHEMA block below.
-- =====================================================================

-- NOTE: do NOT add `\set ON_ERROR_STOP on` here — that is a psql-only
-- meta-command and will be a SYNTAX ERROR in pgAdmin / DBeaver / SQL Editor.
-- If you run via psql CLI, pass the flag on the command line instead:
--    psql -v ON_ERROR_STOP=1 -d crm_local -f scripts/setup_local_db_full.sql

-- ---------------------------------------------------------------------
-- (OPTIONAL) HARD WIPE — uncomment 2 lines to nuke and rebuild.
-- DANGER: drops EVERYTHING in the public schema. Only use on a dev DB.
-- ---------------------------------------------------------------------
-- DROP SCHEMA IF EXISTS public CASCADE;
-- CREATE SCHEMA public;

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================================
-- 1. ENUM TYPES (idempotent via DO + duplicate_object catch)
-- =====================================================================

DO $$ BEGIN
    CREATE TYPE public.accesstype AS ENUM ('READ', 'WRITE', 'ADMIN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.agreement_status AS ENUM (
        'DRAFT', 'UNDER_REVIEW', 'UNDER_NEGOTIATION', 'READY_FOR_SIGNATURE',
        'SENT_FOR_SIGNATURE', 'EXECUTED', 'CLOSED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.comment_type AS ENUM ('INTERNAL', 'EXTERNAL', 'SYSTEM');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.document_category AS ENUM (
        'investigator_cv', 'signed_cda', 'cta', 'irb_package',
        'feasibility_questionnaire', 'feasibility_response',
        'onsite_visit_report', 'site_visibility_report', 'other'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.document_type AS ENUM ('sponsor', 'site');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.messagechannel AS ENUM ('SMS', 'WHATSAPP', 'EMAIL');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.messagedirection AS ENUM ('INBOUND', 'OUTBOUND');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.messagestatus AS ENUM ('QUEUED', 'SENT', 'DELIVERED', 'FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.review_status AS ENUM ('pending', 'approved', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.site_primary_status AS ENUM (
        'UNDER_EVALUATION', 'STARTUP', 'INITIATING', 'INITIATED_NOT_RECRUITING',
        'RECRUITING', 'ACTIVE_NOT_RECRUITING', 'COMPLETED', 'SUSPENDED',
        'TERMINATED', 'WITHDRAWN', 'CLOSED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.step_status AS ENUM ('not_started', 'in_progress', 'completed', 'locked');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.template_type AS ENUM ('CDA', 'CTA', 'BUDGET', 'OTHER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.userrole AS ENUM (
        'SPONSOR', 'SITE_MANAGER', 'COORDINATOR', 'PARTICIPANT',
        'cra', 'study_manager', 'medical_monitor'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE public.workflow_step_name AS ENUM (
        'site_identification', 'cda_execution', 'feasibility',
        'site_selection_outcome', 'agreement_executed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

SET default_tablespace = '';
SET default_table_access_method = heap;

-- =====================================================================
-- 2. CORE TABLES
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.users (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    name character varying(255),
    email character varying(255),
    password_hash character varying(255),
    role public.userrole NOT NULL,
    is_privileged character varying(10) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_user_id_key UNIQUE (user_id),
    CONSTRAINT users_email_key UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS public.sites (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    site_id character varying(100) NOT NULL,
    name character varying(500) NOT NULL,
    code character varying(100),
    location character varying(500),
    principal_investigator character varying(255),
    address text,
    city character varying(255),
    country character varying(255),
    status character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT sites_pkey PRIMARY KEY (id),
    CONSTRAINT sites_site_id_key UNIQUE (site_id)
);

CREATE TABLE IF NOT EXISTS public.studies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    study_id character varying(100) NOT NULL,
    name character varying(500) NOT NULL,
    description text,
    status character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT studies_pkey PRIMARY KEY (id),
    CONSTRAINT studies_study_id_key UNIQUE (study_id)
);

CREATE TABLE IF NOT EXISTS public.study_sites (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    study_id uuid NOT NULL,
    site_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT study_sites_pkey PRIMARY KEY (id),
    CONSTRAINT uq_study_site UNIQUE (study_id, site_id)
);

CREATE TABLE IF NOT EXISTS public.study_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    study_id uuid NOT NULL,
    template_name character varying(255) NOT NULL,
    template_type public.template_type NOT NULL,
    document_html text,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_active character varying(10) DEFAULT 'true'::character varying NOT NULL,
    template_content jsonb,
    placeholder_config json,
    template_file_path text,
    template_file_url text,
    field_mappings json,
    CONSTRAINT study_templates_pkey PRIMARY KEY (id),
    CONSTRAINT chk_study_template_is_active CHECK (((is_active)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[])))
);

CREATE TABLE IF NOT EXISTS public.agreements (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    site_id uuid NOT NULL,
    title character varying(500) NOT NULL,
    status public.agreement_status DEFAULT 'DRAFT'::public.agreement_status NOT NULL,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_legacy character varying(10) DEFAULT 'false'::character varying NOT NULL,
    zoho_request_id character varying(255),
    signature_status character varying(50),
    study_id uuid,
    agreement_type public.template_type,
    study_site_id uuid,
    editing_user_id character varying(255),
    editing_started_at timestamp with time zone,
    CONSTRAINT agreements_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.agreement_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    version_number integer NOT NULL,
    document_html text,
    created_from_template_id uuid,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_signed_version character varying(10) DEFAULT 'false'::character varying NOT NULL,
    document_content jsonb,
    document_file_path text,
    CONSTRAINT agreement_documents_pkey PRIMARY KEY (id),
    CONSTRAINT uq_agreement_document_version UNIQUE (agreement_id, version_number),
    CONSTRAINT chk_agreement_document_is_signed CHECK (((is_signed_version)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[])))
);

CREATE TABLE IF NOT EXISTS public.agreement_changes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    document_version_id uuid NOT NULL,
    previous_version_id uuid,
    change_type character varying(50) NOT NULL,
    section_reference character varying(500),
    old_text text,
    new_text text,
    paragraph_index integer,
    table_index integer,
    row_index integer,
    cell_index integer,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    is_external_change character varying(10) DEFAULT 'false'::character varying NOT NULL,
    is_accepted character varying(10) DEFAULT 'false'::character varying NOT NULL,
    accepted_by character varying(255),
    accepted_at timestamp with time zone,
    CONSTRAINT agreement_changes_pkey PRIMARY KEY (id),
    CONSTRAINT chk_agreement_changes_change_type CHECK (((change_type)::text = ANY ((ARRAY['ADDED'::character varying, 'DELETED'::character varying, 'MODIFIED'::character varying])::text[]))),
    CONSTRAINT chk_agreement_changes_is_accepted CHECK (((is_accepted)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[]))),
    CONSTRAINT chk_agreement_changes_is_external_change CHECK (((is_external_change)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[])))
);

CREATE TABLE IF NOT EXISTS public.agreement_comments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    version_id uuid,
    comment_type public.comment_type NOT NULL,
    content text NOT NULL,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agreement_comments_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.agreement_inline_comments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    document_id uuid NOT NULL,
    comment_text text NOT NULL,
    position_reference jsonb,
    comment_type public.comment_type NOT NULL,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agreement_inline_comments_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.agreement_review_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    token character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    used_at timestamp with time zone,
    is_active character varying(10) DEFAULT 'true'::character varying NOT NULL,
    CONSTRAINT agreement_review_tokens_pkey PRIMARY KEY (id),
    CONSTRAINT agreement_review_tokens_token_key UNIQUE (token),
    CONSTRAINT chk_agreement_review_tokens_is_active CHECK (((is_active)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[])))
);

CREATE TABLE IF NOT EXISTS public.agreement_review_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    review_token_id uuid NOT NULL,
    base_version_id uuid NOT NULL,
    review_file_path text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    is_submitted character varying(10) DEFAULT 'false'::character varying NOT NULL,
    submitted_at timestamp with time zone,
    CONSTRAINT agreement_review_documents_pkey PRIMARY KEY (id),
    CONSTRAINT chk_agreement_review_documents_is_submitted CHECK (((is_submitted)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[])))
);

-- OnlyOffice review comments extracted from review copies. Folded in from
-- migrations/add_agreement_document_comments.sql so NEW environments get it
-- automatically (it was previously a hand-run script, the deployed "comments not
-- showing" hazard). The NAMED unique constraint below is load-bearing: the upsert in
-- _upsert_comments_from_docx uses ON CONFLICT ON CONSTRAINT uq_agreement_doc_comment_oo_id
-- — if this constraint is missing, every comment insert fails. Do not rename it.
CREATE TABLE IF NOT EXISTS public.agreement_document_comments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    comment_id character varying(50) NOT NULL,
    review_document_id uuid,
    agreement_id uuid NOT NULL,
    author_email character varying(255) DEFAULT ''::character varying NOT NULL,
    comment_text text DEFAULT ''::text NOT NULL,
    referenced_text text,
    oo_date character varying(50),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    parent_comment_id uuid,
    is_internal_reply character varying(10) DEFAULT 'false'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT agreement_document_comments_pkey PRIMARY KEY (id),
    CONSTRAINT uq_agreement_doc_comment_oo_id UNIQUE (comment_id, review_document_id),
    CONSTRAINT chk_comment_status CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'rejected'::character varying, 'modified'::character varying])::text[]))),
    CONSTRAINT chk_internal_reply CHECK (((is_internal_reply)::text = ANY ((ARRAY['true'::character varying, 'false'::character varying])::text[]))),
    CONSTRAINT agreement_document_comments_review_document_id_fkey FOREIGN KEY (review_document_id) REFERENCES public.agreement_review_documents(id) ON DELETE CASCADE,
    CONSTRAINT agreement_document_comments_agreement_id_fkey FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE,
    CONSTRAINT agreement_document_comments_parent_comment_id_fkey FOREIGN KEY (parent_comment_id) REFERENCES public.agreement_document_comments(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_adc_agreement_id ON public.agreement_document_comments USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_adc_review_document_id ON public.agreement_document_comments USING btree (review_document_id);
CREATE INDEX IF NOT EXISTS idx_adc_parent_comment_id ON public.agreement_document_comments USING btree (parent_comment_id);
CREATE INDEX IF NOT EXISTS idx_adc_status ON public.agreement_document_comments USING btree (status);
CREATE INDEX IF NOT EXISTS idx_adc_created_at ON public.agreement_document_comments USING btree (created_at);

CREATE TABLE IF NOT EXISTS public.agreement_signed_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agreement_id uuid NOT NULL,
    file_path character varying(500) NOT NULL,
    signed_at timestamp with time zone,
    downloaded_from_zoho_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    zoho_request_id character varying(255),
    CONSTRAINT agreement_signed_documents_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.audit_logs (
    id uuid NOT NULL,
    "user" character varying(100),
    action character varying(100) NOT NULL,
    target_type character varying(50) NOT NULL,
    target_id character varying(100) NOT NULL,
    details json,
    "timestamp" timestamp with time zone DEFAULT now(),
    CONSTRAINT audit_logs_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.chat_documents (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    filename character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size integer NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now(),
    CONSTRAINT chat_documents_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    mode character varying(20) NOT NULL,
    document_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT chat_messages_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.conversation_access (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    access_type public.accesstype NOT NULL,
    granted_by character varying(255),
    granted_at timestamp with time zone DEFAULT now(),
    CONSTRAINT conversation_access_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.events (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    event_name character varying(500) NOT NULL,
    internal_external character varying(20) NOT NULL,
    event_type character varying(100),
    date_of_event timestamp with time zone,
    event_description text,
    event_report text,
    relevant_internal_stakeholders json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT events_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.feasibility_attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    study_site_id uuid NOT NULL,
    file_path character varying(500) NOT NULL,
    file_name character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size integer NOT NULL,
    uploaded_by character varying(255),
    uploaded_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT feasibility_attachments_pkey PRIMARY KEY (id),
    CONSTRAINT feasibility_attachments_study_site_id_key UNIQUE (study_site_id)
);

CREATE TABLE IF NOT EXISTS public.feasibility_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    study_site_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    token character varying(255) NOT NULL,
    status character varying(50) DEFAULT 'sent'::character varying NOT NULL,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT feasibility_requests_pkey PRIMARY KEY (id),
    CONSTRAINT feasibility_requests_token_key UNIQUE (token)
);

CREATE TABLE IF NOT EXISTS public.feasibility_responses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    request_id uuid NOT NULL,
    question_text text NOT NULL,
    question_id uuid,
    answer text NOT NULL,
    section character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT feasibility_responses_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.iis_studies (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    study_title character varying(500) NOT NULL,
    asset character varying(255),
    indication character varying(255),
    phases character varying(50),
    enrollment integer,
    enrollment_start_date timestamp with time zone,
    completion_date timestamp with time zone,
    other_associated_hcp_ids json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT iis_studies_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.project_feasibility_custom_questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    study_id uuid NOT NULL,
    workflow_step character varying(50) DEFAULT 'feasibility'::character varying NOT NULL,
    question_text text NOT NULL,
    section character varying(255),
    expected_response_type character varying(50),
    display_order integer DEFAULT 0 NOT NULL,
    created_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT project_feasibility_custom_questions_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.rd_studies (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    study_title character varying(500) NOT NULL,
    nct_number character varying(50),
    asset character varying(255),
    indication character varying(255),
    enrollment integer,
    phases character varying(50),
    start_date timestamp with time zone,
    completion_date timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT rd_studies_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.site_documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    site_id uuid NOT NULL,
    category public.document_category NOT NULL,
    file_path character varying(500) NOT NULL,
    file_name character varying(255) NOT NULL,
    content_type character varying(100) NOT NULL,
    size integer NOT NULL,
    uploaded_by character varying(255),
    uploaded_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    description text,
    metadata jsonb DEFAULT '{}'::jsonb,
    document_type public.document_type DEFAULT 'site'::public.document_type,
    review_status public.review_status DEFAULT 'pending'::public.review_status,
    tmf_filed character varying(10) DEFAULT 'false'::character varying NOT NULL,
    CONSTRAINT site_documents_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.site_profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    site_id uuid NOT NULL,
    site_name character varying(500),
    hospital_name character varying(500),
    pi_name character varying(255),
    pi_email character varying(255),
    pi_phone character varying(50),
    primary_contracting_entity character varying(500),
    authorized_signatory_name character varying(255),
    authorized_signatory_email character varying(255),
    authorized_signatory_title character varying(255),
    address_line_1 character varying(500),
    city character varying(255),
    state character varying(255),
    country character varying(255),
    postal_code character varying(50),
    site_coordinator_name character varying(255),
    site_coordinator_email character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT site_profiles_pkey PRIMARY KEY (id),
    CONSTRAINT site_profiles_site_id_key UNIQUE (site_id)
);

CREATE TABLE IF NOT EXISTS public.site_status_history (
    id uuid NOT NULL,
    site_id uuid NOT NULL,
    status public.site_primary_status NOT NULL,
    previous_status public.site_primary_status,
    metadata json,
    triggering_event character varying(100),
    reason text,
    changed_at timestamp with time zone DEFAULT now(),
    CONSTRAINT site_status_history_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.site_statuses (
    id uuid NOT NULL,
    site_id uuid NOT NULL,
    current_status public.site_primary_status NOT NULL,
    previous_status public.site_primary_status,
    metadata json,
    effective_at timestamp with time zone DEFAULT now(),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT site_statuses_pkey PRIMARY KEY (id),
    CONSTRAINT site_statuses_site_id_key UNIQUE (site_id)
);

CREATE TABLE IF NOT EXISTS public.site_workflow_steps (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    site_id uuid,
    step_name public.workflow_step_name NOT NULL,
    status public.step_status DEFAULT 'not_started'::public.step_status NOT NULL,
    step_data jsonb DEFAULT '{}'::jsonb,
    completed_at timestamp with time zone,
    completed_by character varying(255),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    study_site_id uuid,
    CONSTRAINT site_workflow_steps_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.user_profiles (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    name character varying(255),
    address text,
    phone character varying(50),
    email character varying(255),
    affiliation character varying(500),
    specialty character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT user_profiles_pkey PRIMARY KEY (id),
    CONSTRAINT user_profiles_user_id_key UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS public.user_role_assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id character varying(255) NOT NULL,
    role public.userrole NOT NULL,
    site_id uuid,
    study_id uuid,
    assigned_by character varying(255),
    assigned_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT user_role_assignments_pkey PRIMARY KEY (id),
    CONSTRAINT chk_role_type CHECK ((role = ANY (ARRAY['cra'::public.userrole, 'study_manager'::public.userrole, 'medical_monitor'::public.userrole])))
);

CREATE TABLE IF NOT EXISTS public.user_sites (
    id uuid NOT NULL,
    user_id character varying(255) NOT NULL,
    site_id uuid NOT NULL,
    role character varying(50),
    assigned_at timestamp with time zone DEFAULT now(),
    CONSTRAINT user_sites_pkey PRIMARY KEY (id)
);

-- =====================================================================
-- 3. INDEXES
-- =====================================================================

CREATE INDEX IF NOT EXISTS idx_agreement_changes_agreement_id ON public.agreement_changes USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_agreement_changes_created_at ON public.agreement_changes USING btree (created_at);
CREATE INDEX IF NOT EXISTS idx_agreement_changes_document_version_id ON public.agreement_changes USING btree (document_version_id);
CREATE INDEX IF NOT EXISTS idx_agreement_changes_is_accepted ON public.agreement_changes USING btree (is_accepted);
CREATE INDEX IF NOT EXISTS idx_agreement_changes_is_external_change ON public.agreement_changes USING btree (is_external_change);
CREATE INDEX IF NOT EXISTS idx_agreement_changes_previous_version_id ON public.agreement_changes USING btree (previous_version_id);
CREATE INDEX IF NOT EXISTS idx_agreement_documents_agreement_id ON public.agreement_documents USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_agreement_documents_template_id ON public.agreement_documents USING btree (created_from_template_id);
CREATE INDEX IF NOT EXISTS idx_agreement_review_documents_agreement_id ON public.agreement_review_documents USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_agreement_review_documents_base_version_id ON public.agreement_review_documents USING btree (base_version_id);
CREATE INDEX IF NOT EXISTS idx_agreement_review_documents_created_at ON public.agreement_review_documents USING btree (created_at);
CREATE INDEX IF NOT EXISTS idx_agreement_review_documents_is_submitted ON public.agreement_review_documents USING btree (is_submitted);
CREATE INDEX IF NOT EXISTS idx_agreement_review_documents_review_token_id ON public.agreement_review_documents USING btree (review_token_id);
CREATE INDEX IF NOT EXISTS idx_agreement_review_tokens_agreement_id ON public.agreement_review_tokens USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_agreement_review_tokens_expires_at ON public.agreement_review_tokens USING btree (expires_at);
CREATE INDEX IF NOT EXISTS idx_agreement_review_tokens_token ON public.agreement_review_tokens USING btree (token);
CREATE INDEX IF NOT EXISTS idx_agreement_signed_documents_agreement_id ON public.agreement_signed_documents USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_inline_comments_agreement_id ON public.agreement_inline_comments USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS idx_inline_comments_document_id ON public.agreement_inline_comments USING btree (document_id);
CREATE INDEX IF NOT EXISTS idx_study_templates_is_active ON public.study_templates USING btree (is_active);
CREATE INDEX IF NOT EXISTS idx_study_templates_study_id ON public.study_templates USING btree (study_id);
CREATE INDEX IF NOT EXISTS ix_agreement_comments_agreement_id ON public.agreement_comments USING btree (agreement_id);
CREATE INDEX IF NOT EXISTS ix_agreement_comments_created_at ON public.agreement_comments USING btree (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agreement_comments_version_id ON public.agreement_comments USING btree (version_id);
CREATE INDEX IF NOT EXISTS ix_agreements_created_at ON public.agreements USING btree (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agreements_editing_user_id ON public.agreements USING btree (editing_user_id);
CREATE INDEX IF NOT EXISTS ix_agreements_site_id ON public.agreements USING btree (site_id);
CREATE INDEX IF NOT EXISTS ix_agreements_status ON public.agreements USING btree (status);
CREATE INDEX IF NOT EXISTS ix_agreements_study_site_id ON public.agreements USING btree (study_site_id);
CREATE INDEX IF NOT EXISTS ix_feasibility_attachments_study_site_id ON public.feasibility_attachments USING btree (study_site_id);
CREATE INDEX IF NOT EXISTS ix_feasibility_requests_email ON public.feasibility_requests USING btree (email);
CREATE INDEX IF NOT EXISTS ix_feasibility_requests_status ON public.feasibility_requests USING btree (status);
CREATE INDEX IF NOT EXISTS ix_feasibility_requests_study_site_id ON public.feasibility_requests USING btree (study_site_id);
CREATE INDEX IF NOT EXISTS ix_feasibility_requests_token ON public.feasibility_requests USING btree (token);
CREATE INDEX IF NOT EXISTS ix_feasibility_responses_question_id ON public.feasibility_responses USING btree (question_id);
CREATE INDEX IF NOT EXISTS ix_feasibility_responses_request_id ON public.feasibility_responses USING btree (request_id);
CREATE INDEX IF NOT EXISTS ix_project_feasibility_custom_questions_study_id ON public.project_feasibility_custom_questions USING btree (study_id);
CREATE INDEX IF NOT EXISTS ix_project_feasibility_custom_questions_workflow_step ON public.project_feasibility_custom_questions USING btree (workflow_step);
CREATE INDEX IF NOT EXISTS ix_site_documents_category ON public.site_documents USING btree (category);
CREATE INDEX IF NOT EXISTS ix_site_documents_document_type ON public.site_documents USING btree (document_type);
CREATE INDEX IF NOT EXISTS ix_site_documents_review_status ON public.site_documents USING btree (review_status);
CREATE INDEX IF NOT EXISTS ix_site_documents_site_id ON public.site_documents USING btree (site_id);
CREATE INDEX IF NOT EXISTS ix_site_documents_uploaded_at ON public.site_documents USING btree (uploaded_at DESC);
CREATE INDEX IF NOT EXISTS ix_site_profiles_site_id ON public.site_profiles USING btree (site_id);
CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_site_id ON public.site_workflow_steps USING btree (site_id);
CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_status ON public.site_workflow_steps USING btree (status);
CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_step_name ON public.site_workflow_steps USING btree (step_name);
CREATE INDEX IF NOT EXISTS ix_site_workflow_steps_study_site_id ON public.site_workflow_steps USING btree (study_site_id);
CREATE INDEX IF NOT EXISTS ix_study_sites_site_id ON public.study_sites USING btree (site_id);
CREATE INDEX IF NOT EXISTS ix_study_sites_study_id ON public.study_sites USING btree (study_id);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_role ON public.user_role_assignments USING btree (role);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_site_id ON public.user_role_assignments USING btree (site_id);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_study_id ON public.user_role_assignments USING btree (study_id);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_user_id ON public.user_role_assignments USING btree (user_id);
CREATE INDEX IF NOT EXISTS ix_user_role_assignments_user_role ON public.user_role_assignments USING btree (user_id, role);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agreements_study_site_type ON public.agreements USING btree (study_id, site_id, agreement_type) WHERE ((study_id IS NOT NULL) AND (agreement_type IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS uq_site_workflow_step ON public.site_workflow_steps USING btree (site_id, step_name) WHERE (site_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS uq_study_site_workflow_step ON public.site_workflow_steps USING btree (study_site_id, step_name) WHERE (study_site_id IS NOT NULL);

-- =====================================================================
-- 4. FOREIGN KEYS (wrapped to be idempotent)
-- =====================================================================

DO $$
DECLARE
    fk RECORD;
BEGIN
    FOR fk IN
        SELECT * FROM (VALUES
            ('agreement_changes', 'agreement_changes_agreement_id_fkey',         'FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreement_changes', 'agreement_changes_document_version_id_fkey',  'FOREIGN KEY (document_version_id) REFERENCES public.agreement_documents(id) ON DELETE CASCADE'),
            ('agreement_changes', 'agreement_changes_previous_version_id_fkey',  'FOREIGN KEY (previous_version_id) REFERENCES public.agreement_documents(id) ON DELETE SET NULL'),
            ('agreement_comments', 'agreement_comments_agreement_id_fkey',       'FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreement_documents', 'agreement_documents_agreement_id_fkey',     'FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreement_documents', 'agreement_documents_created_from_template_id_fkey', 'FOREIGN KEY (created_from_template_id) REFERENCES public.study_templates(id) ON DELETE SET NULL'),
            ('agreement_inline_comments', 'agreement_inline_comments_agreement_id_fkey', 'FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreement_inline_comments', 'agreement_inline_comments_document_id_fkey',  'FOREIGN KEY (document_id) REFERENCES public.agreement_documents(id) ON DELETE CASCADE'),
            ('agreement_review_documents', 'agreement_review_documents_agreement_id_fkey',   'FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreement_review_documents', 'agreement_review_documents_base_version_id_fkey','FOREIGN KEY (base_version_id) REFERENCES public.agreement_documents(id) ON DELETE CASCADE'),
            ('agreement_review_documents', 'agreement_review_documents_review_token_id_fkey','FOREIGN KEY (review_token_id) REFERENCES public.agreement_review_tokens(id) ON DELETE CASCADE'),
            ('agreement_review_tokens', 'agreement_review_tokens_agreement_id_fkey','FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreement_signed_documents', 'fk_agreement_signed_documents_agreement','FOREIGN KEY (agreement_id) REFERENCES public.agreements(id) ON DELETE CASCADE'),
            ('agreements', 'agreements_site_id_fkey',       'FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE'),
            ('agreements', 'agreements_study_id_fkey',      'FOREIGN KEY (study_id) REFERENCES public.studies(id)'),
            ('agreements', 'agreements_study_site_id_fkey', 'FOREIGN KEY (study_site_id) REFERENCES public.study_sites(id)'),
            ('chat_documents', 'chat_documents_user_id_fkey', 'FOREIGN KEY (user_id) REFERENCES public.users(user_id)'),
            ('chat_messages', 'chat_messages_user_id_fkey',   'FOREIGN KEY (user_id) REFERENCES public.users(user_id)'),
            ('events', 'events_user_id_fkey',                 'FOREIGN KEY (user_id) REFERENCES public.users(user_id)'),
            ('feasibility_attachments', 'fk_feasibility_attachments_study_site', 'FOREIGN KEY (study_site_id) REFERENCES public.study_sites(id) ON DELETE CASCADE'),
            ('feasibility_requests', 'fk_feasibility_requests_study_site',       'FOREIGN KEY (study_site_id) REFERENCES public.study_sites(id) ON DELETE CASCADE'),
            ('feasibility_responses', 'fk_feasibility_responses_request',        'FOREIGN KEY (request_id) REFERENCES public.feasibility_requests(id) ON DELETE CASCADE'),
            ('iis_studies', 'iis_studies_user_id_fkey', 'FOREIGN KEY (user_id) REFERENCES public.users(user_id)'),
            ('project_feasibility_custom_questions', 'fk_project_feasibility_custom_questions_study', 'FOREIGN KEY (study_id) REFERENCES public.studies(id) ON DELETE CASCADE'),
            ('rd_studies', 'rd_studies_user_id_fkey',   'FOREIGN KEY (user_id) REFERENCES public.users(user_id)'),
            ('site_documents', 'site_documents_site_id_fkey', 'FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE'),
            ('site_profiles', 'fk_site_profile_site',   'FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE'),
            ('site_status_history', 'site_status_history_site_id_fkey', 'FOREIGN KEY (site_id) REFERENCES public.sites(id)'),
            ('site_statuses', 'site_statuses_site_id_fkey',             'FOREIGN KEY (site_id) REFERENCES public.sites(id)'),
            ('site_workflow_steps', 'site_workflow_steps_site_id_fkey',       'FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE'),
            ('site_workflow_steps', 'site_workflow_steps_study_site_id_fkey', 'FOREIGN KEY (study_site_id) REFERENCES public.study_sites(id) ON DELETE CASCADE'),
            ('study_sites', 'study_sites_site_id_fkey',   'FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE'),
            ('study_sites', 'study_sites_study_id_fkey',  'FOREIGN KEY (study_id) REFERENCES public.studies(id) ON DELETE CASCADE'),
            ('study_templates', 'study_templates_study_id_fkey', 'FOREIGN KEY (study_id) REFERENCES public.studies(id) ON DELETE CASCADE'),
            ('user_profiles', 'user_profiles_user_id_fkey',      'FOREIGN KEY (user_id) REFERENCES public.users(user_id)'),
            ('user_role_assignments', 'fk_user_role_site',  'FOREIGN KEY (site_id) REFERENCES public.sites(id) ON DELETE CASCADE'),
            ('user_role_assignments', 'fk_user_role_study', 'FOREIGN KEY (study_id) REFERENCES public.studies(id) ON DELETE CASCADE'),
            ('user_role_assignments', 'fk_user_role_user', 'FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE'),
            ('user_sites', 'user_sites_site_id_fkey', 'FOREIGN KEY (site_id) REFERENCES public.sites(id)'),
            ('user_sites', 'user_sites_user_id_fkey', 'FOREIGN KEY (user_id) REFERENCES public.users(user_id)')
        ) AS t(tbl, cname, defn)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = fk.cname) THEN
            EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I %s', fk.tbl, fk.cname, fk.defn);
        END IF;
    END LOOP;
END $$;

-- =====================================================================
-- 5. SITE BUDGETING TABLES (from create_site_budgeting_tables + phase1 + v2/v3/v4 + align + run_all_refactor)
-- =====================================================================

-- ---- cost_element ----
CREATE TABLE IF NOT EXISTS public.cost_element (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    unit_of_measure VARCHAR(50),
    element_type VARCHAR(20),
    cost_type VARCHAR(30),
    therapeutic_area VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- element_category (phase1)
CREATE TABLE IF NOT EXISTS public.element_category (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    parent_id   UUID REFERENCES public.element_category(id) ON DELETE SET NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_element_category_parent_id ON public.element_category(parent_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_element_category_name_parent
    ON public.element_category(name, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid));

-- element_bundle_composition (phase1)
CREATE TABLE IF NOT EXISTS public.element_bundle_composition (
    bundle_element_id  UUID NOT NULL REFERENCES public.cost_element(id) ON DELETE CASCADE,
    child_element_id   UUID NOT NULL REFERENCES public.cost_element(id) ON DELETE CASCADE,
    quantity_in_bundle DECIMAL(10,4) NOT NULL DEFAULT 1,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bundle_element_id, child_element_id)
);
CREATE INDEX IF NOT EXISTS ix_ebc_bundle_element_id ON public.element_bundle_composition(bundle_element_id);
CREATE INDEX IF NOT EXISTS ix_ebc_child_element_id  ON public.element_bundle_composition(child_element_id);

-- cost_element: category_id FK from phase1
ALTER TABLE public.cost_element ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES public.element_category(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_cost_element_category_id ON public.cost_element(category_id);

-- ---- element_cost_version ----
CREATE TABLE IF NOT EXISTS public.element_cost_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    element_id UUID NOT NULL REFERENCES public.cost_element(id) ON DELETE CASCADE,
    version_label VARCHAR(100) NOT NULL,
    base_unit_cost NUMERIC(18,4) NOT NULL,
    reference_currency CHAR(3) NOT NULL DEFAULT 'USD',
    effective_from DATE,
    effective_to DATE,
    source VARCHAR(100),
    is_bundle_override BOOLEAN NOT NULL DEFAULT FALSE,
    created_by VARCHAR(255),
    approved_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_element_cost_version_label UNIQUE (element_id, version_label)
);
CREATE INDEX IF NOT EXISTS ix_element_cost_version_element_id ON public.element_cost_version (element_id);

-- ---- conversion_factor_type ----
CREATE TABLE IF NOT EXISTS public.conversion_factor_type (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    mode VARCHAR(32) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ---- conversion_factor ----
CREATE TABLE IF NOT EXISTS public.conversion_factor (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    factor_type_id UUID NOT NULL REFERENCES public.conversion_factor_type(id) ON DELETE RESTRICT,
    trial_id UUID REFERENCES public.studies(id) ON DELETE CASCADE,
    country_code VARCHAR(3),
    site_id UUID REFERENCES public.sites(id) ON DELETE CASCADE,
    sequence_order INTEGER NOT NULL DEFAULT 0,
    value NUMERIC(18,6) NOT NULL,
    currency_code VARCHAR(3),
    label VARCHAR(255),
    justification TEXT,
    scope_level VARCHAR(32),
    scope_element_id UUID REFERENCES public.cost_element(id) ON DELETE SET NULL,
    scope_category VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_conversion_factor_trial_id    ON public.conversion_factor (trial_id);
CREATE INDEX IF NOT EXISTS ix_conversion_factor_site_id     ON public.conversion_factor (site_id);
CREATE INDEX IF NOT EXISTS ix_conversion_factor_country_code ON public.conversion_factor (country_code);

-- ---- trial_factor_configuration (post-refactor shape) ----
CREATE TABLE IF NOT EXISTS public.trial_factor_configuration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES public.studies(id) ON DELETE CASCADE,
    factor_type_id UUID REFERENCES public.conversion_factor_type(id) ON DELETE CASCADE,
    application_sequence INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_trial_factor_config_type UNIQUE (trial_id, factor_type_id)
);
CREATE INDEX IF NOT EXISTS ix_trial_factor_config_trial_type ON public.trial_factor_configuration (trial_id, factor_type_id);

-- ---- currency_exchange_rate ----
CREATE TABLE IF NOT EXISTS public.currency_exchange_rate (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_currency VARCHAR(3) NOT NULL,
    to_currency VARCHAR(3) NOT NULL,
    rate NUMERIC(18,8) NOT NULL,
    effective_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_currency_exchange_rate_pair_date
    ON public.currency_exchange_rate (from_currency, to_currency, effective_date);

-- ---- budget_template ----
CREATE TABLE IF NOT EXISTS public.budget_template (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES public.studies(id) ON DELETE CASCADE,
    site_id UUID REFERENCES public.sites(id) ON DELETE SET NULL,
    parent_template_id UUID REFERENCES public.budget_template(id) ON DELETE SET NULL,
    name VARCHAR(500) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    enrollment_planned INTEGER,
    target_currency_code VARCHAR(3) NOT NULL DEFAULT 'USD',
    cost_version_label VARCHAR(100),
    template_level VARCHAR(32),
    country_code VARCHAR(3),
    locked_exchange_rate_date DATE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_id     ON public.budget_template (trial_id);
CREATE INDEX IF NOT EXISTS ix_budget_template_site_id      ON public.budget_template (site_id);
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_level  ON public.budget_template (trial_id, template_level);
CREATE INDEX IF NOT EXISTS ix_budget_template_trial_country ON public.budget_template (trial_id, country_code);

-- ---- budget_line_item (post-refactor shape) ----
CREATE TABLE IF NOT EXISTS public.budget_line_item (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES public.budget_template(id) ON DELETE CASCADE,
    cost_element_id UUID NOT NULL REFERENCES public.cost_element(id) ON DELETE RESTRICT,
    is_excluded BOOLEAN NOT NULL DEFAULT FALSE,
    override_unit_cost NUMERIC(18,4),
    override_currency_code VARCHAR(3),
    override_quantity NUMERIC(18,4),
    default_quantity NUMERIC(10,2),
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    inherited_from_parent BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_budget_line_item_template_id     ON public.budget_line_item (budget_template_id);
CREATE INDEX IF NOT EXISTS ix_budget_line_item_cost_element_id ON public.budget_line_item (cost_element_id);

-- ---- visit_schedule (trial-scoped) ----
CREATE TABLE IF NOT EXISTS public.visit_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID REFERENCES public.budget_template(id) ON DELETE CASCADE,
    trial_id UUID REFERENCES public.studies(id) ON DELETE CASCADE,
    visit_code VARCHAR(100),
    visit_name VARCHAR(255) NOT NULL,
    visit_type VARCHAR(50),
    target_day INTEGER,
    visit_order INTEGER NOT NULL DEFAULT 0,
    window_before INT,
    window_after  INT,
    country_code  CHAR(3),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_visit_schedule_budget_template_id ON public.visit_schedule (budget_template_id);

-- ---- budget_visit_matrix ----
CREATE TABLE IF NOT EXISTS public.budget_visit_matrix (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_line_item_id UUID NOT NULL REFERENCES public.budget_line_item(id) ON DELETE CASCADE,
    visit_schedule_id UUID NOT NULL REFERENCES public.visit_schedule(id) ON DELETE CASCADE,
    units NUMERIC(18,4) NOT NULL DEFAULT 1,
    is_excluded BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_budget_visit_matrix_line_visit UNIQUE (budget_line_item_id, visit_schedule_id)
);

-- ---- budget_milestone ----
CREATE TABLE IF NOT EXISTS public.budget_milestone (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES public.budget_template(id) ON DELETE CASCADE,
    element_id UUID REFERENCES public.cost_element(id) ON DELETE SET NULL,
    name VARCHAR(500) NOT NULL,
    unit_cost NUMERIC(18,4) NOT NULL,
    quantity NUMERIC(10,2) NOT NULL DEFAULT 1,
    payment_trigger VARCHAR(200),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_budget_milestone_budget_template_id ON public.budget_milestone (budget_template_id);

-- ---- budget_note ----
CREATE TABLE IF NOT EXISTS public.budget_note (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    budget_template_id UUID NOT NULL REFERENCES public.budget_template(id) ON DELETE CASCADE,
    user_id VARCHAR(255) REFERENCES public.users(user_id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    category VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ---- site_budgeting_audit_log ----
CREATE TABLE IF NOT EXISTS public.site_budgeting_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(100) NOT NULL,
    entity_id UUID NOT NULL,
    action VARCHAR(20) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    user_id VARCHAR(255) REFERENCES public.users(user_id) ON DELETE SET NULL,
    user_role VARCHAR(50),
    cascade_level VARCHAR(32),
    field_name VARCHAR(100),
    justification TEXT,
    session_id UUID,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_site_budgeting_audit_entity     ON public.site_budgeting_audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_site_budgeting_audit_user_id    ON public.site_budgeting_audit_log (user_id);
CREATE INDEX IF NOT EXISTS ix_site_budgeting_audit_session_id ON public.site_budgeting_audit_log (session_id);

-- ---- study_country ----
CREATE TABLE IF NOT EXISTS public.study_country (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id        UUID NOT NULL,
    country_code    CHAR(3) NOT NULL,
    country_name    VARCHAR(255),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_study_country UNIQUE (trial_id, country_code)
);
CREATE INDEX IF NOT EXISTS ix_study_country_trial_id ON public.study_country(trial_id);

-- =====================================================================
-- 5b. CROSS-CUTTING PERFORMANCE INDEXES
-- =====================================================================
-- Added 2026-05-14 per the May 2026 performance audit. The schema migration
-- `migrations/schema/add_perf_indexes_audit_monitoring_agreements.sql` uses
-- CREATE INDEX CONCURRENTLY for production. The bootstrap below uses plain
-- CREATE INDEX because it runs against an empty database where blocking
-- writes does not matter.
-- ---------------------------------------------------------------------

-- audit_logs: PK-only today. Three high-traffic access patterns covered.
CREATE INDEX IF NOT EXISTS idx_audit_logs_target
    ON public.audit_logs (target_type, target_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time
    ON public.audit_logs ("user", "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action_time
    ON public.audit_logs (action, "timestamp" DESC);

-- site_status_history: append-only ledger; dashboard time-range queries.
CREATE INDEX IF NOT EXISTS idx_site_status_history_site_time
    ON public.site_status_history (site_id, changed_at DESC);

-- agreement_changes: review UI filters on (agreement, is_accepted, is_external_change).
CREATE INDEX IF NOT EXISTS idx_agreement_changes_filter
    ON public.agreement_changes (agreement_id, is_accepted, is_external_change);
CREATE INDEX IF NOT EXISTS idx_agreement_changes_agreement_time
    ON public.agreement_changes (agreement_id, created_at DESC);

-- monitoring_findings indexes are kept in
-- `migrations/schema/monitoring_tab_full_schema.sql` /
-- `migrations/schema/create_monitoring_tables.sql` since the table itself is
-- defined there (NOT in this bootstrap).
-- See: idx_monitoring_findings_lower_status, idx_monitoring_findings_visit.

-- =====================================================================
-- 6. SEED MASTER DATA — site budgeting
-- =====================================================================

-- conversion_factor_type seeds
INSERT INTO public.conversion_factor_type (id, code, name, mode, description) VALUES
  ('8009182e-9955-5ca7-b6ea-3acacc947a6c', 'MULT', 'Multiplicative default', 'MULTIPLICATIVE', 'Default multiplicative factor slot'),
  ('78ac517b-754f-575e-b1f8-cdc67cb2960f', 'ADD', 'Additive default', 'ADDITIVE', 'Default additive factor slot'),
  ('54ccd4af-149e-5c02-ab87-0a9e8da5caee', 'PASS', 'Pass-through default', 'PASS_THROUGH', 'Pass-through / no transform'),
  ('12b68283-a69d-5c78-9394-9cee5f611979', 'COUNTRY', 'Country Adjustment', 'MULTIPLICATIVE', 'Geographic cost multiplier by country'),
  ('1ab797fb-6d14-5b2b-a78e-722d905a4126', 'SITE', 'Site Adjustment', 'MULTIPLICATIVE', 'Site-specific cost multiplier'),
  ('9b368859-4fbb-5330-9836-488be3877336', 'TRIAL_COMPLEXITY', 'Trial Complexity', 'MULTIPLICATIVE', 'Protocol complexity multiplier'),
  ('1196f7bc-477b-53ad-a9d6-3a54e3c9d88c', 'COMPETITIVENESS', 'Market Competitiveness', 'MULTIPLICATIVE', 'Competitive site landscape multiplier')
ON CONFLICT (code) DO NOTHING;

-- cost_element seeds
INSERT INTO public.cost_element (id, code, name, description, unit_of_measure, element_type, cost_type, is_active) VALUES
  ('cb0a8903-2cdb-559a-aaf0-4b7879166988', 'LAB-HEM-001', 'Complete Blood Count (CBC)', 'element_type=ATOMIC; cost_type=PER_PATIENT', 'test', 'ATOMIC', 'PER_PATIENT', true),
  ('dfdecac1-3eaa-51f9-86d4-8076862912cb', 'LAB-CHM-001', 'Comprehensive Metabolic Panel', 'element_type=ATOMIC; cost_type=PER_PATIENT', 'panel', 'ATOMIC', 'PER_PATIENT', true),
  ('59d92ddd-a82d-556a-aa99-1e2e6ac2c834', 'IMG-001',     'CT Scan',                      'element_type=ATOMIC; cost_type=PER_VISIT',   'scan',  'ATOMIC', 'PER_VISIT',   true),
  ('70f33d7a-3bc8-5a20-aca1-5eeaa277dc12', 'PROC-001',    'Physical Examination',         'element_type=ATOMIC; cost_type=PER_VISIT',   'visit', 'ATOMIC', 'PER_VISIT',   true),
  ('e2965a75-583b-5b67-89ab-56c038820b04', 'REG-001',     'IRB Submission',               'element_type=ATOMIC; cost_type=FIXED',       'submission','ATOMIC','FIXED',     true),
  ('7e3d8389-415b-5a67-be00-6fa495c699fb', 'OVR-001',     'Site Initiation Visit',        'element_type=ATOMIC; cost_type=PER_VISIT',   'visit', 'ATOMIC', 'PER_VISIT',   true)
ON CONFLICT (code) DO NOTHING;

-- element_cost_version seeds
INSERT INTO public.element_cost_version (id, element_id, version_label, base_unit_cost, reference_currency, effective_from, effective_to) VALUES
  ('c8c43fd1-1a10-5f82-b8f8-946d0500794d', 'cb0a8903-2cdb-559a-aaf0-4b7879166988', 'FMV 2026 Q1',  35.00,  'USD', CURRENT_DATE, NULL),
  ('2ca3c9da-f41f-5b7c-8932-7ce922acdc65', 'dfdecac1-3eaa-51f9-86d4-8076862912cb', 'FMV 2026 Q1',  55.00,  'USD', CURRENT_DATE, NULL),
  ('baf1c736-be73-5c11-b585-256b3b470ed2', '59d92ddd-a82d-556a-aa99-1e2e6ac2c834', 'FMV 2026 Q1', 450.00,  'USD', CURRENT_DATE, NULL),
  ('fbc05e50-ba0e-5d05-af24-8b2cce7023e7', '70f33d7a-3bc8-5a20-aca1-5eeaa277dc12', 'FMV 2026 Q1', 125.00,  'USD', CURRENT_DATE, NULL),
  ('123978f9-94ca-523a-9a06-85aa61ebbafa', 'e2965a75-583b-5b67-89ab-56c038820b04', 'FMV 2026 Q1',2500.00,  'USD', CURRENT_DATE, NULL),
  ('41f8c3e3-3752-567f-b710-d64ed9ebd5f7', '7e3d8389-415b-5a67-be00-6fa495c699fb', 'FMV 2026 Q1',2200.00,  'USD', CURRENT_DATE, NULL)
ON CONFLICT ON CONSTRAINT uq_element_cost_version_label DO NOTHING;

-- =====================================================================
-- 7. SANITY CHECK
-- =====================================================================

DO $$
DECLARE
    n_tables INT;
    n_types  INT;
    n_ce     INT;
    n_cft    INT;
BEGIN
    SELECT COUNT(*) INTO n_tables FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
    SELECT COUNT(*) INTO n_types  FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'public' AND t.typtype = 'e';
    SELECT COUNT(*) INTO n_ce     FROM public.cost_element;
    SELECT COUNT(*) INTO n_cft    FROM public.conversion_factor_type;
    RAISE NOTICE '---------------- setup_local_db_full.sql DONE ----------------';
    RAISE NOTICE 'tables in public:               %', n_tables;
    RAISE NOTICE 'enum types in public:           %', n_types;
    RAISE NOTICE 'rows in cost_element:           %', n_ce;
    RAISE NOTICE 'rows in conversion_factor_type: %', n_cft;
    RAISE NOTICE '---------------------------------------------------------------';
END $$;
