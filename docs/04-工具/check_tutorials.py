"""检查教程的本地链接、Python 语法和 JSON；不连接数据库或模型。"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

DOCS = Path(__file__).resolve().parents[1]
FENCE = re.compile(r'^```([^\n]*)\n(.*?)^```\s*$', re.MULTILINE | re.DOTALL)
LINK = re.compile(r'!?\[[^\]\n]*\]\(([^\n)]+)\)')


def main() -> int:
    errors = []
    counts = {'Markdown': 0, 'Python 代码块': 0, 'Python 文件': 0, 'JSON 代码块': 0, '本地链接': 0}
    for path in [DOCS.parent / 'README.md', *sorted(DOCS.rglob('*.md'))]:
        text = path.read_text(encoding='utf-8-sig')
        counts['Markdown'] += 1
        for block in FENCE.finditer(text):
            language, code = block.groups()
            line = text.count('\n', 0, block.start()) + 1
            try:
                if language.strip() in {'python', 'py'}:
                    compile(code, str(path), 'exec')
                    counts['Python 代码块'] += 1
                elif language.strip() == 'json':
                    json.loads(code)
                    counts['JSON 代码块'] += 1
            except (SyntaxError, ValueError) as error:
                errors.append(f'{path.relative_to(DOCS.parent)}:{line} {error}')
        prose = FENCE.sub('', text)
        for link in LINK.finditer(prose):
            target = link.group(1).strip().strip('<>')
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            counts['本地链接'] += 1
            if not (path.parent / unquote(parsed.path)).exists():
                errors.append(f'{path.relative_to(DOCS.parent)} 链接不存在：{target}')

    for path in sorted(DOCS.rglob('*.py')):
        try:
            compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
            counts['Python 文件'] += 1
        except SyntaxError as error:
            errors.append(f'{path.relative_to(DOCS.parent)} {error}')

    print('，'.join(f'{name}：{count}' for name, count in counts.items()))
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('文本检查通过；不代表业务、TypeScript/Vue 编译、外部链接或真实服务通过验收。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
