"""Tests for spec parsing, validation, and wire format conversion."""

from __future__ import annotations

from tasker_cli.specs import (
    ArgType,
    SpecsCache,
    action_def_to_wire,
    validate_task_actions,
)


class TestSpecsParsing:
    """Test that recorded fixtures parse correctly with real field names."""

    def test_categorycode_field_parsed(self, specs_cache: SpecsCache) -> None:
        """Real specs use 'categoryCode', not 'category'."""
        flash = specs_cache.find_action("Flash")
        assert flash is not None
        assert flash.code == 548
        assert flash.category == 10  # Alert

        vs = specs_cache.find_action("Variable Set")
        assert vs is not None
        assert vs.category == 120  # Variables


class TestValidation:
    """Test task definition validation against real specs."""

    def test_unknown_action(self, specs_cache: SpecsCache) -> None:
        task_def = {"actions": [{"action": "Nonexistent Action", "args": {}}]}
        errors = validate_task_actions(task_def, specs_cache)
        assert len(errors) == 1
        assert "Unknown action" in errors[0].message

    def test_unknown_arg(self, specs_cache: SpecsCache) -> None:
        task_def = {
            "actions": [{"action": "Flash", "args": {"Text": "Hi", "FakeArg": "x"}}]
        }
        errors = validate_task_actions(task_def, specs_cache)
        assert len(errors) == 1
        assert "Unknown arg: FakeArg" in errors[0].message

    def test_missing_mandatory_arg(self, specs_cache: SpecsCache) -> None:
        task_def = {"actions": [{"action": "Variable Set", "args": {"Name": "%x"}}]}
        errors = validate_task_actions(task_def, specs_cache)
        missing = [e.message for e in errors if "Missing required arg" in e.message]
        assert any("To" in m for m in missing)

    def test_bundle_args_not_required(self, specs_cache: SpecsCache) -> None:
        """Bundle (type 5) args are output-only — validation must skip them."""
        adb_wifi = specs_cache.find_action("ADB Wifi")
        assert adb_wifi is not None
        bundle_args = [a for a in adb_wifi.args if a.arg_type == ArgType.BUNDLE]
        assert bundle_args[0].mandatory is True  # Marked mandatory in spec

        task_def = {
            "actions": [
                {
                    "action": "ADB Wifi",
                    "args": {"Command": "ls", "Timeout (Seconds)": "10"},
                },
            ]
        }
        errors = validate_task_actions(task_def, specs_cache)
        assert not any("Output Variables" in e.message for e in errors)


class TestWireFormat:
    """Test conversion to WebUI wire format."""

    def test_boolean_coercion_from_string(self, specs_cache: SpecsCache) -> None:
        """WebUI rejects string booleans — must be native JSON bools."""
        wire = action_def_to_wire(
            {"action": "Flash", "args": {"Text": "Hi", "Long": "true"}},
            specs_cache,
        )
        long_arg = next(a for a in wire["action"]["args"] if a["id"] == 1)
        assert long_arg["value"] is True

    def test_boolean_false_string(self, specs_cache: SpecsCache) -> None:
        wire = action_def_to_wire(
            {"action": "Flash", "args": {"Text": "Hi", "Long": "false"}},
            specs_cache,
        )
        long_arg = next(a for a in wire["action"]["args"] if a["id"] == 1)
        assert long_arg["value"] is False

    def test_condition_passthrough(self, specs_cache: SpecsCache) -> None:
        condition = [{"e": "%BATT", "b": "LessThan", "f": "20"}]
        wire = action_def_to_wire(
            {"action": "Flash", "args": {"Text": "Low!"}, "condition": condition},
            specs_cache,
        )
        assert wire["action"]["condition"] == condition

    def test_empty_args_control_flow(self, specs_cache: SpecsCache) -> None:
        """Control flow actions (Else, End If) have no args."""
        wire = action_def_to_wire({"action": "Else"}, specs_cache)
        assert wire["action"]["args"] == []
        assert wire["action"]["code"] == 43

    def test_wraps_in_action_key(self, specs_cache: SpecsCache) -> None:
        """WebUI PATCH/POST requires {"action": {...}} wrapping."""
        wire = action_def_to_wire(
            {"action": "Flash", "args": {"Text": "Hi"}}, specs_cache
        )
        assert "action" in wire
        assert wire["action"]["code"] == 548
