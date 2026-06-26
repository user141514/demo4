"""
AI Service — DeepSeek API 封装，借鉴 demo2 的 prompt 工程和 JSON 提取逻辑
"""
import json
import re
from difflib import SequenceMatcher
from openai import OpenAI
from backend.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_CHAT_MODEL,
    DEEPSEEK_REASONER_MODEL,
    LLM_TIMEOUT,
)

client = None  # Lazily initialized in _call_deepseek so tests can import without credentials.

# ── System Prompts（借鉴 demo2 leadership_prompts.py 的精华） ──

SYSTEM_PROMPT = """你是资深领导力建模顾问，服务于中国科技企业。
你的专业领域：胜任力模型构建、BARS行为锚定、领导力发展体系设计。

全局规则：
1. 本次建模只服务一个单一层级/群体，不生成多层级矩阵
2. 信息采集按行业/规模/战略/痛点/目标层级/优秀管理者画像归纳，信息不足时直接指出缺口
3. 维度必须生成4-8个推荐维度+若干备选维度
4. 每个维度包含id、name、definition、sources、priority、priority_judgment、rationale
5. 描述聚焦目标层级，长度50-120字
6. 禁用空泛词：积极、主动、高度、认真、负责、努力、认可、重视、关注、善于、较强、具备、出色、优秀、良好
7. 行为锚定必须输出优秀/达标/不达标三档
8. 每条行为以行为动词开头，可观察、可衡量
9. 信息缺失时直接指出，不虚构
10. 只输出JSON，不输出Markdown"""

CHAT_SYSTEM_PROMPT = """你是资深领导力建模顾问，正在通过自然对话采集企业信息。
你需要像一位专业顾问一样与用户自然交流，逐步收集信息。

━━━ 对话阶段与追问策略 ━━━

【阶段1：启动引导（Q-01）】
用户进入时先发送欢迎语，1-2句话说明本次建模流程和预期产出。例如：
"您好，我是您的专属领导力建模顾问。接下来我们会一起完成一次完整的领导力模型构建——从了解您的企业背景开始，到最终生成一套可落地的领导力模型。整个过程大约需要15-20分钟，您只需要如实回答问题即可。"
首次用户消息到达时自动发送此欢迎语。

【阶段2：企业背景收集（Q-02/Q-03/Q-04）】
Q-02 → "先简单了解一下您的企业背景：公司所在行业和主要业务是什么？"
Q-03 → 追问规模："公司大概多少人？您所关注的管理层级大概带多少个团队？"
Q-04 → 追问战略/痛点："公司当前的战略重点是什么？目前在管理上最主要的痛点或挑战是什么？"

追问策略：
- 当描述不清晰时：「能再说具体一点吗？比如什么行业、主要做什么业务？」
- 当用户同时给出过多信息时：确认已收集到的，再追问缺失项
- 自然穿插，不要像填表

【阶段3：建模对象层级确认（Q-05）】
"您这次想为哪个管理层级建模？
A. 高管层（VP/总监及以上，负责战略决策）
B. 中层管理者（部门经理/业务线负责人，承上启下）
C. 新经理/高潜（带团队不超过2年，或重点培养对象）
D. 自定义（请描述您的目标群体）"

追问策略：
- 当选择D或描述不清晰：「能具体说一下这个群体的汇报关系和主要职责范围吗？大概带多少人？」
- 当用户想同时建两个层级：「我们这次先聚焦一个层级，完成后可以用相同流程为第二个层级单独建模。您觉得先从哪个层级开始更迫切？」

【阶段4：优秀管理者画像收集（Q-06）】
在确认的{层级}中，追问："在{层级}中，您认为表现最好的那位管理者，有哪些让您印象深刻的具体行为？是什么让他/她与普通管理者区分开来？"
追问策略：
- 当描述空泛：「您能举一个具体的场景或事件吗？比如在什么时候、做了什么？」
- 当用户说完一个：「还有其他您认为特别优秀的管理者吗？有没有不同类型的优秀表现？」

【阶段5：标准库参照选择（Q-07/Q-08）— P0必问】
Q-07 → "在构建领导力模型时，您是否希望参考一些成熟的领导力框架作为基线？我们可以将以下框架融入您的模型：
A. 美世（Mercer）领导力模型 — 侧重战略思维与结果导向
B. DDI 成功者画像 — 侧重领导力潜质与成长性
C. 富兰克林柯维（FranklinCovey）— 侧重效能与信任建设
D. 光辉国际（Korn Ferry）全人模型 — 侧重胜任力与经验
E. 暂不参考，完全基于您企业自身特点构建"

Q-08 → 当用户选择A/B/C/D其中之一后追问："您希望这个标准库主要影响哪些方面？比如维度结构、行为描述风格、还是评级标准？"
如果用户表示“不知道、没法回答、无法判断、你来定”，直接采用“系统根据企业信息自动匹配标准库”，继续推进流程。

【最终：汇总（Q-08+）】
当以下信息全部收集完毕后，在回复末尾用【摘要】格式汇总：
企业背景 / 战略重点 / 管理痛点 / 目标层级 / 优秀管理者画像 / 标准库参照
每行格式："字段名：内容"

━━━ 全局对话规则 ━━━
- 用自然友好的中文对话，像顾问一样交流，不输出JSON
- 每次只问1-2个问题，按上述阶段顺序推进
- 根据用户回答灵活调整，信息不足时追问细节
- 用户跳过某阶段时，择机补问
- 不重复追问已经给出的信息；只追问缺口字段
- 信息充分后立即给出【摘要】汇总，用户仍可继续补充修改
- 谨慎收集信息，不急于结束对话阶段"""

DOC_ANALYSIS_SYS = """你是领导力建模顾问，从企业文档中提取建模相关信息。
严格按以下格式输出：

【战略关键词】：3-8个战略方向关键词（逗号分隔）
【高绩效行为特征】：2-4条高绩效管理者典型行为描述
【能力要求关键词】：文档中出现的管理者能力要求关键词（逗号分隔）
【建模参考重点】：1-2条最值得纳入领导力模型的核心洞察

用中文回答，每项不超过150字。文档内容不足时如实说明。"""

