# TODO: These tests probably don't work well on systems without GNU

import platform
import subprocess as sp
import sys

import pytest

from mocksh import (_is_reserved, _parse, CommandError, Process, Command, sh,
                    PIPE)

PY3 = sys.version_info >= (3,)


class FakeProcess(Process):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def raise_exit_code(code):
    if code >= 0:
        return sh.python(c="import sys; sys.exit({})".format(code))
    else:
        return sh.python(c="import os; os.kill(os.getpid(), {})".format(-code))


def write_stderr(message, **kwargs):
    code = "import sys; sys.stderr.write({!r})".format(message)
    return sh.python(c=code, **kwargs)


def test_commanderror():
    assert issubclass(CommandError.code(10), CommandError)
    assert not issubclass(CommandError, CommandError.code(10))
    assert CommandError.code(10) is not CommandError
    assert CommandError.code(10) is CommandError.code(10)
    assert CommandError.code(9).code(10) is CommandError.code(10)
    assert CommandError.code('SIGTERM') is CommandError.code(-15)
    assert CommandError.code(9) is not CommandError.code(10)
    assert CommandError.code(11).returncode == 11

    with pytest.raises(CommandError):
        raise_exit_code(1)

    with pytest.raises(CommandError.code(10)):
        raise_exit_code(10)

    assert CommandError.code(-15).__name__ == "CommandError['SIGTERM']"
    assert CommandError.code(5).__name__ == "CommandError[5]"

    with pytest.raises(CommandError.code('SIGTERM')):
        raise_exit_code(-15)

    try:
        raise_exit_code(10)
    except CommandError.code(9):
        assert False
    except CommandError.code(10) as e:
        assert e.returncode == 10

    process = FakeProcess(args=('foo', 'bar', 'baz'))
    expected = "Command 'foo bar baz' failed with status code 1"
    assert str(CommandError(1, process)) == expected

    process = FakeProcess(args='foo bar  baz')
    expected = "Command 'foo bar  baz' failed with SIGTERM"
    assert str(CommandError(-15, process)) == expected


if sys.version_info >= (3, 7):
    def test_commanderror_class_getitem():
        assert CommandError[10] is CommandError.code(10)
        assert CommandError['SIGTERM'] is CommandError[-15]

        with pytest.raises(CommandError[10]):
            raise_exit_code(10)

        with pytest.raises(CommandError['SIGTERM']):
            raise_exit_code(-15)


def parse(*args, **opts):
    return list(_parse(args, opts))


class StringableType(object):
    def __str__(self):
        return 'foo'


class UnstringableType(object):
    pass


@pytest.mark.parametrize("real,expected", [
    (parse('foo', 'bar', 2, x=True), ['-x', 'foo', 'bar', '2']),
    (parse(), []),
    (parse(y=False, z=False), []),
    (parse(b'foo', u'bar', 100.00), [b'foo', u'bar', '100.0']),
    (parse(foo=10), ['--foo', '10']),
    (parse(_foo=True), ['-foo']),
    (parse(__x_y_z='y'), ['--x-y-z', 'y']),
    (parse(__x=True), ['--x']),
])
def test_argparsing(real, expected):
    assert real == expected


if not (platform.python_implementation() == 'PyPy' and sys.version_info < (3,)):
    def test_argparsing_type_conversion():
        with pytest.raises(TypeError):
            parse(UnstringableType())
        assert parse(StringableType()) == ['foo']


def test_is_reserved():
    assert _is_reserved('env_')
    assert not _is_reserved('__')
    assert not _is_reserved('foo')
    assert _is_reserved('__wrapped__')


def test_iteration():
    assert list(map(int, sh.seq(10, capture_stdout_=True))) == list(range(1, 11))


def test_string():
    assert str(sh.echo('foo\nbar', capture_stdout_=True)) == 'foo\nbar\n'
    assert bytes(sh.echo('foo\nbar', capture_stdout_=True)) == b'foo\nbar\n'
    if not PY3:
        proc = sh.echo('foo\nbar', capture_stdout_=True)
        assert unicode(proc) == u'foo\nbar\n'
        # TODO: non-ASCII unicode doesn't work


