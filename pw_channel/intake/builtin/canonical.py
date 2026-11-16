from pw_sdk import Adapter, CustomerRecord, OutcomeEvent, map_batch


class CanonicalAdapter(Adapter):
    name = "builtin.canonical"
    version = "1.0.0"

    def transform_records(self, payload, ctx):
        return map_batch(payload, lambda raw, index: CustomerRecord.model_validate(raw))

    def transform_events(self, payload, ctx):
        return map_batch(payload, lambda raw, index: OutcomeEvent.model_validate(raw))
