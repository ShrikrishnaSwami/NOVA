from nova.core.computer.intents import match_open_application_command


APPS = [
    {"name": "Spotify", "app_id": r"C:\\Start Menu\\Spotify.lnk"},
    {"name": "Google Chrome", "app_id": r"C:\\Start Menu\\Chrome.lnk"},
    {"name": "Outlook (new)", "app_id": "startapp:Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookforWindows"},
    {"name": "Windows Settings", "app_id": "windows-settings"},
]


def test_match_discovered_app_names() -> None:
    assert match_open_application_command("Open Spotify", APPS) == APPS[0]
    assert match_open_application_command("launch Google Chrome", APPS) == APPS[1]
    assert match_open_application_command("open Outlook", APPS) == APPS[2]
    assert match_open_application_command("Please open Outlook!", APPS) == APPS[2]
    assert match_open_application_command("Open Settings", APPS) == APPS[3]


def test_do_not_match_unknown_or_ambiguous_apps() -> None:
    assert match_open_application_command("What is Spotify?", APPS) is None
    assert match_open_application_command("Open PowerShell", APPS) is None
    duplicate = APPS + [{"name": "Spotify", "app_id": "another-id"}]
    assert match_open_application_command("Open Spotify", duplicate) is None
    assert match_open_application_command("Open Spotify and delete files", APPS) is None