def test_context_manager():
    with sh.sleep.capture_(0.1) as proc:
        assert proc.poll() is None
        assert not proc.stdout.closed
    assert proc.poll() is not None
    assert proc.stdout.closed


def test_output_synchronous(capfd):
    sh.echo('foo', n=True)
    sh.python(c="import sys; sys.stderr.write('bar')")
    out, err = capfd.readouterr()
    assert out == 'foo'
    assert err == 'bar'


def test_basic_pipeline():
    assert str(sh.seq.pipe_(10).grep.capture_(8)) == '8\n'


def test_input():
    proc = sh.head.capture_(input_="foo\nbar\nbaz\n", n=2)
    assert str(proc) == "foo\nbar\n"
    proc = sh.tail.capture_(input_=b"foo\nbar\nbaz\n", n=2)
    assert list(proc) == ['bar', 'baz']


def test_repr():
    proc = sh.true('foo', 'bar', 'baz')
    assert repr(proc) == "<mocksh.Process: true foo bar baz>"
    proc = sh.true.pipe_().true()
    assert repr(proc) == "<mocksh.Process: <mocksh.Process: true> | true>"


def test_check_returncode():
    proc = sh.false.test_()
    with pytest.raises(CommandError):
        proc.check_returncode()
    sh.true.test_().check_returncode()


def test_wait():
    proc = sh.sleep(0.1, wait_=False)
    assert proc.poll() is None
    proc.wait()
    assert proc.poll() is not None


if sys.version_info >= (3, 3):
    def test_timeout():
        with pytest.raises(sp.TimeoutExpired):
            sh.sleep(0.1, timeout_=0.05)
        sh.sleep(0.05, timeout_=0.1)
        with pytest.raises(sp.TimeoutExpired):
            sh.true.pipe_().sleep.pipe_(0.1).true(timeout_=0.05)
        sh.true.pipe_().sleep.pipe_(0.05).true(timeout_=0.1)


def test_stream_output():
    proc = sh.true(capture_stdout_=True, capture_stderr_=True)
    with pytest.raises(AttributeError):
        list(proc)
    proc = sh.true()
    with pytest.raises(AttributeError):
        str(proc)
    proc = write_stderr("foo", capture_stderr_=True, wait_=False)
    assert str(proc) == "foo"


def test_conditionals(capfd):
    assert sh.true.test_()
    assert not sh.false.test_()
    assert sh.test[100, '-eq', 100].test_()
    assert not sh.test._f.test_('/this/does/not/exist')
    out, err = capfd.readouterr()
    assert out == err == ''


def test_shell_mode():
    assert str(sh.echo.capture_('foo   bar', shell_=True)) == 'foo bar\n'


def test_disallowed_arguments():
    if PY3:
        with pytest.raises(ValueError):
            Process(['true'], universal_newlines=False)
    with pytest.raises(TypeError):
        sh.foo(not_a_real_argument_=True)
    with pytest.raises(ValueError):
        Process(['true'], stdout=PIPE, capture_stdout=True)
    with pytest.raises(ValueError):
        Process(['true'], stderr=PIPE, capture_stderr=True)
    Process(['true'], stdout=PIPE, capture_stderr=True)
    Process(['true'], stderr=PIPE, capture_stdout=True)


def test_command_styles():
    assert sh.foo.bar.baz == sh.foo['bar']['baz'] == sh['foo', 'bar', 'baz']
    assert sh.foo[3] == sh['foo', '3']
    assert sh.true('foo').args == sh.true.foo().args


def test_prepared_opts():
    alt = Command(opts={'stdout': sh.PIPE_}, wait=False)
    proc = alt.sh(c="sleep 0.1; echo foo")
    assert proc.poll() is None
    assert str(proc) == 'foo\n'
    assert proc.poll() is not None
    assert alt.true.pipe_().true().stdout is not None
    assert alt.true.pipe_().true.pipe_().true().stdout is not None


if sys.version_info >= (3, 3):
    def test_dir():
        orig = set(object.__dir__(sh))
        expanded = set(dir(sh))
        assert orig <= expanded
        assert {'true', 'false', 'cat', 'tac', 'python'} < expanded
