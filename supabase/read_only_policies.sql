-- Read-only Data API access for synthetic, aggregate surveillance data.
-- Alerts remain protected for the future authenticated approval workflow.

grant usage on schema public to anon, authenticated;
grant select on table
  public.hospitals,
  public.conditions,
  public.hospital_context,
  public.surveillance_observations
to anon, authenticated;

revoke all on table public.alerts from anon, authenticated;

drop policy if exists "public read hospitals" on public.hospitals;
create policy "public read hospitals"
on public.hospitals for select
to anon, authenticated
using (true);

drop policy if exists "public read conditions" on public.conditions;
create policy "public read conditions"
on public.conditions for select
to anon, authenticated
using (true);

drop policy if exists "public read hospital context" on public.hospital_context;
create policy "public read hospital context"
on public.hospital_context for select
to anon, authenticated
using (true);

drop policy if exists "public read surveillance observations" on public.surveillance_observations;
create policy "public read surveillance observations"
on public.surveillance_observations for select
to anon, authenticated
using (true);
