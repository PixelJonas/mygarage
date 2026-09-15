"""Unit tests for financing record schemas."""

import datetime as dt
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.financing import (
    FinancingRecordCreate,
    FinancingRecordResponse,
    FinancingRecordUpdate,
)


def test_financing_record_create_accepts_valid_category():
    record = FinancingRecordCreate(
        vin="1HGBH41JXMN109186",
        date=dt.date(2026, 1, 1),
        amount=Decimal("450.00"),
        category="lease_payment",
    )
    assert record.category == "lease_payment"
    assert record.tax_amount is None


def test_financing_record_create_rejects_invalid_category():
    with pytest.raises(ValidationError):
        FinancingRecordCreate(
            vin="1HGBH41JXMN109186",
            date=dt.date(2026, 1, 1),
            amount=Decimal("450.00"),
            category="not_a_real_category",
        )


def test_financing_record_create_rejects_negative_amount():
    with pytest.raises(ValidationError):
        FinancingRecordCreate(
            vin="1HGBH41JXMN109186",
            date=dt.date(2026, 1, 1),
            amount=Decimal("-1.00"),
            category="loan_payment",
        )


def test_financing_record_update_all_fields_optional():
    update = FinancingRecordUpdate()
    assert update.amount is None
    assert update.category is None


def test_financing_record_response_from_attributes():
    class _FakeORMRecord:
        id = 1
        vin = "1HGBH41JXMN109186"
        date = dt.date(2026, 1, 1)
        amount = Decimal("450.00")
        tax_amount = None
        category = "lease_payment"
        vendor_id = None
        notes = None
        created_at = dt.datetime(2026, 1, 1, 10, 0, 0)
        updated_at = None

    response = FinancingRecordResponse.model_validate(_FakeORMRecord())
    assert response.id == 1
    assert response.category == "lease_payment"
