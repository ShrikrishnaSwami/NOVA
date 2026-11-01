from nova.core.computer.intents import application_candidates, match_open_application_command, requested_application_name


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


def test_application_candidates_keep_ambiguous_choices_for_user() -> None:
    apps = [
        {"name": "Outlook (new)", "app_id": "new"},
        {"name": "Outlook classic", "app_id": "classic"},
        {"name": "Microsoft Teams", "app_id": "teams"},
    ]
    candidates = application_candidates("Open Outlook", apps)
    assert {app["app_id"] for app in candidates} == {"new", "classic"}


def test_application_candidates_match_short_app_names() -> None:
    apps = [
        {"name": "Google Chrome", "app_id": "chrome"},
        {"name": "Microsoft Word", "app_id": "word"},
        {"name": "Visual Studio Code", "app_id": "vscode"},
    ]
    assert application_candidates("Launch Chrome", apps) == [apps[0]]
    assert application_candidates("Open Word", apps) == [apps[1]]
    assert application_candidates("Open Studio Code", apps) == [apps[2]]


def test_planner_recognizes_filename_and_content_search() -> None:
    from nova.core.computer.intents import plan_computer_intent

    filename = plan_computer_intent("Hey NOVA, find my physics assignment")
    assert filename == {
        "action": "search_files",
        "parameters": {"query": "physics assignment"},
        "description": "search all accessible drives for files or folders matching 'physics assignment'",
    }
    contents = plan_computer_intent("Search inside my files for thermodynamics")
    assert contents["action"] == "search_file_contents"
    assert contents["parameters"] == {"query": "thermodynamics"}


def test_planner_requires_explicit_paths_for_open_and_read() -> None:
    from nova.core.computer.intents import plan_computer_intent

    assert plan_computer_intent(r"Open C:\Users\Apha\Documents\notes.txt")["action"] == "open_path"
    assert plan_computer_intent(r"Read C:\Users\Apha\Documents\notes.txt")["action"] == "read_text_file"
    assert plan_computer_intent("Open my private files") is None
    assert plan_computer_intent(r"Delete C:\Users\Apha\Documents\notes.txt") is None


def test_os_query_planner_recognizes_read_only_questions() -> None:
    from nova.core.computer.intents import plan_os_query

    assert plan_os_query("What apps are running?")["kind"] == "processes"
    assert plan_os_query("What am I looking at?")["kind"] == "windows"
    assert plan_os_query("Show my system information")["kind"] == "system"
    assert plan_os_query("Tell me a joke") is None
