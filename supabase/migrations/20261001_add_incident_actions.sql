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

create index if not exists incident_actions_status_due_idx
  on public.incident_actions (status, due_at nulls last);
create index if not exists incident_actions_alert_idx
  on public.incident_actions (alert_id);

alter table public.incident_actions enable row level security;
revoke all on table public.incident_actions from anon, authenticated;
grant select, insert, update, delete on table public.incident_actions to service_role;
grant usage, select on sequence public.incident_actions_id_seq to service_role;
