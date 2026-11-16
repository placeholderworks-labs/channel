import time


class PendingCall:
    __slots__ = ("ref_id", "reference_id", "phone_no", "queued_at", "connected")

    def __init__(self, ref_id: str, reference_id: str, phone_no: str):
        self.ref_id = ref_id
        self.reference_id = reference_id
        self.phone_no = phone_no
        self.queued_at = time.monotonic()
        self.connected = False