# ━━━ 阶段引导消息（Q-09 / Q-12 / Q-14）━━━
# 用户在 Step2/3/4 等待 AI 返回时看到的过程性说明

STEP2_GUIDANCE = "正在综合您的企业信息、管理者画像和标准库参照，为您生成专属的领导力维度框架...（预计10-15秒）维度模型从**战略拆解**、**行为一致性**和**发展价值**三个角度切入，确保每个维度贴合企业语境、具备可观察的行为指向。"

STEP3_GUIDANCE = "正在为确认的维度展开详细定义和描述，将关键词转化为可沟通的组织语言..."

STEP4_GUIDANCE = "正在为每个维度生成 BARS 五级行为描述与正负向行为对照。行为锚定确保可观察、可衡量。"


# ── JSON 提取（借鉴 demo2 leadership_llm.py） ──

class LLMError(Exception):
    pass


PRIORITY_FORMULA = "score = 战略相关性*0.35 + 证据强度*0.25 + 层级关键性*0.25 + 发展杠杆*0.15"
PRIORITY_THRESHOLDS = {"core": 4.2, "important": 3.0}
PRIORITY_COMPONENTS = {
    "strategic_relevance": {
        "label": "战略相关性",
        "weight": 0.35,
        "aliases": ["strategic_relevance", "strategy", "战略相关性"],
    },
    "evidence_strength": {
        "label": "证据强度",
        "weight": 0.25,
        "aliases": ["evidence_strength", "evidence", "证据强度"],
    },
    "role_criticality": {
        "label": "层级关键性",
        "weight": 0.25,
        "aliases": ["role_criticality", "criticality", "层级关键性", "角色关键性"],
    },
    "development_leverage": {
        "label": "发展杠杆",
        "weight": 0.15,
        "aliases": ["development_leverage", "leverage", "发展杠杆"],
    },
}
PRIORITY_FALLBACK_COMPONENTS = {
    "core": {
        "strategic_relevance": 5,
        "evidence_strength": 4,
        "role_criticality": 5,
        "development_leverage": 4,
    },
    "important": {
        "strategic_relevance": 4,
        "evidence_strength": 3,
        "role_criticality": 4,
        "development_leverage": 3,
    },
    "supplementary": {
        "strategic_relevance": 2,
        "evidence_strength": 2,
        "role_criticality": 3,
        "development_leverage": 2,
    },
}


def _clamp_component(value, default=3):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = default
    return max(1, min(5, number))


def _priority_label(score):
    if score >= PRIORITY_THRESHOLDS["core"]:
        return "core"
    if score >= PRIORITY_THRESHOLDS["important"]:
        return "important"
    return "supplementary"


def _extract_priority_components(raw):
    raw = raw or {}
    if not isinstance(raw, dict):
        return None
    source = raw.get("components") if isinstance(raw.get("components"), dict) else raw
    values = {}
    for key, spec in PRIORITY_COMPONENTS.items():
        found = None
        for alias in spec["aliases"]:
            if alias in source:
                found = source.get(alias)
                break
        if found is None:
            return None
        values[key] = _clamp_component(found)
    return values


def _priority_score(components):
    return round(sum(
        components[key] * PRIORITY_COMPONENTS[key]["weight"]
        for key in PRIORITY_COMPONENTS
    ), 2)


def normalize_priority_judgment(dim: dict) -> dict:
    """将 LLM/前端的优先级判断归一成有公式、有分项、有阈值的结构。"""
    dim = dim or {}
    raw = dim.get("priority_judgment") or dim.get("priority_reasoning") or dim.get("pj") or {}
    components = _extract_priority_components(raw)
    source = "llm"
    if not components:
        label = dim.get("priority") or dim.get("pri") or "important"
        components = dict(PRIORITY_FALLBACK_COMPONENTS.get(label, PRIORITY_FALLBACK_COMPONENTS["important"]))
        source = "fallback"

    score = _priority_score(components)
    label = _priority_label(score)
    rationale = ""
    if isinstance(raw, dict):
        rationale = raw.get("rationale") or raw.get("reason") or ""
    rationale = rationale or dim.get("rationale") or "基于现有信息按公式化评分生成。"

    return {
        "score": score,
        "label": label,
        "formula": PRIORITY_FORMULA,
        "components": components,
        "thresholds": {
            "core": "score >= 4.2",
            "important": "3.0 <= score < 4.2",
            "supplementary": "score < 3.0",
        },
        "rationale": rationale,
        "source": source,
    }


SOURCE_TYPES = {"战略文档关键词", "标准库映射", "对话归纳"}


def _lookup_kb_dimension(dim_id: str):
    """按 LN 编号回查本地知识库，确保前端能显示连接的成熟模型。"""
    if not dim_id:
        return None
    try:
        from backend.knowledge_base import LEADERSHIP_DIMENSIONS
    except Exception:
        return None
    for item in LEADERSHIP_DIMENSIONS:
        if item.get("id") == dim_id:
            return item
    return None


