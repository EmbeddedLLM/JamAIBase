"""
Adapted from
https://github.com/gdavid7/cryptocode/blob/main/cryptocode.py
but with simpler code and fixed empty salt to enable DB lookup.
"""

import hashlib
import secrets
from base64 import b64decode, b64encode
from hashlib import blake2b

from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
from loguru import logger


def _encrypt(message: str, password: str, aes_mode: int) -> str:
    """
    pass
    """
    if not (aes_mode == AES.MODE_SIV or aes_mode == AES.MODE_GCM):
        raise ValueError("`aes_mode` can only be `AES.MODE_SIV` or `AES.MODE_GCM`.")

    # Use the Scrypt KDF to get a private key from the password
    if aes_mode == AES.MODE_SIV:
        salt = b""
    elif aes_mode == AES.MODE_GCM:
        salt = get_random_bytes(AES.block_size)
    else:
        raise ValueError("`aes_mode` can only be `AES.MODE_SIV` or `AES.MODE_GCM`.")
    private_key = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    # Create cipher config
    cipher_config = AES.new(private_key, aes_mode)
    cipher_text, tag = cipher_config.encrypt_and_digest(message.encode("utf-8"))
    cipher_text = b64encode(cipher_text).decode("utf-8")
    tag = b64encode(tag).decode("utf-8")
    # Create final encrypted text
    if aes_mode == AES.MODE_SIV:
        encrypted = f"{cipher_text}*{tag}"
    else:
        salt = b64encode(salt).decode("utf-8")
        nonce = b64encode(cipher_config.nonce).decode("utf-8")
        encrypted = f"{cipher_text}*{salt}*{nonce}*{tag}"
    return encrypted


def encrypt_random(message: str, password: str) -> str:
    """
    Encryption using AES GCM mode with random salt and nonce.
    """
    return _encrypt(message, password, AES.MODE_GCM)


def encrypt_deterministic(message: str, password: str) -> str:
    """
    Deterministic encryption using AES SIV mode with
    fixed empty salt and without nonce to enable DB lookup.
    """
    return _encrypt(message, password, AES.MODE_SIV)


def decrypt(encrypted: str, password: str) -> str:
    parts = encrypted.split("*")
    n_parts = len(parts)

    # Decode the entries from base64
    if n_parts == 4:
        cipher_text, salt, nonce, tag = parts
        salt = b64decode(salt)
        nonce = b64decode(nonce)
    elif n_parts == 2:
        cipher_text, tag = parts
        salt = b""
        nonce = None
    # elif n_parts == 1:
    #     logger.warning(f"Attempting to decrypt string that looks unencrypted: {encrypted}")
    #     return encrypted
    else:
        raise ValueError(f"Encrypted string must have either 2 or 4 parts, received: {n_parts}")
    cipher_text = b64decode(cipher_text)
    tag = b64decode(tag)
    # Generate the private key from the password and salt
    private_key = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    # Create the cipher config
    if n_parts == 4:
        cipher = AES.new(private_key, AES.MODE_GCM, nonce=nonce)
    else:
        cipher = AES.new(private_key, AES.MODE_SIV)
    # Decrypt the cipher text
    decrypted = cipher.decrypt_and_verify(cipher_text, tag)
    return decrypted.decode("UTF-8")


def hash_string_blake2b(string: str, digest_size: int = 8) -> str:
    hasher = blake2b(digest_size=digest_size)
    hasher.update(string.encode())
    return hasher.hexdigest()


def hash_file(file, hasher_constructor, ashexstr: bool = False, blocksize: int = 2**10):
    hasher = hasher_constructor()
    block = file.read(blocksize)
    while len(block) > 0:
        hasher.update(block)
        block = file.read(blocksize)
    return hasher.hexdigest() if ashexstr else hasher.digest()


def blake2b_hash_file(file, blocksize: int = 2**10):
    return hash_file(file, hasher_constructor=blake2b, ashexstr=True, blocksize=blocksize)


def generate_key(key_length: int = 48, prefix: str = "") -> str:
    """
    Generates a random key.

    Args:
        key_length (int, optional): The desired length of the key. Defaults to 48.
        prefix (str, optional): Prefix of the key. Defaults to "".

    Raises:
        ValueError: If `key_length` is < 16 or not a multiple of 2.

    Returns:
        api_key (str): A random key.
    """
    if key_length < 16:
        raise ValueError("Key length must be at least 16 characters.")
    if key_length % 2 != 0:
        raise ValueError("Key length must be a multiple of 2.")
    api_key = blake2b(secrets.token_bytes(key_length), digest_size=key_length // 2).hexdigest()
    return f"{prefix}{api_key}"
