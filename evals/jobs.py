"""Does the queue actually deliver each job once, under real processes and real kills.

The claim in `jobs.Queue.claim` is that concurrent callers get disjoint sets, the claim in `reclaim`
is that a worker killed mid-job loses its lease and not its job, and the claim in `ack` is that a
worker which lost its lease cannot finish the job anyway. All three are the reason to write a queue
rather than adopt one, so all three get measured here rather than argued.

Four measurements, all against one SQLite file on disk with separate OS processes:

- **contention**: N workers drain M jobs at once. Exactly-once means every job ends `done` with
  exactly one row in `job_runs`. A double-claim shows up as a job with two run rows.
- **crash**: workers are SIGKILLed mid-job. Nothing may be lost. Redeliveries are the price of
  at-least-once and are counted, not hidden.
- **slow**: handlers that outlive their lease, so the job is reclaimed under a worker that is still
  running it. Two workers then hold one job, and the fence is what stops both of them acking it.
- **rate**: claims per second, so "polling costs nothing at this workload" is a number.

Every measurement checks worker exit codes. A worker that dies at startup makes the queue look
better than it is by taking contention away with it, so `workers` here is the number that ran.

    python -m evals.jobs
"""
import os, signal, sys, time
from collections import Counter
from multiprocessing import Process
from pathlib import Path
from tempfile import mkdtemp

import apsw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from litesearch import database
from vishalakshi.jobs import Queue

WORKERS, JOBS = 8, 400


def _open(path, tries:int=6):
    'litesearch runs apsw bestpractice on connect, whose `pragma optimize` predates any busy timeout.'
    for i in range(tries):
        try: return database(path)
        except apsw.BusyError:
            if i == tries - 1: raise
            time.sleep(0.05 * 2**i)


def _q(path, name='w', kill_after=None, lease=30, max_attempts=5):
    'A queue on `path` whose handler writes a side effect, then dies if this worker is a victim.'
    db = _open(path)
    db.t.side.create(id=int, n=int, worker=str, pk='id', if_not_exists=True)
    q = Queue(db, lease=lease, max_attempts=max_attempts, base=1)
    done = []
    def unit(p):
        # the side effect lands first, so a kill here is the case at-least-once has to pay for
        db.q('INSERT INTO side(n, worker) VALUES(?,?)', [p['n'], name])
        done.append(p['n'])
        if kill_after is not None and len(done) > kill_after: os.kill(os.getpid(), signal.SIGKILL)
        if p.get('slow'): time.sleep(p['slow'])
        return dict(n=p['n'])
    q.register('unit', unit)
    return q


def _drain(path, name, kill_after=None, lease=30, until=None):
    'One worker process. `kill_after` SIGKILLs it inside the handler, after the write, before the ack.'
    q = _q(path, name=name, kill_after=kill_after, lease=lease)
    while True:
        if (got := q.claim(name, n=1)): q.run_one(got[0])
        elif until is None or time.time() >= until: return
        else: time.sleep(0.05)


def _reclaimer(path, lease, until):
    'The poller that puts expired leases back, running alongside the workers rather than after them.'
    q = _q(path, name='reclaimer', lease=lease)
    while time.time() < until:
        q.reclaim()
        time.sleep(lease / 4)


def _ran(ps) -> dict:
    'Worker exit codes: 0 finished, negative was signalled, positive died on its own.'
    c = Counter(p.exitcode for p in ps)
    return dict(finished=c[0], killed=sum(v for k, v in c.items() if k and k < 0),
                failed=sum(v for k, v in c.items() if k and k > 0))


