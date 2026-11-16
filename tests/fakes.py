from pw_channel.core import registry
from pw_channel.core.channel import Channel, ChannelError, ChannelResult, ChannelTask
from pw_sdk.contracts.outcomes import TaskOutcome
from pw_sdk import Adapter, CustomerRecord, OutcomeEvent, map_batch


class FakeChannel(Channel):
    def __init__(self, name: str, result: str = "waiting", outcome: TaskOutcome = TaskOutcome.SENT, fail: bool = False):
        self.name = name
        self.result = result
        self.outcome = outcome
        self.fail = fail
        self.calls: list[ChannelTask] = []

    async def execute(self, task: ChannelTask) -> ChannelResult:
        self.calls.append(task)
        if self.fail:
            raise ChannelError("provider down")
        ref = f"{self.name}-{task.task_id}-{len(self.calls)}"
        if self.result == "done":
            return ChannelResult.done(self.outcome, ref)
        return ChannelResult.waiting(ref, outcome=self.outcome)


def install_fakes(**overrides) -> dict[str, FakeChannel]:
    registry.reset()
    fakes = {
        "voice": FakeChannel("voice", "waiting", None),
        "whatsapp": FakeChannel("whatsapp"),
        "email": FakeChannel("email"),
    }
    fakes.update(overrides)
    for fake in fakes.values():
        registry.register(fake)
    return fakes


def record(reference: str = "CART-1", phone: str = "+919812345678", email: str | None = "asha@example.com", **extra) -> CustomerRecord:
    data = {
        "ref": {"reference_id": reference},
        "customer": {"name": "Asha", "phone": phone, "email": email},
        "journey": {"stage": "payment_pending", "resume_url": "https://shop.example.com/r/" + reference},
        "cart": {"currency": "INR", "total": 15400, "items": [{"item_id": "f1", "type": "flight", "title": "Delhi to Goa"}]},
    }
    data.update(extra)
    return CustomerRecord.model_validate(data)


class DemoCartAdapter(Adapter):
    name = "demo.cart"
    version = "2.1.0"

    def transform_records(self, payload, ctx):
        def build(raw, index):
            if raw.get("boom"):
                raise RuntimeError("adapter bug")
            return CustomerRecord.model_validate({
                "ref": {"reference_id": raw["cart_id"]},
                "customer": {"name": raw.get("name", ""), "phone": raw.get("mobile")},
                "cart": {"currency": "INR", "total": raw.get("total", 0)},
            })
        if isinstance(payload, dict) and payload.get("explode"):
            raise RuntimeError("whole batch broke")
        if isinstance(payload, dict) and payload.get("hang"):
            import time

            time.sleep(2)
        return map_batch(payload, build)

    def transform_events(self, payload, ctx):
        return map_batch(payload, lambda raw, index: OutcomeEvent.model_validate(raw))
