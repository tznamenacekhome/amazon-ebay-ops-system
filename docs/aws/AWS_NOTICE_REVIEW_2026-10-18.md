# AWS notice review — October 18, 2026

Account verified through STS: `297464765814` (Midnight Blue Cloud).
Scope: the complete 20-notice package supplied from the operator's email review.
No application deployment, maintenance restart, opt-out, permission change,
credential change, billing change, or data mutation was necessary or performed.
Existing uncommitted sourcing work was preserved.

## Cognito: compatible with the announced additive changes

The October 16 notice announces gradual rollout November 4, 2026; optional
temporary opt-out requests are due November 2, with all-pools default February
28, 2027. Existing claims are not renamed, removed, or retyped. New optional
claims include `acr` (string) and `amr` (string array, including a single method).
Discovery may add `acr_values_supported`, `code_challenge_methods_supported`,
and `grant_types_supported`.

Repository inspection found:

- Authentication is handled by the AWS ALB/Cognito integration. MBOP does not
  parse Cognito JWT payloads or OIDC discovery metadata, so it has no strict
  field allowlist or scalar `amr` assumption to change.
- No application JWT verification/JWKS lookup implementation was found. Dynamic
  `kid` lookup and refresh on unknown keys therefore do not require application
  changes. If JWT verification is introduced later, follow the token issuer's
  verification rules; ALB-signed user-info JWTs have a different key source from
  Cognito user-pool JWTs.
- `web/app/api/_server.ts` checks ALB header presence alongside the existing
  same-origin/CSRF gate. Other OIDC header usages read the identity string for
  actor attribution. These paths do not interpret added claims. This review does
  not replace validation of the ALB-only network trust boundary.
- No Cognito-token database columns, fixed token buffers, token slicing, custom
  header size limit, or cookie-size assumption was found in the application.
- `web/app/api/logout/route.ts` expires the base ALB session cookie and shards
  `-0` through `-3`. AWS documents support for up to four shards. The signed-out
  destination is separate from protected application pages.

Disposition: retain current behavior; no compatibility patch or opt-out needed
based on the inspected code. No runtime tests were added for nonexistent claim
parsers. This was a static compatibility review plus read-only infrastructure
inspection, not a post-rollout authentication test. After November 4, verify a
fresh sign-in and logout through the production browser and check the metrics
below. Do not use a local build as production authentication proof.

At 07:55 Pacific October 18, the preceding seven-day CloudWatch query recorded
no `ELBAuthUserClaimsSizeExceeded` or `ELBAuthError` events. It returned 14
`ELBAuthFailure` events; their causes were not established by this review and
they do not demonstrate failure from the future additive rollout. AWS documents
an 11 KB combined IdP claims/access-token limit and the size-exceeded metric;
monitor these during rollout rather than reducing permissions or claims
speculatively.

