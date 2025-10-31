import os
import json
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

# ========================================
# 🌏 환경변수
# ========================================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
GROQ_API_KEY         = os.environ.get('GROQ_API_KEY')
GEMINI_API_KEY       = os.environ.get('GEMINI_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')

WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')

SLACK_LINK_WORDPRESS = os.environ.get('SLACK_LINK_WORDPRESS', 'https://your-wordpress-site.com')
SLACK_LINK_INSTA     = os.environ.get('SLACK_LINK_INSTA', 'https://instagram.com/')
SLACK_LINK_NAVER     = os.environ.get('SLACK_LINK_NAVER', 'https://blog.naver.com/')

# 하루에 만들 글 수
POSTS_PER_DAY = 3

# 한국 시간
KST = ZoneInfo("Asia/Seoul")

# ========================================
# 🏪 편의점 목록
# 필요한 것만 3개씩 쓸 거라 길어도 됨
# ========================================
STORES = {
    "gs25": {
        "name_kr": "GS25",
        "name_jp": "GS25",
        "country": "kr",
        "category": "convenience"
    },
    "cu": {
        "name_kr": "CU",
        "name_jp": "CU",
        "country": "kr",
        "category": "convenience"
    },
    "7eleven": {
        "name_kr": "세븐일레븐",
        "name_jp": "セブンイレブン",
        "country": "kr",
        "category": "convenience"
    },
    "familymart": {
        "name_kr": "패밀리마트",
        "name_jp": "ファミリーマート",
        "country": "jp",
        "category": "convenience"
    },
    "lawson": {
        "name_kr": "로손",
        "name_jp": "ローソン",
        "country": "jp",
        "category": "convenience"
    },
}

# ========================================
# 🧩 공통 유틸
# ========================================
def _ensure_dict(result):
    if isinstance(result, list):
        return result[0] if result else None
    return result

# ========================================
# 🇯🇵 한국/일본 같이 보이게 보정
# ========================================
def ensure_bilingual_content(html: str, store_name: str) -> str:
    """
    AI가 한국어만 쓰거나 일본어를 맨 끝에만 쓰는 경우,
    공주님이 보여준 것처럼 각 섹션 끝에 일본어 박스를 자동으로 달아준다.
    h2 / h3 기준으로 쪼갠다.
    """
    if not html:
        return ""

    jp_box = (
        "<div style='background:#ffe9d5;"
        "padding:14px 16px 13px;border-radius:14px;"
        "margin:16px 0 6px 0;border-left:5px solid #ff9f66;"
        "font-size:13.5px;line-height:1.6;color:#5a3a25'>"
        "<strong style='display:block;margin-bottom:4px;font-size:14.5px;'>🇯🇵 日本語要約</strong>"
        f"{store_name}の新商品について上で説明しました。味のポイント・価格・おすすめの食べ方を韓国語で書いています。日本のフォロワーさんはこのボックスだけ読んでもOKです 💛"
        "</div>"
    )

    # h2 단위로 먼저 나눠본다
    if "<h2" in html:
        parts = html.split("<h2")
        new_html = parts[0]
        for p in parts[1:]:
            if "</h2>" in p:
                head, tail = p.split("</h2>", 1)
                new_html += "<h2" + head + "</h2>"
                new_html += jp_box + tail
            else:
                new_html += "<h2" + p
        return new_html

    # h3 기준
    if "<h3" in html:
        parts = html.split("<h3")
        new_html = parts[0]
        for p in parts[1:]:
            if "</h3>" in p:
                head, tail = p.split("</h3>", 1)
                new_html += "<h3" + head + "</h3>"
                new_html += jp_box + tail
            else:
                new_html += "<h3" + p
        return new_html

    # 섹션이 아예 없으면 그냥 맨 아래에만
    return html + jp_box

