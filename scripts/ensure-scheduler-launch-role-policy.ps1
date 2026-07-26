param(
  [string]$Profile = "mbop-admin",
  [string]$Region = "us-west-2",
  [string]$LaunchRoleName = "mbopEventBridgeSchedulerEcsRole",
  [string]$PolicyName = "mbop-scheduler-run-task",
  [string]$AccountId = "297464765814",
  [string]$ClusterName = "mbop-cluster1",
  [string]$TaskDefinitionFamily = "mbop-scheduler-task",
  [string]$ExecutionRoleName = "ecsTaskExecutionRole",
  [string]$TaskRoleName = "mbop-scheduler-task-role"
)

$ErrorActionPreference = "Stop"

$clusterArn = "arn:aws:ecs:${Region}:${AccountId}:cluster/${ClusterName}"
$taskDefinitionArn = "arn:aws:ecs:${Region}:${AccountId}:task-definition/${TaskDefinitionFamily}:*"
$executionRoleArn = "arn:aws:iam::${AccountId}:role/${ExecutionRoleName}"
$taskRoleArn = "arn:aws:iam::${AccountId}:role/${TaskRoleName}"

aws sts get-caller-identity --profile $Profile --output json | Out-Null

$policy = @{
  Version = "2012-10-17"
  Statement = @(
    @{
      Sid = "AllowRunMbopSchedulerTask"
      Effect = "Allow"
      Action = @("ecs:RunTask")
      Resource = $taskDefinitionArn
      Condition = @{
        ArnEquals = @{
          "ecs:cluster" = $clusterArn
        }
      }
    },
    @{
      Sid = "AllowPassSchedulerRoles"
      Effect = "Allow"
      Action = "iam:PassRole"
      Resource = @($executionRoleArn, $taskRoleArn)
      Condition = @{
        StringEquals = @{
          "iam:PassedToService" = "ecs-tasks.amazonaws.com"
        }
      }
    }
  )
}

$policyFile = Join-Path ([System.IO.Path]::GetTempPath()) "mbop-scheduler-launch-role-policy.json"
$policy | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $policyFile -Encoding ascii

aws iam put-role-policy `
  --profile $Profile `
  --role-name $LaunchRoleName `
  --policy-name $PolicyName `
  --policy-document "file://$policyFile" | Out-Null

Write-Host "Updated $LaunchRoleName/$PolicyName" -ForegroundColor Green
Write-Host "RunTask:  $taskDefinitionArn"
Write-Host "PassRole: $executionRoleArn"
Write-Host "PassRole: $taskRoleArn"
