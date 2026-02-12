"""Root conftest: neutralize multiprocessing.set_start_method for mutmut compatibility.

mutmut 3.x trampolines import mutmut.__main__ which calls
multiprocessing.set_start_method('fork') at module scope. When __main__
is re-imported during stats collection (e.g. from a mutated module's
trampoline), the redundant call raises RuntimeError. This conftest
patches set_start_method to tolerate redundant calls.
"""

import multiprocessing
from contextlib import suppress

_orig = multiprocessing.set_start_method


def _safe_set_start_method(method, force=False):
    with suppress(RuntimeError):
        _orig(method, force=force)


multiprocessing.set_start_method = _safe_set_start_method