# ========================================
# 🧁 워드프레스 HTML 빌더
# (공주님이 캡쳐 보여준 스타일)
# ========================================
def build_wp_html(ai_result: dict, store_info: dict) -> str:
    store_name = store_info.get('name_kr', '편의점')
    title_kor = ai_result.get('title') or f"{store_name} 신상 제품 리뷰!"
    main_content_raw = ai_result.get('content') or "<p>오늘 나온 신상들이에요 💖</p>"

    # 한국/일본 보정
    main_content = ensure_bilingual_content(main_content_raw, store_name)

    # 인스타/블로그용 해시태그 빵빵하게
    hashtags = " ".join([
        "#편의점신상", "#편의점", "#편의점추천", "#신상품", "#CU", "#GS25", "#세븐일레븐",
        "#コンビニ", "#コンビニ新商品", "#韓国コンビニ", "#コンビニグルメ", "#MZおすすめ",
        "#오늘뭐먹지", "#오늘간식", "#kconbini", "#koreaconbini", "#おやつ", "#간편식",
        "#디저트", "#convenience_store", f"#{store_name}"
    ])

    html = f"""
<div style="max-width: 840px;margin: 0 auto;font-family: 'Malgun Gothic','Apple SD Gothic Neo',sans-serif">

  <!-- 상단 캡션 박스 -->
  <div style="background: linear-gradient(120deg,#fff0f5 0%,#edf1ff 100%);border: 1px solid rgba(248,132,192,0.25);padding: 18px 20px 14px;border-radius: 18px;margin-bottom: 18px;display:flex;gap:12px;align-items:flex-start">
    <div style="font-size:30px;line-height:1">🛒</div>
    <div>
      <p style="margin:0 0 4px 0;font-weight:700;color:#d62976;font-size:14px;letter-spacing:0.4px">K-CONBINI DAILY PICK</p>
      <p style="margin:0 0 3px 0;font-size:17px;color:#222;font-weight:700">{title_kor}</p>
      <p style="margin:0;color:#666;font-size:13px">🇰🇷 한국 + 🇯🇵 일본 팔로워 같이 보는 글이에요. 그대로 인스타에도 복붙해서 써도 돼요 💖</p>
    </div>
  </div>

  <!-- 제목 블록 -->
  <div style="background: radial-gradient(circle at top, #667eea 0%, #764ba2 50%, #ffffff 100%);padding: 34px 28px 28px;border-radius: 24px;margin-bottom: 30px;text-align: center;box-shadow: 0 12px 36px rgba(103,114,229,0.15)">
    <h1 style="color: #fff;font-size: 28px;margin: 0 0 10px 0;font-weight: 700">🛒 {title_kor}</h1>
    <p style="color: rgba(255,255,255,0.9);font-size: 15px;margin: 0">コンビニ新商品レビュー 🇰🇷🇯🇵 | {store_name}</p>
  </div>

  <!-- 인사말 -->
  <div style="background: #fff7fb;padding: 22px 22px 20px;border-radius: 16px;margin-bottom: 26px;border: 1.4px solid rgba(252,95,168,0.25)">
    <p style="font-size: 15.2px;line-height: 1.7;margin: 0;color: #222">
      <strong style="font-size: 16.4px">안녕 편스타그램 친구들 💖</strong><br>
      오늘은 <strong>{store_name}</strong>에서 막 나온 신상만 골라왔어! 한국 친구들은 위쪽 한국어 설명 보면 되고,
      일본 친구들은 각 섹션 아래쪽 <strong>「🇯🇵 日本語要約」</strong>만 봐도 이해돼요 ✨
    </p>
  </div>

  <!-- 본문 (AI가 준 HTML + 일본어 보정) -->
  <div style="background: #ffffff;padding: 0 0 0;border-radius: 16px;margin-bottom: 30px;">
    {main_content}
  </div>

  <!-- 엔딩 박스 -->
  <div style="background: linear-gradient(135deg,#5f63f2 0%,#7a4fff 60%,#c6b8ff 100%);padding: 28px 26px 26px;border-radius: 18px;margin-bottom: 28px;box-shadow: 0 12px 30px rgba(95,99,242,0.25)">
    <p style="color:#fff;font-size:15.5px;line-height:1.8;margin:0 0 8px 0;">
      오늘 소개해드린 {store_name} 신상품, 어땠나요? 😋 기회 되면 꼭 한 번 드셔보고,
      “이 조합도 맛있다!” 싶은 거 있으면 댓글로 알려줘요 💜
    </p>
    <p style="color:rgba(255,255,255,0.9);font-size:14px;line-height:1.7;margin:0">
      今日紹介した{store_name}の新商品はいかがでしたか？気になるアイテムがあったらぜひ試してみてくださいね ✨
    </p>
  </div>

  <!-- 해시태그 -->
  <div style="background: linear-gradient(to right, #f8f9ff 0%, #fff5f8 100%);padding: 25px 22px;border-radius: 16px;text-align: center;border: 1px dashed rgba(118,75,162,0.3);margin-bottom: 10px">
    <p style="margin: 0 0 10px 0;font-size: 15px;color: #667eea;font-weight: 600">📎 해시태그 / ハッシュタグ</p>
    <p style="margin: 0;font-size: 13.5px;line-height: 2.0;color: #4b4b4b;word-break:break-all">
      {hashtags}
    </p>
  </div>

</div>
"""
    return html