def normalize_dimension_source(dim: dict) -> dict:
    sources = dim.get("sources") if isinstance(dim.get("sources"), dict) else {}
    dim_id = str(dim.get("id") or dim.get("dimension_id") or "")
    kb_dim = _lookup_kb_dimension(dim_id)
    kb_sources = kb_dim.get("sources", {}) if kb_dim else {}

    source_type = dim.get("source_type") or sources.get("type")
    if not source_type:
        if kb_dim or sources.get("framework") or dim_id.startswith("LN-"):
            source_type = "标准库映射"
        elif sources.get("strategy"):
            source_type = "战略文档关键词"
        else:
            source_type = "对话归纳"
    if source_type not in SOURCE_TYPES:
        source_type = "对话归纳"

    framework_name = (
        dim.get("framework_name")
        or sources.get("framework")
        or sources.get("reference")
        or kb_sources.get("framework")
        or kb_sources.get("reference")
        or ""
    )
    framework_dimension = (
        dim.get("framework_dimension")
        or (kb_dim.get("name") if kb_dim else "")
        or (dim.get("name") if dim_id.startswith("LN-") else "")
        or ""
    )
    detail = dim.get("source_detail") or sources.get("detail") or ""
    if not detail and kb_dim:
        detail = f"{kb_dim['id']} {kb_dim['name']}"
    if not detail:
        if source_type == "战略文档关键词":
            detail = sources.get("strategy") or dim.get("rationale") or "战略文档关键词"
        elif source_type == "标准库映射":
            detail = framework_name or "标准库映射"
        else:
            detail = sources.get("interview") or "对话归纳"

    return {
        "source_type": source_type,
        "source_detail": str(detail),
        "framework_dimension": str(framework_dimension or ""),
        "framework_name": str(framework_name or ""),
        "sources": {
            "type": source_type,
            "detail": str(detail),
            "strategy": sources.get("strategy", ""),
            "framework": framework_name,
            "interview": sources.get("interview", ""),
            "knowledge_id": dim_id if dim_id.startswith("LN-") else "",
            "knowledge_name": kb_dim.get("name", "") if kb_dim else "",
        },
    }


def build_rule_based_dimensions(company_info: str, level: str = "中层管理者", min_count: int = 6, max_count: int = 8) -> dict:
    """LLM 不可用时，按知识库稳定生成 6-8 个维度，避免维度池为空。"""
    from backend.knowledge_base import search_knowledge_base

    matched = search_knowledge_base(company_info or "", level, top_n=max_count + 4)
    recommended = []
    alternatives = []
    for idx, dim in enumerate(matched):
        item = {
            "id": dim["id"],
            "name": dim["name"],
            "definition": dim["definition"],
            "source_type": "标准库映射",
            "source_detail": f"{dim['id']} {dim['name']}",
            "framework_dimension": dim["name"],
            "framework_name": dim.get("sources", {}).get("framework", ""),
            "sources": {
                "type": "标准库映射",
                "detail": f"{dim['id']} {dim['name']}",
                "framework": dim.get("sources", {}).get("framework", ""),
                "strategy": "",
                "interview": "",
            },
            "rationale": "根据已采集信息与领导力知识库匹配生成。",
        }
        if idx < max_count:
            recommended.append(item)
        else:
            alternatives.append({**item, "added": False})
    return {"recommended": recommended[:max_count], "alternatives": alternatives[:4]}


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
    if not DEEPSEEK_API_KEY:
        raise LLMError("LLM API Key 未配置，请设置 OPENAI_API_KEY 或 mykey.py。")
    model = DEEPSEEK_REASONER_MODEL if use_reasoner else DEEPSEEK_CHAT_MODEL
    llm_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=LLM_TIMEOUT)
    response = llm_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


def _chat_role_label(role: str) -> str:
    """兼容前端 role='ai' 与 OpenAI role='assistant' 两种写法。"""
    return "AI" if role in {"assistant", "ai"} else "用户"


def _collect_chat_signals(messages: list[dict], context: str = "") -> str:
    """从用户回答中抽取高置信线索，用于提示模型不要重复追问。"""
    user_text = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") not in {"assistant", "ai", "doc"})
    all_text = f"{context}\n{user_text}"
    signals: list[str] = []

    size_match = re.search(r"(?:约|大概|大约|差不多)?\s*(\d{2,6})\s*(?:个)?\s*(?:人|员工|同事)", all_text)
    if size_match:
        signals.append(f"公司规模已给出：约{size_match.group(1)}人")
    elif re.search(r"几百人|数百人|上百人|百人", all_text):
        signals.append("公司规模已给出：百人级/数百人级")

    stage_hits = []
    for kw in ["快速扩张", "快速成长", "高速增长", "增长期", "稳定经营", "稳定期", "转型", "调整期", "初创", "成熟期"]:
        if kw in all_text:
            stage_hits.append(kw)
    if stage_hits:
        signals.append("发展阶段已给出：" + "、".join(dict.fromkeys(stage_hits[:3])))

    level_hits = []
    for kw in ["中层", "基层", "高层", "经理", "负责人", "总监", "项目总监", "运营总监"]:
        if kw in all_text:
            level_hits.append(kw)
    if level_hits:
        signals.append("建模层级/对象已出现：" + "、".join(dict.fromkeys(level_hits[:4])))

    team_match = re.search(r"(?:带|管理|负责|团队)\D{0,12}(\d{1,4})\s*(?:个)?\s*(?:人|团队|小组)", all_text)
    if team_match:
        signals.append(f"管理幅度已给出：约{team_match.group(1)}人/团队")

    if re.search(r"美世|Mercer|DDI|富兰克林|柯维|Franklin|Korn\s*Ferry|光辉|暂不参考|不参考|自动匹配|系统匹配|不知道|没法回答|无法判断", all_text, re.I):
        signals.append("标准库参照已有回答或可默认系统自动匹配")

    if not signals:
        return ""
    return "\n\n【已识别信息，不得重复追问】\n" + "\n".join(f"- {s}" for s in signals)


