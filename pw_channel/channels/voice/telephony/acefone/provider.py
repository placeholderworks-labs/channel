import asyncio
import logging

import httpx

from pw_channel import config
from pw_channel.channels.voice.telephony import lifecycle
from pw_channel.channels.voice.telephony.acefone.ids import encode_custom_identifier
from pw_channel.channels.voice.telephony.base import CallRef, DialRequest, DialResult, TelephonyError, TelephonyProvider
from pw_channel.channels.voice.telephony.tracker import record_origination
from pw_sdk.utils import http
from pw_sdk.utils.auth import authorization_value

logger = logging.getLogger(__name__)

TRANSFER_OPERATION = 4
REFUSED = (False, "false", "False")


class AcefoneTelephony(TelephonyProvider):
    name = "acefone"
    supports_outbound = True
    supports_transfer = True

    def _base(self) -> str:
        return config.ACEFONE_API_BASE.rstrip("/")

    def _headers(self) -> dict:
        if not config.ACEFONE_AUTH_TOKEN:
            raise TelephonyError("ACEFONE_AUTH_TOKEN is not configured", retryable=False)
        return {"Content-Type": "application/json", "Accept": "application/json",
                "Authorization": authorization_value(config.ACEFONE_AUTH_TOKEN)}

    def websocket_endpoint(self):
        from pw_channel.channels.voice.routes.ws import ws_acefone

        return ws_acefone

    async def place_call(self, request: DialRequest) -> DialResult:
        if not config.ACEFONE_API_KEY:
            raise TelephonyError("Acefone outbound needs ACEFONE_API_KEY", retryable=False)
        number = self.dial_number(request.phone_e164)
        payload = {
            "customer_number": number,
            "api_key": config.ACEFONE_API_KEY,
            "async": 1,
            "custom_identifier": encode_custom_identifier(request.reference_id, request.customer_name),
        }
        if config.ACEFONE_CALLER_ID:
            payload["caller_id"] = config.ACEFONE_CALLER_ID
        if config.ACEFONE_RING_TIMEOUT:
            payload["customer_ring_timeout"] = config.ACEFONE_RING_TIMEOUT
        if config.ACEFONE_CALL_TIMEOUT:
            payload["call_timeout"] = config.ACEFONE_CALL_TIMEOUT
        try:
            response = await http.request("POST", f"{self._base()}/click_to_call_support", json=payload,
                                          headers=self._headers(), retries=0, timeout=15.0)
        except httpx.HTTPError as error:
            raise TelephonyError(f"Acefone unreachable: {error}") from error
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}
        if response.status_code in (401, 403):
            raise TelephonyError(f"Acefone refused the credentials ({response.status_code})", retryable=False)
        if response.is_error:
            raise TelephonyError(f"Acefone API {response.status_code}: {body}", retryable=response.status_code >= 500)
        if isinstance(body, dict) and body.get("success") in REFUSED:
            raise TelephonyError(f"Acefone rejected the call: {body.get('message') or body}")
        ref_id = (body.get("ref_id") if isinstance(body, dict) else "") or ""
        logger.info(f"[acefone] call originated ref_id={ref_id} reference_id={request.reference_id}")
        record_origination(ref_id=ref_id or "unknown", reference_id=request.reference_id, phone_no=number,
                           wait_secs=(config.ACEFONE_RING_TIMEOUT or 30) + 15)
        session_id = None
        if ref_id:
            session_id = await asyncio.to_thread(
                lifecycle.opened, ref_id=ref_id, phone_no=number, booking_reference_id=request.reference_id,
                customer_name=request.customer_name, channel=self.name, task_id=request.task_id,
            )
        return DialResult(provider_ref=ref_id or f"acefone:{request.idempotency_key}", session_id=session_id,
                          raw=body if isinstance(body, dict) else {})

    async def transfer(self, call: CallRef, destination: str) -> dict:
        intercom = self.dial_number(destination if destination.startswith("+") else f"+91{destination[-10:]}")
        attempts, seen, failures = [], set(), []
        for name, value in (("ref_id", call.ref_id), ("call_id", call.call_id), ("uuid", call.call_uuid)):
            value = (value or "").strip()
            if value and value not in seen:
                seen.add(value)
                attempts.append((name, value))
        if not attempts:
            raise TelephonyError("no ref_id, call_id or uuid known for this call", retryable=False)
        for name, value in attempts:
            payload = {"type": TRANSFER_OPERATION, name: value, "intercom": intercom}
            try:
                response = await http.request("POST", f"{self._base()}/call/options", json=payload,
                                              headers=self._headers(), retries=0, timeout=10.0)
            except httpx.HTTPError as error:
                failures.append(f"{name}={value}: {error!r}")
                continue
            try:
                body = response.json()
            except ValueError:
                body = {"raw": response.text}
            refused = isinstance(body, dict) and body.get("success") in REFUSED
            if response.is_success and not refused:
                logger.info(f"[acefone] transfer accepted via {name}={value} to {intercom}")
                return {"identifier": name, "value": value, "intercom": intercom, "body": body}
            failures.append(f"{name}={value}: {(body.get('message') if isinstance(body, dict) else None) or response.status_code}")
        raise TelephonyError("; ".join(failures))

    async def live_calls(self) -> set[str] | None:
        from pw_channel.channels.voice.telephony.acefone import live_calls

        rows = await live_calls.fetch_live_calls()
        return live_calls._identifiers(rows)

    def register_routes(self) -> None:
        from pw_channel.channels.voice.telephony.acefone import webhook_routes

        webhook_routes.install_acefone_webhook_routes

    async def start(self) -> None:
        from pw_channel.channels.voice.telephony.acefone import live_calls

        await live_calls.start()

    async def stop(self) -> None:
        from pw_channel.channels.voice.telephony.acefone import live_calls

        await live_calls.stop()