def _audit(q, jobs:int) -> dict:
    'Per-job run counts, from the history the queue writes whether a job succeeds or not.'
    runs = Counter(r['job_id'] for r in q.db.q('SELECT job_id FROM job_runs'))
    ok = Counter(r['job_id'] for r in q.db.q("SELECT job_id FROM job_runs WHERE status='ok'"))
    st = q.stats()
    done = {r['id'] for r in q.db.q("SELECT id FROM jobs WHERE state='done'")}
    side = Counter(r['n'] for r in q.db.q('SELECT n FROM side'))
    return dict(enqueued=jobs, done=len(done), lost=jobs - len(done),
                once=sum(1 for j in done if runs[j] == 1),
                twice=sum(1 for j in done if runs[j] > 1),
                acked_twice=sum(1 for j in ok if ok[j] > 1),
                refused=len(q.db.q("SELECT id FROM job_runs WHERE status='lost'")),
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
    return dict(_audit(_q(path), jobs), workers=workers, **_ran(ps), took=round(took, 2),
                per_sec=round(jobs / took, 1))


def crash(workers:int=4, jobs:int=200, kill_after:int=5) -> dict:
    'Workers SIGKILLed mid-job. Nothing may be lost; redeliveries are counted.'
    path = str(Path(mkdtemp()) / 'q.db')
    q = _q(path, lease=2)
    q.enqueue_all('unit', [dict(n=i) for i in range(jobs)])
    ps = [Process(target=_drain, args=(path, f'k{i}', kill_after, 2)) for i in range(workers)]
    for p in ps: p.start()
    for p in ps: p.join()
    q = _q(path, name='recover', lease=2)
    stuck = q.stats()['running']
    time.sleep(2.1)                      # let the leases the dead workers held expire
    q.reclaim()
    for _ in range(40):                  # backoff is 1s here, so a few passes finish the tail
        if not q.drain('recover', limit=jobs): time.sleep(1.1)
        if q.stats()['ready'] == 0 and q.stats()['running'] == 0: break
    return dict(_audit(q, jobs), workers=workers, **_ran(ps), stranded_by_the_kills=stuck)


def slow(workers:int=4, jobs:int=24, lease:float=0.5, work:float=3., every:int=4,
         attempts:int=3, secs:float=40.) -> dict:
    '''Every `every`th handler outlives the lease, so two workers hold one job and both try to ack it.

    `work` has to clear the lease *and* the retry backoff, or the first worker acks before the job is
    handed on and the two never overlap.'''
    path = str(Path(mkdtemp()) / 'q.db')
    q = _q(path, lease=lease, max_attempts=attempts)
    q.enqueue_all('unit', [dict(n=i, slow=work if i % every == 0 else 0.) for i in range(jobs)])
    until = time.time() + secs
    rp = Process(target=_reclaimer, args=(path, lease, until))
    rp.start()
    ps = [Process(target=_drain, args=(path, f's{i}', None, lease, until)) for i in range(workers)]
    for p in ps: p.start()
    for p in ps: p.join()
    rp.join()
    return dict(_audit(_q(path), jobs), workers=workers, **_ran(ps),
                slow_jobs=len(range(0, jobs, every)))


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
    assert c['failed'] == 0, f"{c['failed']} workers died before doing any work"
    assert c['lost'] == 0,  f"lost {c['lost']} jobs"
    assert c['twice'] == 0, f"{c['twice']} jobs ran twice with no crash to excuse it"
    print('\n## crash'); k = crash(); print(k)
    assert k['failed'] == 0, f"{k['failed']} workers died of something other than the kill"
    assert k['lost'] == 0, f"lost {k['lost']} jobs across {k['killed']} kills"
    assert k['never_applied'] == 0, f"{k['never_applied']} jobs never had their side effect applied"
    print('\n## slow'); s = slow(); print(s)
    assert s['failed'] == 0, f"{s['failed']} workers died"
    assert s['acked_twice'] == 0, f"{s['acked_twice']} jobs were acked by two workers each"
    assert s['never_applied'] == 0, f"{s['never_applied']} jobs never had their side effect applied"
    print('\n## rate'); print(rate())


if __name__ == '__main__': main()
