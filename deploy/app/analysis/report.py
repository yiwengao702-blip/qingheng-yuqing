# 文件位置: backend/app/analysis/report.py
# 功能: 结构化舆情研判报告编排与导出（Markdown / HTML / PDF）。
from __future__ import annotations

import datetime
from typing import Dict, List

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle)
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # 注册中文字体（Adobe 宋体），保证 PDF 中文可读
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    HAS_REPORTLAB = True
except Exception:  # pragma: no cover
    HAS_REPORTLAB = False

from app.config import settings


def assemble_report(event: dict, analysis: Dict, narr: Dict[str, str], pr: Dict) -> Dict:
    """组装结构化研判报告（与需求中的报告格式对齐）。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    sent = analysis.get("sentiment", {})
    risk = analysis.get("risk", {})
    sections = [
        {"key": "overview", "title": "一、事件概述", "body": narr.get("overview", "")},
        {"key": "situation", "title": "二、舆情态势", "body": narr.get("situation", "")},
        {"key": "propagation", "title": "三、传播溯源", "body": narr.get("propagation", "")},
        {"key": "viewpoints", "title": "四、核心观点与公众诉求", "body": narr.get("viewpoints", "")},
        {"key": "risk", "title": "五、风险评级与预警", "body": narr.get("risk", "")},
    ]
    report = {
        "kind": "event",
        "title": f"舆情事件研判报告 · {event.get('title', '')}",
        "meta": {
            "事件": event.get("title", ""),
            "事件类别": event.get("category", "其他"),
            "风险等级": risk.get("grade", "C"),
            "监测周期": f"{event.get('start_time', '—')} ~ {now}",
            "生成时间": now,
            "声量": analysis.get("volume", 0),
            "负面占比": f"{round(sent.get('negative_ratio', 0) * 100)}%",
            "生成方式": "模拟大模型（可替换为真实 LLM）" if settings.use_mock_llm else "真实大模型",
        },
        "summary": narr.get("overview", ""),
        "sections": sections,
        "pr_strategy": pr.get("strategy", []),
        "pr_draft": pr.get("draft", ""),
        "pr_category": pr.get("category", "其他"),
        "pr_demand": pr.get("demand", ""),
    }
    return report


def _word_of(h) -> str:
    """兼容热词的多种结构（dict / list / tuple / str），统一取出词面。"""
    if isinstance(h, dict):
        return str(h.get("word") or h.get("name") or "")
    if isinstance(h, (list, tuple)):
        return str(h[0]) if h else ""
    return str(h)


def assemble_periodic(overview: Dict, events: List[dict], alerts: List[dict],
                      kind: str = "daily") -> Dict:
    """组装周期简报（日报 / 周报）：基于全网态势、重点事件排行与预警进展自动汇编。

    与事件研判报告共用导出链路（Markdown / HTML / PDF），因此保持同样的顶层结构：
    {kind, title, meta, summary, sections}。周期简报不含单独的公关话术章节，
    导出函数会依据 kind == "periodic" 跳过该章节。
    """
    now = datetime.datetime.now()
    is_daily = kind == "daily"
    label = "舆情日报" if is_daily else "舆情周报"
    if is_daily:
        period = now.strftime("%Y-%m-%d")
        cycle_note = "每日 09:00 自动生成"
    else:
        week_start = (now - datetime.timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        period = f"{week_start} ~ {now.strftime('%Y-%m-%d')}"
        cycle_note = "每周一自动生成"

    total = overview.get("total_volume", 0)
    sent = overview.get("sentiment", {}) or {}
    pos, neu, neg = sent.get("positive", 0), sent.get("neutral", 0), sent.get("negative", 0)
    neg_ratio = round(neg / total * 100) if total else 0
    dedup = overview.get("dedup", {}) or {}
    risk_dist = overview.get("risk_distribution", {}) or {}
    event_count = overview.get("event_count", 0)
    alert_count = overview.get("alert_count", 0)
    hotwords = overview.get("hotwords", []) or []

    # ---- 一、总体态势 ----
    top_words = "、".join(_word_of(h) for h in hotwords[:12] if _word_of(h))
    # 口径说明：total_volume 为去重后的有效声量，采集总量在 dedup.total
    raw_total = dedup.get("total", total)
    s1 = (
        f"统计周期内，全网共采集舆情信息 {raw_total} 条，经 SimHash 指纹去重后保留 {total} 条"
        f"（判定为重复 {dedup.get('duplicates', 0)} 条）。"
        f"情感分布为：正面 {pos} 条、中性 {neu} 条、负面 {neg} 条，负面占比 {neg_ratio}%。"
        f"整体情绪{'偏于负面，需重点关注' if neg_ratio >= 50 else '总体平稳可控'}。\n"
        f"风险分布：S 级 {risk_dist.get('S', 0)} 条、A 级 {risk_dist.get('A', 0)} 条、"
        f"B 级 {risk_dist.get('B', 0)} 条、C 级 {risk_dist.get('C', 0)} 条。"
        + (f"\n高频热词：{top_words}。" if top_words else "")
    )

    # ---- 二、重点事件排行 ----
    ranked = sorted(events, key=lambda e: (e.get("grade") != "S", e.get("grade") != "A",
                                          -e.get("intensity", 0)))[:5]
    if ranked:
        rows = [
            f"{i}. 【{e.get('grade', 'C')} 级】{e.get('title', '')}（{e.get('category', '其他')}）"
            f"：声量 {e.get('volume', 0)}、烈度 {e.get('intensity', 0)}、"
            f"负面占比 {round(e.get('negative_ratio', 0) * 100)}%。"
            for i, e in enumerate(ranked, 1)
        ]
        s2 = "按风险等级与舆情烈度排序，本期重点关注事件如下：\n" + "\n".join(rows)
    else:
        s2 = "统计周期内未形成规模性舆情事件。"

    # ---- 三、预警与处置进展 ----
    by_type: Dict[str, int] = {}
    for a in alerts:
        t = a.get("type", "其他")
        by_type[t] = by_type.get(t, 0) + 1
    type_txt = "、".join(f"{k} {v} 条" for k, v in by_type.items()) or "无"
    high = [a for a in alerts if a.get("level") in ("S", "A")]
    s3 = (f"本期共触发预警 {alert_count} 条，其中 S/A 级高危预警 {len(high)} 条。"
          f"预警类型分布：{type_txt}。\n")
    if high:
        s3 += "高危预警明细：\n" + "\n".join(
            f"· [{a.get('level')}] {a.get('title', '')}（{a.get('time', '')}）" for a in high[:5])
    else:
        s3 += "本期无 S/A 级高危预警，整体处于可管可控状态。"

    # ---- 四、趋势研判与关注建议 ----
    advice: List[str] = []
    if risk_dist.get("S", 0) or risk_dist.get("A", 0):
        advice.append("对 S/A 级高危信息建立 2 小时响应机制，优先核实信源真实性并同步处置进度。")
    if neg_ratio >= 50:
        advice.append("负面占比较高，建议公关与业务方联合拟定统一口径，避免多头回应造成次生舆情。")
    else:
        advice.append("整体情绪可控，维持常规监测频次即可，重点关注负面信息的情感演化拐点。")
    if len(high) >= 3:
        advice.append("高危预警较为集中，建议成立专项跟踪小组，按事件维度逐一闭环。")
    advice.append("持续关注高频热词背后的公众诉求变化，并将诉求点回传至产品与服务改进流程。")
    s4 = "综合本期态势，提出如下关注建议：\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(advice, 1))

    sections = [
        {"key": "overview", "title": "一、总体态势", "body": s1},
        {"key": "events", "title": "二、重点事件排行", "body": s2},
        {"key": "alerts", "title": "三、预警与处置进展", "body": s3},
        {"key": "advice", "title": "四、趋势研判与关注建议", "body": s4},
    ]
    return {
        "kind": "periodic",
        "title": f"{label} · {period}",
        "meta": {
            "简报类型": label,
            "统计周期": period,
            "生成时间": now.strftime("%Y-%m-%d %H:%M"),
            "生成方式": cycle_note,
            "监测事件": f"{event_count} 起",
            "全网声量": total,
            "负面占比": f"{neg_ratio}%",
            "预警总数": alert_count,
        },
        "summary": s1,
        "sections": sections,
    }


def export_markdown(report: Dict) -> str:
    """导出 Markdown 格式报告。"""
    lines: List[str] = []
    lines.append(f"# {report['title']}\n")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    for k, v in report["meta"].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    for sec in report["sections"]:
        lines.append(f"## {sec['title']}\n")
        lines.append(sec["body"] + "\n")
    if report.get("kind") == "periodic":
        # 周期简报无单独的公关话术章节，到此为止
        return "\n".join(lines)
    lines.append("## 六、公关应对策略与回应话术草案\n")
    lines.append(f"**事件性质**：{report['pr_category']}　**核心诉求**：{report['pr_demand']}\n")
    lines.append("**应对策略**：\n")
    for s in report["pr_strategy"]:
        lines.append(f"- {s}")
    lines.append("\n**回应话术草案**：\n")
    lines.append("```\n" + report["pr_draft"] + "\n```\n")
    return "\n".join(lines)


def export_html(report: Dict) -> str:
    """导出 HTML 报告（含打印样式，可直接「打印为 PDF」）。"""
    meta_rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in report["meta"].items())
    sec_html = ""
    for sec in report["sections"]:
        # pre-line 保留正文里的 \n 换行，否则多段内容会被压成一行
        sec_html += f'<h2>{sec["title"]}</h2><div style="white-space:pre-line">{sec["body"]}</div>'
    if report.get("kind") == "periodic":
        tail = ""
    else:
        strategy_html = "".join(f"<li>{s}</li>" for s in report["pr_strategy"])
        tail = f"""<h2>六、公关应对策略与回应话术草案</h2>
