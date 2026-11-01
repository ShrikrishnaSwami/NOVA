from nova.core.computer.intents import match_open_application_command, requested_application_name


APPS = [
    {"name": "Spotify", "app_id": r"C:\\Start Menu\\Spotify.lnk"},
    {"name": "Google Chrome", "app_id": r"C:\\Start Menu\\Chrome.lnk"},
    {"name": "Outlook (new)", "app_id": "startapp:Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookforWindows"},
    {"name": "Windows Settings", "app_id": "windows-settings"},
]


def test_match_conversational_app_launch_requests() -> None:
    for phrase in (
        "Open Outlook",
        "Please open Outlook!",
        "Can you open Outlook?",
        "Could you please open Outlook for me?",
        "Hey NOVA, launch Outlook please",
        "I want you to open Outlook",
        "I'd like you to start Outlook",
    ):
        assert match_open_application_command(phrase, APPS) == APPS[2]

    assert match_open_application_command("launch Google Chrome", APPS) == APPS[1]
    assert match_open_application_command("Open Settings", APPS) == APPS[3]


def test_reject_unknown_ambiguous_and_non_launch_requests() -> None:
    assert match_open_application_command("What is Spotify?", APPS) is None
    assert match_open_application_command("Open PowerShell", APPS) is None
    assert match_open_application_command("Open Spotify and delete files", APPS) is None
    assert requested_application_name("Tell me about Outlook") is None

    duplicate = APPS + [{"name": "Outlook classic", "app_id": "classic-outlook"}]
    assert match_open_application_command("Open Outlook", duplicate) is None
