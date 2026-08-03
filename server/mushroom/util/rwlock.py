import threading


class RWLock:
    """
    A read-write lock.
    Will allow concurrent reads but serialize all writes.
    Write operations have a higher priority.

    Example use:
        lock = RWLock()

        with lock.r:
            read_stuff()

        with lock.w:
            write_stuff()
    """

    class Selector:
        def __init__(self, rwlock, write):
            self.rwlock = rwlock
            self.write = write

        def __enter__(self):
            if self.write:
                self.rwlock.acquire_w()
            else:
                self.rwlock.acquire_r()

        def __exit__(self, exc_t, exc_v, trace):
            self.rwlock.release()

    def __init__(self):
        self.lock = threading.Lock()
        self.r_cv = threading.Condition(self.lock)
        self.w_cv = threading.Condition(self.lock)
        self.readers = 0
        self.writers = 0

        # 'public' members
        self.r = RWLock.Selector(self, write=False)
        self.w = RWLock.Selector(self, write=True)

    def acquire_r(self):
        with self.lock:
            while self.readers < 0 or self.writers:
                self.r_cv.wait()
            self.readers += 1

    def acquire_w(self):
        with self.lock:
            while self.readers != 0:
                self.writers += 1
                self.w_cv.wait()
                self.writers -= 1
            self.readers = -1

    def release(self):
        with self.lock:
            if self.readers < 0:
                self.readers = 0
            else:
                self.readers -= 1
            if self.writers and self.readers == 0:
                self.w_cv.notify()
            elif self.writers == 0:
                self.r_cv.notify_all()
