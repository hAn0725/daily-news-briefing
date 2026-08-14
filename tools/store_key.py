"""把 .env 中的 DeepSeek API Key 用 Windows DPAPI 加密后写回 .env，并清除明文。

用法：python tools/store_key.py
效果：.env 只保留 DEEPSEEK_API_KEY_ENC（加密密文，绑定当前 Windows 用户与本机），
     明文不再落盘；即使文件被拷贝也无法在其它机器/账号解密。
更换 Key 后重新运行本脚本即可。
"""
import base64
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv  # noqa: E402
from news_crawler.secure import protect  # noqa: E402

load_dotenv(BASE / ".env")
key = os.getenv("DEEPSEEK_API_KEY", "").strip()
if not key:
    print("[错误] .env 中没有明文 DEEPSEEK_API_KEY，无法加密。")
    sys.exit(1)

enc_b64 = base64.b64encode(protect(key.encode("utf-8"))).decode("ascii")

env_path = BASE / ".env"
lines = env_path.read_text(encoding="utf-8").splitlines()
out = [
    ln for ln in lines
    if not (ln.startswith("DEEPSEEK_API_KEY=") or ln.startswith("DEEPSEEK_API_KEY_ENC="))
]
out.append(f"DEEPSEEK_API_KEY_ENC={enc_b64}")
out.append("# 明文密钥已加密（Windows DPAPI，绑定当前用户）。")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

print("[完成] 已加密写入 .env 的 DEEPSEEK_API_KEY_ENC，明文已清除。")
