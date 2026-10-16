-- Assessment runs retain the chosen evidence checks and decision trail.
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

-- The agent may create internal verification requests, never clinical orders or external notices.
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
notify pgrst, 'reload schema';
