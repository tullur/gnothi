import time, psycopg2, traceback, pdb, multiprocessing, threading, os
from psycopg2.extras import Json as jsonb
from box import Box
import torch
import socket
from sqlalchemy import text
import logging
logger = logging.getLogger(__name__)

# from books import run_books
from themes import themes
from influencers import influencers
from common.utils import utcnow
from common.database import SessLocal, engine
from utils import cluster, cosine, clear_gpu
from nlp import nlp_

m = Box({
    'sentiment-analysis': nlp_.sentiment_analysis,
    'question-answering': nlp_.question_answering,
    'summarization': nlp_.summarization,
    'sentence-encode': nlp_.sentence_encode,
    'entry': nlp_.entry,

    'cosine': cosine,
    'influencers': influencers,
    'cluster': cluster,
    # 'books': run_books,
    'themes': themes,
})

non_returning = ['entry', 'books']

def remove_stale_jobs(sess):
    sql = f"""
    delete from jobs
    where created_at < {utcnow} - interval '1 hour';
    """
    sess.execute(sql)


def run_job(job):
    jid, k = str(job.id), job.method
    jid = {'jid': jid}
    sess = SessLocal.main()
    job = sess.execute("select * from jobs where id=:jid;", jid).fetchone()
    args = job.data.get('args', [])
    kwargs = job.data.get('kwargs', {})

    print(f"Running job {k}")

    if k == 'books':
        sess.close()
        return os.system(f"python books.py {args[0]}")

    try:
        start = time.time()
        res = m[k](*args, **kwargs)
        sql = text(f"update jobs set state='done', data=:data where id=:jid;")
        sess.execute(sql, {'data': jsonb(res), **jid})
        print(f"Job Complete {time.time() - start}")
    except Exception as err:
        err = str(traceback.format_exc())
        # err = str(err)
        res = {"error": err}
        sql = text(f"update jobs set state='error', data=:data where id=:jid;")
        sess.execute(sql, {'data': jsonb(res), **jid})
        print(f"Job Error {time.time() - start} {err}", )

    remove_stale_jobs(sess)
    sess.commit()
    sess.close()

    # 3eb71b3: unloading models. multiprocessing handles better


if __name__ == '__main__':
    print(f"torch.cuda.current_device() {torch.cuda.current_device()}")
    print(f"torch.cuda.device(0) {torch.cuda.device(0)}")
    print(f"torch.cuda.device_count() {torch.cuda.device_count()}")
    print(f"torch.cuda.get_device_name(0) {torch.cuda.get_device_name(0)}")
    print(f"torch.cuda.is_available() {torch.cuda.is_available()}")
    print("\n\n")

    inactivity = 15 * 60  # 15 minutes
    while True:
        # if active_jobs: GPUtil.showUtilization()

        # Notify is online.
        sql = f"update jobs_status set status='on', ts_svc={utcnow}, svc=:svc"
        engine.execute(text(sql), svc=socket.gethostname())

        # Find jobs
        sql = f"""
        update jobs set state='working'
        where id = (select id from jobs where state='new' limit 1)
        returning id, method;
        """
        job = engine.execute(sql).fetchone()
        if not job:
            sql = f"""
            select extract(epoch FROM ({utcnow} - ts_client)) as elapsed_client
            from jobs_status;
            """
            if engine.execute(sql).fetchone().elapsed_client > inactivity:
                nlp_.clear()

            time.sleep(.5)
            continue

        # Threading keeps models around for re-use (cleared after inactivity)
        # Multiprocessing fully wipes the process after run. Keras/TF has model-training memleak & can't recover GPU
        # RAM, so just run books in Process https://github.com/tensorflow/tensorflow/issues/36465#issuecomment-582749350
        # FIXME Running influencers in process too because it crashes sometimes. Find solution
        if job.method in []:  # ['books', 'influencers']:
            multiprocessing.Process(target=run_job, args=(job,)).start()
        else:
            threading.Thread(target=run_job, args=(job,)).start()
        # run_job(job.id)
