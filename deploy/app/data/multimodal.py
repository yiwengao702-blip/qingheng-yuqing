# 文件位置: backend/app/data/multimodal.py
# 功能: 多模态解析模拟（图文 OCR、音视频 ASR 转录）。演示态用预置文本映射，
#       生产可替换为真实 OCR/ASR 服务（保持相同入参/出参契约即可）。
from __future__ import annotations

from typing import Dict

from app.data.clean import normalize_text

# 预置 OCR 样本（图片 -> 识别文字）。演示用，覆盖食品安全/服务/合规等场景。
OCR_SAMPLES: Dict[str, str] = {
    "ocr_food_1": "实拍：瓶身封口处有不明黑色异物，已拍照留存，@XX监管 请关注",
    "ocr_food_2": "门店后厨监控截图流出：食材落地后直接装盘，卫生堪忧",
    "ocr_logi_1": "快递面单合集：连续三单显示已签收但本人未收到，系统异常",
    "ocr_ev_1": "车友群聊截图：仪表盘续航 320km 实际仅 210km，虚标严重",
    "ocr_pub_1": "菜市场价签：青菜 12 元/斤，较上周翻倍，居民排队抢购",
}

# 预置 ASR 样本（音视频 -> 转写文字）
ASR_SAMPLES: Dict[str, str] = {
    "asr_food_1": "我昨天买的这个饮料，打开以后发现里面飘着一块黑乎乎的东西，喝下去肚子到现在还疼，真的太离谱了。",
    "asr_food_2": "我们是这家店的常客，今天看到后厨那个样子，以后再也不会去了，必须给大家提个醒。",
    "asr_logi_1": "客服让我等，等了五天还是没消息，我的急件就这么没了，谁负责？",
    "asr_ev_1": "销售当时跟我说能跑五百公里，结果高速上一半就报警了，这不是骗人是什么。",
    "asr_pub_1": "菜价涨得太凶了，一家老小开销一下子上去了，希望有关部门管一管。",
}


def ocr_image(sample_id: str) -> str:
    """模拟图文 OCR 识别。"""
    return OCR_SAMPLES.get(sample_id, "（示例图片，OCR 未能识别到有效文字）")


def asr_audio(sample_id: str) -> str:
    """模拟音视频 ASR 转录。"""
    return ASR_SAMPLES.get(sample_id, "（示例音频，ASR 未能转写有效语音）")


def parse_multimodal_item(item: dict) -> dict:
    """解析一条多模态原始条目，输出抽取文本与清洗后文本。

    item 结构：{"content_type": "ocr"|"transcript"|"text", "sample_id"?, "content"?}
    """
    ct = item.get("content_type", "text")
    if ct == "ocr":
        raw = ocr_image(item.get("sample_id", ""))
    elif ct == "transcript":
        raw = asr_audio(item.get("sample_id", ""))
    else:
        raw = item.get("content", "")
    return {"extracted_text": raw, "cleaned_text": normalize_text(raw)}
