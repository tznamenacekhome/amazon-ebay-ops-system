"""Create private, versioned MBOP finance archive and narrowly grant worker access."""
import json
import sys
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integrations'))
from finance_payload_archive import ACCOUNT_ID, BUCKET, PREFIX

session = boto3.Session(profile_name='mbop-admin', region_name='us-west-2')
assert session.client('sts').get_caller_identity()['Account'] == ACCOUNT_ID
s3 = session.client('s3')
try:
    s3.head_bucket(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID)
except ClientError as exc:
    if exc.response['Error']['Code'] not in ('404', 'NoSuchBucket'):
        raise
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={'LocationConstraint': 'us-west-2'},
                     ObjectOwnership='BucketOwnerEnforced')
s3.put_public_access_block(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID,
    PublicAccessBlockConfiguration=dict(BlockPublicAcls=True, IgnorePublicAcls=True,
                                         BlockPublicPolicy=True, RestrictPublicBuckets=True))
s3.put_bucket_versioning(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID,
                         VersioningConfiguration={'Status': 'Enabled'})
s3.put_bucket_encryption(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID,
    ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault':
                                                 {'SSEAlgorithm': 'AES256'}}]})
s3.put_bucket_policy(Bucket=BUCKET, ExpectedBucketOwner=ACCOUNT_ID, Policy=json.dumps({
    'Version': '2012-10-17', 'Statement': [{'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
    'Resource': [f'arn:aws:s3:::{BUCKET}', f'arn:aws:s3:::{BUCKET}/*'],
    'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}))
session.client('iam').put_role_policy(RoleName='mbop-scheduler-task-role',
    PolicyName='MBOPFinancePayloadArchive', PolicyDocument=json.dumps({
        'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
        'Action': ['s3:PutObject', 's3:GetObject'],
        'Resource': f'arn:aws:s3:::{BUCKET}/{PREFIX}*'}]}))
print(json.dumps({'bucket': BUCKET, 'private': True, 'versioning': 'Enabled',
                  'worker_prefix': PREFIX, 'delete_permission': False}))
