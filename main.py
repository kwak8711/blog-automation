# main.py
import os
import json
import re
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

# ------------------------------------------------------------------
# 🌏 환경 변수
# ------------------------------------------------------------------
OPENAI_API_KEY       = os.environ.get("OPENAI_API_KEY")
GROQ_API_KEY         = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY")
SLACK_WEBHOOK_URL    = os.environ.get("SLACK_WEBHOOK_URL")

WORDPRESS_URL        = os.environ.get("WORDPRESS_URL")
WORDPRESS_USERNAME   = os.environ.get("WORDPRESS_USERNAME")
WORDPRESS_PASSWORD   = os.environ.get("WORDPRESS_PASSWORD")

SLACK_LINK_WORDPRESS = os.environ.get("SLACK_LINK_WORDPRESS", "https://your-wordpress-site.com")
SLACK_LINK_INSTA     = os.environ.get("SLACK_LINK_INSTA", "https://instagram.com/")
SLACK_LINK_NAVER     = os.environ.get("SLACK_LINK_NAVER", "https://blog.naver.com/")

AI_PROVIDER          = os.environ.get("AI_PROVIDER", "AUTO")
MODE                 = os.environ.get("MODE", "generate")

# 하루 3개 → 09:00, 12:00, 18:00
POSTS_PER_DAY = 3

KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")

# ------------------------------------------------------------------
# 🏪 편의점 정보
# ------------------------------------------------------------------
STORES = {
    "gs25":       {"name_kr": "GS25",       "name_jp": "GS25",            "country": "kr", "category": "convenience"},
    "cu":         {"name_kr": "CU",         "name_jp": "CU",              "country": "kr", "category": "convenience"},
    "7eleven":    {"name_kr": "세븐일레븐",  "name_jp": "セブンイレブン",     "country": "kr", "category": "convenience"},
    "familymart": {"name_kr": "패밀리마트",  "name_jp": "ファミリーマート",    "country": "jp", "category": "convenience"},
    "lawson":     {"name_kr": "로손",       "name_jp": "ローソン",          "country": "jp", "category": "convenience"},
}


