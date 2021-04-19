import os
from typing import Optional, BinaryIO

from cryptography.hazmat import backends
from cryptography.hazmat.primitives import serialization

from creepy.types.secure_string import SecureString


class ProcessifiedPrivateKey:
    def __init__(self, session):
        self._session = session
        self._public_key = None

    def public_key(self):
        if self._public_key is None:
            from cryptography.hazmat.primitives import serialization
            public_bytes = self._session.request('public_bytes')
            self._public_key = serialization.load_ssh_public_key(public_bytes)
        return self._public_key

    def decrypt(self, ciphertext: bytes, padding=None) -> bytes:
        return self._session.request('decrypt', ciphertext, padding)

    def sign(self, message: bytes, padding = None, algorithm = None) -> bytes:
        return self._session.request('sign', message, padding, algorithm)


_id_filenames = ['id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519']


def _find_key(path: Optional[str], ext: str = '', ssh_dir: Optional[str] = None) -> str:
    if path is not None:
        return os.path.expanduser(path)
    if ssh_dir is None:
        ssh_dir = os.path.expanduser('~/.ssh')
    for id_filename in _id_filenames:
        path = os.path.join(ssh_dir, id_filename + ext)
        if os.path.isfile(path):
            return path


def load_private_key(path=None, passphrase: Optional[SecureString] = None, ssh_dir: Optional[str] = None):
    """
    Load private key from a file.

    Parameters
    ----------
    path: string or pathlib.Path
        Path to a private key file.
    passphrase: SecureString, optional
        Passphrase to decrypt private key file, if not specified user will be prompted to enter it.
    ssh_dir: string or pathlib.Path, optional
        If `path` is not specified private key file is searched in `ssh_dir` directory.
    """
    assert passphrase is None or isinstance(passphrase, SecureString)
    from .pipe import connect
    path = _find_key(path, ssh_dir=ssh_dir)
    if path is None:
        raise RuntimeError('Failed to find private key file')
    session = connect('_detail/private_key', '34567e51eb5fe1f26845cb26f52bfdfaff94d0830d286437e468df60cda059e0')
    session.request('load', path, passphrase)
    return ProcessifiedPrivateKey(session)


def load_public_key(file=None, ssh_dir: Optional[str] = None):
    """
    Parameters
    ----------
    file: file-like object, string, pathlib.Path or bytes, optional
        The public key file to load, its filename or content.
    ssh_dir: string or pathlib.Path, optional
        If `path` is not specified public key file is searched in `ssh_dir` directory.
    """
    if file is None or isinstance(file, str):
        path = _find_key(file, '.pub', ssh_dir=ssh_dir)
        if path is None:
            raise RuntimeError('Failed to find public key file')
        with open(path, 'rb') as f:
            return load_public_key(f)
    key_bytes = file if isinstance(file, bytes) else file.read()
    loaders = [serialization.load_pem_public_key, serialization.load_ssh_public_key]
    backend = backends.default_backend()
    for loader in loaders:
        try:
            return loader(key_bytes, backend=backend)
        except (TypeError, ValueError):
            pass
    return ValueError('Invalid key format')


def dump_private_key(private_key, file) -> SecureString:
    """
    Dump private key to a file and return passphrase.

    Parameters
    ----------
    private_key
    file: file-like object, string, or pathlib.Path
        Depending on type treated as file object or path to a destination file.
    """
    from creepy.utils import processify

    if isinstance(file, str):
        with open(file, 'wb') as f:
            return dump_private_key(private_key, f)
    from cryptography.hazmat.primitives import serialization
    passphrase = SecureString.random(16)

    @processify  # run in separate process so passphrase bytes are exposed only during writting a key to a file
    def doit():
        with passphrase as passphrase_mem:
            passphrase_bytes = bytes(passphrase_mem)
            private_key_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.BestAvailableEncryption(passphrase_bytes)
            )
            file.write(private_key_bytes)

    doit()
    return passphrase


def dump_public_key(public_key, file):
    """
    Dump public key to a file.

    Parameters
    ----------
    public_key
    file: file-like object, string, or pathlib.Path
        File or filename to which the public key is dumped.
    """
    if not isinstance(file, BinaryIO):
        with open(file, 'wb') as f:
            return dump_public_key(public_key, f)
    public_key_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.OpenSSH
    )
    file.write(public_key_bytes)