def chat(messages: list[dict], context: str = "", force_summary: bool = False) -> str:
    """Step1: 引导式对话，采集企业背景信息"""
    user_context = f"\n\n已收集的企业信息：{context}" if context else ""
    conversation = "\n".join(
        f"{_chat_role_label(m.get('role', 'user'))}：{m.get('content', '')}"
        for m in messages[-14:]
        if m.get("role") != "doc"
    )
    anti_repeat_context = _collect_chat_signals(messages, context)
    summary_policy = ""
    if force_summary:
        summary_policy = "\n\n已达到信息采集上限：必须输出【摘要】，可以标注仍缺失的信息，但不要继续追问。"
    user_prompt = f"""正在进行领导力建模信息采集。需收集11项：公司名称、行业/业务、规模/阶段、战略重点、管理痛点、管理层级、建模层级、建模对象说明、管理幅度、优秀管理者画像、标准库参照。

对话记录：
{conversation}{user_context}{anti_repeat_context}{summary_policy}

追问约束：
- 不得重复询问已经明确回答的信息；例如已经出现“约500人”时，不能再问“公司大概多少人”，只能追问仍缺失的团队管理幅度或管理场景。
- 如果用户表示成熟框架“不知道/没法回答/无法判断”，默认采用“系统根据企业信息自动匹配标准库”，不要强制用户选择框架。
- 如果摘要已生成但用户继续补充，请吸收新增信息并重新给出更新后的【摘要】。

请根据进度自然地回复用户，引导完成信息采集。当收集到足够信息时，在末尾附上摘要：
【摘要】
公司名称：xxx
行业/业务：xxx
规模/阶段：xxx
战略重点：xxx
管理痛点：xxx
管理层级：xxx（短字段，如中层管理者/基层管理者/高层管理者）
建模层级：xxx（完整建模对象，可包含角色范围和管理人数）
建模对象说明：xxx（具体适用角色，如产品负责人、研发小组负责人等）
管理幅度：xxx（如6-20人；没有明确则写未提供）
优秀画像：xxx
标准库参照：xxx"""
    return _call_deepseek(CHAT_SYSTEM_PROMPT, user_prompt, max_tokens=1200)


def analyze_document(text: str, filename: str) -> str:
    """Step1: 文档分析"""
    user_prompt = f"分析以下文档，提取与领导力建模相关的核心信息。\n文件名：{filename}\n\n文档内容：\n{text[:8000]}"
    return _call_deepseek(DOC_ANALYSIS_SYS, user_prompt, max_tokens=1000)


def generate_dimensions(company_info: str, level: str = "中层管理者", use_kb: bool = True) -> dict:
    """Step2: 生成维度 → 返回结构化 dict"""
    # ── 知识库上下文 ──
    kb_context = ""
    if use_kb:
        try:
            from backend.knowledge_base import build_kb_context
            kb_context = build_kb_context(company_info, level)
        except Exception:
            kb_context = ""  # 知识库异常时退化到纯AI生成

    kb_instruction = f"""
【领导力知识库 @LN 参考】
以下是从标准领导力知识库中匹配的相关维度。请优先选择最匹配的4-6个作为推荐维度（直接使用其ID），再从知识库中选3-5个次相关的作为备选维度。
{ kb_context if kb_context else '（知识库暂无匹配条目，请根据企业信息自主生成。）' }

要求：
1. 推荐维度优先从上述知识库中选择，使用知识库条目的ID（如 LN-001）和名称
2. 如果知识库没有完全匹配的某个企业特殊需求，可生成1-2个自定义维度（ID使用D前缀）
3. 每个维度的 sources 字段标注来源：framework 填知识库参考框架名，strategy 填战略文档关键词，interview 填对话归纳
4. 备选维度池从知识库次相关条目中选3-5个
"""
    prompt = f"""根据以下企业信息，为{level}生成推荐维度和备选维度。
企业背景：{company_info}

{kb_instruction}

输出 JSON：
{{"recommended":[{{"id":"LN-001","name":"2-5字","definition":"2-3句定义","sources":{{"strategy":"战略来源","framework":"框架来源","interview":"访谈来源"}},"priority":"core|important|supplementary","priority_judgment":{{"strategic_relevance":1-5,"evidence_strength":1-5,"role_criticality":1-5,"development_leverage":1-5,"rationale":"1句评分理由"}},"rationale":"1句理由"}}],"alternatives":[]}}

要求：
- 推荐4-6个核心/重要维度，备选3-5个补充维度
- 名称精炼有力，定义包含可观察行为指向
- 贴合企业实际情况
- 每个维度必须由你自主判断4项1-5分：战略相关性、证据强度、层级关键性、发展杠杆；后端将按公式 score = 战略相关性*0.35 + 证据强度*0.25 + 层级关键性*0.25 + 发展杠杆*0.15 复算 priority
- priority 标签口径：score>=4.2 为 core；3.0<=score<4.2 为 important；score<3.0 为 supplementary
- 严格禁止使用以下词汇：主动、积极、高度、认真、负责、努力、认可、重视、关注、善于、较强、具备、出色、优秀、良好
- 违反禁令的维度将被拒绝"""
    result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=2000)
    payload = _extract_json(result)

    # 兼容多种输出格式
    recommended = payload.get("recommended") or payload.get("dimensions") or []
    alternatives = payload.get("alternatives") or []

    def normalize_dim(d, idx):
        """规范化维度字段，确保必需字段存在；不向前端暴露权重/优先级。"""
        dim_id = d.get("id", f"D{idx+1}")
        normalized = {
            "id": dim_id,
            "name": d.get("name", ""),
            "definition": d.get("definition", ""),
            "rationale": d.get("rationale", ""),
        }
        normalized.update(normalize_dimension_source({**d, **normalized}))
        return normalized

    return {
        "recommended": [normalize_dim(d, i) for i, d in enumerate(recommended)],
        "alternatives": [normalize_dim(d, i) for i, d in enumerate(alternatives)],
    }


