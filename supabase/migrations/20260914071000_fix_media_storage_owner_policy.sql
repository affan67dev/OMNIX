-- Align Storage object ownership policy with server-created paths: bucket/uid/file.
drop policy if exists storage_insert_own_media on storage.objects;
drop policy if exists storage_select_own_media on storage.objects;
drop policy if exists storage_delete_own_media on storage.objects;

create policy storage_insert_own_media on storage.objects for insert to authenticated
  with check (
    bucket_id in ('stories','posts','reels')
    and (storage.foldername(name))[2] = auth.uid()::text
  );
create policy storage_select_own_media on storage.objects for select to authenticated
  using (
    bucket_id in ('stories','posts','reels')
    and (storage.foldername(name))[2] = auth.uid()::text
  );
create policy storage_delete_own_media on storage.objects for delete to authenticated
  using (
    bucket_id in ('stories','posts','reels')
    and (storage.foldername(name))[2] = auth.uid()::text
  );
