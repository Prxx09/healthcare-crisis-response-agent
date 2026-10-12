alter table public.email_alert_config
  add column if not exists owner_emails jsonb not null default '{
    "Epidemiology lead": "prajwal.khadse@maqsoftware.com",
    "Operations lead": "prajwal.khadse@maqsoftware.com",
    "Incident communications": "prajwal.khadse@maqsoftware.com",
    "Incident Commander": "prajwal.khadse@maqsoftware.com"
  }'::jsonb;

create table if not exists public.task_owner_notifications (
  id bigint generated always as identity primary key,
  alert_id bigint not null references public.alerts(id) on delete cascade,
  action_id bigint not null references public.incident_actions(id) on delete cascade,
  owner_role text not null,
  recipient text,
  status text not null check (status in ('success', 'failed', 'skipped')),
  subject text,
  error_message text,
  sent_at timestamptz not null default now(),
  unique (action_id)
);

create index if not exists task_owner_notifications_alert_idx
  on public.task_owner_notifications (alert_id, sent_at desc);

alter table public.task_owner_notifications enable row level security;
revoke all on table public.task_owner_notifications from anon, authenticated;
grant select, insert on table public.task_owner_notifications to service_role;
grant usage, select on sequence public.task_owner_notifications_id_seq to service_role;
