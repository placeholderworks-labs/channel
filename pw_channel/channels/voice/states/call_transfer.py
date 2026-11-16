from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class TransferHandle:

    call_id: str = ""
    ref_id: str = ""
    destination: str = ""
    on_transferred: Callable[[], None] | None = None
    transferred: bool = False
    session_row_id: int | None = None
