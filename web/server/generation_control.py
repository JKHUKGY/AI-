"""协作取消与独立进程组；提交结果与取消使用同一把锁。"""
from contextlib import contextmanager
from functools import wraps
import os
import signal
import subprocess
import threading
import time

_local = threading.local()


class Cancelled(Exception):
    pass


def stop_process(proc):
    """只用于由网站以 start_new_session 启动的进程。包括其派生进程。"""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=5)


class Control:
    def __init__(self):
        self.lock = threading.RLock()
        self.cancelled = False
        self.finished = False
        self.proc = None
        self.done = threading.Event()
        self.username = None

    def check(self):
        if self.cancelled:
            raise Cancelled()

    def cancel(self):
        with self.lock:
            if self.finished:
                return False
            self.cancelled = True
            if self.proc is not None:
                stop_process(self.proc)
            return True

    def run(self, cmd, *, input, timeout, **kwargs):
        with self.lock:
            self.check()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True, **kwargs)
            self.proc = proc
        try:
            deadline = time.monotonic() + timeout
            first = True
            while True:
                if self.username:
                    import control_store
                    if not control_store.account(self.username)['enabled']:
                        self.cancel()
                self.check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    stdout, stderr = proc.communicate(input=input if first else None,
                                                      timeout=min(.5, remaining) if self.username else remaining)
                    break
                except subprocess.TimeoutExpired:
                    first = False
                    if not self.username:
                        raise
            self.check()
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            stop_process(proc)
            proc.communicate()
            raise
        except Cancelled:
            stop_process(proc)
            proc.communicate()
            raise
        finally:
            with self.lock:
                self.proc = None


@contextmanager
def activate(control):
    previous = getattr(_local, 'control', None)
    _local.control = control
    try:
        yield
    finally:
        _local.control = previous


def current():
    return getattr(_local, 'control', None)


@contextmanager
def guard():
    control = current()
    if control is None:
        yield
    else:
        with control.lock:
            control.check()
            yield


def protected(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with guard():
            return fn(*args, **kwargs)
    return wrapped
