import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import re
from urllib.parse import quote

# ── 页面设置 ──────────────────────────────────
st.set_page_config(page_title="献血新媒体创意助手", page_icon="🩸", layout="centered")

# ── Session State 初始化 ───────────────────────
defaults = {
    "topics": [], "ideas": [], "custom_ideas": [],
    "auto_raw": "", "custom_result": "", "regen_idx": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── API Key ────────────────────────────────────
api_key = ""
try:
    api_key = st.secrets["CLAUDE_API_KEY"]
except Exception:
    pass
if not api_key:
    api_key = st.text_input("请输入 API Key", type="password", placeholder="sk-ant-oat01-...")


# ══════════════════════════════════════════════
# 热点抓取（微博 / 百度 / 抖音）
# ══════════════════════════════════════════════
def get_weibo_hot():
    topics = []
    try:
        r = requests.get(
            "https://weibo.com/ajax/statuses/hot_band",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                     "Referer": "https://s.weibo.com/"},
            timeout=15,
        )
        for item in r.json().get("data", {}).get("band_list", [])[:25]:
            w = item.get("word", "").strip()
            if w:
                topics.append({"topic": w, "source": "微博热搜"})
    except Exception:
        pass
    return topics


def get_baidu_hot():
    topics = []
    try:
        r = requests.get(
            "https://top.baidu.com/board?tab=realtime",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in [{"class_": "c-single-text-ellipsis"}, {"class_": "title-content-title"}]:
            items = soup.find_all("div", **sel)
            if items:
                for item in items[:25]:
                    t = item.get_text(strip=True)
                    if t and len(t) > 1:
                        topics.append({"topic": t, "source": "百度热搜"})
                break
    except Exception:
        pass
    return topics


def get_douyin_hot():
    topics = []
    try:
        r = requests.get(
            "https://api.vvhan.com/api/hotlist?type=douyin",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        for item in r.json().get("data", [])[:20]:
            t = (item.get("title") or item.get("word") or "").strip()
            if t:
                topics.append({"topic": t, "source": "抖音热搜"})
    except Exception:
        pass
    return topics


def collect_topics():
    seen, result = set(), []
    for item in get_weibo_hot() + get_baidu_hot() + get_douyin_hot():
        t = item["topic"]
        if t and t not in seen:
            seen.add(t)
            result.append(item)
    return result


def filter_health_topics(topics, key):
    """用 AI 筛选出大健康相关热点"""
    if not topics:
        return []
    topic_list = "\n".join(f"{i+1}. {t['topic']}" for i, t in enumerate(topics))
    prompt = f"""热搜话题列表：
{topic_list}

请从中选出与"大健康"相关的话题编号。
大健康包括：医疗、疾病、药品、公共卫生、营养饮食、运动健身、心理健康、生育母婴、老龄化、血液献血、医保政策、食品安全、中医养生等。
只输出符合条件的编号，用英文逗号分隔，例如：1,4,7
没有符合的则输出：无"""
    result = call_ai(prompt, key, max_tokens=100)
    if not result or result.strip() == "无":
        return []
    nums = re.findall(r"\d+", result)
    indices = [int(n) - 1 for n in nums if 0 < int(n) <= len(topics)]
    return [topics[i] for i in sorted(set(indices))]


# ══════════════════════════════════════════════
# 热点列表展示（可折叠）
# ══════════════════════════════════════════════
SOURCE_BADGE = {
    "微博热搜": ("#ff4b4b", "🔴"),
    "百度热搜": ("#1a73e8", "🔵"),
    "抖音热搜": ("#333333", "⚫"),
}

def get_topic_url(topic, source):
    q = quote(topic)
    if source == "微博热搜":
        return f"https://s.weibo.com/weibo?q={q}"
    elif source == "抖音热搜":
        return f"https://www.douyin.com/search/{q}"
    return f"https://www.baidu.com/s?wd={q}"


def show_topics_box(topics):
    label = f"📊 大健康相关热点（共 {len(topics)} 条，点击展开 / 收起）"
    with st.expander(label, expanded=False):
        cols = st.columns(2)
        for i, item in enumerate(topics):
            color, icon = SOURCE_BADGE.get(item["source"], ("#888", "⚪"))
            url = get_topic_url(item["topic"], item["source"])
            cols[i % 2].markdown(
                f"{i+1}. [{item['topic']}]({url}) "
                f"<span style='font-size:11px;color:{color}'>{icon} {item['source']}</span>",
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════
# AI 调用（流式，可选 placeholder）
# ══════════════════════════════════════════════
def call_ai(prompt, key, placeholder=None, max_tokens=2000):
    resp = requests.post(
        "https://code.newcli.com/claude/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": "gpt-5", "max_tokens": max_tokens, "stream": True,
              "messages": [{"role": "user", "content": prompt}]},
        stream=True, timeout=120,
    )
    if resp.status_code != 200:
        st.error(f"AI 调用失败（{resp.status_code}）")
        return ""
    full_text = ""
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8") if isinstance(line, bytes) else line
        if line.startswith("data: "):
            data = line[6:]
            if data.strip() == "[DONE]":
                break
            try:
                c = json.loads(data).get("choices", [{}])[0].get("delta", {}).get("content", "")
                if c:
                    full_text += c
                    if placeholder:
                        placeholder.markdown(full_text + "▌")
            except Exception:
                continue
    if placeholder:
        placeholder.empty()
    return full_text


# ══════════════════════════════════════════════
# 创意解析 & 展示
# ══════════════════════════════════════════════
def parse_ideas(text):
    ideas = []
    parts = re.split(r"===IDEA_\d+===", text)
    for part in parts:
        part = part.replace("===IDEA_END===", "").strip()
        if not part:
            continue
        idea = {}
        for line in part.split("\n"):
            line = line.strip()
            if line.startswith("HOT_TOPIC:"):
                idea["hot_topic"] = line[10:].strip()
            elif line.startswith("STARS:"):
                m = re.search(r"\d", line[6:])
                idea["stars"] = int(m.group()) if m else 3
            elif line.startswith("RATIONALE:"):
                idea["rationale"] = line[10:].strip()
            elif line.startswith("CONTENT:"):
                idea["content"] = line[8:].strip()
            elif line.startswith("TITLE:"):
                idea["title"] = line[6:].strip()
        if idea.get("content"):
            ideas.append(idea)
    return ideas


def stars_str(n):
    n = max(1, min(5, n))
    return "⭐" * n + "☆" * (5 - n)


def show_idea_card(idea, idx, regen_key_prefix="auto"):
    with st.container(border=True):
        col_title, col_btn = st.columns([5, 1])
        with col_title:
            hot_topic = idea.get("hot_topic", "")
            source = next(
                (t["source"] for t in st.session_state.get("topics", []) if t["topic"] == hot_topic),
                "百度热搜",
            )
            t_url = get_topic_url(hot_topic, source)
            st.markdown(
                f"**[{hot_topic}]({t_url})** &emsp;"
                f"{stars_str(idea.get('stars', 3))} "
                f"<span style='color:#888;font-size:12px'>（关联度 {idea.get('stars',3)}/5）</span>",
                unsafe_allow_html=True,
            )
        with col_btn:
            if st.button("🔄 重做", key=f"{regen_key_prefix}_regen_{idx}",
                         use_container_width=True):
                st.session_state.regen_idx = (regen_key_prefix, idx)
                st.rerun()

        st.caption(f"📌 关联理由：{idea.get('rationale', '')}")
        st.markdown(f"**创意方向：** {idea.get('content', '')}")
        st.info(f"💡 推荐主题：**{idea.get('title', '')}**")


# ══════════════════════════════════════════════
# Prompts
# ══════════════════════════════════════════════
IDEA_FORMAT = """\
===IDEA_1===
HOT_TOPIC:[热点名称]
STARS:[1-5]
RATIONALE:[关联理由，诚实评分，50字内]
CONTENT:[创意方向，具体说明如何将热点与无偿献血结合，60-80字]
TITLE:[推荐主题，官方有温度，不夸张不标题党，15字以内]
===IDEA_END===
===IDEA_2===
HOT_TOPIC:[热点名称]
STARS:[1-5]
RATIONALE:[...]
CONTENT:[...]
TITLE:[...]
===IDEA_END===
===IDEA_3===
HOT_TOPIC:[热点名称]
STARS:[1-5]
RATIONALE:[...]
CONTENT:[...]
TITLE:[...]
===IDEA_END==="""

STAR_GUIDE = """\
评分标准（必须诚实，不得虚高，保持客观公平）：
5星：热点与献血高度相关，能非常自然地结合
4星：有一定关联，可以合理切入
3星：关联一般，需要一定发挥
2星：关联较弱，有些牵强
1星：基本无关，强行关联也很突兀"""

TITLE_GUIDE = "标题要求：官方、有温度、不标题党、不用惊叹号/问号煽情、不用夸张词汇，15字以内。"


def prompt_auto(topics):
    today = datetime.now().strftime("%Y年%m月%d日")
    topic_list = "\n".join(
        f"{i+1}. {item['topic']}（{item['source']}）"
        for i, item in enumerate(topics[:30])
    )
    return f"""今天是{today}，以下是今日各平台热搜：
{topic_list}

你是一名无偿献血公益事业的新媒体策划师，请从以上热点中选出3个，分别生成创意方向。

{STAR_GUIDE}
{TITLE_GUIDE}

严格按以下格式输出，不得修改格式标记：
{IDEA_FORMAT}"""


def prompt_regen_one(hot_topic, topics):
    topic_list = "\n".join(
        f"{i+1}. {item['topic']}（{item['source']}）"
        for i, item in enumerate(topics[:30])
    )
    return f"""当前热点列表：
{topic_list}

请针对热点「{hot_topic}」重新生成一个与之前完全不同的新创意方向。

{STAR_GUIDE}
{TITLE_GUIDE}

按格式输出：
===IDEA_1===
HOT_TOPIC:{hot_topic}
STARS:[1-5]
RATIONALE:[关联理由]
CONTENT:[创意方向，60-80字]
TITLE:[推荐主题]
===IDEA_END==="""


def prompt_custom(topic):
    return f"""热点话题：「{topic}」

你是无偿献血公益新媒体策划师，针对这个热点，从3个不同角度分别生成创意方向。

{STAR_GUIDE}
{TITLE_GUIDE}

严格按以下格式输出：
{IDEA_FORMAT.replace('[热点名称]', topic)}"""


# ══════════════════════════════════════════════
# 处理"重做单个创意"（在页面顶部执行，避免冲突）
# ══════════════════════════════════════════════
if st.session_state.regen_idx is not None:
    prefix, idx = st.session_state.regen_idx
    st.session_state.regen_idx = None
    if prefix == "auto" and st.session_state.topics and idx < len(st.session_state.ideas):
        hot_topic = st.session_state.ideas[idx].get("hot_topic", "")
        with st.spinner(f"💡 重新生成第 {idx+1} 个创意..."):
            raw = call_ai(prompt_regen_one(hot_topic, st.session_state.topics), api_key)
        new = parse_ideas(raw)
        if new:
            st.session_state.ideas[idx] = new[0]
    elif prefix == "custom" and idx < len(st.session_state.custom_ideas):
        hot_topic = st.session_state.custom_ideas[idx].get("hot_topic", "")
        with st.spinner(f"💡 重新生成第 {idx+1} 个创意..."):
            raw = call_ai(prompt_regen_one(hot_topic, st.session_state.topics or []), api_key)
        new = parse_ideas(raw)
        if new:
            st.session_state.custom_ideas[idx] = new[0]
    st.rerun()


# ══════════════════════════════════════════════
# 页面主体
# ══════════════════════════════════════════════
st.title("🩸 献血新媒体创意助手")
st.caption("自动抓取热点 · 生成创意方向 · 推荐主题标题")

if not api_key:
    st.warning("请先在上方填入 API Key")
    st.stop()

st.divider()

# ────────────────────────────────────────────
# 区域一：今日热点创意
# ────────────────────────────────────────────
st.subheader("📡 今日热点创意")
st.caption("自动从微博、百度、抖音获取热点，AI 分析并生成创意方向")

c1, c2 = st.columns(2)
fetch_btn    = c1.button("🚀 获取热点并生成创意", type="primary", use_container_width=True)
regen_all_btn = c2.button("🔄 全部重新生成", use_container_width=True,
                           disabled=not st.session_state.topics)

if fetch_btn:
    with st.spinner("📡 正在抓取微博 / 百度 / 抖音热点..."):
        all_topics = collect_topics()
    if not all_topics:
        st.error("热点获取失败，请检查网络后重试。")
    else:
        with st.spinner("🔍 AI 正在筛选大健康相关热点..."):
            health_topics = filter_health_topics(all_topics, api_key)
        if health_topics:
            st.session_state.topics = health_topics
        else:
            st.session_state.topics = all_topics
            st.warning("未找到大健康相关热点，显示全部热点供参考。")
        ph = st.empty()
        ph.info("💡 AI 正在分析创意，请稍候（约 20 秒）...")
        raw = call_ai(prompt_auto(st.session_state.topics), api_key)
        ph.empty()
        st.session_state.ideas = parse_ideas(raw)
        st.session_state.auto_raw = raw
        st.rerun()

elif regen_all_btn and st.session_state.topics:
    ph = st.empty()
    ph.info("💡 AI 重新生成创意中...")
    raw = call_ai(prompt_auto(st.session_state.topics), api_key)
    ph.empty()
    st.session_state.ideas = parse_ideas(raw)
    st.session_state.auto_raw = raw
    st.rerun()

# 热点列表（可折叠）
if st.session_state.topics:
    show_topics_box(st.session_state.topics)

# 创意卡片
if st.session_state.ideas:
    st.markdown("### 💡 创意方向")
    for i, idea in enumerate(st.session_state.ideas):
        show_idea_card(idea, i, regen_key_prefix="auto")
elif st.session_state.auto_raw:
    st.warning("内容解析异常，显示原始结果：")
    st.text(st.session_state.auto_raw)

# ────────────────────────────────────────────
# 区域二：指定热点处理
# ────────────────────────────────────────────
st.divider()
st.subheader("🎯 指定热点处理")
st.caption("输入任意热点关键词，AI 从 3 个不同角度生成创意（独立输出区域）")

custom_topic = st.text_input(
    "热点", placeholder="例如：三八妇女节、高考、世界杯……",
    label_visibility="collapsed",
)
custom_btn = st.button("✨ 生成指定热点创意", disabled=not custom_topic)

if custom_btn and custom_topic:
    ph2 = st.empty()
    ph2.info(f"💡 AI 正在分析「{custom_topic}」...")
    raw2 = call_ai(prompt_custom(custom_topic), api_key)
    ph2.empty()
    st.session_state.custom_ideas = parse_ideas(raw2)
    st.session_state.custom_result = raw2
    st.rerun()

if st.session_state.custom_ideas:
    st.markdown("### 💡 创意方向")
    for i, idea in enumerate(st.session_state.custom_ideas):
        show_idea_card(idea, i, regen_key_prefix="custom")
elif st.session_state.custom_result:
    st.warning("内容解析异常，显示原始结果：")
    st.text(st.session_state.custom_result)
