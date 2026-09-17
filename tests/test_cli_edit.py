import sys
from pathlib import Path

from iop.cli import _edit


# Create a simple no-op editor script for testing
def _create_test_editor(tmp_path):
    editor_script = tmp_path / "test_editor.py"
    editor_script.write_text(
        "import sys\n"
        "if len(sys.argv) > 1:\n"
        "    with open(sys.argv[1], 'a'):\n"
        "        pass\n",
        encoding="utf-8"
    )
    return str(editor_script)


# Create an editor script that captures the path argument it receives
def _create_capturing_editor(tmp_path, capture_file):
    editor_script = tmp_path / "capturing_editor.py"
    editor_script.write_text(
        "import sys, pathlib\n"
        "if len(sys.argv) > 1:\n"
        f"    pathlib.Path(r'{capture_file}').write_text(sys.argv[1])\n",
        encoding="utf-8"
    )
    return str(editor_script)


def test_edit_creates_parent_directory_and_invokes_the_editor(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "recipes.toml"
    captured = tmp_path / "captured_path.txt"
    editor_script = _create_capturing_editor(tmp_path, captured)
    monkeypatch.setenv("EDITOR", f"{sys.executable} {editor_script}")
    code = _edit(path)
    assert code == 0
    assert path.parent.is_dir()
    assert captured.read_text(encoding="utf-8") == str(path)


def test_edit_reports_a_missing_editor_as_127(tmp_path, monkeypatch, capsys):
    path = tmp_path / "recipes.toml"
    monkeypatch.setenv("EDITOR", "definitely-not-a-real-editor-xyz")
    code = _edit(path)
    assert code == 127
    assert "not found" in capsys.readouterr().err


def test_edit_seeds_a_default_recipes_toml_when_none_exists(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "recipes.toml"
    monkeypatch.setenv("EDITOR", f"{sys.executable} -c \"import sys\"")  # no-op editor
    code = _edit(path)
    assert code == 0
    content = path.read_text(encoding="utf-8")
    assert content == (
        "[whoami]\n"
        'desc  = "set your git identity (name and email) for this machine"\n'
        'vars  = ["name", "email"]\n'
        "steps = [\n"
        '  "git config --global user.name {name}",\n'
        '  "git config --global user.email {email}",\n'
        "]\n"
        "\n"
        "[push]\n"
        'desc  = "pull, stage everything, commit, push"\n'
        'vars  = ["msg"]\n'
        "steps = [\n"
        '  "git pull",\n'
        '  "git status",\n'
        '  "git add -A",\n'
        '  { run = "git commit -m {msg}", ok_fail = true },\n'
        '  "git push",\n'
        "]\n"
        "\n"
        "[undo]\n"
        'desc  = "take back the last commit but keep its changes staged"\n'
        "steps = [\n"
        '  "git reset --soft HEAD~1",\n'
        '  "git status",\n'
        "]\n"
        "\n"
        "[serve]\n"
        'desc  = "serve the current directory over HTTP"\n'
        'vars  = ["port"]\n'
        'steps = ["python -m http.server {port}"]\n'
        "\n"
        "[docker]\n"
        'desc  = "build an image and run it"\n'
        'vars  = ["tag"]\n'
        "steps = [\n"
        '  "docker build -t {tag} .",\n'
        '  "docker run --rm -it {tag}",\n'
        "]\n"
    )


def test_seeded_default_recipes_toml_is_valid_and_loads(tmp_path, monkeypatch):
    # Byte-equality above guards against accidental edits to the seed;
    # this guards against the other failure mode -- a seed that is the
    # intended text but not valid TOML / not a valid recipe file, which
    # would make every fresh install exit 3 on its very first run.
    from iop.config import load

    path = tmp_path / "recipes.toml"
    monkeypatch.setenv("EDITOR", f"{sys.executable} -c \"import sys\"")
    assert _edit(path) == 0
    recipes = load(path)
    assert sorted(recipes) == ["docker", "push", "serve", "undo", "whoami"]
    assert recipes["serve"].vars == ("port",)
    assert recipes["docker"].vars == ("tag",)
    assert recipes["undo"].vars == ()
    assert recipes["whoami"].vars == ("name", "email")


def test_edit_does_not_overwrite_an_existing_recipes_toml(tmp_path, monkeypatch):
    path = tmp_path / "recipes.toml"
    path.write_text("[existing]\nsteps = [\"echo hi\"]\n", encoding="utf-8")
    editor_script = _create_test_editor(tmp_path)
    monkeypatch.setenv("EDITOR", f"{sys.executable} {editor_script}")
    code = _edit(path)
    assert code == 0
    assert path.read_text(encoding="utf-8") == "[existing]\nsteps = [\"echo hi\"]\n"
