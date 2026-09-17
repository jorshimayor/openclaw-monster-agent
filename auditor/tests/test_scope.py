"""The scope gate fails closed. These are the tests that matter most here."""

from datetime import date
from pathlib import Path

import pytest
import yaml

from auditor.scope import ScopeError, check_scope, load_programs, normalize_repo


def write_scope(tmp_path: Path, programs: list[dict]) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    path = config / "scope.yaml"
    path.write_text(yaml.safe_dump({"programs": programs}))
    return path


def test_unknown_target_is_refused(tmp_path):
    programs = load_programs(write_scope(tmp_path, [
        {"name": "p", "platform": "immunefi", "authorization": "url",
         "repos": ["https://github.com/allowed/repo"]},
    ]))
    with pytest.raises(ScopeError, match="not in scope"):
        check_scope("https://github.com/someone/else", programs=programs)


def test_empty_scope_authorizes_nothing(tmp_path):
    programs = load_programs(write_scope(tmp_path, []))
    with pytest.raises(ScopeError, match="no programs"):
        check_scope("anything", programs=programs)


def test_entry_without_authorization_is_rejected(tmp_path):
    path = write_scope(tmp_path, [{"name": "p", "platform": "immunefi"}])
    with pytest.raises(ScopeError, match="authorization"):
        load_programs(path)


def test_expired_program_is_refused_and_says_so(tmp_path):
    programs = load_programs(write_scope(tmp_path, [
        {"name": "old", "platform": "immunefi", "authorization": "url",
         "expires": date(2020, 1, 1), "repos": ["https://github.com/a/b"]},
    ]))
    with pytest.raises(ScopeError, match="scope has ended"):
        check_scope("https://github.com/a/b", programs=programs, today=date(2026, 1, 1))


def test_repo_forms_are_one_repo(tmp_path):
    programs = load_programs(write_scope(tmp_path, [
        {"name": "p", "platform": "immunefi", "authorization": "url",
         "repos": ["https://github.com/a/b"]},
    ]))
    for form in ("https://github.com/a/b.git", "git@github.com:a/b", "github.com/A/B/"):
        assert check_scope(form, programs=programs).program.name == "p"


def test_path_outside_the_allowed_tree_is_refused(tmp_path):
    allowed = tmp_path / "targets" / "ok"
    allowed.mkdir(parents=True)
    outside = tmp_path / "secrets"
    outside.mkdir()

    path = write_scope(tmp_path, [
        {"name": "p", "platform": "immunefi", "authorization": "url",
         "paths": ["targets/ok"]},
    ])
    # paths in the file resolve relative to the package root, so point at the
    # real directory for this test rather than reimplementing the resolution.
    programs = load_programs(path)
    object.__setattr__(programs[0], "paths", (allowed.resolve(),))

    assert check_scope(str(allowed), programs=programs).program.name == "p"
    with pytest.raises(ScopeError):
        check_scope(str(outside), programs=programs)
    with pytest.raises(ScopeError):
        check_scope(str(allowed / ".." / "secrets"), programs=programs)


def test_shipped_scope_file_parses_and_authorizes_only_practice():
    programs = load_programs()
    assert [p.name for p in programs] == ["practice"]
    assert normalize_repo("https://github.com/theredguild/damn-vulnerable-defi") in programs[0].repos
    with pytest.raises(ScopeError):
        check_scope("https://github.com/some/live-protocol", programs=programs)
