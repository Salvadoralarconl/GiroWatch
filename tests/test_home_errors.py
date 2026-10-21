import unittest
from home_errors import build_incidents

class HomeErrorTests(unittest.TestCase):
    def test_later_clean_completed_run_resolves_prior_errors_only(self):
        lines=['10/17/2026 09:00:00 AM BEGIN','10/17/2026 09:00:01 AM FAIL','END',
               'BEGIN','WARN','END','BEGIN','IGNORE','END','BEGIN','FAIL']
        labels=['Run_Start','Other','Run_End','Run_Start','Other','Run_End','Run_Start','Other','Run_End','Run_Start','Other']
        findings=[[],[{'alert':True,'severity':'Critical','message':'Failure'}],[],[],
                  [{'alert':True,'severity':'Warning','message':'Retry'}],[],[],[],[],[],
                  [{'alert':True,'severity':'Critical','message':'Failure'}]]
        rows=build_incidents('Cam','SATURDAY/20261017.log',lines,labels,findings)
        self.assertEqual([r['status'] for r in rows],['Resolved','Resolved','Active'])
        self.assertEqual([r['severity'] for r in rows],['Error','Warning','Error'])
        self.assertEqual(rows[0]['context'],lines[:3])
        pending=build_incidents('Cam','today.log',lines[:7],labels[:7],findings[:7])
        self.assertEqual([r['status'] for r in pending],['Active','Active'])
        self.assertEqual(build_incidents('Other','today.log',['BEGIN','END'],['Run_Start','Run_End'],[[],[]]),[])

    def test_errors_outside_a_run_are_retained_and_clean_run_can_resolve_them(self):
        finding={'alert':True,'severity':'Warning','message':'File locked'}
        rows=build_incidents('Cam','today.log',['10/17/2026 08:40:00 AM lock','stack','BEGIN','END'],
                             ['Other','Other','Run_Start','Run_End'],[[finding],[],[],[]])
        self.assertEqual(rows[0]['status'],'Resolved')
        self.assertEqual(rows[0]['context'],['10/17/2026 08:40:00 AM lock','stack'])

    def test_incremental_today_scan_survives_restart_and_excludes_yesterday(self):
        import tempfile
        from pathlib import Path
        from datetime import datetime,timedelta
        from unittest.mock import patch
        from web_service import WatchStore
        from monitoring_service import classifier_for
        with tempfile.TemporaryDirectory() as temp:
            store=WatchStore(Path(temp))
            profile={'messages':['BEGIN PROCESS','END PROCESS','FAIL request','ordinary work'],
                     'labels':['Run_Start','Run_End','Other','Other']}
            rules=[{'match':'FAIL','severity':'Critical','message':'Request failed'}]
            store.configure({'action':'save','application':'Test','section':'run','profile':profile})
            today=datetime.now().strftime('%Y%m%d')+'.log'
            path=Path(temp)/today
            path.write_text('BEGIN PROCESS\nFAIL request\nEND PROCESS\n',encoding='utf-8')
            classifier=classifier_for(profile)
            store.home_errors.update('Test',path,today,profile,rules,classifier)
            self.assertEqual(store.home_errors.results()['incidents'][0]['status'],'Active')
            with patch('monitoring_service.classify_lines',side_effect=AssertionError('Unchanged files must not be reclassified')):
                store.home_errors.update('Test',path,today,profile,rules,classifier)
            path.write_text(path.read_text()+'BEGIN PROCESS\nordinary work\n',encoding='utf-8')
            store.home_errors.update('Test',path,today,profile,rules,classifier)
            self.assertEqual(store.home_errors.results()['incidents'][0]['status'],'Active')
            with path.open('a') as file: file.write('END PROCESS\n')
            store.home_errors.update('Test',path,today,profile,rules,classifier)
            reloaded=WatchStore(Path(temp)).home_errors.results()['incidents']
            self.assertEqual(len(reloaded),1)
            self.assertEqual(reloaded[0]['status'],'Resolved')
            self.assertEqual(store.home_errors.results(reloaded[0]['id'])['incident']['context'],['BEGIN PROCESS','FAIL request','END PROCESS'])
            yesterday=(datetime.now()-timedelta(days=1)).strftime('%Y%m%d')+'.log'
            store.home_errors.update('Test',path,yesterday,profile,rules,classifier)
            self.assertEqual(len(store.home_errors.results()['incidents']),1)

    def test_same_error_within_sixty_seconds_merges_without_hiding_other_errors(self):
        from home_errors import merge_incidents
        def row(identifier,stamp,app='Cam',match='LOCK',status='Resolved'):
            return {'id':identifier,'application':app,'filename':'today.log','time':'2026-10-17T'+stamp,
                    'line_number':int(identifier),'severity':'Warning','message':'Log locked','match':match,
                    'status':status,'line':identifier,'context':['original '+identifier]}
        rows=[row('1','08:40:33'),row('2','08:40:34',status='Active'),row('3','08:41:34'),
              row('4','08:40:35',match='OTHER'),row('5','08:40:35',app='Other')]
        result=merge_incidents(rows)
        self.assertEqual(len(result),4)
        merged=next(item for item in result if item['id']=='1')
        self.assertEqual(merged['occurrence_count'],2)
        self.assertEqual(merged['status'],'Active')
        self.assertEqual(merged['time'],'2026-10-17T08:40:34')
        self.assertIn('original 1',merged['context'])
        self.assertIn('original 2',merged['context'])
        self.assertEqual(len(merged['occurrences']),2)
        self.assertNotIn('occurrences',rows[0])
