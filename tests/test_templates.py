import pytest

from pw_channel.orchestrator.template import JourneyTemplate, TemplateError, load_templates
from pw_sdk.contracts.outcomes import TaskOutcome

CART = {
    "steps": [
        {"key": "whatsapp", "channel": "whatsapp", "action": "send_template", "params": {"template": "t"},
         "delay": "5m", "response_window": "30m"},
        {"key": "call", "channel": "voice", "depends_on": ["whatsapp"], "when": ["no_response"], "retries": 2},
        {"key": "email", "channel": "email", "depends_on": "call", "when": ["no_answer", "failed"], "delay": "2h"},
    ],
    "on": {"whatsapp.replied": "cancel:call", "link.clicked": "pause:30m", "payment.failed": "start:single_call"},
}


def test_parse_steps_and_defaults():
    template = JourneyTemplate.parse("cart_recovery", CART)
    call = template.step("call")
    assert template.step("whatsapp").delay_secs == 300 and template.step("whatsapp").response_window_secs == 1800
    assert call.action == "call" and call.max_attempts == 3 and call.when == {TaskOutcome.NO_RESPONSE}
    assert template.step("email").depends_on == ("call",)
    assert [r.text() for r in template.rules_for("booking.confirmed")] == ["complete"]
    assert [r.text() for r in template.rules_for("link.clicked")] == ["pause:30m"]


@pytest.mark.parametrize("steps,message", [
    ([], "no steps"),
    ([{"key": "a", "channel": "voice"}, {"key": "a", "channel": "voice"}], "unique"),
    ([{"key": "a", "channel": "voice", "depends_on": ["x"]}], "unknown step"),
    ([{"key": "a", "channel": "voice", "depends_on": ["b"]}, {"key": "b", "channel": "voice", "depends_on": ["a"]}], "loop"),
    ([{"key": "a", "channel": "voice", "when": ["sometimes"]}], "not a valid"),
    ([{"key": "a", "channel": "voice", "join": "most"}], "join"),
])
def test_invalid_templates(steps, message):
    with pytest.raises(TemplateError, match=message):
        JourneyTemplate.parse("bad", {"steps": steps})


def test_rules_are_checked():
    with pytest.raises(TemplateError, match="unknown step"):
        JourneyTemplate.parse("bad", {"steps": [{"key": "a", "channel": "voice"}], "on": {"x": "cancel:nope"}})
    with pytest.raises(TemplateError, match="unknown rule action"):
        JourneyTemplate.parse("bad", {"steps": [{"key": "a", "channel": "voice"}], "on": {"x": "explode"}})
    with pytest.raises(TemplateError, match="unknown journey"):
        load_templates({"j": {"steps": [{"key": "a", "channel": "voice"}], "on": {"x": "start:missing"}}})


def test_channel_must_be_enabled():
    with pytest.raises(TemplateError, match="not enabled"):
        JourneyTemplate.parse("j", {"steps": [{"key": "a", "channel": "sms"}]}, {"voice"})
    assert "single_call" in load_templates({"cart_recovery": CART}, {"voice", "whatsapp", "email"})