<p><b>事件性质</b>：{report['pr_category']}　<b>核心诉求</b>：{report['pr_demand']}</p>
<p><b>应对策略</b>：</p><ul>{strategy_html}</ul>
<p><b>回应话术草案</b>：</p>
<div class="draft">{report['pr_draft']}</div>"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{report['title']}</title>
<style>
 body{{font-family:"Microsoft YaHei",sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#222;line-height:1.7}}
 h1{{border-bottom:3px solid #c0392b;padding-bottom:8px}} h2{{color:#c0392b;margin-top:28px}}
 table{{border-collapse:collapse;width:100%;margin:12px 0}} th,td{{border:1px solid #ddd;padding:8px 10px;text-align:left}}
 th{{background:#f7f7f7;width:140px}} .draft{{background:#fbfbfb;border-left:4px solid #c0392b;padding:12px;white-space:pre-wrap}}
 @media print{{body{{margin:0}}}}
</style></head>
<body>
<h1>{report['title']}</h1>
<table>{meta_rows}</table>
{sec_html}
{tail}
</body></html>"""


def export_pdf(report: Dict) -> bytes:
    """导出 PDF 报告（依赖 reportlab + 中文字体）。不可用时回退到 HTML 字节。"""
    if not HAS_REPORTLAB:
        return export_html(report).encode("utf-8")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Cn", parent=styles["Normal"],
                              fontName="STSong-Light", fontSize=10, leading=16))
    styles.add(ParagraphStyle(name="CnH1", parent=styles["Title"],
                              fontName="STSong-Light", fontSize=18))
    styles.add(ParagraphStyle(name="CnH2", parent=styles["Heading2"],
                              fontName="STSong-Light", fontSize=13))
    doc = SimpleDocTemplate(None, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            title=report["title"])
    from io import BytesIO
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm, title=report["title"])
    flow = []
    flow.append(Paragraph(report["title"], styles["CnH1"]))
    meta_data = [[k, str(v)] for k, v in report["meta"].items()]
    t = Table(meta_data, colWidths=[4 * cm, 12 * cm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "STSong-Light", 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
    ]))
    flow.append(t)
    flow.append(Spacer(1, 0.4 * cm))
    for sec in report["sections"]:
        flow.append(Paragraph(sec["title"], styles["CnH2"]))
        # Paragraph 不识别 \n，必须转成 <br/>，否则多段正文会被压成一行
        flow.append(Paragraph(sec["body"].replace("\n", "<br/>"), styles["Cn"]))
    if report.get("kind") == "periodic":
        doc.build(flow)
        return buf.getvalue()
    flow.append(Paragraph("六、公关应对策略与回应话术草案", styles["CnH2"]))
    flow.append(Paragraph(f"事件性质：{report['pr_category']}　核心诉求：{report['pr_demand']}", styles["Cn"]))
    for s in report["pr_strategy"]:
        flow.append(Paragraph(f"• {s}", styles["Cn"]))
    flow.append(Paragraph("回应话术草案：", styles["Cn"]))
    flow.append(Paragraph(report["pr_draft"].replace("\n", "<br/>"), styles["Cn"]))
    doc.build(flow)
    return buf.getvalue()