def generate_descriptions(dimensions: list, company_info: str, level: str = "中层管理者", enterprise_terms: str = "") -> list:
    """Step3: 生成维度描述 → 返回 list"""
    dims_json = json.dumps(dimensions, ensure_ascii=False)
    prompt = f"""为{level}的每个维度生成定位描述。

维度列表：{dims_json}
企业背景：{company_info}
企业专有词汇：{enterprise_terms or '无'}

输出 JSON：
{{"descriptions":[{{"dimension_id":"D1","dimension_name":"维度名","description":"50-120字","quality_check":{{"passed":true,"issues":[]}}}}]}}

要求：
- 每个描述50-120字，聚焦{level}的实际工作场景
- 如果提供企业专有词汇，必须自然融入维度定位描述
- 使用可观察的行为动词（制定、推动、识别、建立、拆解、复盘等）
- 严格禁止空泛词：主动、积极、高度、认真、负责、努力、认可、重视、关注、善于、较强、具备、出色、优秀、良好
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


BARS_LEVELS = [
    ("5分（卓越）", "系统设计与提前预防"),
    ("4分（超出预期）", "预判风险并跨方协调"),
    ("3分（符合预期）", "按标准完成"),
    ("2分（需改进）", "被动补救且影响进度"),
    ("1分（不符合）", "缺失关键动作并造成损失"),
]


def _scenario_for_dimension(dim_name: str) -> tuple[str, str]:
    """给兜底五级描述补充差异化业务场景，避免每档只换程度词。"""
    name = dim_name or "该维度"
    table = [
        (("战略", "规划", "目标"), "年度目标拆解和季度经营复盘", "业务、产品、交付等相关团队"),
        (("团队", "赋能", "人才", "梯队"), "成员成长任务和关键岗位接续", "团队成员和协作导师"),
        (("质量", "流程", "过程"), "交付质量检查和流程改进", "交付、运营和质量接口人"),
        (("协作", "沟通", "影响", "冲突"), "跨部门项目协同和分歧处理", "上下游负责人和关键干系人"),
        (("数据", "决策", "商业"), "指标分析和经营决策", "数据、业务和一线执行团队"),
        (("变革", "创新", "转型"), "新机制落地和试点推广", "试点团队和受影响岗位"),
        (("风险", "合规", "安全"), "业务风险预警和应急处理", "风险责任人和执行团队"),
    ]
    for keywords, scene, actors in table:
        if any(kw in name for kw in keywords):
            return scene, actors
    return f"{name}相关管理场景", "团队成员和关键协作方"


def build_distinct_bars5(dim_name: str, evidence_event: str = "") -> list[dict]:
    scene, actors = _scenario_for_dimension(dim_name)
    return [
        {
            "level": BARS_LEVELS[0][0],
            "text": f"设计{scene}的目标拆解表、风险清单和复盘节奏，协调{actors}提前处理关键阻塞，并沉淀可复用机制。",
        },
        {
            "level": BARS_LEVELS[1][0],
            "text": f"预判{scene}中的主要依赖和风险，拉齐{actors}的交付标准，在节点偏差出现前完成资源调整。",
        },
        {
            "level": BARS_LEVELS[2][0],
            "text": f"按照既定计划推进{scene}，同步进度、处理常规问题，并在节点结束后完成复盘记录。",
        },
        {
            "level": BARS_LEVELS[3][0],
            "text": f"等待问题暴露后才处理{scene}中的协作偏差，沟通对象和结果标准不清，造成返工或进度波动。",
        },
        {
            "level": BARS_LEVELS[4][0],
            "text": f"放任{scene}缺少目标、责任人和检查节点，关键信息长期不透明，导致团队反复救火或交付失控。",
        },
    ]


def _bars5_need_distinction_fix(dim_name: str, bars5: list[dict]) -> bool:
    if len(bars5) < 5:
        return True
    texts = [str(row.get("text", "")).strip() if isinstance(row, dict) else str(row).strip() for row in bars5[:5]]
    if any(len(text) < 18 for text in texts):
        return True
    normalized = [_norm_anchor_for_similarity(text, dim_name) for text in texts]
    if len(set(normalized)) < 4:
        return True
    for i, left in enumerate(normalized):
        for right in normalized[i + 1:]:
            if left and right and SequenceMatcher(None, left, right).ratio() >= 0.76:
                return True
    return False


def ensure_distinct_bars5(dim_name: str, bars5: list[dict], evidence_event: str = "") -> list[dict]:
    if _bars5_need_distinction_fix(dim_name, bars5):
        return build_distinct_bars5(dim_name, evidence_event)
    return bars5[:5]


def generate_anchors(dimensions: list, company_info: str, level: str = "中层管理者", critical_incidents: str = "") -> list:
    """Step4: 基于关键事件生成五级BARS与正负向行为对照。"""
    dims_json = json.dumps(dimensions, ensure_ascii=False)
    prompt = f"""请基于真实关键事件，为每个维度生成两种行为描述呈现方式。

维度信息：{dims_json}
企业背景：{company_info}
目标层级：{level}
关键事件与行为素材：{critical_incidents or '用户未提供充分关键事件，请基于已采集信息生成，并在 evidence_event 中注明信息不足'}

输出 JSON：
{{"anchors":[{{"dimension_id":"D1","dimension_name":"维度名","evidence_event":"引用的关键事件或信息来源","bars5":[{{"level":"5分（卓越）","text":"行为描述"}},{{"level":"4分（超出预期）","text":"行为描述"}},{{"level":"3分（符合预期）","text":"行为描述"}},{{"level":"2分（需改进）","text":"行为描述"}},{{"level":"1分（不符合）","text":"行为描述"}}],"positive_behaviors":["正向行为1","正向行为2"],"negative_behaviors":["负向行为1","负向行为2"]}}]}}

