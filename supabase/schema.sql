-- Healthcare Crisis Prediction and Response Agent
-- Synthetic, aggregate surveillance schema. No patient-level health information is stored.

create table if not exists public.hospitals (
  id bigint generated always as identity primary key,
  code text not null unique check (code ~ '^[a-z0-9_]+$'),
  name text not null unique,
  bed_capacity integer not null check (bed_capacity > 0),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.conditions (
  id bigint generated always as identity primary key,
  code text not null unique check (code in ('ili', 'age', 'dengue')),
  name text not null unique,
  syndrome_group text not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.hospital_context (
  id bigint generated always as identity primary key,
  observation_date date not null,
  hospital_id bigint not null references public.hospitals(id) on delete restrict,
  staffed_beds integer not null check (staffed_beds > 0),
  occupied_beds integer not null check (occupied_beds >= 0 and occupied_beds <= staffed_beds),
  staffing_coverage_pct numeric(5,2) not null check (staffing_coverage_pct between 0 and 100),
  supply_readiness_pct numeric(5,2) not null check (supply_readiness_pct between 0 and 100),
  context_note text,
  created_at timestamptz not null default now(),
  unique (observation_date, hospital_id)
);

create table if not exists public.surveillance_observations (
  id bigint generated always as identity primary key,
  observation_date date not null,
  hospital_id bigint not null references public.hospitals(id) on delete restrict,
  condition_id bigint not null references public.conditions(id) on delete restrict,
  signal_source text not null check (signal_source in ('visits', 'lab_positives', 'pharmacy_demand')),
  observation_count integer not null check (observation_count >= 0),
  coverage_pct numeric(5,2) not null check (coverage_pct between 0 and 100),
  data_quality text not null check (data_quality in ('validated', 'partial', 'delayed')),
  source_note text,
  synthetic_run_id text not null,
  created_at timestamptz not null default now(),
  unique (observation_date, hospital_id, condition_id, signal_source, synthetic_run_id)
);

create table if not exists public.alerts (
  id bigint generated always as identity primary key,
  analysis_date date,
  hospital_id bigint not null references public.hospitals(id) on delete restrict,
  condition_id bigint not null references public.conditions(id) on delete restrict,
  alert_level text not null check (alert_level in ('monitor', 'investigate', 'escalate')),
  evidence_summary jsonb not null default '{}'::jsonb,
  rule_version text not null,
  status text not null default 'pending_approval' check (status in ('pending_approval', 'approved', 'dismissed', 'closed')),
  approved_by uuid references auth.users(id) on delete set null,
  approved_at timestamptz,
  reviewed_by text,
  review_note text,
  created_at timestamptz not null default now(),
  check ((status in ('approved', 'dismissed', 'closed')) = (approved_at is not null) or status = 'pending_approval')
);

create table if not exists public.incident_actions (
  id bigint generated always as identity primary key,
  alert_id bigint not null references public.alerts(id) on delete cascade,
  action_key text not null,
  category text not null,
  action_text text not null,
  owner_role text not null,
  assignee_name text,
  timeframe text not null,
  due_at timestamptz,
  status text not null default 'pending' check (status in ('pending', 'in_progress', 'completed', 'cancelled')),
  completion_note text,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (alert_id, action_key),
  constraint incident_actions_completion_check
    check ((status = 'completed' and completed_at is not null) or (status <> 'completed' and completed_at is null))
);

create index if not exists surveillance_observations_lookup_idx
  on public.surveillance_observations (condition_id, hospital_id, observation_date desc, signal_source);
create index if not exists hospital_context_lookup_idx
  on public.hospital_context (hospital_id, observation_date desc);
create index if not exists alerts_review_idx
  on public.alerts (status, created_at desc);
create index if not exists surveillance_observations_hospital_idx
  on public.surveillance_observations (hospital_id);
create index if not exists alerts_hospital_idx
  on public.alerts (hospital_id);
create index if not exists alerts_condition_idx
  on public.alerts (condition_id);
create index if not exists alerts_approved_by_idx
  on public.alerts (approved_by);
create unique index if not exists alerts_analysis_scope_rule_idx
  on public.alerts (analysis_date, hospital_id, condition_id, rule_version)
  where analysis_date is not null;
create index if not exists incident_actions_status_due_idx
  on public.incident_actions (status, due_at nulls last);
create index if not exists incident_actions_alert_idx
  on public.incident_actions (alert_id);

-- Tables remain unavailable through the public Data API until explicit role policies are added.
-- The FastAPI backend is the first access path and keeps its service-role credential server-only.
alter table public.hospitals enable row level security;
alter table public.conditions enable row level security;
alter table public.hospital_context enable row level security;
alter table public.surveillance_observations enable row level security;
alter table public.alerts enable row level security;
alter table public.incident_actions enable row level security;

revoke all on table public.incident_actions from anon, authenticated;
grant select, insert, update, delete on table public.incident_actions to service_role;
grant usage, select on sequence public.incident_actions_id_seq to service_role;

-- Predictive agent decision trail and internal evidence requests.
create table if not exists public.predictive_assessments (
  id bigint generated always as identity primary key,
  analysis_date date not null,
  hospital_code text not null references public.hospitals(code),
  condition_code text not null references public.conditions(code),
  risk_level text not null check (risk_level in ('routine', 'watch', 'prepare', 'uncertain')),
  next_review_at timestamptz not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists predictive_assessments_scope_idx
  on public.predictive_assessments (hospital_code, condition_code, analysis_date, created_at desc, id desc);
alter table public.predictive_assessments enable row level security;

create table if not exists public.agent_followup_requests (
  id bigint generated always as identity primary key,
  assessment_id bigint not null references public.predictive_assessments(id) on delete restrict,
  analysis_date date not null,
  hospital_code text not null references public.hospitals(code),
  condition_code text not null references public.conditions(code),
  request_key text not null check (request_key in ('verify_reporting', 'verify_lab_backlog', 'verify_readiness')),
  owner_role text not null,
  request_text text not null,
  due_at timestamptz not null,
  status text not null default 'open' check (status in ('open', 'completed')),
  completion_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (analysis_date, hospital_code, condition_code, request_key)
);
create index if not exists agent_followup_requests_open_idx
  on public.agent_followup_requests (due_at) where status = 'open';
alter table public.agent_followup_requests enable row level security;

-- Uploaded originals are private; only the backend service key accesses this library.
create table if not exists public.playbook_documents (
  id text primary key check (id ~ '^[a-f0-9]{64}$'),
  filename text not null,
  format text not null check (format in ('pdf','docx','json','yaml','yml')),
  size_bytes integer not null check (size_bytes between 1 and 5242880),
  storage_path text not null,
  extracted_text text not null,
  actions jsonb not null default '[]'::jsonb check (jsonb_typeof(actions) = 'array'),
  extraction_method text,
  index_namespace text not null unique,
  vector_count integer not null default 0 check (vector_count >= 0),
  status text not null check (status in ('processing','indexed','failed')),
  active boolean not null default false,
  error_message text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (not active or (status='indexed' and reviewed_by is not null and reviewed_at is not null))
);
create index if not exists playbook_documents_active_idx on public.playbook_documents(created_at desc) where active and status='indexed';
alter table public.playbook_documents enable row level security;
revoke all on table public.playbook_documents from anon, authenticated;
grant select, insert, update, delete on table public.playbook_documents to service_role;
insert into storage.buckets (id,name,public,file_size_limit)
values ('playbook-sources','playbook-sources',false,5242880)
on conflict (id) do nothing;
notify pgrst, 'reload schema';

-- Preserve the source of each response task after a playbook is deactivated.
alter table public.incident_actions add column if not exists source_document_id text references public.playbook_documents(id);
alter table public.incident_actions add column if not exists source_action_id text;
create index if not exists incident_actions_source_document_idx on public.incident_actions(source_document_id) where source_document_id is not null;
