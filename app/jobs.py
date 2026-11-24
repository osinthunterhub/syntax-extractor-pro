import asyncio
from dataclasses import dataclass, field
import uuid
from .providers import ProviderError

@dataclass
class Job:
    user_id: int
    chat_id: int
    connection: object = field(repr=False)
    course_id: str = ''
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    cancelled: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    destination: object = None

class Jobs:
    """One worker + at most three waiting jobs, one job per user, hard job deadline."""
    def __init__(self, provider, deliver, notify, capacity=3, deadline=180):
        self.provider, self.deliver, self.notify = provider, deliver, notify
        self.queue = asyncio.Queue(maxsize=capacity)
        self.active = {}
        self.task = None
        self.deadline = deadline

    def submit(self, uid, chat, conn, cid, destination=None):
        if uid in self.active:
            raise ProviderError('YOU_ALREADY_HAVE_A_JOB_USE_CANCEL')
        if self.queue.full():
            raise ProviderError('QUEUE_FULL_TRY_LATER')
        job = Job(uid, chat, conn, cid, destination=destination)
        self.active[uid] = job
        self.queue.put_nowait(job)
        return job

    def cancel(self, uid):
        job = self.active.get(uid)
        if job:
            job.cancelled.set()
        return bool(job)

    async def run(self):
        while True:
            job = await self.queue.get()
            try:
                if job.cancelled.is_set():
                    raise ProviderError('JOB_CANCELLED')
                async def execute():
                    await self.notify(job, 'Job started. /cancel stops your job.')
                    last = asyncio.get_running_loop().time()
                    async def progress(folders, links):
                        nonlocal last
                        if job.cancelled.is_set():
                            raise ProviderError('JOB_CANCELLED')
                        now = asyncio.get_running_loop().time()
                        if now - last >= 25:
                            await self.notify(job, f'Progress: {folders} folders, {links} clear links.')
                            last = now
                    result = await self.provider.export(job.connection, job.course_id, job.cancelled, progress)
                    if job.cancelled.is_set():
                        raise ProviderError('JOB_CANCELLED')
                    await self.deliver(job, result)
                await asyncio.wait_for(execute(), self.deadline)
            except asyncio.TimeoutError:
                await self.safe_notify(job, 'JOB_TIME_LIMIT_EXCEEDED')
            except ProviderError as e:
                await self.safe_notify(job, str(e))
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.safe_notify(job, 'JOB_FAILED_NO_SECRETS_LOGGED')
            finally:
                if self.active.get(job.user_id) is job:
                    self.active.pop(job.user_id, None)
                self.queue.task_done()
                job = None  # drop the completed connection snapshot while worker is idle

    async def safe_notify(self, job, text):
        try:
            await self.notify(job, text)
        except Exception:
            pass

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.active.clear()
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
