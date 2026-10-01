-- Healthcare Crisis Prediction and Response Agent
-- Synthetic, aggregate surveillance schema. No patient-level health information is stored.

create table if not exists public.regions (
  id bigint generated always as identity primary key,
  code text not null unique check (code ~ '^[a-z0-9_]+$'),
  name text not null unique,
  population integer not null check (population > 0),
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

create table if not exists public.regional_context (
  id bigint generated always as identity primary key,
  observation_date date not null,
  region_id bigint not null references public.regions(id) on delete restrict,
  rainfall_index numeric(7,2),
  mobility_index numeric(7,2),
  temperature_c numeric(5,2),
  context_note text,
  created_at timestamptz not null default now(),
  unique (observation_date, region_id)
);

create table if not exists public.surveillance_observations (
  id bigint generated always as identity primary key,
  observation_date date not null,
  region_id bigint not null references public.regions(id) on delete restrict,
  condition_id bigint not null references public.conditions(id) on delete restrict,
  signal_source text not null check (signal_source in ('visits', 'lab_positives', 'pharmacy_demand')),
  observation_count integer not null check (observation_count >= 0),
  coverage_pct numeric(5,2) not null check (coverage_pct between 0 and 100),
  data_quality text not null check (data_quality in ('validated', 'partial', 'delayed')),
  source_note text,
  synthetic_run_id text not null,
  created_at timestamptz not null default now(),
  unique (observation_date, region_id, condition_id, signal_source, synthetic_run_id)
);

create table if not exists public.alerts (
  id bigint generated always as identity primary key,
  region_id bigint not null references public.regions(id) on delete restrict,
  condition_id bigint not null references public.conditions(id) on delete restrict,
  alert_level text not null check (alert_level in ('monitor', 'investigate', 'escalate')),
  evidence_summary jsonb not null default '{}'::jsonb,
  rule_version text not null,
  status text not null default 'pending_approval' check (status in ('pending_approval', 'approved', 'dismissed', 'closed')),
  approved_by uuid references auth.users(id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  check ((status in ('approved', 'dismissed', 'closed')) = (approved_at is not null) or status = 'pending_approval')
);

create index if not exists surveillance_observations_lookup_idx
  on public.surveillance_observations (condition_id, region_id, observation_date desc, signal_source);
create index if not exists regional_context_lookup_idx
  on public.regional_context (region_id, observation_date desc);
create index if not exists alerts_review_idx
  on public.alerts (status, created_at desc);
create index if not exists surveillance_observations_region_idx
  on public.surveillance_observations (region_id);
create index if not exists alerts_region_idx
  on public.alerts (region_id);
create index if not exists alerts_condition_idx
  on public.alerts (condition_id);
create index if not exists alerts_approved_by_idx
  on public.alerts (approved_by);

-- Tables remain unavailable through the public Data API until explicit role policies are added.
-- The FastAPI backend is the first access path and keeps its service-role credential server-only.
alter table public.regions enable row level security;
alter table public.conditions enable row level security;
alter table public.regional_context enable row level security;
alter table public.surveillance_observations enable row level security;
alter table public.alerts enable row level security;