要求：
- BARS 五级行为描述必须形成清晰递进：5/4/3/2/1 五档都要有
- 五档必须区分触发条件、行动范围、协同对象、结果标准：5分=系统设计与提前预防；4分=预判风险并跨方协调；3分=按标准完成；2分=被动补救且影响进度；1分=缺失关键动作并造成明显损失
- 同一维度内五档不得只是替换“优秀/达标/不达标”等程度词，句式和行为结果也要明显不同
- 正负向行为对照必须直接服务于360度评估反馈，不是泛泛评价
- 填写示例只代表某一个单一领导力维度的行为写法和颗粒度，不能当成所有维度的通用内容
- 对每个维度分别读取 dimension_id、dimension_name、definition/description，再生成只属于该维度的正向/负向行为
- 如果关键事件素材只覆盖某一个维度，只能把它作为该维度的 evidence_event；其他维度应结合企业背景和维度定义另行生成
- 每个维度必须引用不同的业务场景、行为对象和结果标准，避免模板化换词
- 所有行为以强动词开头，具体、可观察、可追踪
- 禁止空泛词：主动、积极、高度、认真、负责、努力、认可、重视、关注、善于、较强、具备、出色、优秀、良好"""
    result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=5000, use_reasoner=True)
    payload = _extract_json(result)
    return [normalize_anchor_item(item) for item in (payload.get("anchors") or [])]


def build_rule_based_anchors(dimensions: list, critical_incidents: str = "") -> list[dict]:
    """LLM 不可用或返回空结果时，按维度和关键事件生成稳定的五级行为锚定。

    这个兜底放在后端，避免前端误报“生成失败”。输出结构与 LLM 结果一致，后续仍可人工编辑。
    """
    result = []
    evidence = "基于已采集关键事件素材归纳"
    if critical_incidents:
        compact = re.sub(r"\s+", " ", str(critical_incidents)).strip()
        if compact:
            evidence = compact[:120] + ("…" if len(compact) > 120 else "")
    for idx, dim in enumerate(dimensions or [], 1):
        dim_id = dim.get("dimension_id") or dim.get("id") or f"D{idx}"
        dim_name = dim.get("dimension_name") or dim.get("name") or dim.get("nm") or f"维度{idx}"
        bars5 = build_distinct_bars5(dim_name, evidence)
        result.append({
            "dimension_id": dim_id,
            "dimension_name": dim_name,
            "evidence_event": evidence,
            "bars5": bars5,
            "positive_behaviors": [bars5[0]["text"], bars5[1]["text"], bars5[2]["text"]],
            "negative_behaviors": [bars5[3]["text"], bars5[4]["text"]],
            "anchors": {
                "excellent": [{"id": f"{dim_id}-E1", "text": bars5[0]["text"], "level": "excellent"}],
                "standard": [{"id": f"{dim_id}-S1", "text": bars5[2]["text"], "level": "standard"}],
                "below": [{"id": f"{dim_id}-B1", "text": bars5[4]["text"], "level": "below"}],
            },
        })
    return result


def normalize_anchor_item(item: dict) -> dict:
    """兼容旧三档结构，同时补齐五级BARS和正负向行为字段。"""
    dim_id = item.get("dimension_id") or item.get("id") or ""
    dim_name = item.get("dimension_name") or item.get("name") or item.get("nm") or ""
    bars5 = item.get("bars5") or item.get("bars") or []
    if not bars5:
        anc = item.get("anchors") or {}
        excellent = _plain_anchor_texts(anc.get("excellent") or item.get("excellent") or item.get("ex") or [])
        standard = _plain_anchor_texts(anc.get("standard") or item.get("standard") or item.get("st") or [])
        below = _plain_anchor_texts(anc.get("below") or item.get("below") or item.get("bl") or [])
        fallback = build_distinct_bars5(dim_name, item.get("evidence_event") or item.get("event") or "")
        bars5 = [
            {"level": "5分（卓越）", "text": excellent[0] if excellent else fallback[0]["text"]},
            {"level": "4分（超出预期）", "text": standard[0] if standard else fallback[1]["text"]},
            {"level": "3分（符合预期）", "text": standard[1] if len(standard) > 1 else fallback[2]["text"]},
            {"level": "2分（需改进）", "text": below[0] if below else fallback[3]["text"]},
            {"level": "1分（不符合）", "text": below[1] if len(below) > 1 else fallback[4]["text"]},
        ]
    bars5 = [
        {"level": str(row.get("level", f"{idx}分")), "text": str(row.get("text", ""))}
        if isinstance(row, dict) else {"level": f"{idx}分", "text": str(row)}
        for idx, row in zip([5, 4, 3, 2, 1], bars5[:5])
    ]
    if len(bars5) < 5:
        fallback = build_distinct_bars5(dim_name, item.get("evidence_event") or item.get("event") or "")
        bars5.extend(fallback[len(bars5):5])
    bars5 = ensure_distinct_bars5(dim_name, bars5, item.get("evidence_event") or item.get("event") or "")

    positives = item.get("positive_behaviors") or item.get("dos") or []
    negatives = item.get("negative_behaviors") or item.get("donts") or []
    if not positives:
        positives = [bars5[0]["text"], bars5[2]["text"]]
    if not negatives:
        negatives = [bars5[3]["text"], bars5[4]["text"]]
    return {
        "dimension_id": dim_id,
        "dimension_name": dim_name,
        "evidence_event": item.get("evidence_event") or item.get("event") or "基于已采集信息归纳",
        "bars5": bars5,
        "positive_behaviors": _plain_anchor_texts(positives)[:3],
        "negative_behaviors": _plain_anchor_texts(negatives)[:3],
        "anchors": {
            "excellent": [{"id": f"{dim_id}-E1", "text": bars5[0]["text"], "level": "excellent"}],
            "standard": [{"id": f"{dim_id}-S1", "text": bars5[2]["text"], "level": "standard"}],
            "below": [{"id": f"{dim_id}-B1", "text": bars5[4]["text"], "level": "below"}],
        },
    }


def _plain_anchor_texts(values) -> list[str]:
    result = []
    for value in values or []:
        if isinstance(value, dict):
            text = value.get("text") or value.get("behavior") or ""
        else:
            text = str(value)
        text = str(text).strip()
        if text:
            result.append(text)
    return result


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def check_critical_incidents(
    critical_incidents: str,
    dimensions: list | None = None,
    company_info: str = "",
    level: str = "中层管理者",
) -> dict:
    """Step4 关键事件完整度校验。

    返回稳定 JSON，前端可直接展示。即使没有 LLM Key，也能作为 AI 校验按钮的兜底质量闸门。
    """
    text = (critical_incidents or "").strip()
    checks = [
        {
            "key": "background",
            "label": "背景/场景",
            "passed": bool(text) and _has_any(text, ["背景", "场景", "项目", "业务", "客户", "团队", "上线", "续约", "交付"]),
            "question": "补充事件发生的业务背景：是什么项目、任务或管理场景？",
        },
        {
            "key": "task",
            "label": "任务/目标",
            "passed": bool(text) and _has_any(text, ["目标", "任务", "要求", "标准", "指标", "节点", "交付", "续约", "上线"]),
            "question": "补充当时要达成的目标、交付标准或时间节点。",
        },
        {
            "key": "action",
            "label": "具体行动",
            "passed": bool(text) and _has_any(text, ["拆解", "组织", "协调", "推动", "复盘", "澄清", "设定", "追踪", "处理", "对齐", "识别"]),
            "question": "补充管理者实际做了什么动作，而不是只写评价。",
        },
        {
            "key": "result",
            "label": "结果/影响",
            "passed": bool(text) and _has_any(text, ["结果", "最终", "导致", "完成", "延期", "返工", "提升", "降低", "达成", "失败", "投诉"]),
            "question": "补充动作带来的结果：完成、延期、返工、投诉、效率变化或复盘结论。",
        },
        {
            "key": "contrast",
            "label": "正反样本",
            "passed": bool(text) and _has_any(text, ["正向", "反向", "表现突出", "表现不佳", "优秀", "失败", "延期", "返工"]),
            "question": "最好同时提供一个正向事件和一个反向事件，便于生成区分度更高的五级行为描述。",
        },
    ]
    passed_count = sum(1 for item in checks if item["passed"])
    score = int(round(passed_count / len(checks) * 100)) if checks else 0
    missing = [item["label"] for item in checks if not item["passed"]]
    questions = [item["question"] for item in checks if not item["passed"]]
    dimension_names = [str(d.get("name") or d.get("nm") or "") for d in (dimensions or [])]
    return {
        "score": score,
        "passed": passed_count,
        "total": len(checks),
        "can_generate": score >= 60 and bool(text),
        "missing": missing,
        "checks": checks,
        "suggestions": questions[:4],
        "summary": (
            "关键事件信息基本完整，可以生成行为锚定。"
            if score >= 80 else
            "关键事件可以生成初稿，但建议补充缺口以提高五级描述区分度。"
            if score >= 60 else
            "关键事件信息不足，建议先补充背景、任务、行动和结果。"
        ),
        "dimension_hint": "、".join([n for n in dimension_names if n][:6]),
        "level": level,
    }


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


# ═══════════════════════════════════════════════════════════
#  质量审计 + 残差式定向修复
# ═══════════════════════════════════════════════════════════

BANNED_WORDS = [
    "主动", "积极", "高度", "认真", "负责",
    "努力", "认可", "重视", "关注", "善于",
    "较强", "具备", "出色", "优秀", "良好",
]

# 复合词白名单：包含禁用词但不是空泛用法
BANNED_WHITELIST = [
    "负责人", "负责范围", "负责任", "负责任的决策",
    "主动性", "主动沟通", "主动解决问题", "主动识别机会", "主动承担",
    "积极性", "积极倾听", "积极参与",
    "关注点", "关注细节", "关注业务趋势",
    "善于沟通", "善于协调资源", "善于授权",
    "抗压能力较强", "影响力较强",
    "具备行业知识", "具备跨部门经验",
    "优秀实践", "优秀案例", "优秀水平", "优秀行为",
    "良好的工作关系",
    "重视人才培养", "重视客户价值", "高度重视",
    "高度复杂", "高度不确定", "高度协作",
]  # 复合词豁免：包含禁用词但在特定语境下不是空泛用法


def audit_text(text: str, context: str = "") -> list[str]:
    """审计单段文本，返回问题列表（空列表=通过）"""
    issues = []
    # 1. 禁用词检查
    for word in BANNED_WORDS:
        if word in text:
            # 检查是否在白名单复合词中
            whitelisted = any(wl in text and word in wl for wl in BANNED_WHITELIST)
            if not whitelisted:
                # 需要确认不是复合词的一部分
                # 若 word="负责"且"负责人"在text中，则不算违规
# 白名单豁免已在上面统一处理
                issues.append(f"包含禁用词「{word}」，请替换为具体的行为描述")
    # 2. 行为动词检查（仅对行为锚定文本）
    if context == "anchor":
        first_char = text.strip()[0] if text.strip() else ""
        weak_starts = {"在", "为", "与", "和", "对", "从", "以", "通", "按", "凭", "通", "将"}
        if first_char in weak_starts:
            issues.append(f"行为应以强动词开头，当前以「{first_char}」开头")
    # 3. 长度检查
    if context == "description":
        ln = len(text)
        if ln < 50:
            issues.append(f"描述过短({ln}字)，需≥50字")
        elif ln > 120:
            issues.append(f"描述过长({ln}字)，需≤120字")
    return issues


def find_similar_anchor_texts(anchors: list[dict], threshold: float = 0.82) -> list[dict]:
    """识别跨维度模板化行为锚定。

    去除维度名、空白和常见标点后比较同一水平分级的行为文本。返回值用于审计报告。
    """
    records = []
    for item in anchors or []:
        name = item.get("dimension_name") or item.get("nm") or item.get("name") or ""
        dim_id = item.get("dimension_id") or item.get("id") or ""
        anc = item.get("anchors") or {
            "excellent": item.get("excellent") or item.get("ex") or [],
            "standard": item.get("standard") or item.get("st") or [],
            "below": item.get("below") or item.get("bl") or [],
        }
        for level in ["excellent", "standard", "below"]:
            for idx, behavior in enumerate(anc.get(level) or []):
                text = behavior.get("text") if isinstance(behavior, dict) else str(behavior)
                norm = _norm_anchor_for_similarity(text, name)
                if norm:
                    records.append({
                        "dimension_id": dim_id,
                        "dimension_name": name,
                        "level": level,
                        "index": idx,
                        "text": text,
                        "normalized": norm,
                    })

    issues = []
    for i, left in enumerate(records):
        for right in records[i + 1:]:
            if left["dimension_id"] == right["dimension_id"] or left["level"] != right["level"]:
                continue
            similarity = SequenceMatcher(None, left["normalized"], right["normalized"]).ratio()
            if similarity >= threshold:
                issues.append({
                    "level": left["level"],
                    "dimension_ids": [left["dimension_id"], right["dimension_id"]],
                    "dimension_names": [left["dimension_name"], right["dimension_name"]],
                    "texts": [left["text"], right["text"]],
                    "similarity": round(similarity, 3),
                })
    return issues


def _norm_anchor_for_similarity(text: str, dimension_name: str = "") -> str:
    text = str(text or "")
    if dimension_name:
        text = text.replace(dimension_name, "")
    text = re.sub(r"[，。；：、,.!！?？\s]", "", text)
    text = re.sub(r"[“”\"'（）()【】\[\]]", "", text)
    return text


def retry_item_with_feedback(
    item_type: str,
    original: str,
    issues: list[str],
    dimension_name: str = "",
    max_retries: int = 2,
) -> str:
    """残差式修复：仅针对具体问题重新生成，保留原始内容框架"""
    if not issues:
        return original

    feedback = "\n".join(f"- {issue}" for issue in issues)
    prompt = f"""修复以下{ item_type }中的质量问题，保留原始内容的优点和框架，仅修改有问题的部分。

