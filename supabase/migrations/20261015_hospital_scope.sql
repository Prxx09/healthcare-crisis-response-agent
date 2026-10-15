-- Convert the synthetic geographic scope to hospitals without changing observation,
-- alert, action, or notification IDs. Apply once to the existing project.
begin;

alter table public.regions rename to hospitals;
alter table public.regional_context rename to hospital_context;
alter table public.hospitals rename column population to bed_capacity;
alter table public.hospital_context rename column region_id to hospital_id;
alter table public.surveillance_observations rename column region_id to hospital_id;
alter table public.alerts rename column region_id to hospital_id;

alter table public.hospitals drop constraint regions_population_check;
update public.hospitals
set code = replace(code, '_district', '_hospital'),
    name = replace(name, ' District', ' Hospital'),
    bed_capacity = case code
      when 'north_district' then 120
      when 'central_district' then 180
      when 'east_district' then 110
      when 'lakeside_district' then 140
    end
where code in ('north_district', 'central_district', 'east_district', 'lakeside_district');
alter table public.hospitals add constraint hospitals_bed_capacity_check check (bed_capacity > 0);

alter table public.hospital_context
  add column staffed_beds integer,
  add column occupied_beds integer,
  add column staffing_coverage_pct numeric(5,2),
  add column supply_readiness_pct numeric(5,2);

update public.hospital_context c
set staffed_beds = greatest(1, round(h.bed_capacity * 0.85))::integer,
    occupied_beds = least(greatest(1, round(h.bed_capacity * 0.85))::integer,
      greatest(0, round(h.bed_capacity * 0.85 *
        (0.65 + 0.08 * sin(2 * pi() * (c.observation_date - date '2025-10-01') / 90.0))))::integer),
    staffing_coverage_pct = round((90 + 4 * sin(2 * pi() * (c.observation_date - date '2025-10-01') / 7.0))::numeric, 1),
    supply_readiness_pct = round((88 + 3 * sin(2 * pi() * (c.observation_date - date '2025-10-01') / 90.0))::numeric, 1),
    context_note = 'Synthetic hospital operations snapshot'
from public.hospitals h
where c.hospital_id = h.id;

alter table public.hospital_context
  alter column staffed_beds set not null,
  alter column occupied_beds set not null,
  alter column staffing_coverage_pct set not null,
  alter column supply_readiness_pct set not null,
  add constraint hospital_context_staffed_beds_check check (staffed_beds > 0),
  add constraint hospital_context_occupied_beds_check check (occupied_beds between 0 and staffed_beds),
  add constraint hospital_context_staffing_check check (staffing_coverage_pct between 0 and 100),
  add constraint hospital_context_supply_check check (supply_readiness_pct between 0 and 100),
  drop column rainfall_index,
  drop column mobility_index,
  drop column temperature_c;

-- Evidence JSON is a snapshot of the alert. Align both the top-level case
-- scope and every source signal with the preserved hospital ID.
update public.alerts a
set evidence_summary = jsonb_set(
  jsonb_set(
    jsonb_set(a.evidence_summary - 'region' - 'region_code', '{hospital}', to_jsonb(h.name), true),
    '{hospital_code}', to_jsonb(h.code), true),
  '{signals}', coalesce((
    select jsonb_agg(
      jsonb_set(jsonb_set(signal - 'region_name' - 'region_code',
        '{hospital_name}', to_jsonb(h.name), true),
        '{hospital_code}', to_jsonb(h.code), true)
      order by signal_ordinal)
    from jsonb_array_elements(coalesce(a.evidence_summary->'signals', '[]'::jsonb))
      with ordinality as signals(signal, signal_ordinal)
  ), '[]'::jsonb), true)
from public.hospitals h
where a.hospital_id = h.id;

alter table public.hospitals rename constraint regions_pkey to hospitals_pkey;
alter table public.hospitals rename constraint regions_code_key to hospitals_code_key;
alter table public.hospitals rename constraint regions_name_key to hospitals_name_key;
alter table public.hospitals rename constraint regions_code_check to hospitals_code_check;
alter table public.hospital_context rename constraint regional_context_pkey to hospital_context_pkey;
alter table public.hospital_context rename constraint regional_context_region_id_fkey to hospital_context_hospital_id_fkey;
alter table public.hospital_context rename constraint regional_context_observation_date_region_id_key to hospital_context_observation_date_hospital_id_key;
alter table public.surveillance_observations rename constraint surveillance_observations_region_id_fkey to surveillance_observations_hospital_id_fkey;
alter table public.surveillance_observations rename constraint surveillance_observations_observation_date_region_id_condit_key to surveillance_observations_date_hospital_condition_source_run_key;
alter table public.alerts rename constraint alerts_region_id_fkey to alerts_hospital_id_fkey;

alter index public.regional_context_lookup_idx rename to hospital_context_lookup_idx;
alter index public.surveillance_observations_region_idx rename to surveillance_observations_hospital_idx;
alter index public.alerts_region_idx rename to alerts_hospital_idx;
alter sequence public.regions_id_seq rename to hospitals_id_seq;
alter sequence public.regional_context_id_seq rename to hospital_context_id_seq;

drop policy if exists "public read regions" on public.hospitals;
drop policy if exists "public read regional context" on public.hospital_context;
create policy "public read hospitals" on public.hospitals for select to anon, authenticated using (true);
create policy "public read hospital context" on public.hospital_context for select to anon, authenticated using (true);

commit;
notify pgrst, 'reload schema';
