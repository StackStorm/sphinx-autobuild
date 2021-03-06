"""
Sphinx Documentation Automatic Builder

MIT License. See LICENSE for more details.
Copyright (c) 2013, Jonathan Stoppani
"""


import argparse
import os
import subprocess
import sys

try:
    import pty
except ImportError:
    pty = None

from livereload import Server

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


__version__ = '0.3.0'
__url__ = 'https://github.com/GaretJax/sphinx-autobuild'


class _WatchdogHandler(FileSystemEventHandler):

    def __init__(self, watcher, action):
        super(_WatchdogHandler, self).__init__()
        self._watcher = watcher
        self._action = action

    def on_any_event(self, event):
        if event.is_directory:
            return
        self._action(self._watcher, event.src_path)


class LivereloadWatchdogWatcher(object):

    def __init__(self):
        super(LivereloadWatchdogWatcher, self).__init__()
        self._changed = False
        self._action_file = None  # TODO: Hack.
                                  # Allows the LivereloadWatchdogWatcher
                                  # instance to set the file which was
                                  # modified. Used for output purposes only.

        self._observer = Observer()
        self._observer.start()

        # Compatibility with livereload's builtin watcher
        self._tasks = True  # Accessed by LiveReloadHandler's on_message method
                            # to decide if a task has to be added to watch the
                            # cwd.
        self.filepath = None  # Accessed by LiveReloadHandler's watch_task
                              # method. When set to a boolean false value,
                              # everything is reloaded in the browser ('*').

    def set_changed(self):
        self._changed = True

    def examine(self):
        """
        Called by LiveReloadHandler's poll_tasks method. If a boolean true
        value is returned, then the waiters (browsers) are reloaded.
        """
        if self._changed:
            self._changed = False
            return self._action_file or True  # TODO: Hack (see above)

    def watch(self, path, action):
        """
        Called by the Server instance when a new watch task is requested.
        """
        if action is None:
            action = lambda w, _: w.set_changed()
        event_handler = _WatchdogHandler(self, action)
        self._observer.schedule(event_handler, path=path, recursive=True)

    def start(self, callback):
        """
        Start the watcher running, calling callback when changes are observed.
        If this returns False, regular polling will be used.
        """
        return False


class SphinxBuilder(object):

    def __init__(self, outdir, args, ignored=None):
        self._outdir = outdir
        self._args = args
        self._ignored = ignored or []
        self._ignored.append(outdir)

    def __call__(self, watcher, src_path):
        path = self.get_relative_path(src_path)

        for i in self._ignored:
            if src_path.startswith(i + os.sep):
                return

        watcher._action_file = path  # TODO: Hack (see above)

        pre = '+--------- {0} changed '.format(path)
        sys.stdout.write('\n')
        sys.stdout.write(pre)
        sys.stdout.write('-' * (81 - len(pre)))
        sys.stdout.write('\n')

        args = ['sphinx-build'] + self._args
        if pty:
            master, slave = pty.openpty()
            stdout = os.fdopen(master)
            subprocess.Popen(args, stdout=slave)
            os.close(slave)
        else:
            stdout = subprocess.Popen(args,
                                      stdout=subprocess.PIPE,
                                      universal_newlines=True).stdout
        try:
            while 1:
                line = stdout.readline()
                if not line:
                    break
                sys.stdout.write('| ')
                sys.stdout.write(line.rstrip())
                sys.stdout.write('\n')
        except IOError:
            pass
        finally:
            if not pty:
                stdout.close()
        sys.stdout.write('+')
        sys.stdout.write('-' * 80)
        sys.stdout.write('\n\n')

    def get_relative_path(self, path):
        return os.path.relpath(path)


SPHINX_BUILD_OPTIONS = (
    ('b', 'builder'),
    ('a', None),
    ('E', None),
    ('d', 'path'),
    ('j', 'N'),

    ('c', 'path'),
    ('C', None),
    ('D', 'setting=value'),
    ('t', 'tag'),
    ('A', 'name=value'),
    ('n', None),

    ('v', None),
    ('q', None),
    ('Q', None),
    ('w', 'file'),
    ('W', None),
    ('T', None),
    ('N', None),
    ('P', None),
)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=8000)
    parser.add_argument('-H', '--host', type=str, default='127.0.0.1')

    for opt, meta in SPHINX_BUILD_OPTIONS:
        if meta is None:
            parser.add_argument('-{0}'.format(opt), action='count',
                                help='See `sphinx-build -h`')
        else:
            parser.add_argument('-{0}'.format(opt), action='append',
                                metavar=meta, help='See `sphinx-build -h`')

    parser.add_argument('sourcedir')
    parser.add_argument('outdir')
    parser.add_argument('filenames', nargs='*', help='See `sphinx-build -h`')
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    srcdir = os.path.realpath(args.sourcedir)
    outdir = os.path.realpath(args.outdir)

    build_args = []
    for arg, meta in SPHINX_BUILD_OPTIONS:
        val = getattr(args, arg)
        if not val:
            continue
        opt = '-{0}'.format(arg)
        if meta is None:
            build_args.extend([opt] * val)
        else:
            for v in val:
                build_args.extend([opt, v])

    build_args.extend([srcdir, outdir])
    build_args.extend(args.filenames)

    ignored = []
    if args.w:  # Logfile
        ignored.append(os.path.realpath(args.w[0]))
    if args.d:  # Doctrees
        ignored.append(os.path.realpath(args.d[0]))

    if not os.path.exists(outdir):
        os.makedirs(outdir)

    server = Server(watcher=LivereloadWatchdogWatcher())
    server.watch(srcdir, SphinxBuilder(outdir, build_args, ignored))
    server.watch(outdir)
    server.serve(port=args.port, host=args.host, root=outdir)
