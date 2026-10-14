# 文件位置: backend/app/analysis/llm_sim.py
# 功能: 模拟大模型层 —— 基于分析结果生成研判叙事与公关应对策略/回应话术草案。
#       演示态默认开启；生产可替换为真实 LLM 接口（保持相同入参/出参契约）。
from __future__ import annotations

from typing import Dict

from app.config import settings

# 事件性质 -> 公关应对重点
_CATEGORY_FOCUS = {
    "质量争议": ["事实澄清", "涉事产品下架/召回", "委托第三方权威检测并公示", "畅通退换货与补偿通道"],
    "服务纠纷": ["公开致歉并给出补偿方案", "优化服务流程与时效", "专人跟进个案", "建立客诉闭环机制"],
    "合规风险": ["主动对接监管部门", "数据与方法论透明披露", "限期整改并公示进度", "合规自查常态化"],
    "公共事件": ["民生关切优先回应", "协同政府/行业权威发声", "信息持续透明更新", "避免次生舆情"],
    "其他": ["持续监测跟踪", "保持真诚沟通", "准备事实口径", "必要时发布官方说明"],
}


def _category_of(event: dict, override: str | None = None) -> str:
    if override:
        return override
    return event.get("category", "其他")


def generate_pr_strategy(event: dict, analysis: Dict, category: str | None = None,
                         demand: str | None = None) -> Dict:
    """生成公关应对策略与回应话术草案。"""
    cat = _category_of(event, category)
    focus = _CATEGORY_FOCUS.get(cat, _CATEGORY_FOCUS["其他"])

    grade = analysis.get("risk", {}).get("grade", "C")
    neg_ratio = analysis.get("sentiment", {}).get("negative_ratio", 0.0)
    top_viewpoint = ""
    if analysis.get("viewpoints"):
        top_viewpoint = analysis["viewpoints"][0].get("label", "")

    demand_text = demand or analysis.get("core_demand") or "（未提供，建议结合核心观点提炼）"

    strategy = [
        f"总体定调：以「{cat}」为主线，当前风险等级 {grade}，负面声量占比约 {round(neg_ratio * 100)}%。",
        "响应节奏：2 小时内首发回应、24 小时内进展同步、争议澄清随证据更新。",
    ] + [f"应对要点：{f}" for f in focus]

    draft = (
        f"【关于「{event.get('title', '')}」的回应说明】\n"
        f"近期我们关注到公众围绕「{top_viewpoint or event.get('title', '')}」的讨论，"
        f"核心诉求集中于：{demand_text}。我们高度重视，现作如下说明：\n"
        f"一、事实层面：已成立专项小组核查相关情况，{focus[0] if focus else '正在核实'}。\n"
        f"二、情感层面：对给大家带来的困扰与不安，我们真诚致歉，理解并重视每一位用户的感受。\n"
        f"三、行动层面：{'; '.join(focus[1:3]) if len(focus) > 1 else '将尽快公布处置进展'}。\n"
        f"四、后续：我们将持续同步进展，并接受社会监督。感谢理解与信任。"
    )
    return {
        "category": cat,
        "demand": demand_text,
        "strategy": strategy,
        "draft": draft,
        "generated_by": "mock-llm" if settings.use_mock_llm else "real-llm",
    }


def narrative_sections(event: dict, analysis: Dict) -> Dict[str, str]:
    """为报告生成各章节叙事文本（模拟大模型总结）。"""
    sent = analysis.get("sentiment", {})
    risk = analysis.get("risk", {})
    prop = analysis.get("propagation", {})
    viewpoints = analysis.get("viewpoints", [])

    overview = (
        f"「{event.get('title', '')}」事件自 {event.get('start_time', '—')} 起进入监测视野，"
        f"归类为「{event.get('category', '其他')}」。截至统计时点共采集相关舆情 "
        f"{analysis.get('volume', 0)} 条，当前风险等级评定为 {risk.get('grade', 'C')}。"
    )

    situation = (
        f"全网声量 {analysis.get('volume', 0)} 条，其中正面 {sent.get('positive', 0)} 条、"
        f"中性 {sent.get('neutral', 0)} 条、负面 {sent.get('negative', 0)} 条，"
        f"负面占比约 {round(sent.get('negative_ratio', 0) * 100)}%。"
        f"情感结构显示公众情绪以"
        f"{analysis.get('dominant_emotion') or '中性'}为主，需重点关注负面情绪发酵。"
    )

    prop_text = "暂无足够传播数据。"
    if prop.get("origin"):
        origin = prop["origin"]
        prop_text = (
            f"首发信源为 {origin.get('platform')} 用户「{origin.get('author')}」"
            f"（{origin.get('publish_time')}），内容要点：{origin.get('content', '')}。"
            f"传播最大深度约 {prop.get('max_depth', 0)} 层，关键引爆节点 "
            f"{len(prop.get('key_nodes', []))} 个，呈"
            f"{'指数扩散' if risk.get('factors', {}).get('spread_speed', 0) > 10 else '平稳蔓延'}态势。"
        )

    vp_text = "未聚类出显著观点簇。"
    if viewpoints:
        parts = [
            f"观点簇「{v.get('label')}」（{v.get('size')}条，意图：{v.get('intent')}）：{v.get('representative', {}).get('content', '')}"
            for v in viewpoints[:3]
        ]
        vp_text = "；".join(parts) + "。"

    risk_text = (
        f"舆情烈度指数 {risk.get('intensity', 0)}，风险等级 {risk.get('grade', 'C')}。"
        f"主要驱动因素：传播速度 {risk.get('factors', {}).get('spread_speed')} 条/小时、"
        f"累计互动 {risk.get('factors', {}).get('interaction')}、"
        f"最高 KOL 权重 {risk.get('factors', {}).get('kol_max')}、"
        f"高危敏感词命中 {risk.get('factors', {}).get('sensitive_hits')} 次。"
    )

    return {
        "overview": overview,
        "situation": situation,
        "propagation": prop_text,
        "viewpoints": vp_text,
        "risk": risk_text,
    }
