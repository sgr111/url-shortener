"""
Unit tests for Base62 encoding.
These are pure function tests — no DB, no HTTP.
"""

import pytest

from app.core.base62 import decode, encode


class TestBase62Encode:
    def test_encode_one(self):
        assert encode(1) == "1"

    def test_encode_62_is_10(self):
        # 62 in Base62 is "10" (like 10 in decimal is base 10)
        assert encode(62) == "10"

    def test_encode_125(self):
        # 125 = 2*62 + 1 → "21" in Base62
        assert encode(125) == "21"

    def test_encode_large_number(self):
        result = encode(3_500_000_000)
        assert isinstance(result, str)
        assert len(result) <= 7  # 3.5B fits in 6-7 Base62 chars

    def test_encode_only_valid_chars(self):
        valid = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for i in [1, 10, 100, 1000, 99999]:
            assert all(c in valid for c in encode(i))

    def test_encode_zero_raises(self):
        with pytest.raises(ValueError):
            encode(0)

    def test_encode_negative_raises(self):
        with pytest.raises(ValueError):
            encode(-5)


class TestBase62Decode:
    def test_decode_one(self):
        assert decode("1") == 1

    def test_decode_10_is_62(self):
        assert decode("10") == 62

    def test_decode_invalid_char_raises(self):
        with pytest.raises(ValueError):
            decode("ab!c")

    def test_decode_empty_raises(self):
        with pytest.raises(ValueError):
            decode("")


class TestBase62RoundTrip:
    """encode → decode must always return the original ID."""

    @pytest.mark.parametrize("original_id", [1, 2, 62, 100, 999, 10_000, 999_999])
    def test_roundtrip(self, original_id: int):
        assert decode(encode(original_id)) == original_id
