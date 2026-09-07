"""Persist scheduler STOPPED details without command overrides or credentials."""
import datetime as dt
import json
from pathlib import Path
import boto3

ACCOUNT = "297464765814"
REGION = "us-west-2"
GROUP = "/ecs/mbop-scheduler-events"
RULE = "mbop-scheduler-stopped-task-diagnostics"
aws = boto3.Session(profile_name="mbop-admin", region_name=REGION)
assert aws.client("sts").get_caller_identity()["Account"] == ACCOUNT
logs, events = aws.client("logs"), aws.client("events")
out = Path("logs/diagnostics") / ("event-logging-config-" + dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ"))
out.mkdir(parents=True)
before = {"log_groups": logs.describe_log_groups(logGroupNamePrefix=GROUP)["logGroups"],
          "resource_policies": logs.describe_resource_policies()["resourcePolicies"]}
try:
    before["rule"] = events.describe_rule(Name=RULE)
    before["targets"] = events.list_targets_by_rule(Rule=RULE)["Targets"]
except events.exceptions.ResourceNotFoundException:
    before["rule"] = None
(out / "before.json").write_text(json.dumps(before, default=str, indent=2))
if not any(row["logGroupName"] == GROUP for row in before["log_groups"]):
    logs.create_log_group(logGroupName=GROUP)
logs.put_retention_policy(logGroupName=GROUP, retentionInDays=30)
rule_arn = f"arn:aws:events:{REGION}:{ACCOUNT}:rule/{RULE}"
log_arn = f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:{GROUP}"
policy = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
    "Principal": {"Service": ["events.amazonaws.com", "delivery.logs.amazonaws.com"]},
    "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
    "Resource": log_arn + ":*"}]}
logs.put_resource_policy(policyName=RULE, policyDocument=json.dumps(policy))
pattern = {"source": ["aws.ecs"], "detail-type": ["ECS Task State Change"],
           "detail": {"clusterArn": [f"arn:aws:ecs:{REGION}:{ACCOUNT}:cluster/mbop-cluster1"],
                      "taskDefinitionArn": [{"prefix": f"arn:aws:ecs:{REGION}:{ACCOUNT}:task-definition/mbop-scheduler-task:"}],
                      "lastStatus": ["STOPPED"]}}
events.put_rule(Name=RULE, EventPattern=json.dumps(pattern), State="ENABLED",
                Description="Persist sanitized scheduler task exits for catalog crash diagnosis")
paths = {"timestamp": "$.time", "task": "$.detail.taskArn", "definition": "$.detail.taskDefinitionArn",
         "exit": "$.detail.containers[0].exitCode", "stopCode": "$.detail.stopCode", "reason": "$.detail.stoppedReason"}
template = '{"timestamp":<timestamp>,"message":"task=<task> definition=<definition> exit=<exit> stopCode=<stopCode> reason=<reason>"}'
result = events.put_targets(Rule=RULE, Targets=[{"Id": "scheduler-exits", "Arn": log_arn,
    "InputTransformer": {"InputPathsMap": paths, "InputTemplate": template}}])
assert result["FailedEntryCount"] == 0, result
(out / "configured.json").write_text(json.dumps({"rule": rule_arn, "log_group": GROUP, "pattern": pattern, "retention_days": 30}, indent=2))
print(json.dumps({"rule": rule_arn, "log_group": GROUP, "backup": str(out)}))
