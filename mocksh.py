# Copyright 2018 Jan Verbeek <jan.verbeek@posteo.nl>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""A wrapper around subprocess for simple function-like process calling.

The main access point is the mocksh.sh object.

Examples:
    >>> from mocksh import sh
    >>> sh.echo("Hello, world")
    Hello, world
    <mocksh.Process: echo Hello, world>
    >>> str(sh.echo.capture_("Hello, world"))
    'Hello, world\n'
    >>> list(sh.seq.capture_(3))
    ['1', '2', '3']
    >>> sh.fortune.pipe_().cowsay()
     ______________________________________
    / Are you making all this up as you go \
    \ along?                               /
     --------------------------------------
            \   ^__^
             \  (oo)\_______
                (__)\       )\/\
                    ||----w |
                    ||     ||
    <mocksh.Process: <mocksh.Process: fortune> | cowsay>

For more, see README.rst.
"""

import errno
import os
import signal
import sys

try:
    from time import monotonic as _time  # type: ignore
except ImportError:
    from time import time as _time

import subprocess
from subprocess import PIPE, STDOUT
if sys.version_info >= (3, 3):
    from subprocess import DEVNULL

PY3 = sys.version_info >= (3,)

MYPY = False
if MYPY:
    from types import TracebackType  # noqa: F401
    from typing import (Any, Dict, IO, Iterator, List, Mapping,  # noqa: F401
                        NoReturn, Optional, Sequence, Text,
                        TextIO, Tuple, Type, Union)
    if sys.version_info >= (3, 6):
        StrTypes = Union[Text, bytes, os.PathLike]
    else:
        StrTypes = Union[Text, bytes]

    if PY3:
        StreamType = TextIO
    else:
        StreamType = IO[str]

__all__ = ['CommandError', 'Process', 'Command', 'sh', 'PIPE', 'STDOUT',
           'DEVNULL']

_STR_TYPES = (str, bytes)  # type: Tuple[Type, ...]
if not PY3:
    _STR_TYPES = (str, unicode)  # noqa: F821
elif sys.version_info >= (3, 6):
    _STR_TYPES = (str, bytes, os.PathLike)


def _to_strlike(obj):
    # type: (Any) -> StrTypes
    """Convert an object to a string-like type."""
    if isinstance(obj, _STR_TYPES):
        # Object is already suitable for subprocess
        return obj  # type: ignore
    # Only convert objects that have an explicit string representation
    # e.g. ints are fine, tuples are not
    # Implicitly converting to bytes is not a good idea, argv can't even
    # contain null bytes
    if getattr(type(obj), '__str__', object.__str__) is object.__str__:
        # Note: this doesn't work on PyPy 2, but it doesn't break anything
        raise TypeError("Object of type '{}' can't be converted to string"
                        .format(type(obj).__name__))
    return str(obj)


def _parse(args, opts):
    # type: (Sequence[Any], Mapping[str, Any]) -> Iterator[StrTypes]
    """Convert Python function arguments to GNU getopt-style command arguments.

    opts are converted using the following procedure:
    - Underscores in keys are replaced by dashes, because dashes are common
      in options but not supported by Python.
    - If a key does not start with a dash, dashes are prepended based on the
      key's length.
      - A single character is assumed to be a short option, and gets one dash.
      - Other keys are assumed to be long options, and get two dashes.
    - If the value is the False object, the option is discarded.
    - If the value is the True object, only the key is yielded.
    - Otherwise, the key is yielded first, and then the value, converted to a
      string unless it's a bytes object.

    args (that are not bytes) are converted to strings and yielded otherwise
    unchanged.

    >>> list(_parse(['foo', b'bar'], dict(x=True, y=False, baz=23)))
    ['-x', '--baz', '23', 'foo', b'bar']

    Args:
        args: A sequence of positional arguments, like *args.
        opts: A dictionary of keyword arguments, like **kwargs.

    Yields:
        strings or bytes that can be used as command arguments.
    """
    for key, value in opts.items():

        key = key.replace('_', '-')
        if not key.startswith('-'):
            if len(key) == 1:
                key = '-' + key
            else:
                key = '--' + key

        if value is False:
            continue

        if value is True:
            yield key
            continue

        yield key
        yield _to_strlike(value)

    for arg in args:
        yield _to_strlike(arg)


def _is_reserved(name):
    # type: (str) -> bool
    """Return whether a name is reserved by mocksh (or Python itself)."""
    return name.endswith('_') and len(name) > 2


if sys.version_info >= (3, 5):
    _SIGNAL_CODES = {
        signal.name: -signal for signal in signal.Signals
    }  # type: Dict[str, int]
else:
    _SIGNAL_CODES = {
        name: -getattr(signal, name) for name in dir(signal)
        if name.startswith('SIG') and '_' not in name
    }  # type: Dict[str, int]

_SIGNAL_NAMES = {
    value: name for name, value in _SIGNAL_CODES.items()
}  # type: Dict[int, str]


class CommandError(Exception):
    """Raised when a command fails.

    This class is automatically subclassed for different return codes.
    "except CommandError:" works, but more specific handling can be done
    with e.g. "except CommandError.code(10)".
    """
    _subclasses = {}  # type: Dict[int, Type[CommandError]]
    returncode = None

    def __new__(cls, returncode, process):
        # type: (Type[CommandError], int, Process) -> CommandError
        subclass = CommandError.code(returncode)
        return super(CommandError, cls).__new__(subclass)  # type: ignore

    def __init__(self, returncode, process):
        # type: (int, Process) -> None
        super(CommandError, self).__init__(returncode, process)
        self.returncode = returncode
        self.process = process

    def __str__(self):
        # type: () -> str
        if isinstance(self.process.args, _STR_TYPES):
            command = self.process.args
        else:
            command = ' '.join(str(arg) for arg in self.process.args)
        if self.returncode in _SIGNAL_NAMES:
            cause = _SIGNAL_NAMES[self.returncode]
        else:
            cause = "status code {}".format(self.returncode)
        return "Command '{}' failed with {}".format(command, cause)

    @classmethod
    def code(cls, returncode):
        # type: (Union[int, str]) -> Type[CommandError]
        """Get a subclass for an error code."""
        returncode, signame = cls.normalize_code(returncode)
        if returncode not in cls._subclasses:
            def __new__(*_, **__):
                # type: (*Any, **Any) -> NoReturn
                raise TypeError("Cannot instantiate CommandError subclasses")
            index = signame if signame else returncode
            name = "{}[{!r}]".format(cls.__name__, index)
            members = {'__new__': __new__, 'returncode': returncode}
            subclass = type(name, (cls,), members)  # type: Type[CommandError]
            cls._subclasses.setdefault(returncode, subclass)
        return cls._subclasses[returncode]

    __class_getitem__ = code

    @staticmethod
    def normalize_code(returncode):
        # type: (Union[int, str]) -> Tuple[int, Optional[str]]
        """Normalize an exit code or signal name."""
        if isinstance(returncode, str):
            if returncode in _SIGNAL_CODES:
                return _SIGNAL_CODES[returncode], returncode
            raise ValueError("Unknown signal {}".format(returncode))
        elif isinstance(returncode, int):
            if returncode in _SIGNAL_NAMES:
                return returncode, _SIGNAL_NAMES[returncode]
            return returncode, None
        raise TypeError


class Process(subprocess.Popen):
    """A subclass of subprocess.Popen with easier behavior.

    Designed to be used through mocksh.Command.

    Arguments:
        args: A string, or a sequence of program arguments.
        check: Whether to raise an exception if the program exits with failure.
        tail: A Process instance to read the output of and wait for, as in a
              pipeline.
        input: Data to write into the standard input of the process. Can be
               either text or bytes.
        wait: Whether to wait until the process is finished when instantiating.
        timeout: How long to wait before raising a TimeoutExpired exception.
        capture_stdout: Whether to capture standard output.
                        Alias for stdout=PIPE.
        capture_stderr: Whether to capture standard error.
                        Alias for stderr=PIPE.
        kwargs: Arguments to be passed to subprocess.Popen's initializer.
    """
    def __init__(self,
                 args,          # type: subprocess._CMD
                 check=True,    # type: bool
                 tail=None,     # type: Optional[Process]
                 input=None,    # type: Optional[Union[bytes, Text]]
                 wait=False,    # type: bool
                 timeout=None,  # type: Optional[float]
                 capture_stdout=False,  # type: bool
                 capture_stderr=False,  # type: bool
                 **kwargs       # type: Any
                 ):
        # type: (...) -> None
        if kwargs.get('shell') and not isinstance(args, _STR_TYPES):
            # This is weird and not very useful, but just in case
            args = ' '.join(str(arg) for arg in args)
            # Strictly speaking, this breaks compatibility with Popen, which
            # just executes ["/bin/sh", "-c"] + args after normalizing args
            # to a list.
            # On my system, subprocess.Popen(['echo', 'foo'], shell=True)
            # effectively executes "echo", without the foo. But that
            # particular "feature" is never desirable for this module.
        if PY3:
            # TODO: it would be nice to remove this restriction
            # Maybe re-open the files in text mode in __str__ and __iter__?
            # A new attribute? A new property?
            if kwargs.get('universal_newlines', True) is not True:
                raise ValueError("Can't override universal_newlines")
            kwargs['universal_newlines'] = True

        if tail is not None:
            if kwargs.get('stdin') is not None:
                raise ValueError("Can't pipe and set stdin at the same time")
            kwargs['stdin'] = tail.stdout
        if input is not None:
            if kwargs.get('stdin') is not None:
                raise ValueError("Can't input and set stdin at the same time")
            kwargs['stdin'] = PIPE

        if capture_stdout:
            if kwargs.get('stdout') is not None:
                raise ValueError("Can't capture stdout if redirecting it")
            kwargs['stdout'] = PIPE
        if capture_stderr:
            if kwargs.get('stderr') is not None:
                raise ValueError("Can't capture stderr if redirecting it")
            kwargs['stderr'] = PIPE

        super(Process, self).__init__(args, **kwargs)
        self.check = check
        self.tail = tail
        if self.tail is not None:
            self.stdin = self.tail.stdin
        if not hasattr(self, 'args'):
            self.args = args

        if input is not None:
            if self.stdin is None:
                raise TypeError("Couldn't find stdin")
            try:
                if PY3 and isinstance(input, bytes):
                    self.stdin.buffer.write(input)  # type: ignore
                else:
                    self.stdin.write(input)
            except IOError as exc:
                if exc.errno not in {errno.EINVAL, errno.EPIPE}:
                    raise
            finally:
                self.stdin.close()

        if wait or timeout is not None:
            if timeout is not None:
                self.wait(timeout=timeout)
            else:
                self.wait()
            if self.check:
                self.check_returncode()

    @property
    def captured(self):
        # type: () -> StreamType
        """Get the output stream that's being captured."""
        if self.stdout and self.stderr:
            # People might (reasonably) expect captured to access both if this
            # is possible
            raise AttributeError("Capturing both stdout and stderr, use "
                                 ".stdout and .stderr directly instead")
        if self.stdout:
            return self.stdout  # type: ignore
        if self.stderr:
            return self.stderr  # type: ignore
        raise AttributeError("Not capturing any output")

    def __repr__(self):
        # type: () -> str
        argv = ' '.join(str(arg) for arg in self.args)
        name = type(self).__module__ + '.' + type(self).__name__
        if self.tail is None:
            return "<{}: {}>".format(name, argv)
        return "<{}: {!r} | {}>".format(name, self.tail, argv)

    def wait(self, timeout=None):
        # type: (Optional[float]) -> int
        """Wait for this process and its tail (if any) to finish.

        Arguments:
            timeout: How many seconds to wait before raising
                     subprocess.TimeoutExpired. Only supported in Python 3.3+.
        """
        if timeout is None:
            if self.tail is not None:
                self.tail.wait()
            return super(Process, self).wait()
        elif sys.version_info >= (3, 3):
            orig_time = _time()
            if self.tail is not None:
                self.tail.wait(timeout=timeout)
            rest = orig_time + timeout - _time()
            return super(Process, self).wait(timeout=rest)
        else:
            raise TypeError("Waiting with a timeout requires Python 3.3+")

    def check_returncode(self):
        # type: () -> None
        """Raise a CommandError if the exit code is non-zero."""
        returncode = self.wait()
        if returncode != 0:
            raise CommandError(returncode, self)

    def __enter__(self):
        # type: () -> Process
        return self

    def __exit__(self,
                 type,      # type: Optional[Type[BaseException]]
                 value,     # type: Optional[BaseException]
                 traceback  # type: Optional[TracebackType]
                 ):
        # type: (...) -> bool
        """Close all streams and wait for the process to finish."""
        try:
            if self.tail is not None:
                self.tail.__exit__(type, value, traceback)
            for stream in self.stdout, self.stderr, self.stdin:
                if stream:
                    stream.close()
        finally:
            self.wait()
        if self.check:
            self.check_returncode()
        return False

    def __iter__(self):
        # type: () -> Iterator[str]
        """Loop through the lines of command output, without newlines."""
        with self:
            for line in self.captured:
                yield line.rstrip('\r\n')

    def __str__(self):
        # type: () -> str
        """Read the output of the command as a string."""
        with self:
            return self.captured.read()

    if PY3:
        def __bytes__(self):
            # type: () -> bytes
            """Read the output of the command as bytes."""
            with self:
                return self.captured.buffer.read()

    def __bool__(self):
        # type: () -> bool
        """Check whether the process exited successfully."""
        return self.wait() == 0

    __nonzero__ = __bool__


