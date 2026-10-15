-- Synthetic, aggregate data seed from 1 October 2025 through 13 October 2026.
-- Keeps four hospitals constant and includes transparent threshold-crossing demonstration scenarios.

insert into public.hospitals (code, name, bed_capacity, active)
values
  ('north_hospital', 'North Hospital', 120, true),
  ('central_hospital', 'Central Hospital', 180, true),
  ('east_hospital', 'East Hospital', 110, true),
  ('lakeside_hospital', 'Lakeside Hospital', 140, true)
on conflict (code) do update set name = excluded.name, bed_capacity = excluded.bed_capacity, active = excluded.active;

insert into public.conditions (code, name, syndrome_group, active)
values
  ('ili', 'Influenza-like Illness', 'Respiratory syndrome', true),
  ('age', 'Acute Gastroenteritis', 'Gastrointestinal syndrome', true),
  ('dengue', 'Dengue', 'Vector-borne febrile illness', true)
on conflict (code) do update set name = excluded.name, syndrome_group = excluded.syndrome_group, active = excluded.active;

-- Preserve one idempotent synthetic series when extending the original seed window.
update public.surveillance_observations
set synthetic_run_id = 'seed-42-oct-2025-oct-2026'
where synthetic_run_id = 'seed-42-oct-2025-sep-2026';

with days as (
  select generate_series(date '2025-10-01', date '2026-10-13', interval '1 day')::date as observation_date
), numbered_days as (
  select observation_date, row_number() over (order by observation_date) - 1 as day_index from days
)
insert into public.hospital_context (observation_date, hospital_id, staffed_beds, occupied_beds, staffing_coverage_pct, supply_readiness_pct, context_note)
select
  d.observation_date,
  r.id,
  r.staffed_beds,
  least(r.staffed_beds, greatest(0, round(r.staffed_beds * (0.65 + 0.08 * sin(2 * pi() * d.day_index / 90.0) + 0.02 * sin(d.day_index * 1.7))))::integer),
  round((90 + 4 * sin(2 * pi() * d.day_index / 7.0) + 2 * sin(d.day_index * 2.3))::numeric, 1),
  round((88 + 3 * sin(2 * pi() * d.day_index / 90.0) + 2 * sin(d.day_index * 1.1))::numeric, 1),
  'Synthetic hospital operations snapshot'
from numbered_days d
cross join lateral (
  select id, greatest(1, round(bed_capacity * 0.85))::integer as staffed_beds from public.hospitals
) r
on conflict (observation_date, hospital_id) do update
set staffed_beds = excluded.staffed_beds,
    occupied_beds = excluded.occupied_beds,
    staffing_coverage_pct = excluded.staffing_coverage_pct,
    supply_readiness_pct = excluded.supply_readiness_pct,
    context_note = excluded.context_note;

with days as (
  select generate_series(date '2025-10-01', date '2026-10-13', interval '1 day')::date as observation_date
), numbered_days as (
  select observation_date, row_number() over (order by observation_date) - 1 as day_index from days
), base_signals as (
  select
    d.observation_date,
    d.day_index,
    r.id as hospital_id,
    r.code as hospital_code,
    c.id as condition_id,
    c.code as condition_code,
    greatest(0, round((
      (case c.code when 'ili' then 34 when 'age' then 22 else 8 end)
      + (case r.code when 'central_hospital' then 4 when 'east_hospital' then 2 when 'lakeside_hospital' then 3 else 0 end)
      + 2 * sin(d.day_index * 1.7)
    ) * case c.code
      when 'ili' then 1.0 + 0.10 * sin(2 * pi() * d.day_index / 7.0)
      when 'age' then 1.0 + 0.05 * sin(2 * pi() * d.day_index / 7.0)
      else 1.0 + 0.10 * sin(2 * pi() * d.day_index / 90.0)
    end * case
      when c.code = 'ili' and r.code = 'central_hospital' and d.day_index between 62 and 75 then 1.0 + 0.10 * (d.day_index - 61)
      when c.code = 'age' and r.code = 'lakeside_hospital' and d.day_index between 35 and 42 then 1.0 + 0.18 * least(d.day_index - 34, 5)
      when c.code = 'dengue' and r.code = 'east_hospital' and d.day_index >= 68 then 1.0 + 0.06 * (d.day_index - 67)
      else 1.0
    end * case
      -- Small lead-in increases make the demonstration trend visible while
      -- keeping the 13 October values well above the 28-day baseline.
      when d.observation_date between date '2026-10-10' and date '2026-10-12'
        and (
          (r.code, c.code) in (
            ('central_hospital', 'ili'),
            ('central_hospital', 'dengue'),
            ('east_hospital', 'age'),
            ('east_hospital', 'dengue'),
            ('lakeside_hospital', 'age'),
            ('lakeside_hospital', 'dengue'),
            ('north_hospital', 'ili'),
            ('north_hospital', 'dengue')
          )
        ) then 1.15 + 0.10 * (d.observation_date - date '2026-10-10')
      when d.observation_date = date '2026-10-13' and r.code = 'central_hospital' and c.code = 'ili' then 2.8
      when d.observation_date = date '2026-10-13' and r.code = 'central_hospital' and c.code = 'dengue' then 3.2
      when d.observation_date = date '2026-10-13' and r.code = 'east_hospital' and c.code = 'age' then 3.0
      when d.observation_date = date '2026-10-13' and r.code = 'east_hospital' and c.code = 'dengue' then 2.8
      when d.observation_date = date '2026-10-13' and r.code = 'lakeside_hospital' and c.code = 'age' then 2.7
      when d.observation_date = date '2026-10-13' and r.code = 'lakeside_hospital' and c.code = 'dengue' then 2.4
      when d.observation_date = date '2026-10-13' and r.code = 'north_hospital' and c.code = 'ili' then 2.6
      when d.observation_date = date '2026-10-13' and r.code = 'north_hospital' and c.code = 'dengue' then 3.4
      else 1.0
    end
  ))::integer as visits
  from numbered_days d
  cross join public.hospitals r
  cross join public.conditions c
)
insert into public.surveillance_observations (
  observation_date, hospital_id, condition_id, signal_source, observation_count,
  coverage_pct, data_quality, source_note, synthetic_run_id
)
select
  b.observation_date,
  b.hospital_id,
  b.condition_id,
  x.signal_source,
  x.observation_count,
  x.coverage_pct,
  'validated',
  x.source_note,
  'seed-42-oct-2025-oct-2026'
from base_signals b
cross join lateral (
  values
    ('visits', b.visits, 95::numeric, 'Syndromic visits or suspected-case counts'),
    ('lab_positives', greatest(0, round(b.visits * case b.condition_code when 'ili' then 0.22 when 'age' then 0.14 else 0.32 end))::integer, 95::numeric, 'Synthetic laboratory positives'),
    ('pharmacy_demand', greatest(0, round(b.visits * case b.condition_code when 'ili' then 1.45 else 1.20 end))::integer, 90::numeric, 'Synthetic pharmacy demand index')
) as x(signal_source, observation_count, coverage_pct, source_note)
where b.condition_code in ('ili', 'age') or x.signal_source <> 'pharmacy_demand'
on conflict (observation_date, hospital_id, condition_id, signal_source, synthetic_run_id) do update
set observation_count = excluded.observation_count,
    coverage_pct = excluded.coverage_pct,
    data_quality = excluded.data_quality,
    source_note = excluded.source_note;
