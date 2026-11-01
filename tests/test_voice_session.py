import pytest

from nova.core.voice.session import WakeWordSession


def test_wake_word_session_requires_a_phrase():
    with pytest.raises(ValueError, match="wake phrase"):
        WakeWordSession("missing", lambda: None, lambda _text: None, wake_phrases=())


def test_wake_word_session_can_be_stopped_before_start():
    session = WakeWordSession("missing", lambda: None, lambda _text: None)
    session.stop()
    assert session.running is False
