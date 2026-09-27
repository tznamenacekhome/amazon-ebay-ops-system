begin;

create table college_planner.requirement_course_selections (
  id uuid primary key default gen_random_uuid(),
  degree_plan_id uuid not null references college_planner.degree_plans(id) on delete cascade,
  requirement_code text not null check (length(trim(requirement_code)) > 0),
  course_id uuid not null references college_planner.courses(id),
  created_at timestamptz not null default now(),
  unique (degree_plan_id, requirement_code, course_id),
  unique (degree_plan_id, course_id)
);

alter table college_planner.requirement_course_selections enable row level security;

revoke all on college_planner.requirement_course_selections from anon, authenticated;
grant select, insert, update, delete on college_planner.requirement_course_selections to service_role;

-- Preserve existing choices without touching semester assignments.
insert into college_planner.requirement_course_selections
  (degree_plan_id, requirement_code, course_id)
select distinct on (pt.degree_plan_id, pc.course_id)
  pt.degree_plan_id,
  coalesce(rg.code, 'non_degree_free_electives'),
  pc.course_id
from college_planner.planned_courses pc
join college_planner.planned_terms pt on pt.id = pc.planned_term_id
left join college_planner.degree_requirement_groups rg on rg.id = pc.requirement_group_id
where pc.course_id is not null
  and not pc.is_placeholder
  and coalesce(rg.code, '') <> 'core_vfv'
order by pt.degree_plan_id, pc.course_id, pt.sequence_number, pc.sort_order, pc.id
on conflict do nothing;

notify pgrst, 'reload schema';

commit;
