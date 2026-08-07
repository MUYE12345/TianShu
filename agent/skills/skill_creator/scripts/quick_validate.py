#!/usr/bin/env python3
"""
Skill验证器 — 检查SKILL.md是否符合Anthropic标准

用法: python scripts/quick_validate.py <skill_directory>
"""
import sys
import re
import yaml
from pathlib import Path

ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}


def validate_skill(skill_path):
    """验证skill目录结构"""
    skill_path = Path(skill_path)

    if not skill_path.is_dir():
        return False, f"不是有效目录: {skill_path}"

    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "缺少SKILL.md文件"

    content = skill_md.read_text(encoding='utf-8')
    if not content.startswith('---'):
        return False, "SKILL.md必须以YAML frontmatter开头(---)"

    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    try:
        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            return False, "Frontmatter必须是YAML字典"
    except yaml.YAMLError as e:
        return False, f"YAML解析错误: {e}"

    unexpected = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected:
        return False, f"不允许的字段: {unexpected}. 允许: {ALLOWED_PROPERTIES}"

    if 'name' not in frontmatter:
        return False, "缺少 'name' 字段"
    if 'description' not in frontmatter:
        return False, "缺少 'description' 字段"

    name = str(frontmatter['name']).strip()
    if not re.match(r'^[a-z0-9-]+$', name):
        return False, f"名称'{name}'必须是kebab-case(小写字母+数字+连字符)"
    if len(name) > 64:
        return False, f"名称过长({len(name)}字符, 最多64)"

    desc = str(frontmatter.get('description', '')).strip()
    if len(desc) > 1024:
        return False, f"描述过长({len(desc)}字符, 最多1024)"
    if '<' in desc or '>' in desc:
        return False, "描述中不能包含尖括号"

    # 检查body长度
    body = content.split('---', 2)[-1].strip() if content.count('---') >= 2 else ''
    body_lines = body.count('\n') + 1
    if body_lines > 500:
        print(f"  ⚠️  警告: body有{body_lines}行, 建议<500行 (当前不影响验证)")

    return True, f"✅ 验证通过: {name}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python scripts/quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
