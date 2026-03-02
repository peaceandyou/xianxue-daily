import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json

# ── 页面设置 ──────────────────────────────
st.set_page_config(
    page_title="献血新媒体日报",
    page_icon="🩸",
    layout="centered",
)

st.title("🩸 献血新媒体日报生成器")
st.caption("自动抓取今日热点，AI 分析关联，生成 300 字新媒体文章")
st.divider()

# ── API Key 处理 ──────────────────────────
# 优先从服务器密钥读取（部署后无需用户填写）
# 如果没有配置，则显示输入框
api_key = ""
try:
    api_key = st.secrets["CLAUDE_API_KEY"]
except Exception:
    pass

if not api_key:
    api_key = st.text_input(
        "请输入你的 API Key",
        type="password",
        placeholder="sk-ant-oat01-...",
        help="在 code.newcli.com 后台获取你的 API Key",
    )


# ── 热点抓取函数 ──────────────────────────
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
    weibo = get_weibo_hot()
    baidu = get_baidu_hot()
    seen, result = set(), []
    for t in weibo + baidu:
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


# ── AI 生成函数 ──────────────────────────
def ai_generate(topics, key):
    today = datetime.now().strftime("%Y年%m月%d日")
    topic_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics[:25]))

    prompt = f"""今天是{today}。

以下是今日各平台热搜话题：
{topic_list}

你是一名专注于无偿献血公益事业的新媒体编辑，擅长将时事热点与献血主题自然融合，写出有温度、有感染力的微信/微博文章。

请完成两步任务：

第一步——选题分析：
从上面的热点中，挑出最适合与"献血"话题结合的1-2个热点，说明选择理由（不超过50字）。

第二步——创作文章：
- 标题：吸引眼球，体现热点与献血的关联，有温度感
- 正文：300字左右，语言亲切接地气，用热点自然切入献血话题，不说教不灌输
- 结尾：正能量收尾，引导读者关注无偿献血

请严格按以下格式输出：

【选题分析】
热点：[选出的热点名称]
理由：[50字内说明]

【标题】
[文章标题]

【正文】
[约300字正文]"""

    resp = requests.post(
        "https://code.newcli.com/claude/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={"model": "gpt-5", "max_tokens": 2000, "stream": True,
              "messages": [{"role": "user", "content": prompt}]},
        stream=True,
        timeout=120,
    )

    if resp.status_code != 200:
        st.error(f"AI 调用失败（{resp.status_code}）：{resp.text[:200]}")
        return ""

    full_text = ""
    placeholder = st.empty()
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


# ── 主界面 ───────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    run_btn = st.button("🚀 生成今日文章", type="primary", use_container_width=True,
                        disabled=not api_key)
with col2:
    date_str = datetime.now().strftime("%m月%d日")
    st.markdown(f"<div style='text-align:center;padding-top:8px;color:gray'>{date_str}</div>",
                unsafe_allow_html=True)

if not api_key:
    st.info("请先在上方填入 API Key，再点击生成按钮。")

if run_btn and api_key:
    # 第一步：抓热点
    with st.spinner("📡 正在获取今日热点..."):
        topics = collect_topics()

    if not topics:
        st.error("热点获取失败，请检查网络后重试。")
        st.stop()

    with st.expander(f"📊 今日热点（共 {len(topics)} 条，点击展开）"):
        for i, t in enumerate(topics[:20], 1):
            st.write(f"{i}. {t}")

    st.divider()

    # 第二步：AI 写文章
    st.subheader("✍️ AI 正在写文章...")
    result = ai_generate(topics, api_key)

    if result:
        st.divider()
        st.success("文章生成完毕！复制后发布前建议稍作润色。")

        # 提供纯文本复制框
        st.text_area("📋 点击下方文本框，全选复制（Ctrl+A → Ctrl+C）",
                     value=result, height=400, label_visibility="visible")

        # 下载按钮
        today_str = datetime.now().strftime("%Y%m%d")
        st.download_button(
            label="⬇️ 下载为 txt 文件",
            data=result.encode("utf-8"),
            file_name=f"{today_str}_献血日报.txt",
            mime="text/plain",
        )
