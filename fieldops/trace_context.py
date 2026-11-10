"""Conservative trace carriers, without exporters or recording application data."""

import re
from dataclasses import dataclass

PARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-(00|01)\Z")
# Until T09 owns vendor propagation, accept only our opaque vendor entry. No baggage/free text.
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
