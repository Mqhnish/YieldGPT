"""Small dotenv reader: literal values only, no shell evaluation or expansion."""
import os
from pathlib import Path
import re
import shlex


def load_env(path=None):
    path = Path(path or os.getenv('IB_ENV_FILE', Path(__file__).resolve().parents[1] / '.env'))
    if not path.exists():
        return
    if path.stat().st_size > 65536:
        raise ValueError('Environment file exceeds 64 KiB')
    pending = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        name, sep, value = line.partition('=')
        name = name.strip()
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError(f'Invalid environment assignment on line {number}')
        try:
            words = shlex.split(value, comments=True)
        except ValueError:
            raise ValueError(f'Invalid environment value on line {number}') from None
        if len(words) > 1:
            raise ValueError(f'Quote values containing spaces on line {number}')
        pending[name] = words[0] if words else ''
    for key, value in pending.items():
        os.environ.setdefault(key, value)
