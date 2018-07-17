mocksh is a library for shell scripting inside Python. It makes external
commands available as functions, and provides accessible ways to use their
results. It tries to copy the semantics of sh (the Bourne shell) when they
make sense in Python.

It acts as a thin layer around the
`subprocess <https://docs.python.org/3/library/subprocess.html>`_ module.

======
Basics
======

In the simplest case, a command is run until completion, and the output is
shown without being captured:

.. code-block:: python

    >>> from mocksh import sh
    >>> sh.echo("Hello, world")
    Hello, world

If the command fails, it raises an exception:

.. code-block:: python

    >>> sh.false()
    Traceback (most recent call last):
        ...
    mocksh.CommandError[1]: Command 'false' failed with status code 1

This most basic form is useful for commands that are run for their side
effects. Command output isn't captured by default, because it's often useful.
If something goes wrong, it provides extra information that an exception
doesn't know about.

----------------
Capturing output
----------------

Output can be captured with the ``capture_`` method, awkwardly inserted into
the middle, right before the arguments:

.. code-block:: python

    >>> str(sh.echo.capture_("Hello, Python"))
    'Hello, Python\n'

The process doesn't immediately return a string. You have to tell it how you
want to access the output:

.. code-block:: python

    >>> bytes(sh.dd.capture_('if=/dev/urandom', 'count=1', 'bs=16'))  # raw bytes
    b'w\xc4K\xd9\x04\xa7\x8f\x0el\xe9\xb0\xa1(\x8f\tp'
    >>> for num in sh.seq.capture_(3):  # line by line
    ...     print(num)
    1
    2
    3
    >>> list(sh.shuf.capture_('-n', 5, '/usr/share/dict/words'))
    ['upgrading', 'humongous', 'thesauri', 'candidly', 'drools']

Commands called this way return immediately, before the command is finished.
This means the output can be processed line by line without wasting memory
if the output is large.

------
Piping
------

Another special method, ``pipe_``, lets you construct pipelines:

.. code-block::

    >>> sh.fortune.pipe_().cowsay()  # Like 'fortune | cowsay'
     ______________________________________
    / Are you making all this up as you go \
    \ along?                               /
     --------------------------------------
            \   ^__^
             \  (oo)\_______
                (__)\       )\/\
                    ||----w |
                    ||     ||

The next command in the pipeline is called like a method, the same way you
would call a command on the ``sh`` object.

This can naturally be combined with ``capture_``:

.. code-block:: python

    >>> str(sh.fortune.pipe_().rot13.capture_())  # Like 'fortune | rot13'
    'Lbhe cerfrag cynaf jvyy or fhpprffshy.\n'

-------
Testing
-------

By default, commands raise an exception if they fail, but that's not always
desirable. Sometimes you just want to test whether a command succeeded. The
``test_`` special method can be used for that:

.. code-block:: python

    >>> if sh.ping.test_('-c', 1, 'fake.domain'):
    ...     print("fake.domain is up")
    ... else:
    ...     print("fake.domain is down")
    ping: fake.domain: Name or service not known
    fake.domain is down

==========
Installing
==========

::

    $ pip install mocksh

Because the module is only a single file, you could also just dump
``mocksh.py`` into your scripts folder.

==============
Advanced usage
==============

--------------------
Other argument forms
--------------------

Some commands have subcommands. For example, ``git`` has ``git status`` and
``git commit``. They can be separated by a dot:

.. code-block:: python

    >>> sh.git.status()
    On branch master
    ...

Underscores in command names are converted to dashes, because many commands
have dashes in their names but Python doesn't allow dashes in its names. To
run a command that does have an underscore in its name, or any weird
characters, you can use indexing syntax:

.. code-block:: python

    >>> sh.units_cur()  # Doesn't work, converted to units-cur
    Traceback (most recent call last):
    ...
    FileNotFoundError: [Errno 2] No such file or directory: 'units-cur': 'units-cur'
    >>> sh['units_cur']()  # works
    ...
    >>> sh.sudo['units_cur']()
    ...

You can also index with multiple arguments. This gives an easy way of
defining aliases:

.. code-block:: python

    >>> lh = sh.ls['-l', '-h']
    >>> lh('/')
    total 16K
    drwxr-xr-x   1 root root 2.4K Jul 14 08:26 bin
    ...

---------------
Command options
---------------

Options can be passed either as regular arguments or as keyword arguments:

.. code-block:: python

    >>> sh.curl('-L', '--data', 'test', 'httpbin.org/post')  # wordy, but transparent
    ...
    >>> sh.curl('httpbin.org/post', L=True, data='test')     # fancy, but opaque
    ...

Both examples are exactly equivalent, and generate the same command.

Options are processed according to a few rules.

* Options that are one character long are short options, others are long
  options. This means ``v`` is translated to ``-v``, but ``verbose`` is
  translated to ``--verbose``.
* Underscores ( ``_`` ) are translated to dashes ( ``-`` ). This is because
  Python does not allow dashes in keyword arguments. ``cookie_jar`` becomes
  ``--cookie-jar``.
* If the value of the argument is ``False``, it's discarded. If the value is
  ``True``, only the flag is added. Otherwise, the key and the value are
  both added. ``L=True`` becomes ``-L``, and ``data='test'`` becomes
  ``--data test``.
* For long options that nevertheless take a single dash, you can start the
  argument with a dash. ``java -jar ...`` can be expressed as
  ``sh.java(_jar=...)``
