-- PlasmaSpec Studio -- Supabase schema.
--
-- Run this once in the Supabase SQL editor (Project -> SQL Editor -> New
-- query) after creating the project and enabling the Google auth provider
-- (Authentication -> Providers -> Google). This is the single source of
-- truth for the schema; it supersedes the SQL shown in the original
-- planning doc (that version didn't have the points/wavelength_min_nm/
-- wavelength_max_nm columns added below, which let the spectra list load
-- without downloading every file from Storage just to show point counts).
--
-- After running this, copy Project URL / anon public key / JWT secret from
-- Settings -> API into:
--   - plasma-spec-studio/backend/.env  (SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET)
--   - plasma-spec-studio/frontend/.env.local (NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY)

-- Profiles (auto-populated on signup)
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
create policy "profiles: owner select" on public.profiles for select using (auth.uid() = id);
create policy "profiles: owner update" on public.profiles for update using (auth.uid() = id);

create function public.handle_new_user() returns trigger as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, new.raw_user_meta_data->>'full_name');
  return new;
end;
$$ language plpgsql security definer set search_path = public;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Spectra (raw wavelength/intensity arrays live in Storage; this row is the
-- metadata + a few denormalized summary stats so the spectra list doesn't
-- need a Storage round trip per row just to show point count / wavelength
-- range).
create table public.spectra (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  storage_path text not null,
  metadata jsonb not null default '{}',
  preprocessing_history jsonb not null default '[]',
  points integer,
  wavelength_min_nm double precision,
  wavelength_max_nm double precision,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index spectra_user_id_idx on public.spectra(user_id);
alter table public.spectra enable row level security;
create policy "spectra: owner all" on public.spectra for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Recipes
create table public.recipes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  diagnostic text not null,
  recipe_json jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index recipes_user_id_idx on public.recipes(user_id);
alter table public.recipes enable row level security;
create policy "recipes: owner all" on public.recipes for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Fit results
create table public.fit_results (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  spectrum_id uuid references public.spectra(id) on delete set null,
  diagnostic text not null,
  result_json jsonb not null,
  created_at timestamptz not null default now()
);
create index fit_results_user_id_idx on public.fit_results(user_id);
create index fit_results_spectrum_id_idx on public.fit_results(spectrum_id);
alter table public.fit_results enable row level security;
create policy "fit_results: owner all" on public.fit_results for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Exports (generated CSV/XLSX/PDF/HTML reports)
create table public.exports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  storage_path text not null,
  kind text not null,
  created_at timestamptz not null default now()
);
create index exports_user_id_idx on public.exports(user_id);
alter table public.exports enable row level security;
create policy "exports: owner all" on public.exports for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Storage buckets, private, path-prefixed by user id ({user_id}/{file})
insert into storage.buckets (id, name, public) values ('spectra', 'spectra', false);
insert into storage.buckets (id, name, public) values ('exports', 'exports', false);

create policy "spectra bucket: owner all" on storage.objects for all
  using (bucket_id = 'spectra' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'spectra' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "exports bucket: owner all" on storage.objects for all
  using (bucket_id = 'exports' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'exports' and (storage.foldername(name))[1] = auth.uid()::text);

-- =====================================================================
-- Migration: sharing (activity feed) + profile avatars
-- Run this block in the SQL editor once -- it's additive to the schema
-- above, which you've already applied.
-- =====================================================================

alter table public.profiles add column if not exists avatar_url text;

-- Shared results are a self-contained snapshot (name/avatar/result copied
-- at share time), not a live reference to fit_results -- so the feed never
-- needs cross-user reads against profiles or fit_results, which stay
-- owner-only.
create table public.shared_results (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  display_name text,
  avatar_url text,
  spectrum_filename text,
  diagnostic text not null,
  caption text,
  result_json jsonb not null,
  created_at timestamptz not null default now()
);
create index shared_results_created_at_idx on public.shared_results(created_at desc);
alter table public.shared_results enable row level security;
create policy "shared_results: any signed-in member can read" on public.shared_results
  for select using (auth.uid() is not null);
create policy "shared_results: owner can insert" on public.shared_results
  for insert with check (auth.uid() = user_id);
create policy "shared_results: owner can delete" on public.shared_results
  for delete using (auth.uid() = user_id);

-- Avatars bucket is public-read (unlike spectra/exports) since other
-- members need to see them, but still owner-write only.
insert into storage.buckets (id, name, public) values ('avatars', 'avatars', true);

create policy "avatars bucket: public read" on storage.objects for select
  using (bucket_id = 'avatars');
create policy "avatars bucket: owner insert" on storage.objects for insert
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "avatars bucket: owner update" on storage.objects for update
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "avatars bucket: owner delete" on storage.objects for delete
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);
