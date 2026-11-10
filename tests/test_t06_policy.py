"""Pure retry bounds and deliberately restricted trace carrier validation."""

import pytest

from fieldops.trace_context import TraceContext
from fieldops.worker import retry_delay

PARENT = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"


@pytest.mark.parametrize(
    "attempt,delay", [(0, 2), (1, 2), (2, 4), (3, 8), (4, 16), (5, 30), (999, 30)]
)
def test_retry_bounds(attempt, delay):
    assert retry_delay(attempt) == delay


@pytest.mark.parametrize(
    "parent",
    [
        None,
        "",
        "secret-user-text",
        PARENT.upper(),
        PARENT.replace("00-", "ff-", 1),
        PARENT[:-2] + "zz",
        "00-" + "0" * 32 + "-0123456789abcdef-01",
        "00-0123456789abcdef0123456789abcdef-" + "0" * 16 + "-01",
        PARENT + "\n",
    ],
)
def test_invalid_parent_is_ignored(parent):
    assert TraceContext.parse(parent, "fieldops=0123456789abcdef") == TraceContext()


@pytest.mark.parametrize(
    "state",
    [
        None,
        "",
        "user=private-data",
        "fieldops=private-data",
        "fieldops=" + "a" * 513,
        "fieldops=0123456789abcdef\n",
    ],
)
def test_untrusted_state_is_dropped(state):
    assert TraceContext.parse(PARENT, state) == TraceContext(PARENT)


def test_allowed_opaque_context():
    assert TraceContext.parse(PARENT, "fieldops=0123456789abcdef") == TraceContext(
        PARENT, "fieldops=0123456789abcdef"
    )
