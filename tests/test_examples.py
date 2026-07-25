from pathlib import Path

from validator.cli import main

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_examples_validate_clean(capsys):
    assert main([str(EXAMPLES)]) == 0