Sources: [Cognito notice](https://health.aws.amazon.com/health/home?region=us-east-1#/event-log?eventID=arn:aws:health:global::event/COGNITO/AWS_COGNITO_OPERATIONAL_NOTIFICATION/AWS_COGNITO_OPERATIONAL_NOTIFICATION_0033a395c57e7e9743a408e2235d760a76b5844a0af614df24c189a3ad4a7990&eventTab=details&layout=vertical),
[ALB authentication/cookies/logout](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html),
[Cognito discovery compatibility](https://docs.aws.amazon.com/cognito/latest/developerguide/federation-endpoints.html),
[ACR/AMR types](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-step-up-authentication.html).

## Eleven Fargate retirement notices

Current windows are October 16–23 at 19:00 UTC (ARM64) and 21:00 UTC
(DockerLinux), revision `1-4-0-780`. Tasks launched after the corresponding
October 9 times already use the new revision according to the notices.

Direct live verification on October 18:

- `mbop-web-service`: revision `mbop-web-task:187`, deployment `COMPLETED`,
  desired/running 1/1, pending 0, minimum healthy percent 100.
- Web task `1baf4bb0a94244abae897409351be6f5` started October 15 at 19:25
  Pacific and is running. Its ALB target is healthy. Task definition has no
  explicit runtime architecture override (default x86_64); ECS reports platform
  version `1.4.0`, which does not independently expose the patch suffix.
- Two active scheduler tasks using revision 141 started October 18 at 07:50
  and 07:52 Pacific, after the cutoff. These are distinct from the sourcing
  schedule's previously deployed revision 142; no schedule was changed here.
- The shared cluster also contains a College Planner task started October 16.
  No College Planner resource was changed.

AWS Health `DescribeEvents` returned `SubscriptionRequiredException`; affected
entity IDs could not be independently inspected through that API. The supplied
notice package and direct ECS launch/health evidence support no forced restart.
If an individual affected task needs reconciliation, inspect its Affected
Resources tab in the AWS Health console. No operator action is currently
required by the notice itself.

The remaining nine notices are historical maintenance windows, all UTC:

| Window | Revision | Disposition |
| --- | --- | --- |
| October 7–14 19:00, ARM64 | 771 | Elapsed; do not replay maintenance |
| October 7–14 21:00, DockerLinux | 771 | Elapsed; do not replay maintenance |
| September 17–24 20:00 | 769 | Elapsed; do not replay maintenance |
| September 11–18 03:00 | 768 | Elapsed; do not replay maintenance |
| August 27–September 3 00:00 | 764 | Elapsed; do not replay maintenance |
| August 18–25 23:00 | 762 | Elapsed; do not replay maintenance |
| July 28–August 4 02:00 | 759 | Elapsed; do not replay maintenance |
| July 16–23 04:00 | 750 | Elapsed; do not replay maintenance |
| July 7–14 21:00 | 743 | Elapsed; do not replay maintenance |

Sources: [current ARM64 notice](https://health.aws.amazon.com/health/home?region=us-west-2#/event-log?eventID=arn:aws:health:us-west-2::event/ECS/AWS_ECS_TASK_PATCHING_RETIREMENT/AWS_ECS_TASK_PATCHING_RETIREMENT-us-west-2-DockerLinux-ARM64-1-4-0-780-297464765814-MANAGED&eventTab=details&layout=vertical),
[current DockerLinux notice](https://health.aws.amazon.com/health/home?region=us-west-2#/event-log?eventID=arn:aws:health:us-west-2::event/ECS/AWS_ECS_TASK_PATCHING_RETIREMENT/AWS_ECS_TASK_PATCHING_RETIREMENT-us-west-2-DockerLinux-1-4-0-780-297464765814-MANAGED&eventTab=details&layout=vertical).

## Eight billing and informational notices

| Notices | Substance | Disposition |
| --- | --- | --- |
| August 1, September 2, October 2 billing (3) | July $63.83; August $64.75; September $66.13 | Informational automatic-payment notices; none reports payment failure. No payment settings changed. |
| June 19 CloudFront (1) | Free flat-rate plan activated for `E2KKKB5MJ8CV3N` at 23:29:40 UTC | Informational; no plan/distribution change requested. |
| June 19 Fargate (1) | Oregon access validated | Informational; live ECS access now verified. |
| June 19 account plan (2) | Free-plan welcome 16:35 UTC; paid-plan upgrade 16:49 UTC | Paid upgrade supersedes welcome; no further action. |
| June 19 Cost Anomaly Detection (1) | AWS Services monitor and daily summary configured; threshold above $100 and 40% expected spend | Setup confirmation, not an anomaly alert; no change. |

These dispositions describe the supplied notices, not an independent billing
reconciliation. No notice reports an unresolved payment verification step.

Sources: [payment history](https://console.aws.amazon.com/billing/home#/paymenthistory),
[September bill](https://console.aws.amazon.com/billing/home#/bills?year=2026&month=9),
[CloudFront plan](https://us-east-1.console.aws.amazon.com/cloudfront/v4/home#/distributions/E2KKKB5MJ8CV3N?manage-plan=1),
[anomaly monitor](https://console.aws.amazon.com/costmanagement/home#/anomaly-detection/monitors/33700107-b7a0-4b3a-8e94-1c2c0c843f05).

## Result

All 20 notices reviewed. Only this review document was added. No necessary code
or infrastructure update was identified. Remaining verification limits are the
unavailable AWS Health API affected-resource listing and the future Cognito
rollout; no opt-out or payment action is waiting on the operator.
