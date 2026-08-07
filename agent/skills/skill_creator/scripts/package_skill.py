#!/usr/bin/env python3
"""
Skill打包器 — 创建可分发的 .skill 文件 (zip格式)

用法: python scripts/package_skill.py <path/to/skill-folder> [output-directory]
"""
import sys, os, zipfile, fnmatch
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git", "evals"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store"}


def should_exclude(rel_path: Path) -> bool:
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    if rel_path.name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(rel_path.name, pat) for pat in EXCLUDE_GLOBS)


def package_skill(skill_path, output_dir=None):
    skill_path = Path(skill_path).resolve()
    if not skill_path.exists():
        print(f"❌ 技能目录不存在: {skill_path}")
        return None
    if not skill_path.is_dir():
        print(f"❌ 不是目录: {skill_path}")
        return None

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"❌ 缺少SKILL.md")
        return None

    # 验证(如果有本地验证脚本)
    try:
        from quick_validate import validate_skill
        valid, msg = validate_skill(skill_path)
        if not valid:
            print(f"❌ 验证失败: {msg}")
            return None
        print(f"✅ {msg}")
    except ImportError:
        print("⚠️  跳过验证(quick_validate.py未找到)")

    output_dir = Path(output_dir).resolve() if output_dir else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = skill_path.name
    output_path = output_dir / f"{skill_name}.skill"

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in skill_path.rglob('*'):
            if not f.is_file():
                continue
            arcname = f.relative_to(skill_path.parent)
            if should_exclude(arcname):
                continue
            zf.write(f, arcname)
            print(f"  + {arcname}")

    print(f"\n✅ 打包完成: {output_path}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/package_skill.py <skill-folder> [output-dir]")
        sys.exit(1)
    package_skill(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
