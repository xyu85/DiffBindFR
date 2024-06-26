# Copyright (c) MDLDrugLib. All rights reserved.
# Reference by https://github.com/open-mmlab/mmcv/blob/master/mmcv/mmcv/utils/progressbar.py
import sys
from typing import Callable, Tuple, Union, Optional
from collections.abc import Iterable
from multiprocessing import Pool
from shutil import get_terminal_size
from .timer import Timer

class ProgressBar:
    """A progress bar which can print the progress."""

    def __init__(
            self,
            task_num:int = 0,
            bar_width:int = 50,
            start:bool = True,
            file=sys.stdout,
    ):
        self.task_num = task_num
        self.bar_width = bar_width
        self.completed = 0
        self.file = file
        if start:
            self.start()

    def start(self):
        if self.task_num > 0:
            self.file.write(f'[{" " * self.bar_width}] 0/{self.task_num}, elapsed: 0s, ETA')
        else:
            self.file.write('completed: 0, elapsed: 0s')
        self.file.flush()
        self.timer = Timer()

    @property
    def terminal_width(self) -> int:
        width, _ = get_terminal_size()
        return width

    def update(
            self,
            num_tasks:int = 1,
    ) -> None:
        assert num_tasks > 0
        self.completed += num_tasks
        elapsed = self.timer.since_start()
        if elapsed > 0:
            fps = self.completed / elapsed
        else:
            fps = float('inf')
        if self.task_num > 0:
            percentage = self.completed / float(self.task_num)
            eta = int(elapsed * (1 - percentage) / percentage + 0.5)
            msg = f'\r[{{}}] {self.completed}/{self.task_num}, ' \
                  f'{fps:.1f} task/s, elapsed: {int(elapsed + 0.5)}s, ' \
                  f'ETA: {eta:5}s'

            bar_width = min(self.bar_width,
                            int(self.terminal_width - len(msg)) + 2,
                            int(self.terminal_width * 0.6))
            bar_width = max(2, bar_width)
            mark_width = int(bar_width * percentage)
            bar_chars = '>' * mark_width + ' ' * (bar_width - mark_width)
            self.file.write(msg.format(bar_chars))
        else:
            self.file.write(
                f'completed: {self.completed}, elapsed: {int(elapsed + 0.5)}s, '
                f'{fps:1f} tasks/s'
            )
        self.file.flush()

def track_progress(
        func:Callable,
        tasks:Union[list, Tuple[Iterable, int]],
        bar_width:int = 50,
        file = sys.stdout,
        **kwargs,
) -> list:
    """
    Track the progress or tasks execution with a progress bar.
    Tasks are done with a simple for-loop.
    Args:
        func:callable: The function to be applied to each task.
        tasks:list, tuple[Iterable, int]: A list of tasks or (tasks, total num).
        bar_width:int: Width of progress bar.
    Returns:
        list: The task results
    """
    if isinstance(tasks, tuple):
        assert len(tasks) == 2, f"Length of args `tasks` with tuple type must be 2 but got {len(tasks)}"
        assert isinstance(tasks[0], Iterable)
        assert isinstance(tasks[1], int)
        task_num = tasks[1]
        tasks = tasks[0]
    elif isinstance(tasks, Iterable):
        task_num = len(tasks)
    else:
        raise TypeError(
            '"tasks" must be an iterable object or a tuple(iterable, int) object.'
        )
    prog_bar = ProgressBar(task_num, bar_width, file=file)
    results = []
    for task in tasks:
        results.append(func(task, **kwargs))
        prog_bar.update()
    prog_bar.file.write('\n')
    return results

def init_pool(
        process_num:int,
        initializer:Optional[Callable] = None,
        initargs:Optional[tuple] = None,
) -> Pool:
    if initializer is None:
        return Pool(process_num)
    elif initargs is None:
        return Pool(process_num, initializer)
    else:
        if not isinstance(initargs, tuple):
            raise TypeError('"initargs" must be a tuple.')
        return Pool(process_num, initializer, initargs)

