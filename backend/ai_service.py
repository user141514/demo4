"""
AI Service — DeepSeek API 封装，借鉴 demo2 的 prompt 工程和 JSON 提取逻辑
"""
import json
import re
from openai import OpenAI
from backend.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_CHAT_MODEL,
    DEEPSEEK_REASONER_MODEL,
    LLM_TIMEOUT,
)

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=LLM_TIMEOUT)

# ── System Prompts（借鉴 demo2 leadership_prompts.py 的精华） ──

SYSTEM_PROMPT = """你是资深领导力建模顾问，服务于中国科技企业。
你的专业领域：胜任力模型构建、BARS行为锚定、领导力发展体系设计。

全局规则：
1. 本次建模只服务一个单一层级/群体，不生成多层级矩阵
2. 信息采集按行业/规模/战略/痛点/目标层级/优秀管理者画像归纳，信息不足时直接指出缺口
3. 维度必须生成4-8个推荐维度+若干备选维度
4. 每个维度包含id、name、definition、sources、priority、rationale
5. 描述聚焦目标层级，长度50-120字
6. 禁用空泛词：积极、主动、高度、认真、负责、努力、认可、重视、关注、善于、较强、具备、出色、优秀、良好
7. 行为锚定必须输出优秀/达标/不达标三档
8. 每条行为以行为动词开头，可观察、可衡量
9. 信息缺失时直接指出，不虚构
10. 只输出JSON，不输出Markdown"""

DOC_ANALYSIS_SYS = """你是领导力建模顾问，从企业文档中提取建模相关信息。
严格按以下格式输出：

【战略关键词】：3-8个战略方向关键词（逗号分隔）
【高绩效行为特征】：2-4条高绩效管理者典型行为描述
【能力要求关键词】：文档中出现的管理者能力要求关键词（逗号分隔）
【建模参考重点】：1-2条最值得纳入领导力模型的核心洞察

用中文回答，每项不超过150字。文档内容不足时如实说明。"""

# ── JSON 提取（借鉴 demo2 leadership_llm.py） ──

class LLMError(Exception):
    pass


def _extract_json(content: str) -> dict:
    """健壮的JSON提取：先直接解析，再去fence，再regex"""
    content = (content or "").strip()
    # 1. 直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 2. 去 markdown fence
    without_fence = content.strip("`")
    if without_fence.lower().startswith("json"):
        without_fence = without_fence[4:].strip()
        try:
            return json.loads(without_fence)
        except json.JSONDecodeError:
            pass
    # 3. Regex 提取第一个 JSON 对象
    match = re.search(r"\{.*\}", content, re.S)
    if not match:
        raise LLMError("AI 输出不包含 JSON")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMError(f"AI JSON 解析失败: {exc}")


# ── Core Functions ─────────────────────────────────────────────

def _call_deepseek(system: str, user: str, max_tokens: int = 2000, use_reasoner: bool = False) -> str:
    model = DEEPSEEK_REASONER_MODEL if use_reasoner else DEEPSEEK_CHAT_MODEL
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def chat(messages: list[dict], context: str = "") -> str:
    """Step1: 引导式对话，采集企业背景信息"""
    user_context = f"\n\n已收集的企业信息：{context}" if context else ""
    conversation = "\n".join(
        f"{'AI' if m['role'] == 'assistant' else '用户'}：{m['content']}"
        for m in messages[-6:]
    )
    user_prompt = f"""正在进行领导力建模信息采集。需收集6项：行业/业务、规模/阶段、战略重点、管理痛点、建模层级、优秀管理者画像。

对话记录：
{conversation}{user_context}

请根据进度自然地回复用户，引导完成信息采集。当收集到足够信息时，在末尾附上摘要：
【摘要】
行业/业务：xxx
规模/阶段：xxx
战略重点：xxx
管理痛点：xxx
建模层级：xxx
优秀画像：xxx"""
    return _call_deepseek(SYSTEM_PROMPT, user_prompt, max_tokens=1000)


def analyze_document(text: str, filename: str) -> str:
    """Step1: 文档分析"""
    user_prompt = f"分析以下文档，提取与领导力建模相关的核心信息。\n文件名：{filename}\n\n文档内容：\n{text[:8000]}"
    return _call_deepseek(DOC_ANALYSIS_SYS, user_prompt, max_tokens=1000)


