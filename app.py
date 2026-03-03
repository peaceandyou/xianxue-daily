import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json

# ── 页面设置 ──────────────────────────────
st.set_page_config(
    page_title="献血新媒体创意助手",
    page_icon="🩸",
    layout="centered",
)

# ── Session State 初始化 ──────────────────
for key in ["topics", "auto_result", "custom_result"]:
    if key not in st.session_state:
        st.session_state[key] = [] if key == "topics" else ""

# ── API Key ───────────────────────────────
api_key = ""
try:
    api_key = st.secrets["CLAUDE_API_KEY"]
except Exception:
    pass
if not api_key:
    api_key = st.text_input(
        "请输入 API Key",
        type="password",
        placeholder="sk-ant-oat01-...",
    )

# ── 热点抓取 ──────────────────────────────
def get_weibo_hot():
    topics = []
    try:
        r = requests.get(
            "https://weibo.com/ajax/statuses/hot_band",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://s.weibo.com/",
            },
            timeout=15,
        )
        for item in r.json().get("data", {}).get("band_list", [])[:20]:
            w = item.get("word", "").strip()
            if w:
                topics.append(w)
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
                for item in items[:20]:
                    t = item.get_text(strip=True)
                    if t and len(t) > 1:
                        topics.append(t)
                break
    except Exception:
        pass
    return topics


def collect_topics():
    seen, result = set(), []
    for t in get_weibo_hot() + get_baidu_hot():
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


# ── AI 调用（流式）────────────────────────
def call_ai(prompt, key, placeholder):
    resp = requests.post(
        "https://code.newcli.com/claude/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={
            "model": "gpt-5",
            "max_tokens": 1500,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        },
        stream=True,
        timeout=120,
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
                chunk = json.loads(data)
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if content:
                    full_text += content
                    placeholder.markdown(full_text + "▌")
            except Exception:
                continue
    placeholder.markdown(full_text)
    return full_text


# ── 今日热点创意 Prompt ───────────────────
def prompt_auto(topics):
    today = datetime.now().strftime("%Y年%m月%d日")
    topic_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics[:25]))
    return f"""今天是{today}，以下是今日各平台热搜话题：
{topic_list}

你是一名无偿献血公益事业的新媒体策划师，请从上面热点中挑出最适合与献血结合的1-2个，然后给出：

1. 创意方向：3-5个具体角度，说明如何将热点与无偿献血自然结合（每个50字内，接地气、有感染力）
2. 推荐主题标题：3个备选标题，要突出重点、吸引眼球

请严格按以下格式输出：

【选出热点】
[热点名称]

【创意方向】
① [角度1]
② [角度2]
③ [角度3]

【推荐主题】
① [标题1]
② [标题2]
③ [标题3]"""


# ── 指定热点创意 Prompt ───────────────────
def prompt_custom(topic):
    return f"""热点话题：「{topic}」

你是一名无偿献血公益事业的新媒体策划师，请分析这个热点如何与无偿献血主题结合，给出：

1. 热点背景：简要说明这个热点的当前背景（2-3句话）
2. 创意方向：3-5个具体角度，说明如何将热点与无偿献血自然结合（每个50字内）
3. 推荐主题标题：3个备选标题，突出重点、吸引眼球、有感染力

请严格按以下格式输出：

【热点背景】
[2-3句背景说明]

【创意方向】
① [角度1]
② [角度2]
③ [角度3]

【推荐主题】
① [标题1]
② [标题2]
③ [标题3]"""


# ════════════════════════════════════════════
# 标题
# ════════════════════════════════════════════
st.title("🩸 献血新媒体创意助手")
st.caption("自动抓取热点 · 生成创意方向 · 推荐吸睛主题")

if not api_key:
    st.warning("请先在上方填入 API Key")
    st.stop()

st.divider()

# ════════════════════════════════════════════
# 区域一：今日热点创意
# ════════════════════════════════════════════
st.subheader("📡 今日热点创意")
st.caption("自动从微博、百度获取当日热点，AI 分析创意方向与主题建议")

c1, c2 = st.columns(2)
fetch_btn  = c1.button("🚀 获取热点并生成创意", type="primary", use_container_width=True)
regen_btn  = c2.button("🔄 重新生成",
                        use_container_width=True,
                        disabled=not st.session_state.topics)

# 点「获取热点并生成」
if fetch_btn:
    with st.spinner("📡 正在获取今日热点..."):
        st.session_state.topics = collect_topics()
    if not st.session_state.topics:
        st.error("热点获取失败，请检查网络后重试。")
    else:
        st.session_state.auto_result = ""
        ph = st.empty()
        with st.spinner("💡 AI 正在生成创意方向..."):
            st.session_state.auto_result = call_ai(
                prompt_auto(st.session_state.topics), api_key, ph
            )

# 点「重新生成」
elif regen_btn and st.session_state.topics:
    st.session_state.auto_result = ""
    ph = st.empty()
    with st.spinner("💡 AI 重新生成创意方向..."):
        st.session_state.auto_result = call_ai(
            prompt_auto(st.session_state.topics), api_key, ph
        )

# 显示热点列表
if st.session_state.topics:
    with st.expander(f"📊 今日热点（共 {len(st.session_state.topics)} 条，点击展开）"):
        cols = st.columns(2)
        for i, t in enumerate(st.session_state.topics[:20]):
            cols[i % 2].write(f"{i+1}. {t}")

# 显示创意结果
if st.session_state.auto_result:
    st.markdown(st.session_state.auto_result)
    st.download_button(
        "⬇️ 下载创意文档",
        data=st.session_state.auto_result.encode("utf-8"),
        file_name=f"{datetime.now().strftime('%Y%m%d')}_热点创意.txt",
        mime="text/plain",
        key="dl_auto",
    )

# ════════════════════════════════════════════
# 区域二：指定热点处理（完全独立）
# ════════════════════════════════════════════
st.divider()
st.subheader("🎯 指定热点处理")
st.caption("手动输入你感兴趣的任意热点，AI 单独为它生成创意方向与主题")

custom_topic = st.text_input(
    "输入热点关键词",
    placeholder="例如：三八妇女节、高考、世界杯……",
    label_visibility="collapsed",
)
custom_btn = st.button("✨ 生成指定热点创意", disabled=not custom_topic)

if custom_btn and custom_topic:
    st.session_state.custom_result = ""
    ph2 = st.empty()
    with st.spinner(f"💡 AI 正在分析「{custom_topic}」..."):
        st.session_state.custom_result = call_ai(
            prompt_custom(custom_topic), api_key, ph2
        )

if st.session_state.custom_result:
    st.markdown(st.session_state.custom_result)
    st.download_button(
        "⬇️ 下载创意文档",
        data=st.session_state.custom_result.encode("utf-8"),
        file_name=f"{datetime.now().strftime('%Y%m%d')}_指定热点创意.txt",
        mime="text/plain",
        key="dl_custom",
    )
