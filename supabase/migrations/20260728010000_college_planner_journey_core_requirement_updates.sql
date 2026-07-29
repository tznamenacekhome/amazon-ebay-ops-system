-- College Planner Journey Core requirement/catalog canonicalization.
-- MBOP is the migration authority for the shared Supabase project.

begin;

do $$
declare
  lipscomb_id uuid;
  powers_group_id uuid;
  literary_group_id uuid;
  diverse_group_id uuid;
  literary_option_id uuid;
  diverse_option_id uuid;
begin
  select id
    into lipscomb_id
  from college_planner.universities
  where code = 'lipscomb'
     or name = 'Lipscomb University'
  order by case when code = 'lipscomb' then 0 else 1 end
  limit 1;

  if lipscomb_id is null then
    raise exception 'Lipscomb University row not found in college_planner.universities';
  end if;

  insert into college_planner.subjects (university_id, code, name, is_active)
  values
    (lipscomb_id, 'BY', 'BY', true),
    (lipscomb_id, 'ED', 'ED', true),
    (lipscomb_id, 'EN', 'EN', true),
    (lipscomb_id, 'ENGR', 'ENGR', true),
    (lipscomb_id, 'FR', 'FR', true),
    (lipscomb_id, 'GE', 'GE', true),
    (lipscomb_id, 'HI', 'HI', true),
    (lipscomb_id, 'ITA', 'ITA', true),
    (lipscomb_id, 'KIN', 'KIN', true),
    (lipscomb_id, 'LJS', 'LJS', true),
    (lipscomb_id, 'LU', 'LU', true),
    (lipscomb_id, 'ML', 'ML', true),
    (lipscomb_id, 'NURS', 'NURS', true),
    (lipscomb_id, 'PO', 'PO', true),
    (lipscomb_id, 'PS', 'PS', true),
    (lipscomb_id, 'SN', 'SN', true),
    (lipscomb_id, 'SW', 'SW', true)
  on conflict (university_id, code) do update
    set is_active = true,
        updated_at = now();

  with course_data(subject_code, course_number, title, credits) as (
    values
      ('LU', '1013', 'POWERS: Writing to Discover', 3.00::numeric),
      ('LU', '1023', 'POWERS: Communicating to Influence', 3.00::numeric),
      ('EN', '2103', 'Literary Inquiry', 3.00::numeric),
      ('BY', '3553', 'The Art of Anatomy, Culture, & Healthcare', 3.00::numeric),
      ('NURS', '3553', 'The Art of Anatomy, Culture, & Healthcare', 3.00::numeric),
      ('ED', '3343', 'Cultural Perspectives in Education', 3.00::numeric),
      ('EN', '2903', 'Reading and Writing Critically', 3.00::numeric),
      ('EN', '3063', 'African American Literature', 3.00::numeric),
      ('ENGR', '3613', 'Humanitarian Engineering', 3.00::numeric),
      ('FR', '1114', 'Elementary French I', 4.00::numeric),
      ('FR', '1124', 'Elementary French II', 4.00::numeric),
      ('GE', '1114', 'Elementary German I', 4.00::numeric),
      ('GE', '1124', 'Elementary German II', 4.00::numeric),
      ('ITA', '1114', 'Elementary Italian I', 4.00::numeric),
      ('ITA', '1124', 'Elementary Italian II', 4.00::numeric),
      ('KIN', '1303', 'Healthful Living', 3.00::numeric),
      ('KIN', '2013', 'Sport Sociology', 3.00::numeric),
      ('LJS', '3533', 'Women and the Law', 3.00::numeric),
      ('ML', '2103', 'How Language Works', 3.00::numeric),
      ('NURS', '4054', 'Community Health Nursing', 4.00::numeric),
      ('PO', '3153', 'African Politics', 3.00::numeric),
      ('HI', '4053', 'History and Politics of the Middle East', 3.00::numeric),
      ('PO', '4053', 'History and Politics of the Middle East', 3.00::numeric),
      ('PS', '3483', 'Human Sexuality', 3.00::numeric),
      ('PS', '4613', 'History and Systems of Psychology', 3.00::numeric),
      ('SN', '1114', 'Elementary Spanish I', 4.00::numeric),
      ('SN', '1124', 'Elementary Spanish II', 4.00::numeric),
      ('SW', '3133', 'Human Diversity', 3.00::numeric)
  )
  insert into college_planner.courses (
    university_id,
    subject_id,
    course_number,
    title,
    credits_min,
    credits_max,
    level,
    is_variable_credit,
    is_active,
    catalog_title,
    catalog_last_synced_at
  )
  select
    lipscomb_id,
    s.id,
    cd.course_number,
    cd.title,
    cd.credits,
    cd.credits,
    'undergraduate',
    false,
    true,
    cd.title,
    now()
  from course_data cd
  join college_planner.subjects s
    on s.university_id = lipscomb_id
   and s.code = cd.subject_code
  on conflict (university_id, subject_id, course_number) do update
    set title = excluded.title,
        credits_min = excluded.credits_min,
        credits_max = excluded.credits_max,
        level = excluded.level,
        is_variable_credit = false,
        is_active = true,
        catalog_title = coalesce(college_planner.courses.catalog_title, excluded.catalog_title),
        catalog_last_synced_at = coalesce(college_planner.courses.catalog_last_synced_at, excluded.catalog_last_synced_at),
        updated_at = now();

  select id into powers_group_id
  from college_planner.degree_requirement_groups
  where code = 'core_powers'
  limit 1;

  select id into literary_group_id
  from college_planner.degree_requirement_groups
  where code = 'core_literary_inquiry'
  limit 1;

  select id into diverse_group_id
  from college_planner.degree_requirement_groups
  where code = 'core_diverse_perspectives'
  limit 1;

  if powers_group_id is null then
    raise exception 'Requirement group core_powers not found';
  end if;
  if literary_group_id is null then
    raise exception 'Requirement group core_literary_inquiry not found';
  end if;
  if diverse_group_id is null then
    raise exception 'Requirement group core_diverse_perspectives not found';
  end if;

  update college_planner.degree_requirement_groups
  set group_logic = 'all',
      min_courses = null,
      min_credits = null,
      rule_config = coalesce(rule_config, '{}'::jsonb)
        || jsonb_build_object(
          'source', 'Journey Core requirement update 2026-07-28',
          'same_semester_recommended', true,
          'same_semester_note', 'LU 1013 and LU 1023 should be taken in the same semester.'
        ),
      updated_at = now()
  where id = powers_group_id;

  delete from college_planner.degree_requirement_options o
  where o.requirement_group_id = powers_group_id
    and not exists (
      select 1
      from college_planner.courses c
      join college_planner.subjects s on s.id = c.subject_id
      where c.id = o.course_id
        and s.university_id = lipscomb_id
        and (
          (s.code = 'LU' and c.course_number = '1013')
          or (s.code = 'LU' and c.course_number = '1023')
        )
    );

  insert into college_planner.degree_requirement_options (
    requirement_group_id,
    option_type,
    label,
    course_id,
    sort_order,
    rule_config
  )
  select
    powers_group_id,
    'course',
    s.code || ' ' || c.course_number || ' ' || c.title,
    c.id,
    case c.course_number when '1013' then 10 else 20 end,
    jsonb_build_object(
      'source', 'Journey Core requirement update 2026-07-28',
      'same_semester_recommended', true,
      'same_semester_note', 'LU 1013 and LU 1023 should be taken in the same semester.'
    )
  from college_planner.courses c
  join college_planner.subjects s on s.id = c.subject_id
  where s.university_id = lipscomb_id
    and s.code = 'LU'
    and c.course_number in ('1013', '1023')
    and not exists (
      select 1
      from college_planner.degree_requirement_options existing
      where existing.requirement_group_id = powers_group_id
        and existing.option_type = 'course'
        and existing.course_id = c.id
    );

  update college_planner.degree_requirement_options o
  set option_type = 'course',
      label = s.code || ' ' || c.course_number || ' ' || c.title,
      course_tag = null,
      min_credits = null,
      min_courses = null,
      sort_order = case c.course_number when '1013' then 10 else 20 end,
      rule_config = coalesce(o.rule_config, '{}'::jsonb)
        || jsonb_build_object(
          'source', 'Journey Core requirement update 2026-07-28',
          'same_semester_recommended', true,
          'same_semester_note', 'LU 1013 and LU 1023 should be taken in the same semester.'
        ),
      updated_at = now()
  from college_planner.courses c
  join college_planner.subjects s on s.id = c.subject_id
  where o.requirement_group_id = powers_group_id
    and o.course_id = c.id
    and s.university_id = lipscomb_id
    and s.code = 'LU'
    and c.course_number in ('1013', '1023');

  update college_planner.degree_requirement_groups
  set group_logic = 'any',
      updated_at = now()
  where id = literary_group_id;

  select id into literary_option_id
  from college_planner.degree_requirement_options
  where requirement_group_id = literary_group_id
    and option_type = 'course_list'
  order by sort_order
  limit 1;

  if literary_option_id is null then
    insert into college_planner.degree_requirement_options (
      requirement_group_id,
      option_type,
      label,
      sort_order,
      rule_config
    )
    values (
      literary_group_id,
      'course_list',
      'Literary Inquiry',
      10,
      jsonb_build_object('source', 'Journey Core requirement update 2026-07-28')
    )
    returning id into literary_option_id;
  else
    update college_planner.degree_requirement_options
    set label = coalesce(label, 'Literary Inquiry'),
        rule_config = coalesce(rule_config, '{}'::jsonb)
          || jsonb_build_object('source', 'Journey Core requirement update 2026-07-28'),
        updated_at = now()
    where id = literary_option_id;
  end if;

  insert into college_planner.requirement_option_courses (requirement_option_id, course_id, sort_order)
  select literary_option_id, c.id, 10
  from college_planner.courses c
  join college_planner.subjects s on s.id = c.subject_id
  where s.university_id = lipscomb_id
    and s.code = 'EN'
    and c.course_number = '2103'
  on conflict (requirement_option_id, course_id) do update
    set sort_order = excluded.sort_order;

  update college_planner.degree_requirement_groups
  set group_logic = 'minimum',
      min_credits = 3.00,
      allow_double_count = true,
      rule_config = coalesce(rule_config, '{}'::jsonb)
        || jsonb_build_object(
          'source', 'Journey Core requirement update 2026-07-28',
          'approved_course_list_canonical', true
        ),
      updated_at = now()
  where id = diverse_group_id;

  select id into diverse_option_id
  from college_planner.degree_requirement_options
  where requirement_group_id = diverse_group_id
    and option_type = 'course_list'
  order by sort_order
  limit 1;

  if diverse_option_id is null then
    select id into diverse_option_id
    from college_planner.degree_requirement_options
    where requirement_group_id = diverse_group_id
    order by case when option_type = 'tag' then 0 else 1 end, sort_order
    limit 1;

    if diverse_option_id is not null then
      delete from college_planner.requirement_option_tags
      where requirement_option_id = diverse_option_id;

      update college_planner.degree_requirement_options
      set option_type = 'course_list',
          label = 'Diverse Perspectives approved courses',
          course_tag = null,
          min_credits = 3.00,
          min_courses = null,
          rule_config = coalesce(rule_config, '{}'::jsonb)
            || jsonb_build_object(
              'source', 'Journey Core requirement update 2026-07-28',
              'approved_course_list_canonical', true,
              'allow_double_count', true,
              'display_title_overrides', jsonb_build_object(
                'EN 2103', 'Literary Inquiry: World Stories at the Nashville Film Festival'
              )
            ),
          updated_at = now()
      where id = diverse_option_id;
    end if;
  end if;

  if diverse_option_id is null then
    insert into college_planner.degree_requirement_options (
      requirement_group_id,
      option_type,
      label,
      min_credits,
      sort_order,
      rule_config
    )
    values (
      diverse_group_id,
      'course_list',
      'Diverse Perspectives approved courses',
      3.00,
      10,
      jsonb_build_object(
        'source', 'Journey Core requirement update 2026-07-28',
        'approved_course_list_canonical', true,
        'allow_double_count', true,
        'display_title_overrides', jsonb_build_object(
          'EN 2103', 'Literary Inquiry: World Stories at the Nashville Film Festival'
        )
      )
    )
    returning id into diverse_option_id;
  end if;

  with approved(subject_code, course_number, sort_order) as (
    values
      ('BY', '3553', 10),
      ('NURS', '3553', 20),
      ('ED', '3343', 30),
      ('EN', '2103', 40),
      ('EN', '2903', 50),
      ('EN', '3063', 60),
      ('ENGR', '3613', 70),
      ('FR', '1114', 80),
      ('FR', '1124', 90),
      ('GE', '1114', 100),
      ('GE', '1124', 110),
      ('ITA', '1114', 120),
      ('ITA', '1124', 130),
      ('KIN', '1303', 140),
      ('KIN', '2013', 150),
      ('LJS', '3533', 160),
      ('ML', '2103', 170),
      ('NURS', '4054', 180),
      ('PO', '3153', 190),
      ('HI', '4053', 200),
      ('PO', '4053', 210),
      ('PS', '3483', 220),
      ('PS', '4613', 230),
      ('SN', '1114', 240),
      ('SN', '1124', 250),
      ('SW', '3133', 260)
  )
  insert into college_planner.requirement_option_courses (requirement_option_id, course_id, sort_order)
  select diverse_option_id, c.id, a.sort_order
  from approved a
  join college_planner.subjects s
    on s.university_id = lipscomb_id
   and s.code = a.subject_code
  join college_planner.courses c
    on c.university_id = lipscomb_id
   and c.subject_id = s.id
   and c.course_number = a.course_number
  on conflict (requirement_option_id, course_id) do update
    set sort_order = excluded.sort_order;
end $$;

commit;
