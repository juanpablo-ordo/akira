"""Windows CI smoke for bundled llama.cpp + official Qwen3 GGUF.

Do not pass this check merely because /health is ready or a response contains
thinking tokens. Require a nonempty, finished assistant message visible to users.
Never connects to an MT5 account.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = 'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf'
SHA = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def get_model(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and sha256(path) == SHA:
        return path
    partial = path.with_suffix('.partial')
    partial.unlink(missing_ok=True)
    try:
        req = Request(URL, headers={'User-Agent': 'AKIRA-CI/16.3.2'})
        with urlopen(req, timeout=90) as response, partial.open('wb') as stream:
            for chunk in iter(lambda: response.read(2 * 1024 * 1024), b''):
                stream.write(chunk)
        if sha256(partial) != SHA:
            raise ValueError('GGUF SHA256 did not match the pinned official model')
        partial.replace(path)
        return path
    finally:
        partial.unlink(missing_ok=True)


def make_chat_payload():
    # Qwen3 thinks by default. A 24-token budget can be exhausted by hidden
    # thinking before any visible text is emitted. Use its supported soft switch
    # and the llama.cpp chat-template option for a predictable chat smoke.
    return {
        'model': 'Qwen3-4B-Q4_K_M.gguf',
        'messages': [
            {'role': 'system', 'content': '/no_think\nResponde brevemente en espanol.'},
            {'role': 'user', 'content': 'Di hola en una sola palabra.'},
        ],
        'chat_template_kwargs': {'enable_thinking': False},
        'temperature': 0,
        'max_tokens': 256,
        'stream': False,
    }


def validate_completion(response):
    choices = response.get('choices') or []
    choice = choices[0] if choices else {}
    message = choice.get('message') or {}
    content = message.get('content')
    if not isinstance(content, str):
        content = ''
    # Do not count just an unterminated chain-of-thought as a valid answer.
    visible = re.sub(r'<think>.*?</think>', '', content, flags=re.I | re.S).strip()
    if re.match(r'^\s*<think>', visible, re.I) or visible.strip().lower() == '</think>':
        visible = ''
    reason = choice.get('finish_reason')
    if not visible or reason == 'length':
        usage = response.get('usage') or {}
        reasoning = message.get('reasoning_content') or ''
        details = {
            'finish_reason': reason,
            'visible_chars': len(visible),
            'reasoning_chars': len(str(reasoning)),
            'completion_tokens': usage.get('completion_tokens'),
            'total_tokens': usage.get('total_tokens'),
            'model': response.get('model'),
        }
        raise RuntimeError('Qwen3 produced no complete visible answer: ' + json.dumps(details, ensure_ascii=True))
    return visible


def smoke(exe, model):
    exe = Path(exe)
    model = Path(model)
    if not (exe.is_file() and model.is_file()):
        raise FileNotFoundError('Missing CPU llama-server.exe or Qwen3 GGUF')
    cmd = [str(exe), '--model', str(model), '--host', '127.0.0.1', '--port', '18988',
           '--ctx-size', '2048', '--n-gpu-layers', '0', '--threads', '3', '--parallel', '1', '--jinja']
    with open(os.devnull, 'wb') as sink:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=sink, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 170
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('llama-server.exe quit before health was ready')
                try:
                    with urlopen('http://127.0.0.1:18988/health', timeout=2) as response:
                        if response.status == 200:
                            break
                except (OSError, ValueError):
                    pass
                time.sleep(1)
            else:
                raise TimeoutError('llama-server.exe did not reach /health within 170s')

            req = Request('http://127.0.0.1:18988/v1/chat/completions',
                          data=json.dumps(make_chat_payload()).encode('utf-8'),
                          headers={'Content-Type': 'application/json'})
            try:
                with urlopen(req, timeout=180) as response:
                    result = json.load(response)
            except HTTPError as exc:
                detail = exc.read(2000).decode('utf-8', 'replace')
                raise RuntimeError(f'Local model HTTP {exc.code}: {detail}') from exc
            except URLError as exc:
                raise RuntimeError(f'Local model request failed: {exc.reason}') from exc

            visible = validate_completion(result)
            print('AKIRA llama.cpp/Qwen3 visible chat OK; characters:', len(visible))
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    smoke(args.exe, get_model(args.model))


if __name__ == '__main__':
    main()
