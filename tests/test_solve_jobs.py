"""Real HTTP checks for solver jobs, option validation, and full-grid morphology."""
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from app.server import make_server, check_puzzle


def puzzle(**options):
    return dict(name='Job fixture', rows=1, cols=3, language='en', useDictionary=True,
                cells=[dict(black=False,number=str(i+1),letter='C' if i==0 else '') for i in range(3)],
                **options)


class SolveOptionsTests(unittest.TestCase):
    def test_extended_option_survives_validation_and_storage(self):
        from app.server import PuzzleStore
        p = puzzle(searchMode='extended')
        check_puzzle(p)
        with tempfile.TemporaryDirectory() as folder:
            store = PuzzleStore(folder)
            saved = store.save(p)
            self.assertEqual(store.get(saved['id'])['searchMode'], 'extended')

    def test_bad_search_options_are_rejected(self):
        for key, value in [('searchMode','unlimited'),('searchMode',[]),('allowUnknownWords','yes')]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                check_puzzle(puzzle(**{key:value}))


class SolveJobsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=make_server(0,self.temp.name)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self,path,body=None,method=None,headers=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.request(method or ('POST' if body is not None else 'GET'),path,
                     json.dumps(body) if body is not None else None,
                     {'Content-Type':'application/json',**(headers or {})})
        response=conn.getresponse(); result=(response.status,json.loads(response.read()));conn.close()
        return result

    def terminal(self,route):
        until=time.monotonic()+5
        while time.monotonic()<until:
            code,job=self.request(route)
            self.assertEqual(code,200)
            if job['status']!='running': return job
            time.sleep(.02)
        self.fail('Job did not finish promptly')

    def test_job_returns_real_solver_result_and_progress(self):
        code,job=self.request('/api/solve-jobs',puzzle())
        self.assertEqual(code,202)
        result=self.terminal('/api/solve-jobs/'+job['id'])
        self.assertEqual(result['status'],'completed')
        self.assertTrue(result['result']['solutions'])
        self.assertTrue(all(s['letters'][0]=='C' for s in result['result']['solutions']))
        self.assertIn('elapsedSeconds',result['progress'])

    def test_extended_job_uses_five_minute_budget_and_reports_completion(self):
        code, job = self.request('/api/solve-jobs', puzzle(searchMode='extended'))
        self.assertEqual(code, 202)
        result = self.terminal('/api/solve-jobs/' + job['id'])['result']
        self.assertEqual(result['stats']['timeLimitSeconds'], 300)
        self.assertEqual(result['stats']['searchMode'], 'extended')
        self.assertIn(result['stats']['stopReason'], ('search_exhausted', 'solution_limit'))
        self.assertTrue(result['solutions'])

    def test_deep_job_cancel_stops_work_and_allows_next_job(self):
        p=puzzle(searchMode='deep');p['useDictionary']=False
        p.update(rows=20,cols=20,cells=[dict(black=False,number=str(i%26+1),letter='') for i in range(400)])
        code,first=self.request('/api/solve-jobs',p)
        self.assertEqual(code,202)
        route='/api/solve-jobs/'+first['id']
        code,_=self.request(route,method='DELETE')
        self.assertEqual(code,200)
        job=self.terminal(route)
        self.assertEqual(job['status'],'cancelled')
        self.assertEqual(job['result']['status'],'cancelled')
        code,next_job=self.request('/api/solve-jobs',puzzle())
        self.assertEqual(code,202)
        self.assertEqual(self.terminal('/api/solve-jobs/'+next_job['id'])['status'],'completed')

    def test_bad_options_and_foreign_cancellation_are_rejected(self):
        code,_=self.request('/api/solve-jobs',puzzle(searchMode='forever'))
        self.assertEqual(code,400)
        code,_=self.request('/api/solve-jobs',puzzle(),headers={'Origin':'https://example.com'})
        self.assertEqual(code,403)
        code,job=self.request('/api/solve-jobs',puzzle())
        self.assertEqual(code,202)
        route='/api/solve-jobs/'+job['id']
        code,_=self.request(route,method='DELETE',headers={'Origin':'https://example.com'})
        self.assertEqual(code,403)
        self.terminal(route)
        code,_=self.request('/api/solve-jobs/'+'a'*32)
        self.assertEqual(code,404)

    def test_full_grid_morphology_and_toggle_for_sync_and_jobs(self):
        folder=Path(self.temp.name)/'morphology';folder.mkdir()
        with sqlite3.connect(folder/'fi.sqlite') as db:
            db.execute('CREATE TABLE forms(word,length,pattern,lemma,analysis,source)')
            db.execute('INSERT INTO forms VALUES(?,?,?,?,?,?)',('TALOJEN',7,'0.1.2.3.4.5.6','talo','[NUM=PL][CASE=GEN]','test morphology'))
        self.request('/api/dictionaries/fi',{'words':['KISSA']},method='PUT')
        p=puzzle();p.update(language='fi',cols=7,cells=[dict(black=False,number=str(i+1),letter=c if c!='?' else '') for i,c in enumerate('TALO?EN')])
        code,result=self.request('/api/solve',p)
        self.assertEqual(code,200)
        self.assertTrue(result['solutions'])
        self.assertEqual(''.join(result['solutions'][0]['letters']),'TALOJEN')
        code,job=self.request('/api/solve-jobs',p)
        self.assertEqual(code,202)
        result=self.terminal('/api/solve-jobs/'+job['id'])['result']
        self.assertEqual(''.join(result['solutions'][0]['letters']),'TALOJEN')
        p['useMorphology']=False
        _,result=self.request('/api/solve',p)
        self.assertFalse(result['solutions'])

