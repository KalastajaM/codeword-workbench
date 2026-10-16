"""Bounded, in-memory solver jobs with cooperative cancellation.

The supplied runner owns solving. This registry owns job lifetime, progress,
capacity release and shutdown. No puzzle data is written to disk.
"""
import threading
import time
import traceback
import uuid


class JobCapacityError(Exception):
    pass


class SolveJobs:
    def __init__(self, runner, capacity, max_retained=16, retention_seconds=600):
        self.runner = runner
        self.capacity = capacity
        self.max_retained = max_retained
        self.retention_seconds = retention_seconds
        self.lock = threading.Lock()
        self.jobs = {}
        self.closed = False

    def _prune(self):
        now = time.monotonic()
        finished = sorted((job for job in self.jobs.values() if job['status'] != 'running'),
                          key=lambda job: job['finished'])
        for job in finished:
            if now-job['finished'] > self.retention_seconds or len(self.jobs) >= self.max_retained:
                del self.jobs[job['id']]

    def start(self, puzzle, capacity=None, runner=None):
        """Capacity and runner default to the registry's; callers may narrow them per request."""
        capacity = capacity or self.capacity
        with self.lock:
            self._prune()
            if self.closed or len(self.jobs) >= self.max_retained or not capacity.acquire(blocking=False):
                raise JobCapacityError('Another solve or recognition is running. Try again shortly.')
            key = uuid.uuid4().hex
            job = dict(id=key, status='running', started=time.monotonic(), cancel=threading.Event(),
                       capacity=capacity, runner=runner or self.runner,
                       progress=dict(stage='preparing', nodes=0, elapsedSeconds=0, solutionsFound=0))
            self.jobs[key] = job
            # Avoid retaining source images or previous solve results in the worker.
            request = {k:v for k,v in puzzle.items() if k not in ('image','suggestions')}
            job['thread'] = threading.Thread(target=self._run, args=(job,request), daemon=True)
            try:
                job['thread'].start()
            except Exception:
                del self.jobs[key]
                capacity.release()
                raise
            return self._snapshot(job)

    def _run(self, job, puzzle):
        def progress(update):
            with self.lock:
                job['progress'].update(update)
        outcome = {}
        try:
            result = job['runner'](puzzle, cancel=job['cancel'].is_set, progress=progress)
            outcome['result'] = result
        except Exception:
            traceback.print_exc()
            outcome['error'] = 'The local solver could not complete the search. See its terminal output.'
        finally:
            # Publication and capacity release are atomic to polling clients.
            with self.lock:
                result = outcome.get('result')
                if result is not None:
                    cancelled = job['cancel'].is_set() or result.get('status') == 'cancelled'
                    if cancelled:
                        result = dict(result, status='cancelled')
                        result['stats'] = dict(result.get('stats',{}), exhaustive=False, stopReason='cancelled')
                    job.update(status='cancelled' if cancelled else 'completed', result=result)
                else:
                    job.update(status='failed', error=outcome.get('error','The local search stopped unexpectedly.'))
                job['finished'] = time.monotonic()
                job['progress'].update(stage=job['status'],
                                       elapsedSeconds=round(job['finished']-job['started'],3),
                                       solutionsFound=len((result or {}).get('solutions',[])))
                job['capacity'].release()

    def _snapshot(self, job):
        snapshot = {k:job[k] for k in ('id','status','result','error') if k in job}
        snapshot['progress'] = dict(job['progress'])
        if job['status'] == 'running':
            snapshot['progress']['elapsedSeconds'] = round(time.monotonic()-job['started'],3)
        snapshot['cancelRequested'] = job['cancel'].is_set()
        return snapshot

    def get(self, key, cancel=False):
        with self.lock:
            self._prune()
            job = self.jobs.get(key)
            if job is None:
                raise FileNotFoundError('Search job expired or does not exist.')
            if cancel and job['status'] == 'running':
                job['cancel'].set()
            return self._snapshot(job)

    def close(self):
        with self.lock:
            self.closed = True
            active = [job for job in self.jobs.values() if job['status'] == 'running']
            for job in active:
                job['cancel'].set()
        for job in active:
            job['thread'].join(timeout=2)
