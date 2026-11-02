import pytest

from src.plugins.auto_design.services.database_folder import copy_member_model


def test_copy_member_model_copies_only_the_sdb(tmp_path):
    source_folder = tmp_path / "Generation-1" / "Gen-1-7"
    source_folder.mkdir(parents=True)
    (source_folder / "Gen-1-7.sdb").write_text("model")
    (source_folder / "Gen-1-7.OUT").write_text("results")

    target_folder = tmp_path / "Generation-2" / "Gen-2-1"
    new = copy_member_model(source_folder / "Gen-1-7.sdb", target_folder, "Gen-2-1")

    assert new == target_folder / "Gen-2-1.sdb"
    assert new.read_text() == "model"
    assert [p.name for p in target_folder.iterdir()] == ["Gen-2-1.sdb"]
    assert (source_folder / "Gen-1-7.sdb").exists()  # the original stays


def test_copy_member_model_missing_source_gives_a_clear_error(tmp_path):
    with pytest.raises(RuntimeError):
        copy_member_model(tmp_path / "nope.sdb", tmp_path / "x", "Gen-2-1")
