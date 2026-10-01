alter table public.alerts
  add column if not exists analysis_date date,
  add column if not exists reviewed_by text,
  add column if not exists review_note text;

create unique index if not exists alerts_analysis_scope_rule_idx
  on public.alerts (analysis_date, region_id, condition_id, rule_version)
  where analysis_date is not null;

revoke all on table public.alerts from anon, authenticated;
