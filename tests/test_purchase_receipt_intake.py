import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.purchase_receipt_intake import extract_receipt, response_payload, validate_document


class ReceiptExtraction(unittest.TestCase):
    def test_pdf_and_clipboard_image_use_correct_inputs_and_no_response_storage(self):
        pdf = response_payload(b'%PDF-1.7 test', 'application/pdf', 'gpt-6-luna')
        image = response_payload(b'\x89PNG\r\n\x1a\ntest', 'image/png', 'gpt-6-luna')
        self.assertEqual(pdf['input'][1]['content'][0]['type'], 'input_file')
        self.assertEqual(image['input'][1]['content'][0]['type'], 'input_image')
        self.assertFalse(pdf['store'])
        self.assertTrue(pdf['text']['format']['strict'])
        self.assertNotIn('asin', pdf['text']['format']['schema']['properties']['items']['items']['properties'])

    def test_invalid_type_empty_and_oversize_are_rejected(self):
        for data, mime in [(b'<html>invoice', 'application/pdf'), (b'', 'image/png'), (b'x' * (12 * 1024 * 1024 + 1), 'image/jpeg')]:
            with self.assertRaises(ValueError): validate_document(data, mime)

    def test_transient_retry_then_structured_extraction_preserves_unknowns(self):
        receipt = {'supplier': 'Eastern Leaf', 'tax': None, 'items': [{'title': 'Tilly Tacker', 'quantity': 20, 'line_total': None}]}
        post = Mock(side_effect=[Mock(status_code=429), Mock(status_code=200, json=lambda: {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': json.dumps(receipt)}]}]})])
        sleep = Mock()
        result = extract_receipt(b'%PDF-test', 'application/pdf', 'test-secret', 'gpt-6-luna', post, sleep)
        self.assertIsNone(result['tax']); self.assertIsNone(result['items'][0]['line_total'])
        self.assertEqual(post.call_count, 2); sleep.assert_called_once()

    def test_auth_failure_does_not_expose_provider_payload(self):
        post = Mock(return_value=Mock(status_code=401, text='sensitive provider body'))
        with self.assertRaisesRegex(RuntimeError, 'HTTP 401') as error:
            extract_receipt(b'%PDF-test', 'application/pdf', 'secret', 'gpt-6-luna', post)
        self.assertNotIn('sensitive', str(error.exception))

    def test_incomplete_and_refused_results_cannot_become_review_data(self):
        for response in [{'status': 'incomplete'}, {'status': 'completed', 'output': [{'content': [{'type': 'refusal'}]}]}]:
            post = Mock(return_value=Mock(status_code=200, json=lambda: response))
            with self.assertRaises(RuntimeError): extract_receipt(b'%PDF-test', 'application/pdf', 'secret', 'gpt-6-luna', post)


if __name__ == '__main__': unittest.main()
