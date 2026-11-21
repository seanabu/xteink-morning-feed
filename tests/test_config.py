import shutil

import pytest
import yaml

from conftest import FIXTURE_PROFILE
from feed.config import ProfileError, load_profile


def test_loads_fixture_profile():
    p = load_profile(FIXTURE_PROFILE)
    assert p.slug == "profile"
    assert p.settings.daily_target == 3
    assert p.settings.retention_days == 7  # default
    assert [s.name for s in p.sources][0] == "Fixture Always"
    assert p.sources[2].url is None and p.sources[2].verify


def _copy(tmp_path):
    dst = tmp_path / "p"
    shutil.copytree(FIXTURE_PROFILE, dst)
    return dst


def test_unknown_key_is_an_error(tmp_path):
    d = _copy(tmp_path)
    (d / "profile.yaml").write_text("name: X\ndaily_targt: 5\n")
    with pytest.raises(ProfileError, match="daily_targt"):
        load_profile(d)


def test_unknown_source_key_names_the_source(tmp_path):
    d = _copy(tmp_path)
    src = yaml.safe_load((d / "sources.yaml").read_text())
    src[0]["tierr"] = "always"
    (d / "sources.yaml").write_text(yaml.safe_dump(src))
    with pytest.raises(ProfileError, match="Fixture Always"):
        load_profile(d)


def test_url_required_unless_verify(tmp_path):
    d = _copy(tmp_path)
    src = yaml.safe_load((d / "sources.yaml").read_text())
    del src[2]["verify"]
    (d / "sources.yaml").write_text(yaml.safe_dump(src))
    with pytest.raises(ProfileError, match="url is required"):
        load_profile(d)


def test_bad_timezone(tmp_path):
    d = _copy(tmp_path)
    (d / "profile.yaml").write_text("name: X\ntimezone: Mars/Olympus\n")
    with pytest.raises(ProfileError, match="timezone"):
        load_profile(d)


def test_topic_label_falls_back_to_topic():
    p = load_profile(FIXTURE_PROFILE)
    assert p.topic_label("topic-a") == "Topic A"
    assert p.topic_label("topic-b") == "topic-b"
    assert p.topic_label("unknown") == "unknown"
