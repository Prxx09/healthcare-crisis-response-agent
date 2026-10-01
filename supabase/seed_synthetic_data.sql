-- One-year synthetic, aggregate data seed for a dashboard and rule-engine demonstration.
-- Keeps four regions constant and introduces three transparent, documented signal patterns.

insert into public.regions (code, name, population, active)
values
  ('north_district', 'North District', 420000, true),
  ('central_district', 'Central District', 610000, true),
  ('east_district', 'East District', 385000, true),
  ('lakeside_district', 'Lakeside District', 470000, true)
on conflict (code) do update set name = excluded.name, population = excluded.population, active = excluded.active;

insert into public.conditions (code, name, syndrome_group, active)
values
  ('ili', 'Influenza-like Illness', 'Respiratory syndrome', true),
  ('age', 'Acute Gastroenteritis', 'Gastrointestinal syndrome', true),
  ('dengue', 'Dengue', 'Vector-borne febrile illness', true)
on conflict (code) do update set name = excluded.name, syndrome_group = excluded.syndrome_group, active = excluded.active;

with days as (
  select generate_series(date '2025-10-01', date '2026-09-30', interval '1 day')::date as observation_date
), numbered_days as (
  select observation_date, row_number() over (order by observation_date) - 1 as day_index from days
)
insert into public.regional_context (observation_date, region_id, rainfall_index, mobility_index, temperature_c, context_note)
select
  d.observation_date,
  r.id,
  greatest(0, round(30 + 18 * sin(2 * pi() * d.day_index / 90.0) + 8 * region_order + 4 * sin(d.day_index * 1.7))),
  round(100 + 6 * sin(2 * pi() * d.day_index / 7.0) + 2 * sin(d.day_index * 2.3)),
  round((26 + 2.2 * sin(2 * pi() * d.day_index / 90.0) + 0.4 * region_order)::numeric, 1),
  'Synthetic regional context'
from numbered_days d
cross join lateral (
  select id, code, row_number() over (order by code) - 1 as region_order from public.regions
) r
on conflict (observation_date, region_id) do update
set rainfall_index = excluded.rainfall_index,
    mobility_index = excluded.mobility_index,
    temperature_c = excluded.temperature_c,
    context_note = excluded.context_note;

with days as (
  select generate_series(date '2025-10-01', date '2026-09-30', interval '1 day')::date as observation_date
), numbered_days as (
  select observation_date, row_number() over (order by observation_date) - 1 as day_index from days
), base_signals as (
  select
    d.observation_date,
    d.day_index,
    r.id as region_id,
    r.code as region_code,
    c.id as condition_id,
    c.code as condition_code,
    greatest(0, round((
      (case c.code when 'ili' then 34 when 'age' then 22 else 8 end)
      + (case r.code when 'central_district' then 4 when 'east_district' then 2 when 'lakeside_district' then 3 else 0 end)
      + 2 * sin(d.day_index * 1.7)
    ) * case c.code
      when 'ili' then 1.0 + 0.10 * sin(2 * pi() * d.day_index / 7.0)
      when 'age' then 1.0 + 0.05 * sin(2 * pi() * d.day_index / 7.0)
      else 1.0 + 0.012 * greatest(0, 30 + 18 * sin(2 * pi() * d.day_index / 90.0))
    end * case
      when c.code = 'ili' and r.code = 'central_district' and d.day_index between 62 and 75 then 1.0 + 0.10 * (d.day_index - 61)
      when c.code = 'age' and r.code = 'lakeside_district' and d.day_index between 35 and 42 then 1.0 + 0.18 * least(d.day_index - 34, 5)
      when c.code = 'dengue' and r.code = 'east_district' and d.day_index >= 68 then 1.0 + 0.06 * (d.day_index - 67)
      else 1.0
    end
  ))::integer as visits
  from numbered_days d
  cross join public.regions r
  cross join public.conditions c
)
insert into public.surveillance_observations (
  observation_date, region_id, condition_id, signal_source, observation_count,
  coverage_pct, data_quality, source_note, synthetic_run_id
)
select
  b.observation_date,
  b.region_id,
  b.condition_id,
  x.signal_source,
  x.observation_count,
  x.coverage_pct,
  'validated',
  x.source_note,
  'seed-42-oct-2025-sep-2026'
from base_signals b
cross join lateral (
  values
    ('visits', b.visits, 95::numeric, 'Syndromic visits or suspected-case counts'),
    ('lab_positives', greatest(0, round(b.visits * case b.condition_code when 'ili' then 0.22 when 'age' then 0.14 else 0.32 end))::integer, 95::numeric, 'Synthetic laboratory positives'),
    ('pharmacy_demand', greatest(0, round(b.visits * case b.condition_code when 'ili' then 1.45 else 1.20 end))::integer, 90::numeric, 'Synthetic pharmacy demand index')
) as x(signal_source, observation_count, coverage_pct, source_note)
where b.condition_code in ('ili', 'age') or x.signal_source <> 'pharmacy_demand'
on conflict (observation_date, region_id, condition_id, signal_source, synthetic_run_id) do update
set observation_count = excluded.observation_count,
    coverage_pct = excluded.coverage_pct,
    data_quality = excluded.data_quality,
    source_note = excluded.source_note;
