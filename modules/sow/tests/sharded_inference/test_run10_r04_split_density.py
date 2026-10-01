"""Every shard must fit even when token density changes inside a long line."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'modules/sovereign'))
from sovereign_product.shard_modes import split_text


def test_character_fallback_verifies_nonuniform_token_density():
    text = 'a' * 100 + '界' * 20

    def count(value):
        return sum(4 if char == '界' else 1 for char in value)

    chunks = split_text(text, count_tokens=count, max_tokens=16)
    assert ''.join(chunks) == text
    assert all(count(chunk) <= 16 for chunk in chunks)
