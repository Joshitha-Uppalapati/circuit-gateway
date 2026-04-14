import asyncio

_tasks: set[asyncio.Task] = set()


def spawn(coro):
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def drain():
    if not _tasks:
        return
    await asyncio.gather(*list(_tasks), return_exceptions=True)