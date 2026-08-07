"""
社区技能市场 — 安装时创建真实 SKILL.md 到 skills 目录, skill_manager 重载后即生效。

SKILL.md 遵循 YAML frontmatter(name/description) + Markdown 工作流指令。
"""
import os
from pathlib import Path

SKILLS_DIR = Path(__file__).parent

# 市场 id → SKILL.md 内容模板(真实可用)
COMMUNITY_SKILLS = {
    "code-review": """---
name: code-review
description: 审查代码变更, 发现 bug、性能问题和安全漏洞
version: 0.9.0
---

# 代码审查技能

当用户要求审查代码/提交/PR 时, 执行以下流程:

1. **获取变更**: 明确要审查的代码文件或 diff(若为 git 仓库, 可用 git 工具获取 diff)。
2. **逐维度审查**:
   - 正确性: 边界条件、空指针、并发、资源泄漏
   - 性能: 时间复杂度、不必要的重复计算、N+1 查询
   - 安全: 注入、越权、密钥泄漏、未过滤输入
   - 可维护性: 命名、职责单一、重复代码
3. **输出报告**: 按 严重/一般/建议 分级, 每条给出 位置 + 问题 + 修复建议。
4. 若无严重问题, 明确说明"未发现严重问题"。

不要修改代码, 只输出审查报告。
""",
    "data-visualizer": """---
name: data-visualizer
description: 将数据转换为图表和可视化报告
version: 1.1.0
---

# 数据可视化技能

当用户要求把数据可视化时, 执行以下流程:

1. **理解数据**: 明确数据结构(表格/CSV/JSON)与用户要表达的重点。
2. **选图**: 趋势→折线; 对比→柱状; 占比→饼图; 分布→直方图/箱线图; 关联→散点。
3. **生成图表**: 优先用 HTML+ECharts 生成可交互图表(内联 JS), 或 Python matplotlib 出图。
4. **输出**: 图表 + 一句结论解读。

若数据是文件(CSV/Excel), 先用文件工具读取后再绘图。
""",
    "email-composer": """---
name: email-composer
description: 根据要求撰写正式邮件, 支持多语言
version: 0.8.0
---

# 邮件撰写技能

当用户要求撰写邮件时, 执行以下流程:

1. **明确要素**: 收件人身份、主题、目的、语气(正式/礼貌/简洁)、长度。
2. **结构**: 称呼 → 背景一句 → 目的与要点(分条) → 行动请求/截止时间 → 结尾敬语。
3. **多语言**: 默认中文; 用户要求英文或其他语言时切换, 保持术语准确。
4. **输出**: 直接给出可直接发送的邮件正文。

不要虚构不存在的收件人邮箱或敏感信息。
""",
}


def install_community_skill(skill_id: str) -> bool:
    """创建 SKILL.md 到 skills/<id>/ 目录。"""
    content = COMMUNITY_SKILLS.get(skill_id)
    if not content:
        return False
    skill_dir = SKILLS_DIR / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return True


def uninstall_community_skill(skill_id: str) -> bool:
    """删除社区技能目录(仅当它是社区技能)。"""
    if skill_id not in COMMUNITY_SKILLS:
        return False
    import shutil
    skill_dir = SKILLS_DIR / skill_id
    if skill_dir.exists():
        shutil.rmtree(skill_dir, ignore_errors=True)
    return True
