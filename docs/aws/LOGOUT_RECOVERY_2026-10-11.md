# Logout and sourcing freshness correction

The logout handler previously returned to the protected homepage. Cognito clears
its session but does not sign out the Google identity provider; returning to the
homepage immediately starts authentication again. The new destination is a
public, static `/signed-out` page with an explicit Sign in link. The application
shell does not load notifications on that page.

Deploy the web change and configure only the signed-out path as public:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/aws-login.ps1
powershell -ExecutionPolicy Bypass -File scripts/deploy-web.ps1 -AllowDirty
.\.venv\Scripts\python.exe scripts/configure-signed-out.py
.\.venv\Scripts\python.exe scripts/configure-signed-out.py --apply
powershell -ExecutionPolicy Bypass -File scripts/aws-web-status.ps1
```

The configuration helper verifies account 297464765814, preserves existing
Cognito client settings, adds the allowed sign-out URL, and forwards exactly
`/signed-out` without authentication. Operational pages keep their existing
Cognito protection. Run the helper again safely if configuration is interrupted.

Verify through the production browser: click Log out, confirm the signed-out
page remains visible without an automatic login, then click Sign in. Inspect
cookie removal and confirm protected pages still require authentication.

Live database and scheduler inspection on October 11 confirmed coverage cycle
90 last advanced October 9. Both weekend scheduler runs completed successfully;
the October 7 commit had added `--skip-weekends`. The operator confirmed that
sourcing must run every day, so that flag and the weekend early return have been
removed. Coverage labels now describe the last run's
calls, quota, and recorded reset instead of implying current-day quota.

Local TypeScript checking and the Docker production build passed. Docker was
recovered by restarting Desktop. Scheduler revision 142 is digest-pinned to
`sha256:6e44b6f748389ccebe7e5fc4408ee7b30f8166bf648cdd15dadfece76c585e82`;
only `mbop-sourcing-catalog` was retargeted. Its ECS `--list` smoke test exited 0
and listed discovery without the weekend flag.

Web revision 186 uses digest
`sha256:804270f5790e51ab41f967f59815bd56e606e51291ef18db08d515cb7a6084bf`.
The exact `/signed-out` ALB forward rule and Cognito allowed logout URL were
applied with `scripts/configure-signed-out.py --apply`. Browser automation still
fails to initialize; authenticated logout-click verification remains outstanding.
AWS `ecs wait services-stable` succeeded, the new target is healthy, and a
public production HTTP read of `/signed-out` returned 200 with the expected
landing text. These checks do not replace authenticated browser verification.

One manual sourcing task was launched at about 9:09 PM Pacific October 11:
`9aafa8cf4d104762b669ede474511d70`, scheduler run
`b433597c-8419-4a32-8509-6478efbffbce`. It runs
`python run_all_syncs.py --group sourcing-catalog` using the live schedule's
CPU/memory and networking. Preflight found no recent active sourcing run;
database capacity and the production database guard both passed. Startup
verification does not establish completed-run success.
The new discovery record is `d2a1c789-88db-477d-9a15-6cf699dc407c`, started
at 9:11 PM Pacific with all 5,000 Browse calls available and status `running`.

Deploy the scheduler correction separately using its existing production base:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy-scheduler.ps1 -BaseTaskDefinition mbop-scheduler-task:141 -ScheduleNamePrefix mbop-sourcing-catalog -AllowDirty
```

The AWS schedule remains daily at 12:10 AM America/Los_Angeles. The scheduler
image has been deployed so production no longer skips weekends. Regression
tests cover both weekend discovery executions and the sourcing group command.
