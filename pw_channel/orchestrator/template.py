from dataclasses import dataclass, field
from typing import Any

from pw_sdk.contracts.outcomes import TaskOutcome, expand
from pw_sdk.utils.time import parse_duration

ACTIONS = ("complete", "stop", "cancel", "pause", "reschedule", "start", "block", "ignore")
JOIN_MODES = ("all", "any")

DEFAULT_RULES = {
    "booking.confirmed": "complete",
    "payment.succeeded": "complete",
    "call.transferred": "stop",
    "call.not_interested": "stop",
    "call.callback": "reschedule:*",
    "opt_out": "block",
}


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    action: str
    target: str = ""

    @classmethod
    def parse(cls, text: str) -> "Rule":
        action, _, target = str(text).strip().partition(":")
        if action not in ACTIONS:
            raise TemplateError(f"unknown rule action {action!r}; use one of {', '.join(ACTIONS)}")
        if action in ("cancel", "reschedule", "start", "pause") and not target:
            raise TemplateError(f"rule {text!r} needs a target, e.g. {action}:<name>")
        if action == "pause":
            parse_duration(target)
        return cls(action, target)

    def text(self) -> str:
        return f"{self.action}:{self.target}" if self.target else self.action


@dataclass(frozen=True)
class StepSpec:
    key: str
    channel: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    when: frozenset[TaskOutcome] = frozenset(TaskOutcome)
    when_names: tuple[str, ...] = ()
    join: str = "all"
    delay_secs: float = 0.0
    response_window_secs: float = 0.0
    max_attempts: int = 1
    retry_delay_secs: float = 900.0

    @classmethod
    def parse(cls, data: dict) -> "StepSpec":
        try:
            key = str(data["key"]).strip()
            channel = str(data["channel"]).strip()
        except KeyError as missing:
            raise TemplateError(f"every step needs {missing.args[0]!r}") from None
        when = data.get("when") or []
        when = [when] if isinstance(when, str) else list(when)
        try:
            outcomes = expand(when)
        except ValueError as error:
            raise TemplateError(f"step {key}: {error}") from None
        join = str(data.get("join", "all"))
        if join not in JOIN_MODES:
            raise TemplateError(f"step {key}: join must be all or any")
        depends = data.get("depends_on") or []
        depends = [depends] if isinstance(depends, str) else list(depends)
        return cls(
            key=key,
            channel=channel,
            action=str(data.get("action") or ("call" if channel == "voice" else "send_template")),
            params=dict(data.get("params") or {}),
            depends_on=tuple(depends),
            when=outcomes,
            when_names=tuple(when),
            join=join,
            delay_secs=parse_duration(data.get("delay"), 0.0),
            response_window_secs=parse_duration(data.get("response_window"), 0.0),
            max_attempts=1 + int(data.get("retries", 0)),
            retry_delay_secs=parse_duration(data.get("retry_after"), 900.0),
        )


@dataclass(frozen=True)
class JourneyTemplate:
    name: str
    steps: tuple[StepSpec, ...]
    rules: dict[str, tuple[Rule, ...]]
    expires_after_secs: float = 0.0
    on_new_record: str = "merge"

    def step(self, key: str) -> StepSpec | None:
        return next((step for step in self.steps if step.key == key), None)

    def rules_for(self, kind: str) -> tuple[Rule, ...]:
        return self.rules.get(kind, ())

    @classmethod
    def parse(cls, name: str, data: dict, channels: set[str] | None = None) -> "JourneyTemplate":
        raw_steps = data.get("steps") or []
        if not raw_steps:
            raise TemplateError(f"journey {name} has no steps")
        steps = tuple(StepSpec.parse(item) for item in raw_steps)
        keys = [step.key for step in steps]
        if len(keys) != len(set(keys)):
            raise TemplateError(f"journey {name}: step keys must be unique")
        for step in steps:
            for parent in step.depends_on:
                if parent not in keys:
                    raise TemplateError(f"journey {name}: step {step.key} depends on unknown step {parent}")
            if channels is not None and step.channel not in channels:
                raise TemplateError(f"journey {name}: step {step.key} uses channel {step.channel}, which is not enabled")
        _check_acyclic(name, steps)
        merged = dict(DEFAULT_RULES)
        merged.update({str(k): v for k, v in (data.get("on") or {}).items()})
        rules = {}
        for kind, value in merged.items():
            items = value if isinstance(value, list) else [value]
            rules[kind] = tuple(Rule.parse(item) for item in items)
        for kind, items in rules.items():
            for rule in items:
                if rule.action in ("cancel", "reschedule") and rule.target != "*" and rule.target not in keys:
                    raise TemplateError(f"journey {name}: rule {kind} targets unknown step {rule.target}")
        on_new = str(data.get("on_new_record", "merge"))
        if on_new not in ("merge", "restart"):
            raise TemplateError(f"journey {name}: on_new_record must be merge or restart")
        return cls(
            name=name,
            steps=steps,
            rules=rules,
            expires_after_secs=parse_duration(data.get("expires_after"), 0.0),
            on_new_record=on_new,
        )


def _check_acyclic(name: str, steps: tuple[StepSpec, ...]) -> None:
    graph = {step.key: set(step.depends_on) for step in steps}
    done: set[str] = set()
    while graph:
        free = [key for key, parents in graph.items() if parents <= done]
        if not free:
            raise TemplateError(f"journey {name}: steps depend on each other in a loop ({', '.join(sorted(graph))})")
        for key in free:
            done.add(key)
            graph.pop(key)


SINGLE_CALL = {"steps": [{"key": "call", "channel": "voice", "action": "call"}]}


def load_templates(journeys: dict[str, dict], channels: set[str] | None = None) -> dict[str, JourneyTemplate]:
    found = {"single_call": JourneyTemplate.parse("single_call", SINGLE_CALL)}
    for name, data in (journeys or {}).items():
        found[name] = JourneyTemplate.parse(name, data, channels)
    for template in found.values():
        for rules in template.rules.values():
            for rule in rules:
                if rule.action == "start" and rule.target not in found:
                    raise TemplateError(f"journey {template.name}: rule starts unknown journey {rule.target}")
    return found