class Command(object):
    """A launcher for Process instances that mimics function calls.

    Arguments:
        args: A tuple of program arguments.
        opts: Keyword arguments to pass to mocksh.Process.
        kwargs: Alternative syntax for opts.

    In most cases you would use this through the pre-built mockh.sh object.
    """
    # for the benefit of 'from mocksh import sh'
    PIPE_ = PIPE
    STDOUT_ = STDOUT
    if sys.version_info >= (3, 3):
        DEVNULL_ = DEVNULL
    CommandError_ = CommandError

    def __init__(self, args=(), opts=None, **kwargs):
        # type: (Tuple[StrTypes, ...], Optional[Dict[str, Any]], **Any) -> None
        self.args_ = args
        self.opts_ = {}  # type: Dict[str, Any]
        if opts:
            self.opts_.update(opts)
        self.opts_.update(kwargs)

    def __repr__(self):
        # type: () -> str
        name = type(self).__module__ + '.' + type(self).__name__
        return "{}({!r}, {!r})".format(name, self.args_, self.opts_)

    def __eq__(self, other):
        # type: (Any) -> bool
        return (type(self) is type(other) and self.args_ == other.args_
                and self.opts_ == other.opts_)

    def __getattr__(self, item):
        # type: (str) -> Command
        """Return a new instance with `item` appended to the argument list."""
        if _is_reserved(item):
            raise AttributeError(item)
        return type(self)(self.args_ + (item.replace('_', '-'),), self.opts_)

    def __getitem__(self, index):
        # type: (Union[Any, Tuple[Any]]) -> Command
        """Return a new instance with index appended to the argument list.

        index will be cast to a suitable type if necessary.

        Both `command[arg]` and `command[arg1, arg2, arg3]` are supported.
        """
        if not isinstance(index, tuple):
            index = (index,)
        index = tuple(_to_strlike(item) for item in index)
        return type(self)(self.args_ + index, self.opts_)

    def __call__(self, *args, **opts):
        # type: (*Any, **Any) -> Process
        """Launch a new instance of Process.

        args and opts will be converted to (GNU) getopt/argparse-style command
        arguments. However, keyword arguments ending in an underscore will be
        passed (without the underscore) to the initializer of Process instead.

        By default, this method waits until the process is finished. To return
        immediately, pass wait_=False.

        sh.foo('bar', baz=3, cwd_='/') is equivalent to
        Process(('foo', '--baz', '3', 'bar'), cwd='/')
        """
        process_kwargs = self.opts_.copy()
        cmd_opts = {}
        for key, value in opts.items():
            if _is_reserved(key):
                process_kwargs[key[:-1]] = value
            else:
                cmd_opts[key] = value
        argv = self.args_ + tuple(_parse(args, cmd_opts))
        # Wait by default when using this interface
        process_kwargs.setdefault('wait', True)
        return Process(argv, **process_kwargs)

    def pipe_(self, *args, **opts):
        # type: (*Any, **Any) -> Command
        """Launch an instance of Process as part of a pipeline.

        Returns a new Command object to launch a process to continue.
        """
        # wait_=False and check_=False are defaults, stdout_=PIPE is mandatory
        opts.setdefault('wait_', False)
        opts.setdefault('check_', False)
        process = self(*args, stdout_=PIPE, **opts)
        return type(self)(opts=self.opts_, tail=process)

    def capture_(self, *args, **opts):
        # type: (*Any, **Any) -> Process
        """Launch an instance of Process to capture its output."""
        opts.setdefault('wait_', False)
        return self(*args, stdout_=PIPE, **opts)

    def test_(self, *args, **opts):
        # type: (*Any, **Any) -> Process
        """Launch an instance of Process to test whether it succeeds."""
        opts.setdefault('check_', False)
        return self(*args, **opts)

    if sys.version_info >= (3, 3):
        # older versions can't do super().__dir__
        def __dir__(self):
            # type: () -> List[str]
            """Provide PATH autocompletion. Loosely based on shutil.which."""
            listing = list(super(Command, self).__dir__())
            if self.args_:
                return listing
            mode = os.F_OK | os.X_OK
            path = os.environ.get('PATH', os.defpath).split(os.pathsep)
            for directory in filter(os.path.isdir, path):
                for filename in os.listdir(directory):
                    fpath = os.path.join(directory, filename)
                    if os.path.isfile(fpath) and os.access(fpath, mode):
                        listing.append(filename.replace('-', '_'))
            return listing


sh = Command()
