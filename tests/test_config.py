import pytest

from purdue_seat_watch.config import ConfigError, load_config


def test_load_config_parses_watches_and_notifier(tmp_path):
    config_file = tmp_path / "watches.yaml"
    config_file.write_text(
        """
interval_seconds: 30
notifier: macos
watches:
  - term: "202710"
    subject: CS
    course_number: "50200"
    section: LE1
  - term: "202710"
    subject: CS
    course_number: "18000"
"""
    )

    config, notifier_name = load_config(config_file)

    assert notifier_name == "macos"
    assert config.interval_seconds == 30
    assert len(config.watches) == 2
    assert config.watches[0].section == "LE1"
    assert config.watches[1].section is None


def test_load_config_defaults_interval_and_notifier(tmp_path):
    config_file = tmp_path / "watches.yaml"
    config_file.write_text(
        """
watches:
  - term: "202710"
    subject: CS
    course_number: "50200"
"""
    )

    config, notifier_name = load_config(config_file)

    assert notifier_name == "console"
    assert config.interval_seconds == 60


def test_load_config_rejects_missing_watches(tmp_path):
    config_file = tmp_path / "watches.yaml"
    config_file.write_text("interval_seconds: 30\n")

    with pytest.raises(ConfigError, match="watches"):
        load_config(config_file)


def test_load_config_rejects_watch_missing_required_field(tmp_path):
    config_file = tmp_path / "watches.yaml"
    config_file.write_text(
        """
watches:
  - term: "202710"
    subject: CS
"""
    )

    with pytest.raises(ConfigError, match="course_number"):
        load_config(config_file)
