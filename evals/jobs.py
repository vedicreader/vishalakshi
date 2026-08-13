"""Does the queue actually deliver each job once, under real processes and real kills.

The claim in `jobs.Queue.claim` is that concurrent callers get disjoint sets, and the claim in
`reclaim` is that a worker killed mid-job loses its lease and not its job. Both are the reason to
write a queue rather than adopt one, so both get measured here rather than argued.

Three measurements, all against one SQLite file on disk with separate OS processes:

- **contention**: N workers drain M jobs at once. Exactly-once means every job ends `done` with
  exactly one row in `job_runs`. A double-claim shows up as a job with two run rows.
- **crash**: workers are SIGKILLed mid-job. Nothing may be lost. Redeliveries are the price of
  at-least-once and are counted, not hidden.
- **rate**: claims per second, so "polling costs nothing at this workload" is a number.

    python -m evals.jobs
"""
import os, signal, sys, time
from collections import Counter
from multiprocessing import Process
from pathlib import Path
from tempfile import mkdtemp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from litesearch import database
from vishalakshi.jobs import Queue

WORKERS, JOBS = 8, 400


def _q(path, name='w', kill_after=None, **kw):
    'A queue on `path` whose handler writes a side effect, then dies if this worker is a victim.'
    db = database(path)
    db.t.side.create(id=int, n=int, worker=str, pk='id', if_not_exists=True)
    q = Queue(db, lease=kw.pop('lease', 30), max_attempts=kw.pop('max_attempts', 5), base=1, **kw)
    done = []
    def unit(p):
        # the side effect lands first, so a kill here is the case at-least-once has to pay for
        db.q('INSERT INTO side(n, worker) VALUES(?,?)', [p['n'], name])
        done.append(p['n'])
        if kill_after is not None and len(done) > kill_after: os.kill(os.getpid(), signal.SIGKILL)
        return dict(n=p['n'])
    q.register('unit', unit)
    return q


def _drain(path, name, kill_after=None, lease=30):
    'One worker process. `kill_after` SIGKILLs it inside the handler, after the write, before the ack.'
    q = _q(path, name=name, kill_after=kill_after, lease=lease)
    while (got := q.claim(name, n=1)): q.run_one(got[0])


def _audit(q, jobs:int) -> dict:
    'Per-job run counts, from the history the queue writes whether a job succeeds or not.'
    runs = Counter(r['job_id'] for r in q.db.q('SELECT job_id FROM job_runs'))
    st = q.stats()
    done = {r['id'] for r in q.db.q("SELECT id FROM jobs WHERE state='done'")}
    side = Counter(r['n'] for r in q.db.q('SELECT n FROM side'))
    return dict(enqueued=jobs, done=len(done), lost=jobs - len(done),
                once=sum(1 for j in done if runs[j] == 1),
                twice=sum(1 for j in done if runs[j] > 1),
                side_effects=sum(side.values()), applied_twice=sum(1 for n in side if side[n] > 1),
                never_applied=jobs - len(side),
                dead=st['dead'], ready=st['ready'], running=st['running'])


def contention(workers:int=WORKERS, jobs:int=JOBS) -> dict:
    'N processes draining one queue. Every job should end done with exactly one run.'
    path = str(Path(mkdtemp()) / 'q.db')
    q = _q(path)
    q.enqueue_all('unit', [dict(n=i) for i in range(jobs)])
    t0 = time.time()
    ps = [Process(target=_drain, args=(path, f'w{i}')) for i in range(workers)]
    for p in ps: p.start()
    for p in ps: p.join()
    took = time.time() - t0
    return dict(_audit(_q(path), jobs), workers=workers, took=round(took, 2),
                per_sec=round(jobs / took, 1))


def crash(workers:int=4, jobs:int=200, kill_after:int=5) -> dict:
    'Workers SIGKILLed mid-job. Nothing may be lost; redeliveries are counted.'
    path = str(Path(mkdtemp()) / 'q.db')
    q = _q(path, lease=2)
    q.enqueue_all('unit', [dict(n=i) for i in range(jobs)])
    ps = [Process(target=_drain, args=(path, f'k{i}', kill_after, 2)) for i in range(workers)]
    for p in ps: p.start()
    for p in ps: p.join()
    killed = sum(1 for p in ps if p.exitcode and p.exitcode < 0)
    q = _q(path, name='recover', lease=2)
    stuck = q.stats()['running']
    time.sleep(2.1)                      # let the leases the dead workers held expire
    q.reclaim()
    for _ in range(40):                  # backoff is 1s here, so a few passes finish the tail
        if not q.drain('recover', limit=jobs): time.sleep(1.1)
        if q.stats()['ready'] == 0 and q.stats()['running'] == 0: break
    return dict(_audit(q, jobs), workers=workers, killed=killed, stranded_by_the_kills=stuck)


def rate(n:int=2000) -> dict:
    'Enqueue and claim throughput on one process, so the polling cost has a number.'
    q = _q(str(Path(mkdtemp()) / 'q.db'))
    t0 = time.time(); q.enqueue_all('unit', [dict(n=i) for i in range(n)]); t1 = time.time()
    got = 0
    while (c := q.claim('w', n=100)): got += len(c)
    t2 = time.time()
    t3 = time.time(); [q.claim('w', n=1) for _ in range(200)]; t4 = time.time()
    return dict(enqueue_per_sec=round(n / (t1 - t0)), claim_per_sec=round(got / (t2 - t1)),
                empty_poll_ms=round((t4 - t3) / 200 * 1000, 3))


def main():
    print('## contention'); c = contention(); print(c)
    assert c['lost'] == 0,  f"lost {c['lost']} jobs"
    assert c['twice'] == 0, f"{c['twice']} jobs ran twice with no crash to excuse it"
    print('\n## crash'); k = crash(); print(k)
    assert k['lost'] == 0, f"lost {k['lost']} jobs across {k['killed']} kills"
    assert k['never_applied'] == 0, f"{k['never_applied']} jobs never had their side effect applied"
    print('\n## rate'); print(rate())


if __name__ == '__main__': main()
