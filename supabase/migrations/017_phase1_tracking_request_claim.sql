-- Phase 1 new-product ingestion
--
-- Atomically claim pending tracking requests for trusted workers.
--
-- Multiple workers may execute this function concurrently.
-- FOR UPDATE SKIP LOCKED ensures a request is claimed by at most
-- one worker at a time.


create or replace function public.claim_tracking_requests(
    p_limit integer default 1
)
returns setof public.tracking_requests
language plpgsql
security definer
set search_path = ''
as $$
begin
    if (
        p_limit is null
        or p_limit < 1
        or p_limit > 50
    ) then
        raise exception
            'p_limit must be between 1 and 50';
    end if;

    return query
    with candidates as (
        select tr.id
        from public.tracking_requests as tr
        where tr.status = 'pending'
        order by
            tr.created_at asc,
            tr.id asc
        limit p_limit
        for update skip locked
    )
    update public.tracking_requests as tr
    set
        status = 'processing',
        attempt_count = tr.attempt_count + 1,
        started_at = pg_catalog.now(),
        error_code = null,
        error_message = null
    from candidates
    where tr.id = candidates.id
      and tr.status = 'pending'
    returning tr.*;
end;
$$;


-- Normal browser/authenticated users must never be able to claim
-- trusted ingestion work.

revoke all
on function public.claim_tracking_requests(integer)
from public, anon, authenticated;


-- Only the trusted crawler service role may execute it.

grant execute
on function public.claim_tracking_requests(integer)
to service_role;
