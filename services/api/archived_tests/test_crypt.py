import pytest

from owl.utils.crypt import decrypt, encrypt_deterministic, encrypt_random

STRINGS = ["", " ", "test", "test string", "test*string", "#$A122^*$(%)"]


@pytest.mark.parametrize("message", STRINGS)
@pytest.mark.parametrize("password", STRINGS)
def test_deterministic_encryption(message: str, password: str):
    encrypted = encrypt_deterministic(message, password)
    encrypted_repeat = encrypt_deterministic(message, password)
    assert encrypted != message
    assert encrypted == encrypted_repeat
    assert decrypt(encrypted, password) == message


@pytest.mark.parametrize("message", STRINGS)
@pytest.mark.parametrize("password", STRINGS)
def test_random_encryption(message: str, password: str):
    encrypted = encrypt_random(message, password)
    encrypted_repeat = encrypt_random(message, password)
    assert encrypted != message
    assert encrypted != encrypted_repeat
    assert decrypt(encrypted, password) == message


if __name__ == "__main__":
    test_deterministic_encryption("test string", "test string")
