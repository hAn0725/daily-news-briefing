"""把智谱 BigModel API Key 用 Windows DPAPI 加密后写入 .env。

用法：python tools/store_key.py
效果：.env 只保留 BIGMODEL_API_KEY_ENC（加密密文，绑定当前 Windows 用户与本机），
     明文不再落盘；即使文件被拷贝也无法在其它机器/账号解密。
更换 Key 后重新运行本脚本即可。
"""
import base64
import getpass
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv  # noqa: E402

from news_crawler.secure import protect  # noqa: E402

load_dotenv(BASE / ".env")
env_name = "BIGMODEL_API_KEY"
key = os.getenv(env_name, "").strip()
if not key:
    key = getpass.getpass("请粘贴智谱 BigModel API Key（输入不回显）：").strip()
if not key:
    print("[错误] 未输入 API Key。")
    sys.exit(1)

enc_b64 = base64.b64encode(protect(key.encode("utf-8"))).decode("ascii")

env_path = BASE / ".env"
lines = (env_path.read_text(encoding="utf-8").splitlines()
         if env_path.exists() else [])
out = [
    ln for ln in lines
    if not (ln.startswith(f"{env_name}=") or
            ln.startswith(f"{env_name}_ENC="))
]
out.append(f"{env_name}_ENC={enc_b64}")
out.append("# 明文密钥已加密（Windows DPAPI，绑定当前用户）。")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

print(f"[完成] 已加密写入 .env 的 {env_name}_ENC，明文未落盘。")
