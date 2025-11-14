import io

import pytest

from owl.utils.crypt import (
    blake2b_hash_file,
    decrypt,
    encrypt_deterministic,
    encrypt_random,
    generate_key,
    hash_string_blake2b,
)


def test_encrypt_random():
    message = "Hello, World!"
    password = "secret"
    encrypted = encrypt_random(message, password)
    decrypted = decrypt(encrypted, password)
    assert message == decrypted


def test_encrypt_deterministic():
    message = "Hello, World!"
    password = "secret"
    encrypted1 = encrypt_deterministic(message, password)
    encrypted2 = encrypt_deterministic(message, password)
    assert encrypted1 == encrypted2
    decrypted = decrypt(encrypted1, password)
    assert message == decrypted


def test_decrypt_invalid_parts():
    with pytest.raises(ValueError):
        decrypt("invalid*format*with*three*parts", "password")


def test_decrypt_wrong_password():
    message = "Hello, World!"
    password = "correct_password"
    wrong_password = "wrong_password"
    encrypted = encrypt_random(message, password)
    with pytest.raises(ValueError):
        decrypt(encrypted, wrong_password)


def test_empty_message():
    message = ""
    password = "secret"
    encrypted = encrypt_random(message, password)
    decrypted = decrypt(encrypted, password)
    assert message == decrypted


def test_long_message():
    message = "A" * 1000000  # 1 million characters
    password = "secret"
    encrypted = encrypt_random(message, password)
    decrypted = decrypt(encrypted, password)
    assert message == decrypted


def test_hash_string_blake2b():
    string = "Hello, World!"
    hashed = hash_string_blake2b(string)
    assert len(hashed) == 8


def test_hash_string_blake2b_custom_size():
    string = "Hello, World!"
    hashed = hash_string_blake2b(string, key_length=16)
    assert len(hashed) == 16


def test_blake2b_hash_file():
    file_content = b"Hello, World!"
    file = io.BytesIO(file_content)
    hashed = blake2b_hash_file(file)
    assert len(hashed) == 128  # Default blake2b digest size is 64 bytes


def test_blake2b_hash_file_custom_blocksize():
    file_content = b"Hello, World!" * 1000
    file = io.BytesIO(file_content)
    hashed = blake2b_hash_file(file, blocksize=1024)
    assert len(hashed) == 128


def test_generate_key_default():
    key = generate_key()
    assert len(key) == 48


def test_generate_key_custom_length():
    key = generate_key(key_length=32)
    assert len(key) == 32


def test_generate_key_with_prefix():
    key = generate_key(prefix="test_")
    assert key.startswith("test_")
    assert len(key) == 53  # 48 + 5 (prefix length)


def test_generate_key_invalid_length():
    with pytest.raises(ValueError):
        generate_key(key_length=15)


def test_generate_key_odd_length():
    with pytest.raises(ValueError):
        generate_key(key_length=33)
