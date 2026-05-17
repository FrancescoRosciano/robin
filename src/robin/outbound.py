"""Outbound tool callables. STUB — Plan 04 replaces with the real impl.

Signatures are frozen in
docs/superpowers/plans/2026-05-17-robin-00-execution-sequence.md and must
not change; Plan 03 depends only on these shapes.
"""


async def place_negotiation_call(
    phone: str, member_name: str, citations: list[dict]
) -> dict:
    raise NotImplementedError("Plan 04 provides place_negotiation_call")


async def deliver_result(
    channel: str, summary: str, confirmation: str | None
) -> dict:
    raise NotImplementedError("Plan 04 provides deliver_result")
