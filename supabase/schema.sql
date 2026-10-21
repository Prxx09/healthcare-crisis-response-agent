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
  code text not null unique check (code ~ '^[a-z][a-z0-9_]*$' and length(code) <= 80),
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

-- Accept explicitly named diseases, keeping one authoritative uploaded ruleset per disease.
alter table public.conditions drop constraint if exists conditions_code_check;
alter table public.conditions add constraint conditions_code_check
  check (code ~ '^[a-z][a-z0-9_]*$' and length(code) <= 80);

create table if not exists public.playbook_condition_rules (
  condition_code text primary key references public.conditions(code),
  document_id text not null references public.playbook_documents(id),
  enabled boolean not null default true,
  reviewed_by text not null,
  updated_at timestamptz not null default now()
);
create index if not exists playbook_condition_rules_document_idx on public.playbook_condition_rules(document_id);
alter table public.playbook_condition_rules enable row level security;
revoke all on public.playbook_condition_rules from anon, authenticated;
grant select, insert, update on public.playbook_condition_rules to service_role;

create table if not exists public.playbook_rule_events (
  id bigint generated always as identity primary key,
  condition_code text not null references public.conditions(code),
  previous_document_id text references public.playbook_documents(id),
  document_id text not null references public.playbook_documents(id),
  enabled boolean not null,
  reviewed_by text not null,
  created_at timestamptz not null default now()
);
create index if not exists playbook_rule_events_condition_idx on public.playbook_rule_events(condition_code,created_at desc);
create index if not exists playbook_rule_events_previous_idx on public.playbook_rule_events(previous_document_id);
create index if not exists playbook_rule_events_document_idx on public.playbook_rule_events(document_id);
alter table public.playbook_rule_events enable row level security;
revoke all on public.playbook_rule_events from anon, authenticated;
grant select, insert on public.playbook_rule_events to service_role;
grant usage, select on sequence public.playbook_rule_events_id_seq to service_role;
grant select, insert, update on public.conditions to service_role;

-- Runs with caller privileges; callable only by the backend service role.
create or replace function public.activate_playbook_rules(p_document_id text,p_active boolean,p_reviewer text)
returns jsonb language plpgsql security invoker set search_path = public, pg_temp as $$
declare
  doc public.playbook_documents%rowtype;
  disease record;
  previous_id text;
begin
  if length(trim(p_reviewer)) < 2 or length(p_reviewer)>100 then
    raise exception 'A reviewer name of 2-100 characters is required';
  end if;
  -- Serialize registry switches so concurrent activations cannot leave mixed rules.
  perform pg_advisory_xact_lock(hashtext('healthcare_playbook_rule_activation'));
  select * into doc from public.playbook_documents where id=p_document_id for update;
  if not found then raise exception 'Playbook not found' using errcode='P0002'; end if;
  if p_active and (doc.status<>'indexed' or jsonb_array_length(doc.actions)=0 or doc.vector_count=0) then
    raise exception 'Only successfully indexed playbooks with actions can be activated';
  end if;
  if p_active then
    for disease in
      select distinct on (a->>'condition_code') a->>'condition_code' as code,
        coalesce(nullif(a->>'condition_name',''),initcap(replace(a->>'condition_code','_',' '))) as name
      from jsonb_array_elements(doc.actions) a order by a->>'condition_code'
    loop
      if disease.code is null or disease.code !~ '^[a-z][a-z0-9_]*$' or length(disease.code)>80 then
        raise exception 'Invalid disease code in playbook';
      end if;
      insert into public.conditions(code,name,syndrome_group,active)
        values(disease.code,disease.name,'playbook_defined',true)
        on conflict (code) do update set active=true;
      select document_id into previous_id from public.playbook_condition_rules where condition_code=disease.code;
      insert into public.playbook_condition_rules(condition_code,document_id,enabled,reviewed_by,updated_at)
        values(disease.code,p_document_id,true,trim(p_reviewer),now())
        on conflict (condition_code) do update set document_id=excluded.document_id,enabled=true,
          reviewed_by=excluded.reviewed_by,updated_at=excluded.updated_at;
      insert into public.playbook_rule_events(condition_code,previous_document_id,document_id,enabled,reviewed_by)
        values(disease.code,previous_id,p_document_id,true,trim(p_reviewer));
    end loop;
  else
    for disease in select condition_code,document_id from public.playbook_condition_rules
      where document_id=p_document_id and enabled for update
    loop
      update public.playbook_condition_rules set enabled=false,reviewed_by=trim(p_reviewer),updated_at=now()
        where condition_code=disease.condition_code;
      insert into public.playbook_rule_events(condition_code,previous_document_id,document_id,enabled,reviewed_by)
        values(disease.condition_code,p_document_id,p_document_id,false,trim(p_reviewer));
    end loop;
  end if;
  update public.playbook_documents set reviewed_by=trim(p_reviewer),reviewed_at=now(),updated_at=now()
    where id=p_document_id;
  update public.playbook_documents d set active=exists(
    select 1 from public.playbook_condition_rules r where r.document_id=d.id and r.enabled)
    where d.active is distinct from exists(
      select 1 from public.playbook_condition_rules r where r.document_id=d.id and r.enabled);
  select * into doc from public.playbook_documents where id=p_document_id;
  return to_jsonb(doc)-'extracted_text';
end;
$$;
revoke all on function public.activate_playbook_rules(text,boolean,text) from public,anon,authenticated;
grant execute on function public.activate_playbook_rules(text,boolean,text) to service_role;

-- Preserve an existing reviewed active upload when upgrading an older installation.
insert into public.playbook_condition_rules(condition_code,document_id,enabled,reviewed_by)
select distinct on (a->>'condition_code') a->>'condition_code',d.id,true,d.reviewed_by
from public.playbook_documents d cross join lateral jsonb_array_elements(d.actions) a
join public.conditions c on c.code=a->>'condition_code'
where d.active and d.status='indexed' and d.reviewed_by is not null
order by a->>'condition_code',d.reviewed_at desc nulls last,d.created_at desc,d.id
on conflict (condition_code) do nothing;
notify pgrst, 'reload schema';
