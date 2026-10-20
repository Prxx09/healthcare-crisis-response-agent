-- Uploaded originals are private; only the backend service key accesses this library.
create table if not exists public.playbook_documents (
  id text primary key check (id ~ '^[a-f0-9]{64}$'),
  filename text not null,
  format text not null check (format in ('pdf','docx','json','yaml','yml')),
  size_bytes integer not null check (size_bytes between 1 and 5242880),
  storage_path text not null,
  extracted_text text not null,
  actions jsonb not null default '[]'::jsonb check (jsonb_typeof(actions) = 'array'),
  extraction_method text,
  index_namespace text not null unique,
  vector_count integer not null default 0 check (vector_count >= 0),
  status text not null check (status in ('processing','indexed','failed')),
  active boolean not null default false,
  error_message text,
  reviewed_by text,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (not active or (status='indexed' and reviewed_by is not null and reviewed_at is not null))
);
create index if not exists playbook_documents_active_idx on public.playbook_documents(created_at desc) where active and status='indexed';
alter table public.playbook_documents enable row level security;
revoke all on table public.playbook_documents from anon, authenticated;
grant select, insert, update, delete on table public.playbook_documents to service_role;
insert into storage.buckets (id,name,public,file_size_limit)
values ('playbook-sources','playbook-sources',false,5242880)
on conflict (id) do nothing;
notify pgrst, 'reload schema';

-- Preserve the source of each response task after a playbook is deactivated.
alter table public.incident_actions add column if not exists source_document_id text references public.playbook_documents(id);
alter table public.incident_actions add column if not exists source_action_id text;
create index if not exists incident_actions_source_document_idx on public.incident_actions(source_document_id) where source_document_id is not null;
