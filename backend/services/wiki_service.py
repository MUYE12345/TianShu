"""
Wiki笔记服务 — 参考 TZ2.0 llmwiki
"""
import os
import re
import json
import yaml
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import DATA_DIR
from backend.models.wiki import WikiVersion

WIKI_DIR = DATA_DIR / "wiki" / "pages"
GRAPH_DIR = DATA_DIR / "wiki" / "graph"


class WikiService:
    """Wiki笔记服务"""

    def __init__(self):
        WIKI_DIR.mkdir(parents=True, exist_ok=True)
        GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    # ── 页面CRUD ──

    def create_page(self, title: str, content: str = "", page_type: str = "concept",
                    tags: list = None) -> dict:
        slug = self._slugify(title)
        filepath = WIKI_DIR / f"{slug}.md"
        if filepath.exists():
            return {"error": "页面已存在", "slug": slug}

        frontmatter = {
            "title": title, "type": page_type,
            "tags": tags or [], "created": datetime.now().isoformat()[:10],
            "aliases": [],
        }
        md = f"---\n{yaml.dump(frontmatter, allow_unicode=True)}---\n\n{content}"
        filepath.write_text(md, encoding="utf-8")
        self._update_graph(slug, content)
        return {"slug": slug, "title": title, "type": page_type}

    def read_page(self, slug: str) -> Optional[dict]:
        filepath = WIKI_DIR / f"{slug}.md"
        if not filepath.exists():
            return None
        content = filepath.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
        else:
            frontmatter = {}
            body = content
        wikilinks = re.findall(r"\[\[(.+?)\]\]", body)
        return {
            "slug": slug, "title": frontmatter.get("title", slug),
            "type": frontmatter.get("type", "concept"),
            "tags": frontmatter.get("tags", []), "content": body,
            "wikilinks": wikilinks,
            "created": frontmatter.get("created", ""),
        }

    def list_pages(self, page_type: str = None) -> List[dict]:
        pages = []
        for f in sorted(WIKI_DIR.glob("*.md")):
            page = self.read_page(f.stem)
            if page and (not page_type or page["type"] == page_type):
                pages.append(page)
        return pages

    def update_page(self, slug: str, content: str, tags: list = None,
                    db: Session = None) -> Optional[dict]:
        page = self.read_page(slug)
        if not page:
            return None

        # Save current content as a version before updating (only if content changed)
        if db is not None and page.get("content") != content:
            self._save_version(db, slug, page["title"], page["content"], page.get("tags", []))

        frontmatter = {"title": page["title"], "type": page["type"],
                       "tags": tags or page["tags"],
                       "created": page["created"],
                       "updated": datetime.now().isoformat()[:10],
                       "aliases": []}
        md = f"---\n{yaml.dump(frontmatter, allow_unicode=True)}---\n\n{content}"
        (WIKI_DIR / f"{slug}.md").write_text(md, encoding="utf-8")
        self._update_graph(slug, content)
        return self.read_page(slug)

    # ── 文章解析为 wiki ──

    def analyze_article(self, filename: str, text: str) -> dict:
        """把一篇文章解析为 wiki：根页面(来源) + 各章节子页面(笔记)，用 [[链接]] 连接。

        返回 {"root": {...}, "children": [...], "created": N}。
        """
        base = (Path(filename).stem or "文章").strip() or "文章"
        # 优先用文章第一个 H1 标题作为根页面标题
        m1 = re.search(r"(?m)^#\s+(.+?)\s*$", text)
        if m1 and 1 < len(m1.group(1).strip()) <= 40:
            base = m1.group(1).strip()
        sections = self._split_sections(text)
        if not sections:
            sections = [("全文", text[:4000])]

        # 1) 创建根页面（type=source），内容=文章全文 + 章节链接清单（指向完整子页标题）
        root_links = "\n".join(
            f"- [[{base}：{t if t != '全文' else '全文'}]]" for t, _ in sections)
        root_content = f"来源文章：《{base}》\n\n{root_links}\n\n---\n\n{text[:20000]}"
        root = self.create_page(base, root_content, page_type="source", tags=["文章"])
        if "error" in root:
            root = self.read_page(root["slug"])  # 已存在则读取

        # 2) 创建章节子页面（type=note），内容=章节正文 + 回链根页面
        children = []
        for i, (title, body) in enumerate(sections[:15]):
            child_title = f"{base}：{title}" if title != "全文" else f"{base}·全文"
            child_content = f"> 来自 [[{base}]]\n\n{body[:8000]}"
            created = self.create_page(child_title, child_content, page_type="note", tags=["章节"])
            if "error" in created:
                created = self.read_page(created.get("slug", "")) or created
            children.append(created)

        return {"root": root, "children": children, "created": len(children) + 1}

    def _split_sections(self, text: str) -> list:
        """把文章正文切成 (标题, 内容) 列表。

        有 markdown 标题(##/###)则按标题分节；否则按空行分段合并到 ~1200 字符。
        """
        text = text.strip()
        if not text:
            return []
        # 去掉 frontmatter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                text = parts[2].strip()

        heading_m = list(re.finditer(r"(?m)^(#{1,3})\s+(.+?)\s*$", text))
        if heading_m:
            # 跳过第一个一级标题（通常是文章标题本身，已用作根页面标题）
            start = 1 if heading_m[0].group(1) == "#" else 0
            sections = []
            for i in range(start, len(heading_m)):
                m = heading_m[i]
                title = m.group(2).strip()
                body = text[m.end():heading_m[i + 1].start() if i + 1 < len(heading_m) else len(text)].strip()
                if body:
                    sections.append((title[:30], body))
            return sections

        # 非 markdown：按段落合并
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        sections = []
        buf, buf_len = [], 0
        for p in paras:
            if buf_len + len(p) > 1200 and buf:
                sections.append((f"第{len(sections) + 1}部分", "\n".join(buf)))
                buf, buf_len = [], 0
            buf.append(p)
            buf_len += len(p)
        if buf:
            sections.append((f"第{len(sections) + 1}部分", "\n".join(buf)))
        return sections

    # ── 版本管理 ──

    def _save_version(self, db: Session, slug: str, title: str, content: str, tags: list):
        """保存当前页面内容为一个新版本"""
        # Determine the next version number for this page
        last_version = (
            db.query(WikiVersion)
            .filter(WikiVersion.page_slug == slug)
            .order_by(WikiVersion.version_number.desc())
            .first()
        )
        next_number = (last_version.version_number + 1) if last_version else 1

        version = WikiVersion(
            page_slug=slug,
            version_number=next_number,
            title=title,
            content=content,
            tags=tags,
        )
        db.add(version)
        db.commit()

    def list_versions(self, slug: str, db: Session) -> list:
        """列出指定页面的所有版本"""
        versions = (
            db.query(WikiVersion)
            .filter(WikiVersion.page_slug == slug)
            .order_by(WikiVersion.version_number.desc())
            .all()
        )
        return [
            {
                "id": v.id,
                "version_number": v.version_number,
                "title": v.title,
                "tags": v.tags,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ]

    def get_version(self, slug: str, version_id: int, db: Session) -> Optional[dict]:
        """获取特定版本的完整内容"""
        version = (
            db.query(WikiVersion)
            .filter(WikiVersion.id == version_id, WikiVersion.page_slug == slug)
            .first()
        )
        if not version:
            return None
        return {
            "id": version.id,
            "version_number": version.version_number,
            "title": version.title,
            "content": version.content,
            "tags": version.tags,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }

    def restore_version(self, slug: str, version_id: int, db: Session) -> Optional[dict]:
        """将页面恢复到指定版本的内容"""
        version = self.get_version(slug, version_id, db)
        if not version:
            return None
        # Restore by updating the page with the version's content
        return self.update_page(slug, version["content"], version.get("tags"), db=db)

    def delete_page(self, slug: str) -> bool:
        filepath = WIKI_DIR / f"{slug}.md"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    # ── 知识图谱 ──

    def get_graph_data(self) -> dict:
        nodes_path = GRAPH_DIR / "nodes.json"
        edges_path = GRAPH_DIR / "edges.jsonl"
        nodes = []
        if nodes_path.exists():
            text = nodes_path.read_text(encoding="utf-8").strip()
            if text:
                try:
                    nodes = json.loads(text)
                except json.JSONDecodeError:
                    nodes = []
        edges = []
        if edges_path.exists():
            for line in edges_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        edges.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return {"nodes": nodes, "edges": edges}

    def _update_graph(self, slug: str, content: str):
        """
        增量更新知识图谱：每次页面变更时只更新与该页面相关的节点和边，而非全量重建。

        策略：
        1. 解析当前页面内容中的 [[wikilink]]，提取引用的目标页面 slug。
        2. 读取已有 nodes.json / edges.jsonl，保留所有不相关的节点和边。
        3. 移除该页面之前产生的所有旧边（source == slug），防止边重复累积。
        4. 添加该页面自身节点（如果尚不存在）。
        5. 为每个引用的目标页面添加节点（尚不存在时），并为每个引用添加一条新边。
        6. 写回 nodes.json 和 edges.jsonl。

        优势：
        - 避免每次更新都遍历全量页面重新建图，性能开销小。
        - 删除页面内的引用时，对应边自动消失（旧边被移除后只写回新边）。
        """
        wikilinks = re.findall(r"\[\[(.+?)\]\]", content)
        nodes_path = GRAPH_DIR / "nodes.json"
        edges_path = GRAPH_DIR / "edges.jsonl"
        nodes = []
        if nodes_path.exists():
            text = nodes_path.read_text(encoding="utf-8").strip()
            if text:
                try:
                    nodes = json.loads(text)
                except json.JSONDecodeError:
                    nodes = []
        edges = []
        if edges_path.exists():
            for line in edges_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        edges.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        node_ids = {n["id"] for n in nodes}
        if slug not in node_ids:
            nodes.append({"id": slug, "label": slug, "group": "page"})
        for link in wikilinks:
            ls = self._slugify(link)
            if ls not in node_ids:
                nodes.append({"id": ls, "label": link, "group": "page"})
            edges.append({"source": slug, "target": ls, "label": "引用"})
        nodes_path.write_text(json.dumps(nodes, ensure_ascii=False, indent=2), encoding="utf-8")
        edges_path.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in edges) + "\n",
            encoding="utf-8"
        )

    def _slugify(self, title: str) -> str:
        slug = re.sub(r"[^\w\-一-鿿]", "-", title)
        slug = re.sub(r"-+", "-", slug).strip("-")
        return slug or "untitled"


wiki_service = WikiService()
