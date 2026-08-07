"""
SKILL管理器 — 遵循 Anthropic SKILL 标准

SKILL结构:
  skill-name/
  ├── SKILL.md          (必需) — YAML frontmatter + Markdown指令
  ├── scripts/           (可选) — 可执行辅助代码
  ├── references/        (可选) — 按需加载的参考文档
  └── assets/            (可选) — 模板/图标/字体等

三级渐进加载:
  1. Metadata (name + description) — 始终在上下文中 (~100词)
  2. SKILL.md body — skill触发时加载 (<500行)
  3. Bundled resources — 按需加载(无限制)
"""
import os
import yaml
import re
from pathlib import Path
from typing import List, Dict, Optional

SKILLS_DIR = Path(__file__).parent


class SkillInfo:
    """SKILL元数据(Layer 1: 始终可见)"""
    def __init__(self, name: str, description: str, version: str = "0.1.0",
                 path: Path = None, enabled: bool = True):
        self.name = name
        self.description = description
        self.version = version
        self.path = path
        self.enabled = enabled
        self._body_cache = None
        self._ref_cache = {}

    def get_body(self) -> Optional[str]:
        """Layer 2: 按需加载SKILL.md正文"""
        if self._body_cache:
            return self._body_cache
        if not self.path or not self.path.exists():
            return None
        content = self.path.read_text(encoding="utf-8")
        # 移除YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            body = parts[2].strip() if len(parts) >= 3 else content
        else:
            body = content
        self._body_cache = body[:3000]  # 限制长度
        return self._body_cache

    def get_reference(self, ref_name: str) -> Optional[str]:
        """Layer 3: 加载bundled resources"""
        if not self.path:
            return None
        ref_dir = self.path.parent / "references"
        ref_path = ref_dir / ref_name
        if ref_path.exists():
            if ref_name not in self._ref_cache:
                self._ref_cache[ref_name] = ref_path.read_text(encoding="utf-8")[:2000]
            return self._ref_cache[ref_name]
        return None

    def to_dict(self):
        return {"name": self.name, "description": self.description,
                "version": self.version, "enabled": self.enabled}

    def to_prompt(self) -> str:
        """生成注入Agent提示词的技能描述(Layer 1+2)"""
        body = self.get_body() or ""
        return f"""## {self.name}
{self.description}

{body[:500]}
"""


class SkillManager:
    """SKILL管理器 — 三级渐进加载"""

    def __init__(self):
        self.skills: Dict[str, SkillInfo] = {}
        self._load_all()

    def reload(self):
        """重新扫描 skills/ 目录(市场安装/卸载后调用)。"""
        self.skills.clear()
        self._load_all()

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """启用/禁用技能(真实作用于技能管理器, 供市场使用)。"""
        skill = self.skills.get(name)
        if not skill:
            return False
        skill.enabled = enabled
        return True

    def _load_all(self):
        """扫描skills/目录, 加载所有SKILL.md"""
        for skill_dir in SKILLS_DIR.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name.startswith((".", "_", "__")) or skill_dir.name == "__pycache__":
                continue  # 跳过缓存/隐藏目录
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                # 兼容旧版: 用目录名作为fallback, 但要求目录有可识别内容(scripts/references/assets)
                if not any((skill_dir / sub).exists() for sub in ("scripts", "references", "assets")):
                    continue
                name = skill_dir.name
                desc = "暂无描述"
                if name in self.skills:
                    print(f"[WARNING] SKILL命名空间冲突: skill \"{name}\" 已存在，来自 \"{self.skills[name].path}\" 和 \"{skill_md}\"")
                self.skills[name] = SkillInfo(name, desc, path=skill_md)
                continue

            # 解析YAML frontmatter
            content = skill_md.read_text(encoding="utf-8")
            frontmatter = {}
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        frontmatter = yaml.safe_load(parts[1]) or {}
                    except yaml.YAMLError:
                        pass

            name = frontmatter.get("name", skill_dir.name)
            desc = frontmatter.get("description", "暂无描述")
            if name in self.skills:
                print(f"[WARNING] SKILL命名空间冲突: skill \"{name}\" 已存在，来自 \"{self.skills[name].path}\" 和 \"{skill_md}\"")
            self.skills[name] = SkillInfo(
                name=name, description=desc,
                version=frontmatter.get("version", "0.1.0"),
                path=skill_md, enabled=True,
            )

    def list_skills(self) -> List[dict]:
        """列出所有SKILL(Layer 1)"""
        return [s.to_dict() for s in self.skills.values()]

    def get_skill(self, name: str) -> Optional[SkillInfo]:
        return self.skills.get(name)

    def get_skill_body(self, name: str) -> Optional[str]:
        """获取SKILL完整指令(Layer 2)"""
        skill = self.skills.get(name)
        return skill.get_body() if skill else None

    def get_skill_reference(self, name: str, ref: str) -> Optional[str]:
        """获取SKILL参考文档(Layer 3)"""
        skill = self.skills.get(name)
        return skill.get_reference(ref) if skill else None

    def match_skills(self, user_input: str) -> List[SkillInfo]:
        """
        根据用户输入匹配相关SKILL

        策略: 关键词匹配 description + name
        在Agent对话中自动触发最相关的SKILL
        """
        matched = []
        input_lower = user_input.lower()
        for skill in self.skills.values():
            if not skill.enabled:
                continue
            desc_lower = skill.description.lower()
            name_lower = skill.name.lower()
            # 简单关键词匹配
            keywords = name_lower.replace("-", " ").split() + desc_lower.split()[:10]
            score = sum(1 for kw in keywords if kw in input_lower)
            if score >= 2:  # 至少2个关键词匹配
                matched.append((score, skill))
        matched.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in matched[:2]]  # 最多返回2个最匹配的

    def get_skills_prompt(self, user_input: str = "") -> str:
        """
        生成注入Agent提示词的SKILL描述

        渐进式披露:
        - 始终注入: 所有SKILL的name+description (Layer 1)
        - 匹配注入: 匹配到的SKILL注入完整body (Layer 2)
        """
        # Layer 1: 所有SKILL的元数据
        layer1 = "\n".join([
            f"- **{s.name}**: {s.description}"
            for s in self.skills.values() if s.enabled
        ])

        # Layer 2: 匹配到的SKILL注入body
        layer2_parts = []
        if user_input:
            matched = self.match_skills(user_input)
            for skill in matched:
                body = skill.get_body()
                if body:
                    layer2_parts.append(skill.to_prompt())

        prompt = f"""## 可用技能 (Available Skills)

你需要根据用户需求选择合适的技能。每个技能都有详细指令, 匹配后会自动加载。

{layer1}

使用规则:
- 当用户提到与某个技能相关的需求时, 阅读该技能的详细指令后再执行
- 技能不是工具, 而是工作流程指导
"""
        if layer2_parts:
            prompt += "\n## 匹配的技能详情\n\n" + "\n".join(layer2_parts)

        return prompt


skill_manager = SkillManager()
