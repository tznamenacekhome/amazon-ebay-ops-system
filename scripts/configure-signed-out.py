"""Plan/apply the narrowly scoped AWS logout landing-page configuration."""
import argparse
import json

import boto3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(profile_name="mbop-admin", region_name="us-west-2")
    assert session.client("sts").get_caller_identity()["Account"] == "297464765814"
    cognito = session.client("cognito-idp")
    elb = session.client("elbv2")
    pool = "us-west-2_IBxxtQ9xL"
    client_id = "11i581nub6aqvqecjmqddrfj7o"
    listener = "arn:aws:elasticloadbalancing:us-west-2:297464765814:listener/app/mbop-alb/8e84d87a6b73d2a6/e7788b7142dbd3a2"
    target = "arn:aws:elasticloadbalancing:us-west-2:297464765814:targetgroup/mbop-web-tg/fd98cb96dbfae8b1"
    uri = "https://mbop.midnightblueenterprises.com/signed-out"
    client = cognito.describe_user_pool_client(UserPoolId=pool, ClientId=client_id)["UserPoolClient"]
    rules = elb.describe_rules(ListenerArn=listener)["Rules"]
    existing = [r for r in rules if any(c.get("PathPatternConfig", {}).get("Values") == ["/signed-out"] for c in r["Conditions"])]
    occupied = {int(r["Priority"]) for r in rules if r["Priority"] != "default"}
    priority = next(n for n in range(1, 100) if n not in occupied)
    print(json.dumps({"account": "297464765814", "public_path": "/signed-out", "logout_url": uri, "apply": args.apply}))
    if not args.apply:
        return
    if not existing:
        elb.create_rule(ListenerArn=listener, Priority=priority,
                        Conditions=[{"Field": "path-pattern", "PathPatternConfig": {"Values": ["/signed-out"]}}],
                        Actions=[{"Type": "forward", "TargetGroupArn": target}])
    else:
        assert len(existing) == 1 and all(a["Type"] == "forward" for a in existing[0]["Actions"])
        assert existing[0]["Actions"][0].get("TargetGroupArn") == target
    if uri not in client.get("LogoutURLs", []):
        # Preserve every supported existing setting, including OAuth configuration.
        accepted = cognito.meta.service_model.operation_model("UpdateUserPoolClient").input_shape.members
        update = {key: value for key, value in client.items() if key in accepted}
        update.update(UserPoolId=pool, ClientId=client_id, LogoutURLs=[*client.get("LogoutURLs", []), uri])
        cognito.update_user_pool_client(**update)
    verified = cognito.describe_user_pool_client(UserPoolId=pool, ClientId=client_id)["UserPoolClient"]
    assert uri in verified["LogoutURLs"]
    print("Signed-out routing and Cognito logout URL configured.")


if __name__ == "__main__":
    main()