def track_parallel_progress(
        func:Callable,
        tasks:Union[list, Tuple[Iterable, int]],
        nproc:int,
        initializer:Optional[Callable] = None,
        initargs:Optional[tuple] = None,
        bar_width:int = 50,
        chunksize:int = 1,
        skip_first:bool = False,
        keep_order:bool = True,
        file = sys.stdout,
) -> list:
    """
    Track the progress of parallel task execution with a progress bar.
    The built-in:module:`multiprocessing` module is used for process pools and
        tasks are done with :func:`Pool.map` or :func: `Pool.imap_unordered`.
    Args:
        func:Callable: The function to be applied to each task.
        tasks:Union[list, Tuple[Iterable, int]]: A list of tasks or tuple(tasks, total_num)
        nproc:int: Process (worker) number.
        initializer:Optional[Callable]: Refer to :class:`multiprocessing.Pool` for details.
        initargs:Optional[tuple]: Refer to :class:`multiprocessing.Pool` for details.
        chunksize:int: Refer to :class:`multiprocessing.Pool` for details.
        bar_width:int: Width of progress bar.
        skip_first:bool: Whether to skip the first sample for each worker when estimating fps,
            since the initialization step may takes longer.
        keep_order:bool: If True, :func:`Pool.imap` is used, otherwise :func:`Pool.imap_unordered` is used.
    Returns:
        list: The tasks results.
    """
    if isinstance(tasks, tuple):
        assert len(tasks) == 2, f"Length of args `tasks` with tuple type must be 2 but got {len(tasks)}"
        assert isinstance(tasks[0], Iterable)
        assert isinstance(tasks[1], int)
        task_num = tasks[1]
        tasks = tasks[0]
    elif isinstance(tasks, Iterable):
        task_num = len(tasks)
    else:
        raise TypeError(
            '"tasks" must be an iterable object or a tuple(iterable, int) object.'
        )
    pool = init_pool(nproc, initializer, initargs)
    start = not skip_first
    task_num -= nproc * chunksize * int(skip_first)
    prog_bar = ProgressBar(task_num, bar_width, start = start, file = file)
    results = []
    if keep_order:
        genpool = pool.imap(func, tasks, chunksize)
    else:
        genpool = pool.imap_unordered(func, tasks, chunksize)
    for result in genpool:
        results.append(result)
        if skip_first:
            if len(results) < nproc * chunksize:
                continue
            elif len(results) == nproc * chunksize:
                prog_bar.update()
                continue
        prog_bar.update()
    prog_bar.file.write('\n')
    pool.close()
    pool.join()
    return results

def track_iter_progress(
        tasks:Union[list, Tuple[Iterable, int]],
        bar_width:int = 50,
        file = sys.stdout,
) -> list:
    """
    Track the progress of tasks iteraction or enumeration with a progress bar.
    Tasks are yielded with a simple for-loop.
    Args:
        tasks:Union[list, Tuple[Iterable, int]]: A list of tasks or tuple(iterable, int) object.
        bar_width:int: Width of progress bar.
    Returns:
        list: The tasks results.
    """
    if isinstance(tasks, tuple):
        assert len(tasks) == 2, f"Length of args `tasks` with tuple type must be 2 but got {len(tasks)}"
        assert isinstance(tasks[0], Iterable)
        assert isinstance(tasks[1], int)
        task_num = tasks[1]
        tasks = tasks[0]
    elif isinstance(tasks, Iterable):
        task_num = len(tasks)
    else:
        raise TypeError(
            '"tasks" must be an iterable object or a tuple(iterable, int) object.'
        )
    prog_bar = ProgressBar(task_num, bar_width, file=file)
    for task in tasks:
        yield task
        prog_bar.update()
    prog_bar.file.write('\n')