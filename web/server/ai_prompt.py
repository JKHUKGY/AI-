"""口语化修改意见 -> 完整 AI 绘图提示词：调用本机已登录的 Claude Code CLI
（跟 jobs.py 里调 Codex CLI 出图同样的思路——蹭已有的订阅登录，不用另开
Anthropic API key）。这是同步调用（通常几秒到几十秒），不像 jobs.py 那样
需要起子进程轮询，请求线程等一下直接返回结果就行。
"""
import subprocess

CLAUDE_TIMEOUT_SECONDS = 90

_INSTRUCTION_TEMPLATE = """你是短剧 AI 绘图提示词专家。下面是现有的完整 AI 绘图提示词：

{prompt}

剧本家用口语化的方式提出了修改意见：

{instruction}

请把这条修改意见融合进原提示词，输出融合后的完整新提示词——保留原有的画质、
风格、构图、人物一致性、"避免"清单等技术性要求不变，只根据修改意见调整
对应的具体细节。只输出最终的提示词文本本身，不要输出任何解释、前后缀、
引号或 markdown 标记。"""


def rewrite(current_prompt, instruction):
    """返回融合了 instruction 之后的新提示词文本；失败抛 RuntimeError。"""
    query = _INSTRUCTION_TEMPLATE.format(prompt=current_prompt, instruction=instruction)
    try:
        proc = subprocess.run(
            ['claude', '-p', '--restricted', '--output-format', 'text', query],
            capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise RuntimeError('这台机器上没有装 Claude Code CLI（找不到 claude 命令）')
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'Claude 超过 {CLAUDE_TIMEOUT_SECONDS} 秒没有响应，稍后重试')
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or 'claude 调用失败（非零退出码）')
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError('claude 没有返回任何内容')
    return out