class RegistryTests(unittest.TestCase):
    def test_cancellation_keeps_best_result_and_overrides_completed_stop_reason(self):
        from app.solve_jobs import SolveJobs
        ready = threading.Event()
        release = threading.Event()
        def work(p, cancel, progress):
            ready.set()
            release.wait(2)
            # Simulate a cancel arriving as the solver returns its last result.
            return dict(status='solutions_found', solutions=[dict(letters=['C','A','T'], score=1)],
                        partialLetters=['C','A',''], diagnostics=[],
                        stats=dict(exhaustive=True, stopReason='search_exhausted'))
        jobs = SolveJobs(work, threading.BoundedSemaphore(1))
        try:
            started = jobs.start({})
            self.assertTrue(ready.wait(1))
            jobs.get(started['id'], cancel=True)
            release.set()
            deadline = time.monotonic() + 2
            while jobs.get(started['id'])['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.001)
            job = jobs.get(started['id'])
            self.assertEqual(job['status'], 'cancelled')
            self.assertEqual(job['result']['stats']['stopReason'], 'cancelled')
            self.assertFalse(job['result']['stats']['exhaustive'])
            self.assertEqual(job['result']['solutions'][0]['letters'], ['C','A','T'])
            self.assertEqual(job['result']['partialLetters'], ['C','A',''])
        finally:
            release.set()
            jobs.close()

    def test_capacity_cancellation_and_retention(self):
        from app.solve_jobs import SolveJobs, JobCapacityError
        def work(p, cancel, progress):
            progress({'stage':'search','nodes':7})
            while not cancel():
                time.sleep(.001)
            return dict(status='cancelled',solutions=[],stats={},diagnostics=[])
        capacity=threading.BoundedSemaphore(1)
        jobs=SolveJobs(work,capacity,max_retained=2)
        try:
            first=jobs.start({})
            with self.assertRaises(JobCapacityError): jobs.start({})
            jobs.get(first['id'],cancel=True)
            deadline=time.monotonic()+2
            while jobs.get(first['id'])['status']=='running' and time.monotonic()<deadline:time.sleep(.001)
            self.assertEqual(jobs.get(first['id'])['status'],'cancelled')
            second=jobs.start({})
            jobs.get(second['id'],cancel=True)
            while jobs.get(second['id'])['status']=='running' and time.monotonic()<deadline:time.sleep(.001)
            third=jobs.start({})
            with self.assertRaises(FileNotFoundError):jobs.get(first['id'])
            self.assertEqual(jobs.get(third['id'])['status'],'running')
        finally:jobs.close()
        self.assertTrue(capacity.acquire(blocking=False))
        capacity.release()

    def test_worker_failure_releases_capacity_and_reports_failure(self):
        from app.solve_jobs import SolveJobs
        from contextlib import redirect_stderr
        import io
        def fail(p, **options): raise RuntimeError('controlled worker failure')
        capacity=threading.BoundedSemaphore(1)
        jobs=SolveJobs(fail,capacity)
        try:
            with redirect_stderr(io.StringIO()):
                first=jobs.start({})
                deadline=time.monotonic()+2
                while jobs.get(first['id'])['status']=='running' and time.monotonic()<deadline:time.sleep(.001)
            result=jobs.get(first['id'])
            self.assertEqual(result['status'],'failed')
            self.assertIn('error',result)
            self.assertTrue(capacity.acquire(blocking=False));capacity.release()
        finally:jobs.close()
