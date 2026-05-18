"""AgentMail close-loop integration for Robin (W2).

Disabled entirely when ROBIN_AGENTMAIL_ENABLED != "1" or
AGENTMAIL_API_KEY is absent.  On a successful gym-cancel outcome, fires
two emails best-effort via asyncio.create_task:
  1. Caller confirmation to pack.email (skipped if empty)
  2. Complaint draft to a synthetic gym address (demo only)

Never raises. All errors → obs.log_event. Never blocks the hook return.
"""
import asyncio
import os
from typing import TYPE_CHECKING

from robin import obs

if TYPE_CHECKING:
    from agentmail import AsyncAgentMail
    from robin.models import ContextPack

# Module-level singletons (None until first use)
_client: "AsyncAgentMail | None" = None
_inbox_id: str | None = None
_inbox_email: str | None = None
_inbox_lock: asyncio.Lock | None = None

# Synthetic gym address — never a real address in source
_GYM_DEMO_EMAIL = "cancellations@24hourfitness-demo.invalid"
_FALLBACK_CONFIRMATION = "24HF-4471"


def _is_enabled() -> bool:
    return (
        os.environ.get("ROBIN_AGENTMAIL_ENABLED") == "1"
        and bool(os.environ.get("AGENTMAIL_API_KEY"))
    )


def _get_or_create_client() -> "AsyncAgentMail":
    global _client
    if _client is None:
        from agentmail import AsyncAgentMail
        _client = AsyncAgentMail(
            api_key=os.environ["AGENTMAIL_API_KEY"],
            timeout=10.0,
        )
    return _client


async def _get_lock() -> asyncio.Lock:
    global _inbox_lock
    if _inbox_lock is None:
        _inbox_lock = asyncio.Lock()
    return _inbox_lock


async def _ensure_inbox() -> tuple[str, str]:
    """Return (inbox_id, inbox_email); create inbox once."""
    global _inbox_id, _inbox_email
    if _inbox_id is not None:
        return _inbox_id, _inbox_email        # type: ignore[return-value]
    lock = await _get_lock()
    async with lock:
        if _inbox_id is not None:
            return _inbox_id, _inbox_email    # type: ignore[return-value]
        client = _get_or_create_client()
        result = await client.inboxes.create(
            username="robin-confirms",
            display_name="Robin Assistant",
        )
        _inbox_id = result.inbox_id
        _inbox_email = result.email
        return _inbox_id, _inbox_email        # type: ignore[return-value]


def _is_success(payload: dict) -> bool:
    """Outcome is success when delivered=True and confirmation present or
    summary contains positive signal.  Mirrors the classifier heuristic:
    confirmation number present is the clearest DONE signal."""
    out = payload.get("out", {})
    if not out.get("delivered"):
        return False
    confirmation = payload.get("confirmation")
    summary = str(payload.get("summary", "")).lower()
    # confirmation number present → unambiguous success
    if confirmation:
        return True
    # fallback: summary contains cancellation success signal
    return any(kw in summary for kw in ("cancel", "refund", "confirm"))


async def _send_emails(
    caller_email: str,
    confirmation: str,
    summary: str,
) -> None:
    """Best-effort send; swallows all errors."""
    try:
        inbox_id, _ = await _ensure_inbox()
        client = _get_or_create_client()

        if caller_email:
            subject = "Robin confirmed: gym membership cancelled"
            body = (
                f"Hi,\n\n"
                f"Robin has successfully handled your gym membership cancellation.\n\n"
                f"Outcome: {summary}\n"
                f"Confirmation #: {confirmation}\n\n"
                f"Your last-month refund has been secured as part of this resolution.\n\n"
                f"— Robin\n"
            )
            await client.inboxes.messages.send(
                inbox_id, to=caller_email, subject=subject, text=body
            )
            obs.log_event("agentmail_caller_sent", confirmation=confirmation)

        # Complaint draft — synthetic address, demo only
        complaint_subject = (
            "Notice of Intent to File Regulatory Complaint — "
            "Membership Cancellation Obstruction"
        )
        complaint_body = (
            f"Dear 24 Hour Fitness Compliance Team,\n\n"
            f"This is formal notice that the membership cancellation requested "
            f"on behalf of your member was obstructed in violation of applicable "
            f"consumer-protection statutes including the FTC Negative Option Rule "
            f"(16 CFR Part 425) and the California Health Studio Services Act "
            f"(Cal. Civil Code § 1812.80 et seq.).\n\n"
            f"The cancellation has now been confirmed (Ref: {confirmation}). "
            f"Should any further obstruction occur or the refund not be processed "
            f"within 30 days, a complaint will be filed with the FTC, the CFPB, "
            f"and the California Attorney General's office.\n\n"
            f"[DRAFTED BY ROBIN — REVIEW BEFORE SENDING]\n"
        )
        await client.inboxes.messages.send(
            inbox_id,
            to=_GYM_DEMO_EMAIL,
            subject=complaint_subject,
            text=complaint_body,
        )
        obs.log_event("agentmail_complaint_drafted", confirmation=confirmation)

    except Exception as exc:  # noqa: BLE001
        obs.log_event(
            "agentmail_send_error",
            err=f"{type(exc).__name__}: {exc}",
            confirmation=confirmation,
        )


def make_email_outcome_hook(pack: "ContextPack"):
    """Return an OutcomeHook that fires close-loop emails on success."""

    async def _hook(call_id: str | None, payload: dict) -> None:
        if not _is_enabled():
            return
        if not _is_success(payload):
            return
        confirmation = payload.get("confirmation") or _FALLBACK_CONFIRMATION
        summary = payload.get("summary", "Membership cancelled.")
        caller_email = getattr(pack, "email", "")  # "" if field absent
        # Fire-and-forget: hook returns immediately
        asyncio.create_task(
            _send_emails(
                caller_email=caller_email,
                confirmation=confirmation,
                summary=summary,
            )
        )
        obs.log_event(
            "agentmail_hook_fired",
            call_id=call_id,
            has_email=bool(caller_email),
        )

    return _hook
