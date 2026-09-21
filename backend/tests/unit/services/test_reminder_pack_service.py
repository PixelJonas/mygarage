"""Unit tests for reminder pack loading from the shipped JSON files.

Against `builtin_summaries` / `builtin_pack` rather than `list_packs` /
`get_pack`: since saved packs landed, the public pair is async and reads the
database, and none of the path hardening below has anything to do with a
database. The merged behaviour (both sources in one list, `custom-` routing) is
covered in `tests/integration/routes/test_saved_reminder_packs.py`.
"""

import json

import pytest
from fastapi import HTTPException

from app.services import reminder_pack_service
from app.services.reminder_pack_service import builtin_pack, builtin_summaries


@pytest.mark.unit
class TestReminderPackService:
    def test_list_packs_includes_builtins(self):
        packs = builtin_summaries()
        ids = {p.id for p in packs}
        assert "oil_and_filter" in ids
        assert "tire_rotation" in ids
        assert "boat_winterization" in ids
        assert "atv_utv_service" in ids
        assert "snowmobile_season" in ids
        assert "diy_oil_change" not in ids

    def test_list_packs_filters_by_vehicle_type(self):
        boat_packs = builtin_summaries(vehicle_type="Boat")
        boat_ids = {p.id for p in boat_packs}
        assert "boat_winterization" in boat_ids
        assert "oil_and_filter" not in boat_ids

        car_packs = builtin_summaries(vehicle_type="Car")
        car_ids = {p.id for p in car_packs}
        assert "oil_and_filter" in car_ids
        assert "boat_winterization" not in car_ids
        assert "atv_utv_service" not in car_ids

    def test_get_pack_oil_and_filter(self):
        pack = builtin_pack("oil_and_filter")
        assert pack.name
        assert len(pack.reminders) >= 1
        assert pack.reminders[0].title == "Oil & Filter Change"
        # v2 pack format: intervals and a canonical type, not absolute offsets.
        assert pack.reminders[0].maintenance_type == "engine_oil_filter"
        assert pack.reminders[0].interval_months == 6
        assert pack.reminders[0].interval_km == 8000
        assert pack.reminders[0].key == "oil_filter"
        assert any(r.title == "Inspect Drain Plug Washer" for r in pack.reminders)
        assert "Car" in pack.vehicle_types

    def test_get_pack_rejects_path_traversal(self):
        for pack_id in (
            "../oil_and_filter",
            "../../etc/passwd",
            "/etc/passwd",
            "oil_and_filter/../oil_and_filter",
            "foo.json\x00",
        ):
            with pytest.raises(HTTPException) as exc:
                builtin_pack(pack_id)
            assert exc.value.status_code == 404


@pytest.mark.unit
class TestReminderPackLookup:
    """Cover the index-based lookup, including the branch real packs never hit.

    All three shipped packs declare an id equal to their filename stem, so the
    declared-id fallback in ``get_pack`` is dead against real data. These tests
    drive it with a temp packs dir.
    """

    @staticmethod
    def _write(dirpath, filename, payload):
        (dirpath / filename).write_text(json.dumps(payload), encoding="utf-8")

    def test_finds_pack_whose_filename_differs_from_declared_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", tmp_path)
        self._write(
            tmp_path,
            "renamed_file.json",
            {"id": "declared_id", "name": "Declared", "description": "d", "reminders": []},
        )

        # Filename stem misses, so the declared-id scan has to find it.
        pack = builtin_pack("declared_id")
        assert pack.id == "declared_id"
        assert pack.name == "Declared"

    def test_filename_hit_declaring_a_different_id_is_404(self, tmp_path, monkeypatch):
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", tmp_path)
        self._write(
            tmp_path,
            "on_disk.json",
            {"id": "something_else", "name": "N", "description": "d", "reminders": []},
        )

        with pytest.raises(HTTPException) as exc:
            builtin_pack("on_disk")
        assert exc.value.status_code == 404

    def test_unreadable_filename_hit_is_500_not_404(self, tmp_path, monkeypatch):
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", tmp_path)
        (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")

        with pytest.raises(HTTPException) as exc:
            builtin_pack("broken")
        assert exc.value.status_code == 500

    def test_malformed_pack_does_not_break_builtin_summaries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", tmp_path)
        (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
        self._write(
            tmp_path,
            "good.json",
            {"id": "good", "name": "Good", "description": "d", "reminders": []},
        )

        assert [p.id for p in builtin_summaries()] == ["good"]

    def test_symlink_escaping_packs_dir_is_not_loaded(self, tmp_path, monkeypatch):
        packs = tmp_path / "packs"
        packs.mkdir()
        outside = tmp_path / "outside.json"
        self._write(
            tmp_path,
            "outside.json",
            {"id": "outside", "name": "Outside", "description": "d", "reminders": []},
        )
        (packs / "escape.json").symlink_to(outside)
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", packs)

        # resolve() follows the link before the containment check, so the
        # target lands outside PACKS_DIR and is dropped from the index.
        assert builtin_summaries() == []
        with pytest.raises(HTTPException) as exc:
            builtin_pack("escape")
        assert exc.value.status_code == 404


@pytest.mark.unit
class TestReminderPackFormatV1:
    """A pack written for v3.4 (absolute offsets, reminder_type) still loads."""

    def test_v1_keys_map_onto_intervals(self, tmp_path, monkeypatch):
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", tmp_path)
        (tmp_path / "legacy.json").write_text(
            json.dumps(
                {
                    "id": "legacy",
                    "name": "Legacy",
                    "description": "d",
                    "reminders": [
                        {
                            "title": "Oil & Filter Change",
                            "reminder_type": "smart",
                            "due_mileage_km": 8000,
                            "due_date_offset_days": 180,
                            "due_hours": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        pack = builtin_pack("legacy")
        item = pack.reminders[0]
        assert item.interval_km == 8000
        assert item.interval_days == 180
        assert item.interval_hours is None
        assert item.interval_months is None
        assert item.key == "oil_filter_change"
        assert item.maintenance_type is None

    def test_item_without_any_interval_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(reminder_pack_service, "PACKS_DIR", tmp_path)
        (tmp_path / "empty.json").write_text(
            json.dumps(
                {
                    "id": "empty",
                    "name": "Empty",
                    "description": "d",
                    "reminders": [{"title": "Nothing", "reminder_type": "date"}],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(HTTPException) as exc:
            builtin_pack("empty")
        assert exc.value.status_code == 500
