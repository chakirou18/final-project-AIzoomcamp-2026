"""Bounded W3C carriers. Vendor state is restricted to opaque, non-user FieldOps values."""

import re
from dataclasses import dataclass

PARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})\Z")
# W3C flags may include random-trace-id/reserved bits; let the official propagator interpret them.
# Retain only our opaque vendor entry, never baggage, credentials or arbitrary free-text state.
STATE = re.compile(r"fieldops=[0-9a-f]{16,32}\Z")


@dataclass(frozen=True)
class TraceContext:
    traceparent: str | None = None
    tracestate: str | None = None

    @classmethod
    def parse(cls, traceparent: str | None, tracestate: str | None = None):
        match = PARENT.fullmatch(traceparent or "")
        if not match or int(match[1], 16) == 0 or int(match[2], 16) == 0:
            return cls()
        state = tracestate if STATE.fullmatch(tracestate or "") else None
        return cls(traceparent, state)
