import json
import unittest
from datetime import datetime,timezone
from decimal import Decimal
from sourcing_phase3_refresh import exact_json,calendar_window

class RefreshTransportTests(unittest.TestCase):
    def test_exact_decimal_transport(self):
        value={'x':Decimal('12345678901234567890.123456789'),'zero':Decimal('-0.00'),'null':None,'bool':False}
        self.assertEqual(value,json.loads(exact_json(value),parse_float=Decimal))

    def test_calendar_window(self):
        window=calendar_window(datetime(2026,9,14,6,tzinfo=timezone.utc))
        self.assertEqual('2026-08-15T07:00:00+00:00',window['startInclusive'])
        self.assertEqual(30,window['calendarDays'])

    def test_nonfinite_rejected(self):
        for value in [float('nan'),Decimal('Infinity')]:
            with self.assertRaises(ValueError):exact_json(value)
