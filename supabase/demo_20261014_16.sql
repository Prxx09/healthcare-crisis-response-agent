-- Synthetic hospital surveillance continuation for 14-16 October 2026.
-- Repeatable on the same run ID. This is a demonstration dataset, not patient data.
begin;
with days as (
  select generate_series(date '2026-10-14', date '2026-10-16', interval '1 day')::date as observation_date
)
insert into public.surveillance_observations
  (observation_date,hospital_id,condition_id,signal_source,observation_count,coverage_pct,data_quality,source_note,synthetic_run_id)
select d.observation_date, o.hospital_id, o.condition_id, o.signal_source,
  case
    when h.code='central_hospital' and c.code='ili' and o.signal_source='visits' then
      case d.observation_date when date '2026-10-14' then 75 when date '2026-10-15' then 88 else 104 end
    when h.code='central_hospital' and c.code='ili' and o.signal_source='lab_positives' then
      case d.observation_date when date '2026-10-14' then 22 when date '2026-10-15' then 24 else 26 end
    when h.code='central_hospital' and c.code='ili' and o.signal_source='pharmacy_demand' then
      case d.observation_date when date '2026-10-14' then 86 when date '2026-10-15' then 100 else 114 end
    when h.code='lakeside_hospital' and c.code='age' and o.signal_source='visits' then
      case d.observation_date when date '2026-10-14' then 50 when date '2026-10-15' then 60 else 72 end
    when h.code='lakeside_hospital' and c.code='age' and o.signal_source='lab_positives' then 3
    when h.code='lakeside_hospital' and c.code='age' and o.signal_source='pharmacy_demand' then
      case d.observation_date when date '2026-10-14' then 80 when date '2026-10-15' then 95 else 110 end
    when h.code='east_hospital' and c.code='dengue' and o.signal_source='visits' then
      case d.observation_date when date '2026-10-14' then 360 when date '2026-10-15' then 370 else 380 end
    when h.code='east_hospital' and c.code='dengue' and o.signal_source='lab_positives' then
      case d.observation_date when date '2026-10-14' then 100 when date '2026-10-15' then 102 else 104 end
    when h.code='north_hospital' and c.code='ili' and o.signal_source='visits' then
      case d.observation_date when date '2026-10-14' then 40 when date '2026-10-15' then 42 else 46 end
    else o.observation_count + (d.observation_date - date '2026-10-14')
  end,
  case when h.code='north_hospital' and c.code='ili' and o.signal_source='visits' then
    case d.observation_date when date '2026-10-14' then 68 when date '2026-10-15' then 62 else 55 end
  else o.coverage_pct end,
  case when h.code='north_hospital' and c.code='ili' and o.signal_source='visits' then 'partial'
  else 'validated' end,
  'Synthetic hospital agent demonstration; 14-16 October 2026',
  o.synthetic_run_id
from public.surveillance_observations o
join public.hospitals h on h.id=o.hospital_id
join public.conditions c on c.id=o.condition_id
cross join days d
where o.observation_date=date '2026-10-12'
on conflict (observation_date,hospital_id,condition_id,signal_source,synthetic_run_id)
do update set observation_count=excluded.observation_count, coverage_pct=excluded.coverage_pct,
  data_quality=excluded.data_quality, source_note=excluded.source_note;

with days as (
  select generate_series(date '2026-10-14', date '2026-10-16', interval '1 day')::date as observation_date
)
insert into public.hospital_context
  (observation_date,hospital_id,staffed_beds,occupied_beds,staffing_coverage_pct,supply_readiness_pct,context_note)
select d.observation_date, h.id, base.staffed_beds,
  case h.code
    when 'central_hospital' then 130 + 4*(d.observation_date-date '2026-10-14')
    when 'lakeside_hospital' then 100 + 4*(d.observation_date-date '2026-10-14')
    when 'east_hospital' then 80 + 2*(d.observation_date-date '2026-10-14')
    else 75 + (d.observation_date-date '2026-10-14')
  end,
  case h.code
    when 'central_hospital' then 78 - 2*(d.observation_date-date '2026-10-14')
    when 'lakeside_hospital' then 82 - 2*(d.observation_date-date '2026-10-14')
    else base.staffing_coverage_pct
  end,
  case h.code
    when 'central_hospital' then 78 - 3*(d.observation_date-date '2026-10-14')
    when 'lakeside_hospital' then 77 - 3*(d.observation_date-date '2026-10-14')
    when 'east_hospital' then 76 - 2*(d.observation_date-date '2026-10-14')
    else base.supply_readiness_pct
  end,
  'Synthetic hospital readiness for agent demonstration'
from public.hospital_context base
join public.hospitals h on h.id=base.hospital_id
cross join days d
where base.observation_date=date '2026-10-13'
on conflict (observation_date,hospital_id)
do update set staffed_beds=excluded.staffed_beds, occupied_beds=excluded.occupied_beds,
  staffing_coverage_pct=excluded.staffing_coverage_pct, supply_readiness_pct=excluded.supply_readiness_pct,
  context_note=excluded.context_note;
commit;
notify pgrst, 'reload schema';
