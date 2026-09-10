import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
from finance_payload_archive import archive_new_snapshot, archive_payload, restore_payload, BUCKET


class FakeS3:
    def __init__(self):
        self.objects = {}
    def put_object(self, **kwargs):
        self.objects[kwargs['Key']] = kwargs['Body']
        assert kwargs['ServerSideEncryption'] == 'AES256'
    def get_object(self, **kwargs):
        return {'Body': io.BytesIO(self.objects[kwargs['Key']])}


class ArchiveTests(unittest.TestCase):
    def test_lossless_and_content_addressed(self):
        s3 = FakeS3()
        value = {'transactions': [{'id': 'test', 'amount': 12.34, 'text': 'café', 'void': None}]}
        ref = archive_payload(s3, value)
        self.assertEqual(restore_payload(s3, ref), value)
        self.assertEqual(archive_payload(s3, value), ref)
        self.assertEqual(len(s3.objects), 1)

    def test_bad_checksum_fails(self):
        s3 = FakeS3()
        ref = archive_payload(s3, {'transactions': []})
        ref['sha256'] = 'bad'
        with self.assertRaises(ValueError):
            restore_payload(s3, ref)

    def test_wrong_destination_rejected(self):
        with self.assertRaises(ValueError):
            archive_payload(FakeS3(), {}, bucket='public-bucket')

    def test_only_raw_transactions_change_and_input_preserved(self):
        original = {'total_amazon_cash': 25, 'raw_financial_event_groups_json': {'inTransitBreakdown': {}},
                    'raw_transactions_json': {'transactions': [1]}}
        with patch.dict(os.environ, {'MBOP_FINANCE_PAYLOAD_ARCHIVE': '1'}):
            actual = archive_new_snapshot(original, s3=FakeS3())
        self.assertEqual(actual['total_amazon_cash'], original['total_amazon_cash'])
        self.assertEqual(actual['raw_financial_event_groups_json'], original['raw_financial_event_groups_json'])
        self.assertEqual(original['raw_transactions_json'], {'transactions': [1]})
        self.assertEqual(actual['raw_transactions_json']['bucket'], BUCKET)

    def test_disabled_preserves_contract(self):
        row = {'raw_transactions_json': {'transactions': [1]}}
        with patch.dict(os.environ, {'MBOP_FINANCE_PAYLOAD_ARCHIVE': '0'}):
            self.assertIs(archive_new_snapshot(row, s3=FakeS3()), row)

    def test_upload_failure_prevents_reference_creation(self):
        s3 = FakeS3()
        s3.get_object = lambda **kwargs: (_ for _ in ()).throw(RuntimeError('unavailable'))
        with self.assertRaises(RuntimeError):
            archive_payload(s3, {'transactions': [1]})


if __name__ == '__main__':
    unittest.main()