# ------------------------------------------------------------------
# 🔧 공통 유틸
# ------------------------------------------------------------------
def _ensure_obj(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def strip_images(html: str) -> str:
    """AI가 넣어버린 이미지 태그 싹 제거"""
    if not html:
        return ""
    html = re.sub(r"<img[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<figure[^>]*>.*?</figure>", "", html, flags=re.IGNORECASE | re.DOTALL)
    return html


# ------------------------------------------------------------------
# 🇰🇷+🇯🇵 본문 꾸미기
# 1) 한국어 → 파스텔 박스
# 2) 일본어(🇯🇵로 시작하는 문장) → 오렌지 박스
# 3) h2/h3는 예쁜 스타일로 교체
# ------------------------------------------------------------------
def split_kr_jp(segment: str):
    """한 블록 안에서 🇯🇵 이후는 일본어로 본다"""
    if "🇯🇵" in segment:
        kr, jp = segment.split("🇯🇵", 1)
        return kr.strip(), ("🇯🇵 " + jp.strip())
    else:
        return segment.strip(), ""


def wrap_kr_box(text: str) -> str:
    return (
        "<div style=\"background:#fffaf1;border:1px solid rgba(255,166,0,0.22);"
        "padding:15px 18px 13px;border-radius:16px;margin:0 0 10px 0;"
        "line-height:1.68;color:#3a2a1f;font-size:14.2px;\">"
        f"{text}"
        "</div>"
    )


def wrap_jp_box(text: str) -> str:
    return (
        "<div style=\"background:#ffe4d1;border:1px solid rgba(255,144,93,0.35);"
        "padding:13px 16px 11px;border-radius:16px;margin:0 0 14px 0;"
        "line-height:1.6;color:#4d3422;font-size:13.5px;\">"
        "<div style='font-weight:600;margin-bottom:4px;display:flex;gap:6px;align-items:center;'>🇯🇵 日本語要約</div>"
        f"{text}"
        "</div>"
    )


def ensure_bilingual_content(html: str, store_name: str) -> str:
    """
    AI가 준 content가 난잡해도 우리가 강제로
    [제목] → [한국어 박스] → [일본어 박스]
    패턴으로 만들어주는 함수
    """
    html = strip_images(html)

    # h2/h3 단위로 쪼갠다
    # re.split 으로 태그를 남겨놓고 split
    tokens = re.split(r'(<h2.*?>|<h3.*?>)', html, flags=re.IGNORECASE)
    out = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # 제목일 때
        if re.match(r'<h2.*?>', token or "", flags=re.IGNORECASE) or re.match(r'<h3.*?>', token or "", flags=re.IGNORECASE):
            # 실제 제목 텍스트 추출
            title_tag = token
            i += 1
            if i < len(tokens):
                body = tokens[i]
            else:
                body = ""

            # 제목 텍스트만
            title_text = re.sub(r'<.*?>', '', title_tag).strip()

            out.append(
                f"<h2 style=\"font-size:24px;margin:30px 0 14px 0;font-weight:700;color:#2f3542;\">{title_text}</h2>"
            )

            kr, jp = split_kr_jp(body)
            if kr:
                out.append(wrap_kr_box(kr))
            if jp:
                out.append(wrap_jp_box(jp))
        else:
            # 그냥 텍스트 블록
            if token.strip():
                kr, jp = split_kr_jp(token)
                if kr:
                    out.append(wrap_kr_box(kr))
                if jp:
                    out.append(wrap_jp_box(jp))
        i += 1

    return "".join(out)


# ------------------------------------------------------------------
# 🧁 워드프레스 HTML 만들기
# ------------------------------------------------------------------
def build_wp_html(ai_result: dict, store_info: dict) -> str:
    store_name_kr = store_info.get("name_kr", "편의점")
    store_name_jp = store_info.get("name_jp", store_name_kr)
    title_kor = ai_result.get("title") or f"{store_name_kr} 신상 리뷰!"
    title_jp = f"{store_name_jp} の新商品レビュー"

    content_raw = ai_result.get("content") or "<p>오늘 나온 신상들이에요 💖</p>"
    content_wrapped = ensure_bilingual_content(content_raw, store_name_kr)

    # 공주님 인스타 복붙할 때 참고할 해시태그들
    hashtags = " ".join([
        "#편의점신상", "#편의점", "#편의점추천", "#コンビニ新商品", "#コンビニ", "#韓国コンビニ",
        "#コンビニグルメ", "#오늘뭐먹지", "#kconbini", "#koreaconbini", f"#{store_name_kr}"
    ])

    html = f"""
<div style="max-width:840px;margin:0 auto;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;">

  <!-- 상단 캡션 -->
  <div style="background:linear-gradient(120deg,#fff0f5 0%,#edf1ff 100%);
              border:1px solid rgba(248,132,192,0.25);
              padding:18px 20px 15px;
              border-radius:18px;
              margin-bottom:18px;
              display:flex;
              gap:12px;">
    <div style="font-size:30px;">🛒</div>
    <div>
      <p style="margin:0 0 4px 0;font-weight:700;color:#d62976;font-size:14px;">K-CONBINI DAILY</p>
      <p style="margin:0 0 2px 0;font-size:17px;color:#222;font-weight:700;">{title_kor}</p>
      <p style="margin:0;font-size:14px;color:#666;">{title_jp}</p>
    </div>
  </div>

  <!-- 제목 -->
  <h1 style="font-size:31px;margin:4px 0 6px 0;font-weight:700;color:#2f3542;">{title_kor}</h1>
  <p style="margin:0 0 14px 0;font-size:14px;color:#555;">{title_jp}</p>

  <!-- 인사말 -->
  <div style="background:#fff7fb;padding:18px 18px 15px;border-radius:16px;margin-bottom:16px;
              border:1.2px solid rgba(252,95,168,0.25);">
    <p style="font-size:14.8px;line-height:1.7;margin:0;color:#222;">
      안녕하세요, 오늘은 <strong>{store_name_kr}</strong>에서 갓 나온 따끈따끈한 신상을 가져왔어요 😋<br>
      한국/일본 팔로워가 같이 보는 글이라서 아래에 일본어 요약도 붙여뒀어요 💛
    </p>
  </div>

  <!-- 본문 (한국어 박스 + 일본어 박스) -->
  <div style="background:#fff;border-radius:16px;margin-bottom:26px;">
    {content_wrapped}
  </div>

  <!-- 엔딩 -->
  <div style="background:linear-gradient(135deg,#5f63f2 0%,#7a4fff 60%,#c6b8ff 100%);
              padding:22px 20px 20px;
              border-radius:18px;
              margin-bottom:26px;
              box-shadow:0 12px 30px rgba(95,99,242,0.25);">
    <p style="color:#fff;font-size:15px;line-height:1.8;margin:0 0 6px 0;">
      오늘 소개한 것 중에 뭐가 제일 먹고 싶었어요? 댓글로 알려주면 다음엔 그걸로 레시피도 만들어볼게요 💜
    </p>
    <p style="color:rgba(255,255,255,0.88);font-size:14px;line-height:1.6;margin:0;">
      今日紹介した{store_name_jp}の新商品もチェックしてね ✨
    </p>
  </div>

  <!-- 해시태그 -->
  <div style="background:linear-gradient(to right,#f8f9ff 0%,#fff5f8 100%);
              padding:20px 18px;
              border-radius:16px;
              text-align:center;
              border:1px dashed rgba(118,75,162,0.28);">
    <p style="margin:0 0 10px 0;font-size:15px;color:#667eea;font-weight:600;">📎 해시태그 / ハッシュタグ</p>
    <p style="margin:0;font-size:13.5px;line-height:2.0;color:#4b4b4b;word-break:break-all;">
      {hashtags}
    </p>
  </div>

</div>
"""
    return html


# ------------------------------------------------------------------
# 📱 인스타 캡션 만들기
# ------------------------------------------------------------------
def build_insta_caption(ai_result: dict, store_info: dict, scheduled_dt_kst: datetime) -> str:
    store_name = store_info.get("name_kr", "편의점")
    title = ai_result.get("title") or f"{store_name} 신상 털이!"
    time_str = scheduled_dt_kst.strftime("%m/%d %H:%M")

    hashtags = " ".join([
        "#편의점신상", "#コンビニ新商品", "#편스타그램", "#コンビニグルメ",
        "#오늘뭐먹지", "#kconbini", f"#{store_name}"
    ])

    caption = (
        f"🛒 {title}\n"
        f"{store_name} 오늘 나온 거만 모았어 💖\n\n"
        f"⏰ {time_str} (KST) 업로드 예정!\n"
        f"🇰🇷 한국어 OK / 🇯🇵 日本語 OK\n\n"
        f"{hashtags}"
    )
    return caption


# ------------------------------------------------------------------
# 🤖 AI 호출 (Gemini → Groq → OpenAI)
# ------------------------------------------------------------------
def generate_with_auto(prompt: str):
    print("🤖 AUTO 모드: Gemini → Groq → OpenAI")

    # 1) Gemini
    if GEMINI_API_KEY:
        try:
            print("  🟣 Gemini 시도...")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": 8192,
                    "responseMimeType": "application/json"
                },
            }
            r = requests.post(url, json=body, timeout=120)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as e:
            print("  ❌ Gemini 실패:", e)

    # 2) Groq
    if GROQ_API_KEY:
        try:
            print("  🔵 Groq 시도...")
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system",
                     "content": "너는 한국과 일본 팔로워가 같이 보는 '편의점 신상 블로거'야. 각 상품은 한국어 설명 다음 줄에 일본어(🇯🇵) 요약을 넣어. JSON 으로만 답해."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.9
            }
            r = requests.post(url, headers=headers, json=data, timeout=120)
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            print("  ❌ Groq 실패:", e)

    # 3) OpenAI
    if OPENAI_API_KEY:
        try:
            print("  🟢 OpenAI 시도...")
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            data = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system",
                     "content": "너는 한국과 일본 팔로워가 같이 보는 '편의점 신상 블로거'야. 각 상품은 한국어 설명 다음 줄에 일본어(🇯🇵) 요약을 넣어. JSON 으로만 답해."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.9
            }
            r = requests.post(url, headers=headers, json=data, timeout=120)
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:
            print("  ❌ OpenAI 실패:", e)

    return None