def generate_dimensions(company_info: str, level: str = "中层管理者") -> dict:
    """Step2: 生成维度 → 返回结构化 dict"""
    prompt = f"""根据以下企业信息，为{level}生成推荐维度和备选维度。
企业背景：{company_info}

输出 JSON：
{{"recommended":[{{"id":"D1","name":"2-5字","definition":"2-3句定义","sources":{{"strategy":"战略来源","framework":"框架来源","interview":"访谈来源"}},"priority":"core|important|supplementary","rationale":"1句理由"}}],"alternatives":[]}}

要求：
- 推荐4-6个核心/重要维度，备选3-5个补充维度
- 名称精炼有力，定义包含可观察行为指向
- 贴合企业实际情况"""
    result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=2000)
    payload = _extract_json(result)

    # 兼容多种输出格式
    recommended = payload.get("recommended") or payload.get("dimensions") or []
    alternatives = payload.get("alternatives") or []

    return {
        "recommended": [
            {
                "id": d.get("id", f"D{i+1}"),
                "name": d.get("name", ""),
                "definition": d.get("definition", ""),
                "sources": d.get("sources", {}),
                "priority": d.get("priority", "important"),
                "rationale": d.get("rationale", ""),
            }
            for i, d in enumerate(recommended)
        ],
        "alternatives": [
            {
                "id": d.get("id", f"DA{i+1}"),
                "name": d.get("name", ""),
                "definition": d.get("definition", ""),
                "priority": d.get("priority", "supplementary"),
            }
            for i, d in enumerate(alternatives)
        ],
    }


def generate_descriptions(dimensions: list, company_info: str, level: str = "中层管理者") -> list:
    """Step3: 生成维度描述 → 返回 list"""
    dims_json = json.dumps(dimensions, ensure_ascii=False)
    prompt = f"""为{level}的每个维度生成定位描述。

维度列表：{dims_json}
企业背景：{company_info}

输出 JSON：
{{"descriptions":[{{"dimension_id":"D1","dimension_name":"维度名","description":"50-120字","quality_check":{{"passed":true,"issues":[]}}}}]}}

要求：
- 每个描述50-120字，聚焦{level}的实际工作场景
- 使用可观察的行为动词（制定、推动、识别、建立、拆解、复盘等）
- quality_check.passed 为 true 表示通过质检"""
    result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=3000)
    payload = _extract_json(result)
    items = payload.get("descriptions") or []
    return [
        {
            "dimension_id": d.get("dimension_id", ""),
            "dimension_name": d.get("dimension_name", ""),
            "description": d.get("description", ""),
            "quality_check": d.get("quality_check", {"passed": True, "issues": []}),
        }
        for d in items
    ]


def generate_anchors(dimensions: list, company_info: str, level: str = "中层管理者") -> list:
    """Step4: 生成BARS行为锚定 → 返回 list"""
    dims_json = json.dumps(dimensions, ensure_ascii=False)
    prompt = f"""为每个维度生成 BARS 行为锚定（优秀/达标/不达标三档）。

维度信息：{dims_json}
企业背景：{company_info}
目标层级：{level}

输出 JSON：
{{"anchors":[{{"dimension_id":"D1","dimension_name":"维度名","anchors":{{"excellent":[{{"id":"D1-E1","text":"优秀行为","level":"excellent"}}],"standard":[{{"id":"D1-S1","text":"达标行为","level":"standard"}}],"below":[{{"id":"D1-B1","text":"不达标行为","level":"below"}}]}}}}]}}

要求：
- 每个维度：优秀1条、达标2条、不达标2条
- 所有行为以动词开头，具体可观察
- 三档形成清晰的行为递进"""
    result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=4000, use_reasoner=True)
    payload = _extract_json(result)
    return payload.get("anchors") or []


def regenerate_item(original: str, direction: str, item_type: str) -> str:
    """重新生成某条内容"""
    prompt = f"""根据指定方向重新生成内容。

原始内容：{original}
修改方向：{direction}
类型：{item_type}

输出 JSON：
{{"result":"新内容..."}}"""
    result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=1000)
    payload = _extract_json(result)
    return payload.get("result", result)