# ========================================
# 📱 인스타 캡션
# ========================================
def build_insta_caption(ai_result: dict, store_info: dict, scheduled_time_kst: datetime) -> str:
    store_name = store_info.get('name_kr', '편의점')
    title = ai_result.get('title') or f"{store_name} 신상 리뷰!"
    date_line = scheduled_time_kst.strftime("%m/%d %H:%M")
    hashtags = [
        "#편의점신상", "#コンビニ新商品", f"#{store_name}",
        "#편스타그램", "#コンビニグルメ", "#오늘뭐먹지", "#kconbini"
    ]
    cap = [
        f"🛒 {title}",
        f"{store_name} 오늘 나온 거 모아봤어 💖",
        "",
        f"⏰ 업로드 시간: {date_line} (KST)",
        "🇰🇷 한국어 OK / 🇯🇵 日本語 OK",
        "",
        " ".join(hashtags)
    ]
    return "\n".join(cap)

# ========================================
# 🤖 AI 호출 (Gemini → Groq → OpenAI)
# ========================================
def generate_with_auto(prompt):
    print("  🤖 AUTO 모드: Gemini → Groq → OpenAI")

    res = call_gemini(prompt)
    res = _ensure_dict(res)
    if res:
        return res

    res = call_groq(prompt)
    res = _ensure_dict(res)
    if res:
        return res

    res = call_openai(prompt)
    res = _ensure_dict(res)
    if res:
        return res

    return None

def call_gemini(prompt):
    if not GEMINI_API_KEY:
        return None
    try:
        print("  🟣 Gemini 시도...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.85,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            }
        }
        r = requests.post(url, json=data, timeout=120)
        r.raise_for_status()
        text = r.json()['candidates'][0]['content']['parts'][0]['text']
        return json.loads(text)
    except Exception as e:
        print("  ❌ Gemini 실패:", e)
        return None

def call_groq(prompt):
    if not GROQ_API_KEY:
        return None
    try:
        print("  🔵 Groq 시도...")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system",
                 "content": "너는 한국과 일본 팔로워에게 동시에 보여줄 편의점 신상 블로거야. 각 상품마다 한국어 설명과 일본어 요약을 같이 넣어. JSON으로만 답해."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.85,
        }
        r = requests.post(url, headers=headers, json=data, timeout=120)
        r.raise_for_status()
        return json.loads(r.json()['choices'][0]['message']['content'])
    except Exception as e:
        print("  ❌ Groq 실패:", e)
        return None

def call_openai(prompt):
    if not OPENAI_API_KEY:
        return None
    try:
        print("  🟢 OpenAI 시도...")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system",
                 "content": "너는 한국과 일본 팔로워에게 동시에 보여줄 편의점 신상 블로거야. 각 상품마다 한국어 설명과 일본어 요약을 같이 넣어. JSON으로만 답해."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.85,
        }
        r = requests.post(url, headers=headers, json=data, timeout=120)
        r.raise_for_status()
        return json.loads(r.json()['choices'][0]['message']['content'])
    except Exception as e:
        print("  ❌ OpenAI 실패:", e)
        return None

# ========================================
# 🌐 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags, category, scheduled_dt_kst=None):
    try:
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {
            'post_tag': tags,
            'category': [category]
        }
        if scheduled_dt_kst:
            post.date = scheduled_dt_kst
        post_id = wp.call(NewPost(post))
        print(f"  ✅ 워드프레스 발행 성공: {post_id}")
        return post_id
    except Exception as e:
        print(f"  ❌ 워드프레스 발행 실패: {e}")
        return None

# ========================================
# 📨 슬랙 전송
# ========================================
def send_slack(payload: dict):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass

def send_slack_insta_and_html(insta_caption: str, html_preview: str, store_name: str, scheduled_dt: datetime):
    # 너무 길면 잘라
    if len(html_preview) > 2500:
        html_preview = html_preview[:2500] + "\n..."

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📷 인스타 & 워드프레스 알림 💖", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{store_name}* 글이 *{scheduled_dt.strftime('%Y-%m-%d %H:%M')}* 에 올라가요.\n아래는 인스타 복붙용 + 워드프레스 HTML 미리보기예요 ✨"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📱 인스타 캡션*👇"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{insta_caption}```"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📝 워드프레스 HTML (일본어 포함)*👇"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{html_preview}```"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🟩 워드프레스"}, "url": SLACK_LINK_WORDPRESS},
                {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타"}, "url": SLACK_LINK_INSTA}
            ]
        }
    ]
    send_slack({"text": "인스타/워드프레스 알림", "blocks": blocks})

def send_slack_summary(total, kr_count, jp_count, schedule_list):
    sch_text = "\n".join([f"• {title} → {dt.strftime('%Y-%m-%d %H:%M')}" for title, dt in schedule_list]) or "내일 예약이 없어요 😂"
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
            "text": {"type": "mrkdwn", "text": "⏰ *발행 스케줄*\n" + sch_text}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "📱 *바로가기*\n원하는 채널 골라서 확인해줘 💖"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🟩 워드프레스"}, "style": "primary", "url": SLACK_LINK_WORDPRESS},
                {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타"}, "url": SLACK_LINK_INSTA},
                {"type": "button", "text": {"type": "plain_text", "text": "✍️ 네이버"}, "url": SLACK_LINK_NAVER},
            ]
        }
    ]
    send_slack({"text": "예약발행 완료", "blocks": blocks})

