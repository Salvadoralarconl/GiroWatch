import tempfile
from pathlib import Path
from datetime import datetime,timedelta
import unittest
from unittest.mock import patch
from web_service import WatchStore

class RunStatsTests(unittest.TestCase):
    def test_seven_days_distinct_completed_runs_incremental_and_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); logs=root/'logs'/'SATURDAY';logs.mkdir(parents=True)
            store=WatchStore(root)
            profile={'messages':['BEGIN PROCESS','END PROCESS','activity'], 'labels':['Run_Start','Run_End','Other']}
            for section,value in [('run',profile),('folders',{'path':str(logs.parent),'recursive':True})]:
                store.configure({'action':'save','application':'Daily','section':section,'profile':value})
            today=datetime.now().date()
            for ago,count in [(0,2),(1,1),(4,3),(5,7),(6,4),(7,9)]:
                path=logs/((today-timedelta(days=ago)).strftime('%Y%m%d')+'.log')
                path.write_text('BEGIN PROCESS\nactivity\nEND PROCESS\n'*count,encoding='utf-8')
            store.run_stats.scan_once()
            result=store.run_stats.results()
            self.assertEqual([day['count'] for day in result['days']],[4,7,3,0,0,1,2])
            self.assertEqual(result['today'],2)
            with patch('monitoring_service.classify_lines',side_effect=AssertionError('Unchanged files should not be classified')):
                store.run_stats.scan_once()
            path=logs/(today.strftime('%Y%m%d')+'.log')
            with path.open('a') as file:file.write('BEGIN PROCESS\nactivity\n')
            store.run_stats.scan_once()
            self.assertEqual(store.run_stats.results()['today'],2)
            with path.open('a') as file:file.write('END PROCESS\n')
            store.run_stats.scan_once()
            self.assertEqual(WatchStore(root).run_stats.results()['today'],3)
