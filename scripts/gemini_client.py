#!/usr/bin/env python3
"""供 Claude Code 调用 Gemini API 的最小客户端。

用法:
  python3 scripts/gemini_client.py test
      发一个简单文本请求，验证 GEMINI_API_KEY 是否配置正确。

  python3 scripts/gemini_client.py image --prompt "提示词内容" --out out.png [--model gemini-2.5-flash-image]
      调用 Gemini 图像生成模型，把返回的图片保存到 --out 指定路径。

  python3 scripts/gemini_client.py text --prompt "提示词内容" [--model gemini-2.5-flash]
      纯文本生成，打印返回内容。

key 从项目根目录的 .env 文件读取（GEMINI_API_KEY=xxx），不要把 key 写进代码或
提交进仓库。
"""

import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, ".env")
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def load_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "GEMINI_API_KEY" and v.strip():
                    return v.strip()
    return None


def call_gemini(model, payload, api_key):
    url = f"{API_BASE}/{model}:generateContent?key={api_key}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} 错误: {body}", file=sys.stderr)
        sys.exit(1)


def cmd_test(args, api_key):
    payload = {"contents": [{"parts": [{"text": "只回复两个字：正常"}]}]}
    result = call_gemini("gemini-2.5-flash", payload, api_key)
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    print(f"连接成功，模型回复: {text.strip()}")


def cmd_text(args, api_key):
    payload = {"contents": [{"parts": [{"text": args.prompt}]}]}
    result = call_gemini(args.model, payload, api_key)
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    print(text)


def cmd_image(args, api_key):
    payload = {"contents": [{"parts": [{"text": args.prompt}]}]}
    result = call_gemini(args.model, payload, api_key)
    parts = result["candidates"][0]["content"]["parts"]
    saved = False
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            img_bytes = base64.b64decode(inline["data"])
            with open(args.out, "wb") as f:
                f.write(img_bytes)
            print(f"图片已保存到 {args.out}")
            saved = True
        elif part.get("text"):
            print(f"模型附带文字说明: {part['text']}")
    if not saved:
        print("响应里没有找到图片数据，完整返回如下：", file=sys.stderr)
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("test", help="验证 API key 是否配置正确")

    p_text = sub.add_parser("text", help="纯文本生成")
    p_text.add_argument("--prompt", required=True)
    p_text.add_argument("--model", default="gemini-2.5-flash")

    p_image = sub.add_parser("image", help="生成图片")
    p_image.add_argument("--prompt", required=True)
    p_image.add_argument("--out", required=True)
    p_image.add_argument("--model", default="gemini-2.5-flash-image")

    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print(
            "没有找到 GEMINI_API_KEY。请在项目根目录创建 .env 文件，写入：\n"
            "GEMINI_API_KEY=你的key\n"
            "（可以参考 .env.example）",
            file=sys.stderr,
        )
        sys.exit(1)

    {"test": cmd_test, "text": cmd_text, "image": cmd_image}[args.cmd](args, api_key)


if __name__ == "__main__":
    main()
