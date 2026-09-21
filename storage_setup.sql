-- Run this once in Supabase SQL Editor.
-- It keeps your existing memories table and only adds the fields
-- needed for the Admin Dashboard Trash system.

alter table memories
  add column if not exists status text default 'active';

alter table memories
  add column if not exists deleted_at timestamptz;

update memories
set status = 'active'
where status is null;

alter table memories
  alter column status set default 'active';