维度：{dimension_name}
原始内容：{original}

需要修复的问题：
{feedback}

修复规则：
1. 禁用词替换：用具体可观察的动词/描述替代空泛词
   - "主动"→"牵头/发起/率先"
   - "积极"→删除或用"推动/促成"
   - "负责"→"承担/主导/管理"（注意："负责人"作为职位名可使用）
   - "优秀/良好"→具体描述好在哪
   - "高度重视"→"优先保障/投入额外资源"
2. 行为以强动词开头（制定/推动/识别/建立/拆解/复盘/组织/协调/设定/追踪）
3. 保持长度在合理范围

只输出修复后的完整内容，不要输出解释或JSON包装。"""
    for attempt in range(max_retries):
        result = _call_deepseek(SYSTEM_PROMPT, prompt, max_tokens=800)
        # 清理可能的JSON包装
        result = result.strip().strip('"').strip("'")
        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "result" in parsed:
                result = parsed["result"]
        except (json.JSONDecodeError, TypeError):
            pass
        # 验证修复效果
        remaining = audit_text(result, "description" if item_type == "定位描述" else "anchor")
        if not remaining:
            return result
        if attempt < max_retries - 1:
            # 还有重试机会，追加反馈
            feedback += "\n" + "\n".join(f"- [仍存在] {r}" for r in remaining)
    # 所有重试都失败，返回原始内容（标记问题）
    return original


def generate_with_audit(
    generate_fn,
    audit_context: str,
    *args,
    max_total_retries: int = 2,
    **kwargs,
):
    """
    生成+审计+残差修复的通用包装器。

    generate_fn: 生成函数
    audit_context: "dimension" | "description" | "anchor"
    返回: (result, audit_report)
    """
    result = generate_fn(*args, **kwargs)
    report = {"total": 0, "passed": 0, "fixed": 0, "failed": 0, "details": []}

    items = []
    if isinstance(result, dict) and "recommended" in result:
        # dimensions result
        all_items = result.get("recommended", []) + result.get("alternatives", [])
        items = all_items
        for item in all_items:
            report["total"] += 1
            text = item.get("definition", "")
            issues = audit_text(text, "dimension")
            name = item.get("name", "")
            detail = {"name": name, "issues": issues, "fixed": False}
            if issues:
                new_def = retry_item_with_feedback(
                    "维度定义", text, issues, name, max_retries=max_total_retries
                )
                if new_def != text and not audit_text(new_def, "dimension"):
                    item["definition"] = new_def
                    detail["fixed"] = True
                    report["fixed"] += 1
                else:
                    report["failed"] += 1
            else:
                report["passed"] += 1
            report["details"].append(detail)

    elif isinstance(result, list):
        # descriptions or anchors list
        items = result
        for item in items:
            report["total"] += 1
            if audit_context == "description":
                text = item.get("description", "")
                name = item.get("dimension_name", "")
            else:
                # anchor - audit all behavior texts
                name = item.get("dimension_name", "")
                anc = item.get("anchors", {})
                all_texts = []
                for level in ["excellent", "standard", "below"]:
                    for b in anc.get(level, []):
                        all_texts.append(b.get("text", "") if isinstance(b, dict) else str(b))
                text = " ".join(all_texts)

            issues = audit_text(text, audit_context)
            detail = {"name": name, "issues": issues, "fixed": False}

            if issues and audit_context == "description":
                new_desc = retry_item_with_feedback(
                    "定位描述", text, issues, name, max_retries=max_total_retries
                )
                if new_desc != text and not audit_text(new_desc, "description"):
                    item["description"] = new_desc
                    item["quality_check"] = {"passed": True, "issues": []}
                    detail["fixed"] = True
                    report["fixed"] += 1
                else:
                    item["quality_check"] = {"passed": False, "issues": issues}
                    report["failed"] += 1
            elif issues and audit_context == "anchor":
                # 对每条行为单独修复
                anc = item.get("anchors", {})
                fixed_any = False
                for level in ["excellent", "standard", "below"]:
                    for b in anc.get(level, []):
                        if isinstance(b, dict):
                            bt = b.get("text", "")
                            bt_issues = audit_text(bt, "anchor")
                            if bt_issues:
                                new_bt = retry_item_with_feedback(
                                    "行为描述", bt, bt_issues, name, max_retries=max_total_retries
                                )
                                if new_bt != bt and not audit_text(new_bt, "anchor"):
                                    b["text"] = new_bt
                                    fixed_any = True
                if fixed_any:
                    detail["fixed"] = True
                    report["fixed"] += 1
                else:
                    report["failed"] += 1
            else:
                report["passed"] += 1
            report["details"].append(detail)

        if audit_context == "anchor":
            similarity_issues = find_similar_anchor_texts(result)
            if similarity_issues:
                report["failed"] += len(similarity_issues)
                report["details"].append({
                    "name": "跨维度行为相似度",
                    "issues": [
                        f"{'/'.join(issue['dimension_names'])} 的 {issue['level']} 行为相似度 {issue['similarity']}"
                        for issue in similarity_issues
                    ],
                    "fixed": False,
                })

    return result, report