* Options are inserted after the command name and before the other arguments.

This is enough to deal with most programs. But if it doesn't do what you
want, sticking to the simple, dependable form is always a good option.

---------------
Special options
---------------

Keyword arguments that end with an underscore aren't added to the command,
but used for special behavior. ``mocksh`` has a few special keyword
arguments, and any others are forwarded to ``subprocess`` (without the
underscore).

For example, to append command output to a file:

.. code-block:: python

    >>> with open('log.txt', 'a') as f:  # rsync -Pr somedir somehost: >> log.txt
    ...     sh.rsync('-Pr', 'somedir', 'somehost:', stdout_=f)  # stdout_, not stdout

That's roughly equivalent to this use of ``subprocess``:

.. code-block:: python

    >>> import subprocess
    >>> with open('log.txt', 'a') as f:
    ...     subprocess.run(['rsync', '-Pr', 'somedir', 'somehost:'], stdout=f)

In addition to the arguments of `subprocess.Popen <https://docs.python.org/3/library/subprocess.html#subprocess.Popen>`_,
mocksh supports the following arguments:

* ``check``: Whether to automatically raise an exception if the command
  fails. ``True`` by default.
* ``input``: String or bytes to be sent to the standard input of the command.
* ``wait``: Whether to wait until the command is finished before returning.
  To run a command in the background, add ``wait_=False``.
* ``timeout``: Optionally, how many seconds to wait before raising a
  ``subprocess.TimeoutExpred`` exception.
* ``capture_stdout``: If ``True``, capture the standard output of the command.
  ``capture_stdout_=True`` is equivalent to ``stdout_=sh.PIPE_``.
* ``capture_stderr``: Likewise, but for stderr. If only stderr is captured,
  converting the command to a string will give the stderr output.

---------------
Process objects
---------------

Commands return ``mocksh.Process`` objects, a subclass of
``subprocess.Popen``. It can be used like a regular instance of ``Popen``,
but has additional features, most of which are covered by other sections.

A process in a pipeline will have a ``tail`` attribute, set to the previous
command in the pipeline. If the process at the start of the pipeline has an
open ``stdin``, its ``stdin`` attribute is set to that.

``Process.wait`` is pipeline-aware, and will wait for the entire pipeline to
finish, with proper timeout handling.

The ``Process.check_returncode`` method raises a ``CommandError`` even if
``check=False``, for manual checking.

The ``captured`` property points to ``stdout`` if it's captured, or
``stderr`` if that's captured. If both are captured, ``stdout`` and
``stderr`` have to be addressed directly.

---------------------
Asynchronous commands
---------------------

Commands can be run in the background by adding ``wait_=False`` to the
argument list.

To make sure they finish, they can be used as a context manager:

.. code-block:: python

    >>> with sh.wget('some.large/file.ext'):
    ...     something_else()
    ... # wget is now guaranteed to have finished, and would have thrown an
    ... # exception if it failed
    ... use('file.ext')

Because ``capture_`` also runs processes in the background, you can wait
with gathering the output until later. You could loop through its lines:

.. code-block:: python

    >>> for line in sh.long_process():
    ...     process(line)

Or you could collect it all in one go:

.. code-block:: python

    >>> proc = sh.expensive_computation()
    >>> # do things
    >>> output = str(proc)

------------------
Exception handling
------------------

Commands that fail raise a ``CommandError``.

As a convenience for ``from mocksh import sh``, the exception type is
accessible as ``sh.CommandError_`` (note the underscore).

The exception is subclassed for different return codes and signals.
Subclasses can be accessed with the ``code`` classmethod. For example:

.. code-block:: python

    >>> try:
    ...     sh.false()
    ... except sh.CommandError_.code(10):
    ...     print("Exited with 10")
    ... except sh.CommandError_.code(1):
    ...     print("Exited with 1")
    Exited with 1

Signals can be referred to by name:

.. code-block:: python

    >>> try:
    ...     sh.tcc('-run', '-', input_='#include <stdio.h> int main() { puts(0); }')
    ... except sh.CommandError_.code('SIGSEGV'):
    ...     ...

---------------
Command objects
---------------

``sh`` is a ``mocksh.Command`` object. Commands like ``sh.echo`` and
``sh.ls['-l', '-h']`` are also ``Command`` objects.

``Command`` objects can contain a prepared set of arguments for ``Process``.
This is how piping is implemented: ``_pipe`` returns a new ``Command``
object with ``tail`` set to the last ``Process``.

If you're tired of typing ``.capture_`` all the time, you could
create your own launcher like this:

.. code-block:: python

    >>> import mocksh
    >>> mysh = mocksh.Command(capture_stdout=True, wait=False)
    >>> str(mysh.echo('test'))
    'test\n'

-------------------------------------
Why you should use subprocess instead
-------------------------------------

mocksh is a leaky abstraction. It pretends external processes are Python
functions, but external processes don't behave like Python functions at all.
It tries to copy sh's semantics, but sh's semantics are incompatible with
Python's syntax.

In most cases you're better off using ``subprocess`` directly, through a
nice interface like `subprocess.run <https://docs.python.org/3/library/subprocess.html#subprocess.run>`_.
It will be easier to reason about because it doesn't hide what's getting
executed.

----------------
Similar projects
----------------

* `sh <http://amoffat.github.io/sh/>`_ (unrelated to other uses of the word
  ``sh`` in this document)
* `plumbum <https://plumbum.readthedocs.io/>`_
