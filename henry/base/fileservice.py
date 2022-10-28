from builtins import object
import os
import fcntl
from typing import Optional, Callable, Iterator, Iterable
# importation threading


class FileService(object):
    def __init__(self, root: str):
        self.root = root

    def make_fullpath(self, filename: str) -> str:
        dirname, name = os.path.split(filename)
        if not filename.startswith('/'):
            dirname = os.path.join(self.root, dirname)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0o777)
        fullpath = os.path.join(dirname, name)
        return fullpath

    def put_file(
            self,
            filename: str,
            content: str,
            override=True) -> Optional[str]:
        fullpath = self.make_fullpath(filename)
        if not override and os.path.exists(fullpath):
            return None
        with open(fullpath, 'w') as f:
            f.write(content)
            f.flush()
            return fullpath

    def get_file(self, filename: str) -> Optional[str]:
        fullpath = self.make_fullpath(filename)
        if not os.path.exists(fullpath):
            return None
        with open(fullpath) as f:
            return f.read()

    def append_file(self, filename: str, data: str) -> str:
        fullpath = self.make_fullpath(filename)
        with open(fullpath, 'a') as f:
            with LockClass(f):
                f.write(data)
                f.write('\n')
                f.flush()
        return fullpath

    def get_file_lines(self,
                       filenames: Iterable[str],
                       condition: Optional[Callable[[str],
                                                    bool]] = None) -> Iterator[str]:
        for fname in filenames:
            fullpath = self.make_fullpath(fname)
            if os.path.exists(fullpath):
                with open(fullpath) as f:
                    for line in f.readlines():
                        if condition is None or condition(line):
                            yield line


class LockClass(object):
    def __init__(self, fileobj):
        self.fileno = fileobj.fileno()

    def __enter__(self):
        fcntl.flock(self.fileno, fcntl.LOCK_EX)

    def __exit__(self, _, unused, enused2):
        fcntl.flock(self.fileno, fcntl.LOCK_UN)
