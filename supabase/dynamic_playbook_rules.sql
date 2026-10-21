-- Accept explicitly named diseases, keeping one authoritative uploaded ruleset per disease.
alter table public.conditions drop constraint if exists conditions_code_check;
alter table public.conditions add constraint conditions_code_check
  check (code ~ '^[a-z][a-z0-9_]*$' and length(code) <= 80);

create table if not exists public.playbook_condition_rules (
  condition_code text primary key references public.conditions(code),
  document_id text not null references public.playbook_documents(id),
  enabled boolean not null default true,
  reviewed_by text not null,
  updated_at timestamptz not null default now()
);
create index if not exists playbook_condition_rules_document_idx on public.playbook_condition_rules(document_id);
alter table public.playbook_condition_rules enable row level security;
revoke all on public.playbook_condition_rules from anon, authenticated;
grant select, insert, update on public.playbook_condition_rules to service_role;

create table if not exists public.playbook_rule_events (
  id bigint generated always as identity primary key,
  condition_code text not null references public.conditions(code),
  previous_document_id text references public.playbook_documents(id),
  document_id text not null references public.playbook_documents(id),
  enabled boolean not null,
  reviewed_by text not null,
  created_at timestamptz not null default now()
);
create index if not exists playbook_rule_events_condition_idx on public.playbook_rule_events(condition_code,created_at desc);
create index if not exists playbook_rule_events_previous_idx on public.playbook_rule_events(previous_document_id);
create index if not exists playbook_rule_events_document_idx on public.playbook_rule_events(document_id);
alter table public.playbook_rule_events enable row level security;
revoke all on public.playbook_rule_events from anon, authenticated;
grant select, insert on public.playbook_rule_events to service_role;
grant usage, select on sequence public.playbook_rule_events_id_seq to service_role;
grant select, insert, update on public.conditions to service_role;

-- Runs with caller privileges; callable only by the backend service role.
create or replace function public.activate_playbook_rules(p_document_id text,p_active boolean,p_reviewer text)
returns jsonb language plpgsql security invoker set search_path = public, pg_temp as $$
declare
  doc public.playbook_documents%rowtype;
  disease record;
  previous_id text;
begin
  if length(trim(p_reviewer)) < 2 or length(p_reviewer)>100 then
    raise exception 'A reviewer name of 2-100 characters is required';
  end if;
  -- Serialize registry switches so concurrent activations cannot leave mixed rules.
  perform pg_advisory_xact_lock(hashtext('healthcare_playbook_rule_activation'));
  select * into doc from public.playbook_documents where id=p_document_id for update;
  if not found then raise exception 'Playbook not found' using errcode='P0002'; end if;
  if p_active and (doc.status<>'indexed' or jsonb_array_length(doc.actions)=0 or doc.vector_count=0) then
    raise exception 'Only successfully indexed playbooks with actions can be activated';
  end if;
  if p_active then
    for disease in
      select distinct on (a->>'condition_code') a->>'condition_code' as code,
        coalesce(nullif(a->>'condition_name',''),initcap(replace(a->>'condition_code','_',' '))) as name
      from jsonb_array_elements(doc.actions) a order by a->>'condition_code'
    loop
      if disease.code is null or disease.code !~ '^[a-z][a-z0-9_]*$' or length(disease.code)>80 then
        raise exception 'Invalid disease code in playbook';
      end if;
      insert into public.conditions(code,name,syndrome_group,active)
        values(disease.code,disease.name,'playbook_defined',true)
        on conflict (code) do update set active=true;
      select document_id into previous_id from public.playbook_condition_rules where condition_code=disease.code;
      insert into public.playbook_condition_rules(condition_code,document_id,enabled,reviewed_by,updated_at)
        values(disease.code,p_document_id,true,trim(p_reviewer),now())
        on conflict (condition_code) do update set document_id=excluded.document_id,enabled=true,
          reviewed_by=excluded.reviewed_by,updated_at=excluded.updated_at;
      insert into public.playbook_rule_events(condition_code,previous_document_id,document_id,enabled,reviewed_by)
        values(disease.code,previous_id,p_document_id,true,trim(p_reviewer));
    end loop;
  else
    for disease in select condition_code,document_id from public.playbook_condition_rules
      where document_id=p_document_id and enabled for update
    loop
      update public.playbook_condition_rules set enabled=false,reviewed_by=trim(p_reviewer),updated_at=now()
        where condition_code=disease.condition_code;
      insert into public.playbook_rule_events(condition_code,previous_document_id,document_id,enabled,reviewed_by)
        values(disease.condition_code,p_document_id,p_document_id,false,trim(p_reviewer));
    end loop;
  end if;
  update public.playbook_documents set reviewed_by=trim(p_reviewer),reviewed_at=now(),updated_at=now()
    where id=p_document_id;
  update public.playbook_documents d set active=exists(
    select 1 from public.playbook_condition_rules r where r.document_id=d.id and r.enabled)
    where d.active is distinct from exists(
      select 1 from public.playbook_condition_rules r where r.document_id=d.id and r.enabled);
  select * into doc from public.playbook_documents where id=p_document_id;
  return to_jsonb(doc)-'extracted_text';
end;
$$;
revoke all on function public.activate_playbook_rules(text,boolean,text) from public,anon,authenticated;
grant execute on function public.activate_playbook_rules(text,boolean,text) to service_role;

-- Preserve an existing reviewed active upload when upgrading an older installation.
insert into public.playbook_condition_rules(condition_code,document_id,enabled,reviewed_by)
select distinct on (a->>'condition_code') a->>'condition_code',d.id,true,d.reviewed_by
from public.playbook_documents d cross join lateral jsonb_array_elements(d.actions) a
join public.conditions c on c.code=a->>'condition_code'
where d.active and d.status='indexed' and d.reviewed_by is not null
order by a->>'condition_code',d.reviewed_at desc nulls last,d.created_at desc,d.id
on conflict (condition_code) do nothing;
notify pgrst, 'reload schema';