# ------------------------------------------------------------------
# 🌐 워드프레스 발행 (예약)
# ------------------------------------------------------------------
def publish_to_wordpress(title: str, content: str, tags: list, category: str, scheduled_dt_kst: datetime):
    try:
        client = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {"post_tag": tags, "category": [category]}

        # 예약으로 넣기
        if scheduled_dt_kst:
            dt_utc = scheduled_dt_kst.astimezone(UTC)
            post.date = scheduled_dt_kst      # 대시보드에서 보이는 시간
            post.date_gmt = dt_utc            # 실제 예약 시간
            post.post_status = "future"
        else:
            post.post_status = "publish"

        post_id = client.call(NewPost(post))
        post_url = f"{WORDPRESS_URL}/?p={post_id}"
        print(f"✅ 워드프레스 예약 성공: {post_url}")
        return post_id, post_url
    except Exception as e:
        print("❌ 워드프레스 실패:", e)
        return None, None


# ------------------------------------------------------------------
# 📨 슬랙 알림 (공주님 감성 버전)
# ------------------------------------------------------------------
def send_slack(payload: dict):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass


def send_slack_insta_only(insta_caption: str, store_name: str, scheduled_dt: datetime, post_url: str):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📸 인스타 올릴 시간 미리 알려줄게 💖", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{store_name}* 글이 *{scheduled_dt.strftime('%Y-%m-%d %H:%M')}* 에 올라가요.\n이 캡션 복붙해서 인스타에 올리면 끝! 😎"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{insta_caption}```"}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "⏰ 예약된 시간에 맞춰서 워드프레스에 먼저 올라가니까 인스타는 그때 올려줘 💌"}
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "💚 워드프레스 보기"},
                    "url": post_url or SLACK_LINK_WORDPRESS
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📷 인스타 바로가기"},
                    "url": SLACK_LINK_INSTA
                }
            ]
        }
    ]
    send_slack({"text": f"{store_name} 인스타 알림", "blocks": blocks})


def send_slack_summary(schedule_list: list):
    # schedule_list: [{title, time, url, country}]
    total = len(schedule_list)
    kr_count = len([s for s in schedule_list if s["country"] == "kr"])
    jp_count = len([s for s in schedule_list if s["country"] == "jp"])

    lines = []
    for s in schedule_list:
        lines.append(f"• {s['title']} → {s['time'].strftime('%Y-%m-%d %H:%M')}")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🎉 한일 편의점 예약발행 완료!", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📝 총 {total}개 글 자동 예약*\n🇰🇷 한국: {kr_count}개\n🇯🇵 일본: {jp_count}개"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "⏰ *발행 스케줄*\n" + "\n".join(lines)}
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "📱 *바로가기*\n원하는 채널 골라서 확인해줘 💖"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "💚 워드프레스"}, "url": SLACK_LINK_WORDPRESS},
                {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타"}, "url": SLACK_LINK_INSTA},
                {"type": "button", "text": {"type": "plain_text", "text": "✍️ 네이버"}, "url": SLACK_LINK_NAVER},
            ]
        }
    ]
    send_slack({"text": "예약발행 완료", "blocks": blocks})


# ------------------------------------------------------------------
# 🕘 내일 09/12/18 슬롯 만들기
# ------------------------------------------------------------------
def get_tomorrow_slots():
    now = datetime.now(KST)
    t = (now + timedelta(days=1)).date()
    return [
        datetime(t.year, t.month, t.day, 9, 0, tzinfo=KST),
        datetime(t.year, t.month, t.day, 12, 0, tzinfo=KST),
        datetime(t.year, t.month, t.day, 18, 0, tzinfo=KST),
    ]


# ------------------------------------------------------------------
# 🧠 전체 실행
# ------------------------------------------------------------------
def generate_and_schedule():
    print("=" * 60)
    print("🚀 한일 편의점 콘텐츠 자동 생성 시작")
    print("=" * 60)

    slots = get_tomorrow_slots()
    store_keys = list(STORES.keys())

    results_for_summary = []

    for idx, store_key in enumerate(store_keys[:POSTS_PER_DAY]):
        store_info = STORES[store_key]
        slot_dt = slots[idx]

        # 프롬프트
        if store_info["country"] == "kr":
            prompt = f"""
한국 편의점 블로거처럼 JSON으로만 답해.
편의점: {store_info['name_kr']}
조건:
- 필드: title, content, tags
- content는 HTML로
- 각 상품은 "한국어 설명" → 바로 다음 줄에 "🇯🇵 일본어 요약" 순서로 작성
- <img> 태그는 절대 넣지 마
- 말투는 귀엽고, 이모티콘 많이 써
- tags는 ["편의점신상","{store_info['name_kr']}","コンビニ新商品"]
"""
        else:
            prompt = f"""
韓国のコンビニ新商品を紹介するブログ記事をJSONで作ってください。
コンビニ: {store_info['name_jp']}
条件:
- title, content, tags を返す
- content は HTML
- 各商品について 韓国語 → 直後に🇯🇵で始まる日本語まとめ を書く
- <img> タグは書かない
- tags: ["コンビニ新商品","{store_info['name_jp']}","韓国コンビニ"]
"""

        ai_result = generate_with_auto(prompt)
        if not ai_result:
            print(f"❌ {store_info['name_kr']} 생성 실패")
            continue

        ai_result = _ensure_obj(ai_result)
        html = build_wp_html(ai_result, store_info)

        post_id, post_url = publish_to_wordpress(
            title=ai_result.get("title", f"{store_info['name_kr']} 신상 리뷰"),
            content=html,
            tags=ai_result.get("tags", ["편의점신상"]),
            category=store_info.get("category", "convenience"),
            scheduled_dt_kst=slot_dt
        )

        if post_id:
            # 인스타 캡션 알림
            insta_caption = build_insta_caption(ai_result, store_info, slot_dt)
            send_slack_insta_only(insta_caption, store_info["name_kr"], slot_dt, post_url)

            results_for_summary.append({
                "title": ai_result.get("title", store_info["name_kr"]),
                "time": slot_dt,
                "url": post_url,
                "country": store_info["country"],
            })

        time.sleep(1)

    # 하루 요약 알림
    if results_for_summary:
        send_slack_summary(results_for_summary)

    print("✅ 끝! 모두 예약해놨어요 💖")


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------
if __name__ == "__main__":
    # MODE=remind 일 때는 발행 시점 알림만 보내는 용도로 쓸 수도 있음
    if MODE == "generate":
        generate_and_schedule()
    else:
        # 간단 리마인더
        send_slack({"text": "⏰ 예약된 글이 방금 발행됐어! 인스타에도 올려줘 💖"})
