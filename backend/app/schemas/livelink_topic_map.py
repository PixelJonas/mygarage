"""Schemas for the topic-map admin API."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TopicMapBase(BaseModel):
    """Fields shared by create and update."""

    device_id: str = Field(..., max_length=20)
    topic: str = Field(..., max_length=255)
    role: Literal["telemetry", "status"] = "telemetry"
    param_key: str | None = Field(None, max_length=100)
    value_path: str | None = Field(None, max_length=100)
    unit: str | None = Field(None, max_length=20)
    param_class: str | None = Field(None, max_length=50)
    scale: Decimal = Decimal(1)
    value_offset: Decimal = Decimal(0)
    enabled: bool = True

    @field_validator("topic")
    @classmethod
    def reject_wildcards(cls, v: str) -> str:
        """Mapped topics are exact. See LiveLinkTopicMap's docstring."""
        if "+" in v or "#" in v:
            raise ValueError("Mapped topics must be exact; + and # are not allowed")
        return v

    @field_validator("param_key")
    @classmethod
    def canonicalize(cls, v: str | None) -> str | None:
        """Match the uppercase canonicalization every ingest path applies."""
        return v.upper().replace(" ", "_") if v else v

    @model_validator(mode="after")
    def param_key_required_for_telemetry(self) -> TopicMapBase:
        """Only a status row may omit param_key."""
        if self.role == "telemetry" and not self.param_key:
            raise ValueError("param_key is required when role is 'telemetry'")
        return self


class TopicMapCreate(TopicMapBase):
    """Request body for POST."""


class TopicMapUpdate(BaseModel):
    """Request body for PATCH. Every field optional."""

    model_config = ConfigDict(extra="forbid")

    param_key: str | None = None
    value_path: str | None = None
    unit: str | None = None
    param_class: str | None = None
    scale: Decimal | None = None
    value_offset: Decimal | None = None
    enabled: bool | None = None


class TopicMapResponse(TopicMapBase):
    """One stored row."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class TopicDiscoveryRequest(BaseModel):
    """Body for a discovery run."""

    prefix: str = Field(..., max_length=255)
    seconds: int = Field(15, ge=1, le=60)


class PresetApplyRequest(BaseModel):
    """Body for applying a named device preset."""

    device_id: str = Field(..., max_length=20)
    vin: str | None = Field(None, min_length=17, max_length=17)
