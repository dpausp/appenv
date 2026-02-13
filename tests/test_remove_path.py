"""Tests for remove_path() helper function."""

import logging

import appenv


def test_remove_path_removes_symlink(tmp_path):
    """remove_path() removes a symlink."""
    target = tmp_path / "target_dir"
    target.mkdir()
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target)

    assert symlink.is_symlink()
    assert symlink.exists()

    appenv.remove_path(symlink)

    assert not symlink.exists()
    assert target.exists()  # Target should NOT be removed


def test_remove_path_removes_file(tmp_path, caplog):
    """remove_path() removes a regular file."""
    caplog.set_level(logging.DEBUG)
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("test content")

    assert file_path.is_file()

    appenv.remove_path(file_path)

    assert not file_path.exists()
    assert "Removing file" in caplog.text


def test_remove_path_removes_directory(tmp_path, caplog):
    """remove_path() removes a directory with contents."""
    caplog.set_level(logging.DEBUG)
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()
    (dir_path / "subfile.txt").write_text("content")

    assert dir_path.is_dir()

    appenv.remove_path(dir_path)

    assert not dir_path.exists()
    assert "Removing directory" in caplog.text
