from nova.core.computer.intents import match_open_application_command


def test_match_open_calculator_command() -> None:
    assert match_open_application_command("Open Calculator") == "calculator"
    assert match_open_application_command("please launch the calc please") == "calculator"


def test_match_windows_settings_command() -> None:
    assert match_open_application_command("Open Settings") == "windows settings"
    assert match_open_application_command("Open Windows Settings") == "windows settings"


def test_match_other_allowlisted_apps() -> None:
    assert match_open_application_command("Start Notepad.") == "notepad"
    assert match_open_application_command("open file explorer") == "file explorer"


def test_do_not_match_ambiguous_or_unlisted_commands() -> None:
    assert match_open_application_command("What is a calculator?") is None
    assert match_open_application_command("Open PowerShell") is None
    assert match_open_application_command("Open Calculator and delete files") is None
