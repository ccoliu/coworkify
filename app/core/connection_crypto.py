import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class ConnectionsKeyMissing(RuntimeError):
    pass


def _fernet() -> MultiFernet:
    """
    CONNECTIONS_KEY 是一把或多把 Fernet 金鑰，用逗號分隔。加密一律用第一把；解密時每一把都會試，
    所以換金鑰的做法是：把新金鑰放到最前面、舊的留在後面，重新存過每個 connection 之後再拿掉舊的。

    每次呼叫都重新讀環境變數，不在 import 時快取——測試可以換金鑰，部署時改 .env 重啟即可。
    產生金鑰：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    raw = os.getenv("CONNECTIONS_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise ConnectionsKeyMissing(
            "CONNECTIONS_KEY is not set — generate one with "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and add it to .env"
        )
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError(
            "Can't decrypt a stored connection — CONNECTIONS_KEY changed without keeping the old key"
        ) from exc
