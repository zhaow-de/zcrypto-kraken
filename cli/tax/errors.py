"""The refusals of `zcrypto tax blockpit`: a row it cannot map, a check that fails, or an input it cannot read."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Refusal:
    txids: tuple[str, ...]
    kind: str
    reason: str

    def line(self) -> str:
        return f"refused {','.join(self.txids) or '-'} [{self.kind}]: {self.reason}"


class TaxExportError(Exception):
    pass


class Refused(Exception):
    def __init__(self, refusals: list[Refusal]):
        super().__init__(f"{len(refusals)} refusal(s)")
        self.refusals = refusals
