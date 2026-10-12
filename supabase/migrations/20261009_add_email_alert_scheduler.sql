create table if not exists public.email_alert_config (
  id smallint primary key default 1 check (id = 1),
  enabled boolean not null default false,
  schedule_time time not null default '09:00',
  timezone text not null default 'Asia/Kolkata',
  recipients text[] not null default '{}',
  cc text[] not null default '{}',
  minimum_level text not null default 'investigate'
    check (minimum_level in ('investigate', 'escalate')),
  updated_at timestamptz not null default now()
);

insert into public.email_alert_config (id)
values (1)
on conflict (id) do nothing;

create table if not exists public.email_alert_deliveries (
  id bigint generated always as identity primary key,
  trigger_mode text not null check (trigger_mode in ('scheduled', 'manual')),
  status text not null check (status in ('success', 'failed', 'skipped')),
  analysis_date date,
  schedule_date date,
  recipients text[] not null default '{}',
  cc text[] not null default '{}',
  alert_ids bigint[] not null default '{}',
  subject text,
  error_message text,
  sent_at timestamptz not null default now()
);

create unique index if not exists email_alert_deliveries_scheduled_date_idx
  on public.email_alert_deliveries (schedule_date)
  where trigger_mode = 'scheduled';

create index if not exists email_alert_deliveries_sent_at_idx
  on public.email_alert_deliveries (sent_at desc);

alter table public.email_alert_config enable row level security;
alter table public.email_alert_deliveries enable row level security;

revoke all on table public.email_alert_config from anon, authenticated;
revoke all on table public.email_alert_deliveries from anon, authenticated;
grant select, insert, update on table public.email_alert_config to service_role;
grant select, insert on table public.email_alert_deliveries to service_role;
grant usage, select on sequence public.email_alert_deliveries_id_seq to service_role;
