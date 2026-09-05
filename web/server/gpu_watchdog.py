"""独立于网站和浏览器的显卡回收与邮件通知进程。"""
import logging
import threading
import time
import notifications
import runpod_service


def loop(fn, seconds):
    while True:
        try:
            fn()
        except Exception:
            logging.error('%s failed; retrying', fn.__name__)
        time.sleep(seconds)


def start_threads():
    for fn,seconds in ((runpod_service.tick,15),(notifications.deliver_one,2)):
        threading.Thread(target=loop,args=(fn,seconds),daemon=True).start()


if __name__ == '__main__':
    start_threads()
    threading.Event().wait()
