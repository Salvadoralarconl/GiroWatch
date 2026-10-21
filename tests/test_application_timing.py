import unittest
from monitoring_service import record_run_timing


class TimingTests(unittest.TestCase):
    def test_completed_time_without_predicting_next_run(self):
        row={}
        record_run_timing(row,'10/21/2026 11:00:00 AM BEGIN PROCESS','Run_Start')
        record_run_timing(row,'10/21/2026 11:00:03 AM END PROCESS','Run_End')
        self.assertEqual(row['last_completed_at'],'2026-10-21T11:00:03')
        record_run_timing(row,'10/21/2026 11:01:00 AM BEGIN PROCESS','Run_Start')
        self.assertNotIn('next_run_at',row)

    def test_unknown_timestamp_does_not_invent_a_time(self):
        row={}
        record_run_timing(row,'END PROCESS','Run_End')
        self.assertEqual(row,{})

