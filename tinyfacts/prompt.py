from string import Template
from pathlib import Path

_WORDS_PATH = Path(__file__).parent / "thing-explainer/thing-explainer-1000.txt"
_TEMPLATE_PATH = Path(__file__).parent / "prompt_template.txt"

def make_prompt():
    words = sorted(list(_WORDS_PATH.read_text().splitlines()), key=str.lower)
    with open(_TEMPLATE_PATH, "r") as f:
        template = Template(f.read())
    return template.substitute(words=' '.join(words))

if __name__ == "__main__":
    print(make_prompt())