def send_slack_published(slot_label: str):
    emojis = {"morning": "🌅", "noon": "🌤", "evening": "🌙"}
    e = emojis.get(slot_label, "⏰")
    text = f"{e} 예약된 편의점 글이 방금 발행됐어!\n인스타/네이버에도 같이 올려주면 좋아요 💖"
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{e} 발행 완료! 인스타도 올려줘 💖", "emoji": True}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "워드프레스에는 이미 올라갔어. 지금 인스타/네이버에도 올리면 타이밍 딱이야 ✨"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🟩 워드프레스 보기"}, "url": SLACK_LINK_WORDPRESS},
                {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타 가기"}, "url": SLACK_LINK_INSTA},
            ]
        }
    ]
    send_slack({"text": text, "blocks": blocks})

# ========================================
# 🕘 내일 9/12/18시 슬롯 만들기
# ========================================
def get_tomorrow_slots_kst():
    now = datetime.now(KST)
    t = (now + timedelta(days=1)).date()
    return [
        datetime(t.year, t.month, t.day, 9, 0, tzinfo=KST),
        datetime(t.year, t.month, t.day, 12, 0, tzinfo=KST),
        datetime(t.year, t.month, t.day, 18, 0, tzinfo=KST),
    ]

# ========================================
# 🧠 글 생성 + 내일 예약 (00:00)
# ========================================
def generate_and_schedule():
    print("=" * 60)
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M')}] AI 콘텐츠 생성 시작")
    print("=" * 60)

    store_keys = list(STORES.keys())
    slots = get_tomorrow_slots_kst()

    success_count = 0
    kr_count = 0
    jp_count = 0
    schedule_list = []

    for i, store_key in enumerate(store_keys[:POSTS_PER_DAY]):
        slot_dt = slots[i]
        store_info = STORES[store_key]

        if store_info['country'] == 'kr':
            prompt = f"""
한국 편의점 블로거처럼 JSON으로 글을 만들어줘.
편의점: {store_info['name_kr']}
요구사항:
- title (한국어)
- content (HTML)
- 각 상품마다 아래 순서로 써
  1) 한국어 설명
  2) 일본어 요약 (🇯🇵 로 시작)
- 일본어는 마지막에 한 번만 쓰지 말고, 상품마다 써
- tags: ["편의점신상","{store_info['name_kr']}","コンビニ新商品"]
"""
        else:
            prompt = f"""
韓国コンビニの新商品を紹介するブログ記事をJSONで作成してください。
コンビニ: {store_info['name_jp']}
要件:
- title
- content は HTML
- 各商品について 韓国語で説明 → 直後に日本語まとめ(🇯🇵で始める) を必ず書く
- 一番下だけ日本語はダメ。各商品に日本語を入れてください。
- tags: ["コンビニ新商品","{store_info['name_jp']}","韓国コンビニ"]
"""

        post_data = generate_with_auto(prompt)
        if not post_data:
            print(f"❌ {store_info['name_kr']} 생성 실패")
            continue

        post_data = _ensure_dict(post_data)
        html_content = build_wp_html(post_data, store_info)
        post_data['content'] = html_content
        post_data['category'] = store_info.get('category', 'convenience')

        post_id = publish_to_wordpress(
            title=post_data.get('title', f"{store_info['name_kr']} 신상 리뷰"),
            content=post_data['content'],
            tags=post_data.get('tags', []),
            category=post_data['category'],
            scheduled_dt_kst=slot_dt
        )

        if post_id:
            success_count += 1
            if store_info['country'] == 'kr':
                kr_count += 1
            else:
                jp_count += 1

            schedule_list.append((post_data.get('title', store_info['name_kr']), slot_dt))

            # 슬랙: 인스타 + HTML 같이 보내기
            insta_caption = build_insta_caption(post_data, store_info, slot_dt)
            send_slack_insta_and_html(insta_caption, html_content, store_info['name_kr'], slot_dt)

        time.sleep(1)

    # 요약 슬랙
    send_slack_summary(success_count, kr_count, jp_count, schedule_list)

    print("=" * 60)
    print(f"🎉 완료! 총 {success_count}개 예약했어!")
    print("=" * 60)

# ========================================
# 🧭 main
# ========================================
def main():
    mode = os.environ.get("MODE", "generate")
    if mode == "generate":
        generate_and_schedule()
    elif mode == "remind":
        slot = os.environ.get("SLOT", "")
        send_slack_published(slot)
    else:
        # 잘못 들어오면 기본은 generate
        generate_and_schedule()

if __name__ == "__main__":
    main()
