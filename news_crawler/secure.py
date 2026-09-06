"""Windows DPAPI 加解密：API Key 加密存储，绑定当前 Windows 用户与本机。

- protect()：用当前用户凭据加密（仅同用户、同机器可解密）
- unprotect()：解密 protect() 生成的密文
使用系统内置 crypt32.dll，无需额外依赖。
"""
import ctypes
from ctypes import wintypes

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _to_blob(data: bytes) -> tuple[_DATA_BLOB, ctypes.Array]:
    """Build a DATA_BLOB and keep its backing buffer alive for the API call."""
    buf = ctypes.create_string_buffer(data or b"\0", len(data) or 1)
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    return blob, buf


def _from_blob(blob: _DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect(data: bytes) -> bytes:
    """用当前用户凭据加密，返回密文（仅本用户本机可解）"""
    if not data:
        return b""
    blob_in, _input_buffer = _to_blob(data)
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return _from_blob(blob_out)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def unprotect(blob: bytes) -> bytes:
    """解密 protect() 生成的密文"""
    if not blob:
        return b""
    blob_in, _input_buffer = _to_blob(blob)
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return _from_blob(blob_out)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
