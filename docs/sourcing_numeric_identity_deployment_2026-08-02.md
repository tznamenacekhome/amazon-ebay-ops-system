# Sourcing Numeric Identity Deployment

Date: 2026-08-02

Scope: review the remaining context-aware numeric identity positive conflicts
and deploy only the already-completed sourcing presentation gate plus the
context-aware numeric identity matcher. No new matching rules were added.

## Final Positive Conflict Review

The revised numeric matcher left 4 positive-status conflicts from the
read-only audit:

| ASIN | Amazon title | eBay title | Evidence strength | Finding |
| --- | --- | --- | --- | --- |
| `B003RS8I92` | `Rock Band 3 [video game]` | `Rock Band (Sony PlayStation 3, PS3) New Sealed In Box` | Purchased/matched, not receiving-confirmed | Safe block. eBay identifies base `Rock Band`, not `Rock Band 3`. |
| `B003RS8I92` | `Rock Band 3 [video game]` | `Rock Band Game PS3 Brand New & Factory Sealed-PlayStation 3 Rare Harmonix` | Purchased/matched, not receiving-confirmed | Safe block. eBay identifies base `Rock Band`, not `Rock Band 3`. |
| `B00D8S4GRY` | `Just Dance 2014 - PlayStation 4 [video game]` | `NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 )` | Purchased/matched, not receiving-confirmed | Safe block. eBay title and item-specific Game Name identify `Just Dance 2015`; `2014` appears as release-year metadata. |
| `B00D8S4GRY` | `Just Dance 2014 - PlayStation 4 [video game]` | `NEW Just Dance 2015 ( Sony Playstation 4, PS4, 2014 )` | Purchase-item positive, not received/listed/sold | Weak positive evidence. Treat as a likely historical mis-match until receiving/listing/sale evidence proves otherwise. |

Post-deployment operator review confirmed all 4 rows were historical purchase
mistakes rather than valid matches. They are not numeric false-positive
validation failures and should be retained as negative identity training
examples.

Conclusion: deployment was acceptable without treating these rows as blocker
false positives.

## What Is Being Deployed

- Presentation gate from commit `7ef2b65`:
  - batch insertion rejects stale `open` opportunities with stored hard-block
    diagnostics
  - default opportunities API visibility path filters stored hard blocks
- Context-aware numeric identity matcher:
  - classifies numeric tokens before comparison
  - hard-blocks recognized annual/installment identity conflicts
  - ignores platform numbers, release years, quantities/lots, included-content
    amounts, and anniversary numbers for hard-block purposes
  - keeps ambiguous numeric disagreement out of hard-block status

## Validation

Commands run before deployment:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sourcing_match_rules tests.test_ebay_sourcing_search tests.test_sourcing_progressive_batches
.\.venv\Scripts\python.exe -m py_compile integrations\sourcing_match_rules.py integrations\score_sourcing_opportunities.py integrations\ebay_sourcing_search.py integrations\run_sourcing_workflow.py integrations\analyze_sourcing_positive_match_safety.py integrations\analyze_recent_sourcing_dismissals.py
Set-Location C:\Dev\amazon-ebay-ops-system\web; npm.cmd run build
```

Results:

- Python regression tests: 75 passed.
- Python compile check: passed.
- Next.js production build: passed.

Read-only production validation from the sprint:

- Authoritative confirmed positives reviewed: 2,306.
- Old strict numeric positive conflicts: 511 baseline; 520 on the current data.
- Revised numeric positive conflicts: 4 weak/likely incorrect positives.
- Latest 1,000 dismissals newly covered by revised numeric identity: 55.
- Current open opportunities affected: 0 of 33.

## Deployment Details

Status: deployed.

- Commit deployed: `79653afe852c`
- Image tag: `web-79653afe852c`
- ECR image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:b77942af183d1240484914ede504120eef94eca5007e19ac8079180ebd4f1459`
- ECS cluster: `mbop-cluster1`
- ECS service: `mbop-web-service`
- ECS task definition: `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-web-task:99`
- Desired/running/pending tasks after deployment: `1 / 1 / 0`
- Rollout state: `COMPLETED`
- Build environment:
  - `MBOP_BUILD_SHA=79653afe852c`
  - `NEXT_PUBLIC_MBOP_BUILD_SHA=79653afe852c`
- Production URL: `https://mbop.midnightblueenterprises.com`
- Production HTTPS check: root URL returned `302`, expected for the protected
  application entrypoint.

Deployment commands:

```powershell
.\scripts\deploy-web.ps1
.\scripts\aws-web-status.ps1
```

## Post-Deployment Training Update

The 4 operator-confirmed mistakes were seeded into
`matching_intelligence_examples` as `non_match` / `negative_identity` examples
with `dismiss_reason = wrong_edition_version`.

Seed command:

```powershell
.\.venv\Scripts\python.exe integrations\seed_numeric_identity_review_negatives.py --write
```

The seed uses source table `operator_positive_conflict_review` so future
matching-intelligence rebuilds do not erase the reviewed examples.

## Remaining Risks

- The deployment changes future scoring and presentation behavior, but it does
  not rescore existing opportunities. A separate operator-approved rescore is
  required to rewrite stored diagnostics for existing rows.
- Existing positive examples from the historical mistakes may still exist from
  purchase/action history. Scoring will now also have exact negative memory for
  the same ASIN/eBay keys.
- Numeric family coverage remains deliberately conservative; additional
  franchises should be added only with positive-safety review and fixtures.
