alter table public.email_alert_config
  add column if not exists incident_master_email text not null
  default 'prajwal.khadse@maqsoftware.com';

create table if not exists public.incident_review_notifications (
  id bigint generated always as identity primary key,
  alert_id bigint not null references public.alerts(id) on delete cascade,
  recipient text,
  status text not null check (status in ('success', 'failed', 'skipped')),
  subject text,
  error_message text,
  sent_at timestamptz not null default now(),
  unique (alert_id)
);

create index if not exists incident_review_notifications_sent_idx
  on public.incident_review_notifications (sent_at desc);

alter table public.incident_review_notifications enable row level security;
revoke all on table public.incident_review_notifications from anon, authenticated;
grant select, insert on table public.incident_review_notifications to service_role;
grant usage, select on sequence public.incident_review_notifications_id_seq to service_role;
