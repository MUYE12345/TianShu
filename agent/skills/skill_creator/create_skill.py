"""
Skill创建工具 — 由Agent或用户调用来创建新技能

创建流程:
1. 选择模板 (tool_skill / agent_skill / workflow_skill)
2. 填写名称和描述
3. 定义工具列表或Agent配置
4. 写入 skill.yaml 和提示词模板
5. 注册到 skill_manager
"""
import os
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from agent.tools.registry import register_tool

SKILLS_DIR = Path(__file__).parent.parent


class SkillTemplate:
    """SKILL模板定义"""

    TEMPLATES = {
        "tool_skill": {
            "description": "提供一组工具的SKILL",
            "structure": {
                "skill.yaml": {
                    "name": "{{name}}",
                    "description": "{{description}}",
                    "version": "0.1.0",
                    "type": "tool_skill",
                    "tools": ["{{tool_name}}"],
                },
                "templates/system.txt": "你是{{name}}助手。\n你的职责: {{description}}\n\n使用的工具:\n{{tools_list}}",
            }
        },
        "agent_skill": {
            "description": "定义一个专用Agent角色的SKILL",
            "structure": {
                "skill.yaml": {
                    "name": "{{name}}",
                    "description": "{{description}}",
                    "version": "0.1.0",
                    "type": "agent_skill",
                    "agent": {
                        "role": "{{role}}",
                        "model": "default",
                    },
                },
                "templates/system.txt": "你是{{role}}。\n\n## 角色定位\n{{description}}\n\n## 行为规范\n1. 使用专业术语\n2. 提供详细解释\n3. 引用可靠来源",
                "agents/agent.py": '"""{{name}} Agent"""\nfrom agent.skills.skill_base import BaseSkill\n\nclass {{name_class}}Skill(BaseSkill):\n    """{{description}}"""\n    pass\n',
            }
        },
        "workflow_skill": {
            "description": "定义多步骤工作流的SKILL",
            "structure": {
                "skill.yaml": {
                    "name": "{{name}}",
                    "description": "{{description}}",
                    "version": "0.1.0",
                    "type": "workflow_skill",
                    "steps": [
                        {"name": "step1", "description": "第一步"},
                        {"name": "step2", "description": "第二步"},
                    ],
                },
                "templates/system.txt": "你是工作流助手。\n工作流: {{name}}\n\n步骤:\n{{steps_list}}",
            }
        },
    }

    @classmethod
    def list_templates(cls) -> str:
        """列出所有可用模板"""
        result = "可用SKILL模板:\n"
        for name, tpl in cls.TEMPLATES.items():
            result += f"  - {name}: {tpl['description']}\n"
        return result


def create_skill(name: str, description: str, template_type: str = "tool_skill",
                 tools: list = None, role: str = "", steps: list = None) -> str:
    """
    创建新SKILL

    Args:
        name: SKILL名称(英文字母)
        description: SKILL功能描述
        template_type: 模板类型(tool_skill/agent_skill/workflow_skill)
        tools: 工具列表(仅tool_skill)
        role: Agent角色(仅agent_skill)
        steps: 工作流步骤(仅workflow_skill)

    Returns:
        创建结果信息
    """
    import re as _re
    # 名校验: 仅字母/数字/_- (防目录穿越与非法路径)
    if not name or not _re.fullmatch(r"[A-Za-z0-9_\-]+", name or ""):
        return (f"错误: SKILL 名称 '{name}' 不合法, 仅允许字母/数字/下划线/中划线")

    template = SkillTemplate.TEMPLATES.get(template_type)
    if not template:
        return f"错误: 不支持的模板类型 '{template_type}'\n{SkillTemplate.list_templates()}"

    skill_dir = SKILLS_DIR / name
    if skill_dir.exists():
        return f"错误: SKILL '{name}' 已存在"

    # 创建目录结构
    structure = template["structure"]
    for filepath, content_template in structure.items():
        full_path = skill_dir / filepath
        os.makedirs(full_path.parent, exist_ok=True)

        # 替换模板变量
        content = _render_template(content_template, {
            "name": name,
            "description": description,
            "tool_name": tools[0] if tools else "default_tool",
            "tools_list": "\n".join(f"- {t}" for t in (tools or [])),
            "role": role or f"{name}助手",
            "name_class": "".join(w.capitalize() for w in name.replace("-", "_").split("_")),
            "steps_list": "\n".join(f"- {s.get('name', '')}: {s.get('description', '')}" for s in (steps or [])),
        })

        if isinstance(content, dict):
            with open(full_path, "w", encoding="utf-8") as f:
                yaml.dump(content, f, allow_unicode=True, default_flow_style=False)
        else:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

    # 添加到skill_manager
    try:
        from agent.skills.skill_manager import skill_manager, SkillInfo
        skill_manager.skills[name] = SkillInfo(name, description, "0.1.0")
        registered = "，已注册到SKILL管理器"
    except Exception:
        registered = "（skill_manager未就绪，需手动注册）"

    return f"SKILL '{name}' 已创建{registered}\n  类型: {template_type}\n  位置: {skill_dir}"


def list_skills() -> str:
    """列出所有已安装SKILL"""
    from agent.skills.skill_manager import skill_manager
    skills = skill_manager.list_skills()
    if not skills:
        return "暂无已安装的SKILL\n使用 create_skill 创建新SKILL"
    return "\n".join([f"  [{s.get('type', '?')}] {s['name']}: {s.get('description', '')}" for s in skills])


def _render_template(template, variables: dict):
    """简单模板渲染, 替换 {{var}} 占位符"""
    if isinstance(template, str):
        result = template
        for key, value in variables.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result
    elif isinstance(template, dict):
        return {k: _render_template(v, variables) for k, v in template.items()}
    elif isinstance(template, list):
        return [_render_template(item, variables) for item in template]
    return template


# 注册为Agent工具
register_tool(
    name="create_skill",
    description="创建新的SKILL技能。可指定模板类型(tool_skill/agent_skill/workflow_skill)和工具列表。",
    parameters={"type": "object", "properties": {
        "name": {"type": "string", "description": "SKILL名称(英文字母)"},
        "description": {"type": "string", "description": "SKILL功能描述"},
        "template_type": {"type": "string", "enum": ["tool_skill", "agent_skill", "workflow_skill"],
                          "description": "模板类型", "default": "tool_skill"},
        "tools": {"type": "array", "items": {"type": "string"}, "description": "工具列表"},
        "role": {"type": "string", "description": "Agent角色(agent_skill用)"},
    }, "required": ["name", "description"]},
    handler=create_skill, category="skill",
)

register_tool(
    name="list_skill_templates",
    description="列出所有可用的SKILL创建模板",
    parameters={"type": "object", "properties": {}},
    handler=lambda: SkillTemplate.list_templates(), category="skill",
)
