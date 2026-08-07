--
-- PostgreSQL database dump
--

\restrict XtVTnAEcN6OfGj6qEz5mA0SsPKw2G3P7ot2uPA7YlPGPl1NolGzzCkXrytORIoM

-- Dumped from database version 14.23 (Ubuntu 14.23-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.23 (Ubuntu 14.23-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

BEGIN;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: audit_alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_events (
    event_id uuid NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    source_service character varying(200) NOT NULL,
    source_component character varying(100) NOT NULL,
    environment character varying(50) NOT NULL,
    username character varying(200),
    auth_provider character varying(100),
    source_ip character varying(64),
    host_ip character varying(64),
    host_name character varying(255) NOT NULL,
    operation_started_at timestamp with time zone NOT NULL,
    operation_finished_at timestamp with time zone NOT NULL,
    duration_ms bigint NOT NULL,
    action character varying(200) NOT NULL,
    object_type character varying(100) NOT NULL,
    object_id character varying(200),
    result character varying(20) NOT NULL,
    description text NOT NULL,
    request_id uuid NOT NULL,
    session_id character varying(64),
    http_method character varying(10) NOT NULL,
    http_route character varying(500) NOT NULL,
    http_path character varying(1000) NOT NULL,
    http_status integer NOT NULL,
    error_code character varying(100),
    details json NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: backlog_board_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backlog_board_state (
    id integer NOT NULL,
    initialized boolean NOT NULL,
    version integer NOT NULL
);


--
-- Name: backlog_executors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backlog_executors (
    id uuid NOT NULL,
    backlog_item_id uuid NOT NULL,
    team_id uuid NOT NULL,
    effort_by_competency jsonb NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: backlog_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.backlog_items (
    id uuid NOT NULL,
    tribe_id uuid,
    issue_key character varying(80) NOT NULL,
    title character varying(260) NOT NULL,
    description text NOT NULL,
    product character varying(180) NOT NULL,
    owner_team_id uuid,
    initiative_type character varying(120) NOT NULL,
    target_year integer,
    target_quarter character varying(2),
    customer_priority character varying(40) NOT NULL,
    team_priority character varying(40) NOT NULL,
    status character varying(80) NOT NULL,
    tags jsonb NOT NULL,
    systems jsonb NOT NULL,
    sent_to jsonb NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: board_connections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.board_connections (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    client_uid character varying(80) NOT NULL,
    source_kind character varying(40) NOT NULL,
    source_id uuid NOT NULL,
    target_kind character varying(40) NOT NULL,
    target_id uuid NOT NULL,
    relation_type character varying(40) NOT NULL,
    bend_dx double precision,
    bend_dy double precision,
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: initiative_attractions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.initiative_attractions (
    id uuid NOT NULL,
    executor_id uuid NOT NULL,
    issue_key character varying(80) NOT NULL,
    target_initiative_id uuid,
    target_team_id uuid NOT NULL,
    sprint_index integer,
    approval_status character varying(32) NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: initiative_executors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.initiative_executors (
    id uuid NOT NULL,
    initiative_id uuid NOT NULL,
    team_id uuid NOT NULL,
    effort_by_competency jsonb NOT NULL,
    attractions jsonb NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: initiatives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.initiatives (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    backlog_item_id uuid,
    issue_key character varying(80) NOT NULL,
    title character varying(260) NOT NULL,
    description text NOT NULL,
    product character varying(180) NOT NULL,
    owner_team_id uuid,
    initiative_type character varying(120) NOT NULL,
    status character varying(40) NOT NULL,
    goal_text character varying(260) NOT NULL,
    metric character varying(260) NOT NULL,
    current_value character varying(260) NOT NULL,
    target_value character varying(260) NOT NULL,
    hypothesis text NOT NULL,
    redesign text NOT NULL,
    customer_priority character varying(40) NOT NULL,
    team_priority character varying(40) NOT NULL,
    estimate character varying(120) NOT NULL,
    comment text NOT NULL,
    pre_planned boolean NOT NULL,
    on_board boolean NOT NULL,
    agreed boolean NOT NULL,
    approved_by character varying(200),
    approved_at timestamp with time zone,
    tags jsonb NOT NULL,
    sprint_index integer,
    week_index integer,
    sort_order integer NOT NULL,
    board_sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_initiatives_week_index CHECK (((week_index IS NULL) OR (week_index = ANY (ARRAY[0, 1]))))
);


--
-- Name: pi_cycle_capacity_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_cycle_capacity_members (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    team_id uuid NOT NULL,
    client_uid character varying(80) NOT NULL,
    full_name character varying(220) NOT NULL,
    competency character varying(32) NOT NULL,
    rate double precision NOT NULL,
    vacation_ranges jsonb NOT NULL,
    extra_unavailable_ranges jsonb NOT NULL,
    ceremony_percent double precision NOT NULL,
    risk_percent double precision NOT NULL,
    efficiency double precision,
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_capacity_member_efficiency CHECK (((efficiency IS NULL) OR ((efficiency >= (0)::double precision) AND (efficiency <= (1)::double precision)))),
    CONSTRAINT ck_capacity_member_percentages CHECK (((ceremony_percent >= (0)::double precision) AND (ceremony_percent <= (100)::double precision) AND (risk_percent >= (0)::double precision) AND (risk_percent <= (100)::double precision))),
    CONSTRAINT ck_capacity_member_rate CHECK (((rate >= (0)::double precision) AND (rate <= (1)::double precision)))
);


--
-- Name: pi_cycle_goal_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_cycle_goal_options (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    name character varying(260) NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: pi_cycle_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_cycle_tags (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    name character varying(120) NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: pi_cycle_team_competencies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_cycle_team_competencies (
    id uuid NOT NULL,
    cycle_team_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: pi_cycle_teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_cycle_teams (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    team_id uuid NOT NULL,
    team_type character varying(40) NOT NULL,
    excluded_from_goals boolean NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: pi_cycles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_cycles (
    id uuid NOT NULL,
    year integer NOT NULL,
    quarter character varying(2) NOT NULL,
    start_date date,
    sprint_count integer NOT NULL,
    status character varying(40) NOT NULL,
    version integer NOT NULL,
    setup_initialized boolean NOT NULL,
    initiatives_initialized boolean NOT NULL,
    goals_initialized boolean NOT NULL,
    boards_initialized boolean NOT NULL,
    capacity_initialized boolean NOT NULL,
    program_board_initialized boolean NOT NULL,
    risks_initialized boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: pi_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_events (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    name character varying(180) NOT NULL,
    event_date date NOT NULL,
    event_end_date date,
    event_type character varying(20) NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: pi_goal_initiatives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_goal_initiatives (
    id uuid NOT NULL,
    goal_id uuid NOT NULL,
    initiative_id uuid NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: pi_goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pi_goals (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    tribe_id uuid,
    team_id uuid,
    initiative_id uuid,
    title character varying(260) NOT NULL,
    metric character varying(260) NOT NULL,
    current_value character varying(260) NOT NULL,
    target_value character varying(260) NOT NULL,
    hypothesis text NOT NULL,
    redesign text NOT NULL,
    product character varying(180) NOT NULL,
    owner character varying(220) NOT NULL,
    business_value integer,
    status character varying(40) NOT NULL,
    category character varying(40) NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: risks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risks (
    id uuid NOT NULL,
    cycle_id uuid NOT NULL,
    client_uid character varying(80) NOT NULL,
    scope character varying(40) NOT NULL,
    tribe_id uuid,
    team_id uuid,
    initiative_id uuid,
    is_shared boolean NOT NULL,
    description text NOT NULL,
    owner character varying(220) NOT NULL,
    impact text NOT NULL,
    control_point character varying(220) NOT NULL,
    mitigation_plan text NOT NULL,
    probability integer NOT NULL,
    impact_level integer NOT NULL,
    criticality integer NOT NULL,
    reaction_due_date date,
    treatment_plan text NOT NULL,
    status character varying(40) NOT NULL,
    roam character varying(20),
    sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: stories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stories (
    id uuid NOT NULL,
    initiative_id uuid NOT NULL,
    client_uid character varying(80) NOT NULL,
    external_key character varying(80) NOT NULL,
    title character varying(260) NOT NULL,
    effort_by_competency jsonb NOT NULL,
    sprint_index integer,
    week_index integer,
    sort_order integer NOT NULL,
    board_sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_stories_week_index CHECK (((week_index IS NULL) OR (week_index = ANY (ARRAY[0, 1]))))
);


--
-- Name: team_competencies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_competencies (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    code character varying(32) NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_members (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    full_name character varying(220) NOT NULL,
    competency character varying(32) NOT NULL,
    rate double precision NOT NULL,
    unavailable_ranges jsonb NOT NULL,
    ceremony_percent double precision NOT NULL,
    risk_percent double precision NOT NULL,
    efficiency_percent double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    id uuid NOT NULL,
    tribe_id uuid NOT NULL,
    name character varying(180) NOT NULL,
    team_type character varying(40) NOT NULL,
    excluded_from_goals boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: tribes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tribes (
    id uuid NOT NULL,
    name character varying(180) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: work_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.work_items (
    id uuid NOT NULL,
    initiative_id uuid NOT NULL,
    story_id uuid,
    assignee_member_id uuid,
    client_uid character varying(80) NOT NULL,
    assignee_name character varying(220) NOT NULL,
    competency character varying(32) NOT NULL,
    effort double precision NOT NULL,
    sprint_index integer,
    week_index integer,
    sort_order integer NOT NULL,
    board_sort_order integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_work_items_week_index CHECK (((week_index IS NULL) OR (week_index = ANY (ARRAY[0, 1]))))
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_alembic_version audit_alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_alembic_version
    ADD CONSTRAINT audit_alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (event_id);


--
-- Name: backlog_board_state backlog_board_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_board_state
    ADD CONSTRAINT backlog_board_state_pkey PRIMARY KEY (id);


--
-- Name: backlog_executors backlog_executors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_executors
    ADD CONSTRAINT backlog_executors_pkey PRIMARY KEY (id);


--
-- Name: backlog_items backlog_items_issue_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_items
    ADD CONSTRAINT backlog_items_issue_key_key UNIQUE (issue_key);


--
-- Name: backlog_items backlog_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_items
    ADD CONSTRAINT backlog_items_pkey PRIMARY KEY (id);


--
-- Name: board_connections board_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_connections
    ADD CONSTRAINT board_connections_pkey PRIMARY KEY (id);


--
-- Name: initiative_attractions initiative_attractions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_attractions
    ADD CONSTRAINT initiative_attractions_pkey PRIMARY KEY (id);


--
-- Name: initiative_executors initiative_executors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_executors
    ADD CONSTRAINT initiative_executors_pkey PRIMARY KEY (id);


--
-- Name: initiatives initiatives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiatives
    ADD CONSTRAINT initiatives_pkey PRIMARY KEY (id);


--
-- Name: pi_cycle_capacity_members pi_cycle_capacity_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_capacity_members
    ADD CONSTRAINT pi_cycle_capacity_members_pkey PRIMARY KEY (id);


--
-- Name: pi_cycle_goal_options pi_cycle_goal_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_goal_options
    ADD CONSTRAINT pi_cycle_goal_options_pkey PRIMARY KEY (id);


--
-- Name: pi_cycle_tags pi_cycle_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_tags
    ADD CONSTRAINT pi_cycle_tags_pkey PRIMARY KEY (id);


--
-- Name: pi_cycle_team_competencies pi_cycle_team_competencies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_team_competencies
    ADD CONSTRAINT pi_cycle_team_competencies_pkey PRIMARY KEY (id);


--
-- Name: pi_cycle_teams pi_cycle_teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_teams
    ADD CONSTRAINT pi_cycle_teams_pkey PRIMARY KEY (id);


--
-- Name: pi_cycles pi_cycles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycles
    ADD CONSTRAINT pi_cycles_pkey PRIMARY KEY (id);


--
-- Name: pi_events pi_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_events
    ADD CONSTRAINT pi_events_pkey PRIMARY KEY (id);


--
-- Name: pi_goal_initiatives pi_goal_initiatives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goal_initiatives
    ADD CONSTRAINT pi_goal_initiatives_pkey PRIMARY KEY (id);


--
-- Name: pi_goals pi_goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goals
    ADD CONSTRAINT pi_goals_pkey PRIMARY KEY (id);


--
-- Name: risks risks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_pkey PRIMARY KEY (id);


--
-- Name: stories stories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_pkey PRIMARY KEY (id);


--
-- Name: team_competencies team_competencies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_competencies
    ADD CONSTRAINT team_competencies_pkey PRIMARY KEY (id);


--
-- Name: team_members team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_pkey PRIMARY KEY (id);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);


--
-- Name: tribes tribes_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tribes
    ADD CONSTRAINT tribes_name_key UNIQUE (name);


--
-- Name: tribes tribes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tribes
    ADD CONSTRAINT tribes_pkey PRIMARY KEY (id);


--
-- Name: backlog_executors uq_backlog_executor_team; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_executors
    ADD CONSTRAINT uq_backlog_executor_team UNIQUE (backlog_item_id, team_id);


--
-- Name: board_connections uq_board_connection_client_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_connections
    ADD CONSTRAINT uq_board_connection_client_uid UNIQUE (cycle_id, client_uid);


--
-- Name: board_connections uq_board_connection_directed_edge; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_connections
    ADD CONSTRAINT uq_board_connection_directed_edge UNIQUE (cycle_id, source_kind, source_id, target_kind, target_id);


--
-- Name: pi_cycle_capacity_members uq_cycle_capacity_member_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_capacity_members
    ADD CONSTRAINT uq_cycle_capacity_member_uid UNIQUE (cycle_id, client_uid);


--
-- Name: initiatives uq_cycle_initiative_issue; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiatives
    ADD CONSTRAINT uq_cycle_initiative_issue UNIQUE (cycle_id, issue_key);


--
-- Name: risks uq_cycle_risk_client_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT uq_cycle_risk_client_uid UNIQUE (cycle_id, client_uid);


--
-- Name: initiative_attractions uq_initiative_attraction_target; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_attractions
    ADD CONSTRAINT uq_initiative_attraction_target UNIQUE (executor_id, issue_key, target_team_id, sprint_index);


--
-- Name: initiative_executors uq_initiative_executor_team; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_executors
    ADD CONSTRAINT uq_initiative_executor_team UNIQUE (initiative_id, team_id);


--
-- Name: pi_cycle_goal_options uq_pi_cycle_goal_option; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_goal_options
    ADD CONSTRAINT uq_pi_cycle_goal_option UNIQUE (cycle_id, name);


--
-- Name: pi_cycle_tags uq_pi_cycle_tag; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_tags
    ADD CONSTRAINT uq_pi_cycle_tag UNIQUE (cycle_id, name);


--
-- Name: pi_cycle_teams uq_pi_cycle_team; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_teams
    ADD CONSTRAINT uq_pi_cycle_team UNIQUE (cycle_id, team_id);


--
-- Name: pi_cycle_team_competencies uq_pi_cycle_team_competency; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_team_competencies
    ADD CONSTRAINT uq_pi_cycle_team_competency UNIQUE (cycle_team_id, code);


--
-- Name: pi_cycles uq_pi_cycle_year_quarter; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycles
    ADD CONSTRAINT uq_pi_cycle_year_quarter UNIQUE (year, quarter);


--
-- Name: pi_goal_initiatives uq_pi_goal_initiative; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goal_initiatives
    ADD CONSTRAINT uq_pi_goal_initiative UNIQUE (goal_id, initiative_id);


--
-- Name: stories uq_story_client_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT uq_story_client_uid UNIQUE (initiative_id, client_uid);


--
-- Name: team_competencies uq_team_competency; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_competencies
    ADD CONSTRAINT uq_team_competency UNIQUE (team_id, code);


--
-- Name: teams uq_team_tribe_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT uq_team_tribe_name UNIQUE (tribe_id, name);


--
-- Name: work_items uq_work_item_client_uid; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_items
    ADD CONSTRAINT uq_work_item_client_uid UNIQUE (initiative_id, client_uid);


--
-- Name: work_items work_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_items
    ADD CONSTRAINT work_items_pkey PRIMARY KEY (id);


--
-- Name: ix_audit_events_action_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_action_occurred_at ON public.audit_events USING btree (action, occurred_at);


--
-- Name: ix_audit_events_object; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_object ON public.audit_events USING btree (object_type, object_id);


--
-- Name: ix_audit_events_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_occurred_at ON public.audit_events USING btree (occurred_at);


--
-- Name: ix_audit_events_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_request_id ON public.audit_events USING btree (request_id);


--
-- Name: ix_audit_events_result_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_result_occurred_at ON public.audit_events USING btree (result, occurred_at);


--
-- Name: ix_audit_events_username_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_username_occurred_at ON public.audit_events USING btree (username, occurred_at);


--
-- Name: ix_backlog_executors_item_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_backlog_executors_item_sort ON public.backlog_executors USING btree (backlog_item_id, sort_order);


--
-- Name: ix_backlog_items_tribe_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_backlog_items_tribe_sort ON public.backlog_items USING btree (tribe_id, sort_order);


--
-- Name: ix_board_connections_cycle_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_board_connections_cycle_sort ON public.board_connections USING btree (cycle_id, sort_order);


--
-- Name: ix_cycle_capacity_members_team_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cycle_capacity_members_team_sort ON public.pi_cycle_capacity_members USING btree (cycle_id, team_id, sort_order);


--
-- Name: ix_initiative_attractions_executor_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_initiative_attractions_executor_sort ON public.initiative_attractions USING btree (executor_id, sort_order);


--
-- Name: ix_initiatives_cycle_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_initiatives_cycle_sort ON public.initiatives USING btree (cycle_id, sort_order);


--
-- Name: ix_initiatives_program_board_lane; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_initiatives_program_board_lane ON public.initiatives USING btree (cycle_id, on_board, sprint_index, board_sort_order);


--
-- Name: ix_pi_goal_initiatives_goal_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pi_goal_initiatives_goal_sort ON public.pi_goal_initiatives USING btree (goal_id, sort_order);


--
-- Name: ix_pi_goal_initiatives_initiative; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pi_goal_initiatives_initiative ON public.pi_goal_initiatives USING btree (initiative_id);


--
-- Name: ix_pi_goals_cycle_team_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pi_goals_cycle_team_sort ON public.pi_goals USING btree (cycle_id, team_id, sort_order);


--
-- Name: ix_risks_cycle_link_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risks_cycle_link_sort ON public.risks USING btree (cycle_id, tribe_id, team_id, initiative_id, sort_order);


--
-- Name: ix_risks_cycle_scope_team_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risks_cycle_scope_team_sort ON public.risks USING btree (cycle_id, scope, team_id, sort_order);


--
-- Name: ix_stories_initiative_board_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_stories_initiative_board_sort ON public.stories USING btree (initiative_id, board_sort_order);


--
-- Name: ix_work_items_assignee_member; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_items_assignee_member ON public.work_items USING btree (assignee_member_id);


--
-- Name: ix_work_items_initiative_board_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_work_items_initiative_board_sort ON public.work_items USING btree (initiative_id, board_sort_order);


--
-- Name: backlog_executors backlog_executors_backlog_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_executors
    ADD CONSTRAINT backlog_executors_backlog_item_id_fkey FOREIGN KEY (backlog_item_id) REFERENCES public.backlog_items(id) ON DELETE CASCADE;


--
-- Name: backlog_executors backlog_executors_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_executors
    ADD CONSTRAINT backlog_executors_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: backlog_items backlog_items_owner_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_items
    ADD CONSTRAINT backlog_items_owner_team_id_fkey FOREIGN KEY (owner_team_id) REFERENCES public.teams(id);


--
-- Name: backlog_items backlog_items_tribe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_items
    ADD CONSTRAINT backlog_items_tribe_id_fkey FOREIGN KEY (tribe_id) REFERENCES public.tribes(id) ON DELETE SET NULL;


--
-- Name: board_connections board_connections_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.board_connections
    ADD CONSTRAINT board_connections_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: backlog_items fk_backlog_items_tribe_id_tribes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.backlog_items
    ADD CONSTRAINT fk_backlog_items_tribe_id_tribes FOREIGN KEY (tribe_id) REFERENCES public.tribes(id) ON DELETE SET NULL;


--
-- Name: work_items fk_work_items_assignee_member; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_items
    ADD CONSTRAINT fk_work_items_assignee_member FOREIGN KEY (assignee_member_id) REFERENCES public.pi_cycle_capacity_members(id) ON DELETE SET NULL;


--
-- Name: initiative_attractions initiative_attractions_executor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_attractions
    ADD CONSTRAINT initiative_attractions_executor_id_fkey FOREIGN KEY (executor_id) REFERENCES public.initiative_executors(id) ON DELETE CASCADE;


--
-- Name: initiative_attractions initiative_attractions_target_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_attractions
    ADD CONSTRAINT initiative_attractions_target_initiative_id_fkey FOREIGN KEY (target_initiative_id) REFERENCES public.initiatives(id) ON DELETE SET NULL;


--
-- Name: initiative_attractions initiative_attractions_target_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_attractions
    ADD CONSTRAINT initiative_attractions_target_team_id_fkey FOREIGN KEY (target_team_id) REFERENCES public.teams(id);


--
-- Name: initiative_executors initiative_executors_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_executors
    ADD CONSTRAINT initiative_executors_initiative_id_fkey FOREIGN KEY (initiative_id) REFERENCES public.initiatives(id) ON DELETE CASCADE;


--
-- Name: initiative_executors initiative_executors_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiative_executors
    ADD CONSTRAINT initiative_executors_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: initiatives initiatives_backlog_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiatives
    ADD CONSTRAINT initiatives_backlog_item_id_fkey FOREIGN KEY (backlog_item_id) REFERENCES public.backlog_items(id);


--
-- Name: initiatives initiatives_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiatives
    ADD CONSTRAINT initiatives_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: initiatives initiatives_owner_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.initiatives
    ADD CONSTRAINT initiatives_owner_team_id_fkey FOREIGN KEY (owner_team_id) REFERENCES public.teams(id);


--
-- Name: pi_cycle_capacity_members pi_cycle_capacity_members_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_capacity_members
    ADD CONSTRAINT pi_cycle_capacity_members_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: pi_cycle_capacity_members pi_cycle_capacity_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_capacity_members
    ADD CONSTRAINT pi_cycle_capacity_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: pi_cycle_goal_options pi_cycle_goal_options_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_goal_options
    ADD CONSTRAINT pi_cycle_goal_options_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: pi_cycle_tags pi_cycle_tags_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_tags
    ADD CONSTRAINT pi_cycle_tags_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: pi_cycle_team_competencies pi_cycle_team_competencies_cycle_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_team_competencies
    ADD CONSTRAINT pi_cycle_team_competencies_cycle_team_id_fkey FOREIGN KEY (cycle_team_id) REFERENCES public.pi_cycle_teams(id) ON DELETE CASCADE;


--
-- Name: pi_cycle_teams pi_cycle_teams_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_teams
    ADD CONSTRAINT pi_cycle_teams_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: pi_cycle_teams pi_cycle_teams_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_cycle_teams
    ADD CONSTRAINT pi_cycle_teams_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: pi_events pi_events_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_events
    ADD CONSTRAINT pi_events_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: pi_goal_initiatives pi_goal_initiatives_goal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goal_initiatives
    ADD CONSTRAINT pi_goal_initiatives_goal_id_fkey FOREIGN KEY (goal_id) REFERENCES public.pi_goals(id) ON DELETE CASCADE;


--
-- Name: pi_goal_initiatives pi_goal_initiatives_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goal_initiatives
    ADD CONSTRAINT pi_goal_initiatives_initiative_id_fkey FOREIGN KEY (initiative_id) REFERENCES public.initiatives(id) ON DELETE CASCADE;


--
-- Name: pi_goals pi_goals_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goals
    ADD CONSTRAINT pi_goals_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: pi_goals pi_goals_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goals
    ADD CONSTRAINT pi_goals_initiative_id_fkey FOREIGN KEY (initiative_id) REFERENCES public.initiatives(id);


--
-- Name: pi_goals pi_goals_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goals
    ADD CONSTRAINT pi_goals_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: pi_goals pi_goals_tribe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pi_goals
    ADD CONSTRAINT pi_goals_tribe_id_fkey FOREIGN KEY (tribe_id) REFERENCES public.tribes(id);


--
-- Name: risks risks_cycle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_cycle_id_fkey FOREIGN KEY (cycle_id) REFERENCES public.pi_cycles(id) ON DELETE CASCADE;


--
-- Name: risks risks_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_initiative_id_fkey FOREIGN KEY (initiative_id) REFERENCES public.initiatives(id);


--
-- Name: risks risks_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: risks risks_tribe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_tribe_id_fkey FOREIGN KEY (tribe_id) REFERENCES public.tribes(id);


--
-- Name: stories stories_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stories
    ADD CONSTRAINT stories_initiative_id_fkey FOREIGN KEY (initiative_id) REFERENCES public.initiatives(id) ON DELETE CASCADE;


--
-- Name: team_competencies team_competencies_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_competencies
    ADD CONSTRAINT team_competencies_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: team_members team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: teams teams_tribe_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_tribe_id_fkey FOREIGN KEY (tribe_id) REFERENCES public.tribes(id) ON DELETE CASCADE;


--
-- Name: work_items work_items_assignee_member_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_items
    ADD CONSTRAINT work_items_assignee_member_id_fkey FOREIGN KEY (assignee_member_id) REFERENCES public.pi_cycle_capacity_members(id) ON DELETE SET NULL;


--
-- Name: work_items work_items_initiative_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_items
    ADD CONSTRAINT work_items_initiative_id_fkey FOREIGN KEY (initiative_id) REFERENCES public.initiatives(id) ON DELETE CASCADE;


--
-- Name: work_items work_items_story_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_items
    ADD CONSTRAINT work_items_story_id_fkey FOREIGN KEY (story_id) REFERENCES public.stories(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

-- Alembic heads verified by the application release.
INSERT INTO public.alembic_version (version_num) VALUES ('20260807_0024');
INSERT INTO public.audit_alembic_version (version_num) VALUES ('20260804_0001');

COMMIT;

\unrestrict XtVTnAEcN6OfGj6qEz5mA0SsPKw2G3P7ot2uPA7YlPGPl1NolGzzCkXrytORIoM
