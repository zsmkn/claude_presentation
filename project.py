"""Load a project folder (projects/<name>/) given on the command line."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        sys.exit("用法：python <script>.py projects/<專案資料夾> [...]")
    proj = Path(argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("story", proj / "story.py")
    story = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(story)
    return proj, story
