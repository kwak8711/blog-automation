import os
import json
import traceback
import requests
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

# ========================================
# 🧁 환경변수
# ========================================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
GROQ_API_KEY         = os.environ.get('GROQ_API_KEY')
GEMINI_API_KEY       = os.environ.get('GEMINI_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')

WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')

# 슬랙 버튼용 링크
SLACK_LINK_WORDPRESS = os.environ.get('SLACK_LINK_WORDPRESS', 'https://your-wordpress-site.com')
SLACK_LINK_INSTA     = os.environ.get('SLACK_LINK_INSTA', 'https://instagram.com/')
SLACK_LINK_NAVER     = os.environ.get('SLACK_LINK_NAVER', 'https://blog.naver.com/')

# 하루 만들 글 수
POSTS_PER_DAY = 3

# 한국 시간
KST = ZoneInfo("Asia/Seoul")

# ========================================
# 🏪 편의점 매핑
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
# 🍬 공통 유틸
# ========================================
def _ensure_dict(result):
    if isinstance(result, list):
        return result[0] if result else None
    return result

# ========================================
# 🧁 워드프레스 HTML 템플릿 (귀염 ver.)
# ========================================
def build_wp_html(ai_result: dict, store_info: dict) -> str:
    store_name = store_info.get('name_kr', '편의점')
    title_kor = ai_result.get('title') or f"{store_name} 신상 제품 리뷰!"
    main_content = ai_result.get('content') or "<p>오늘 나온 신상들이에요 💖</p>"

    hashtags = (
        "#편의점신상 #コンビニ新商品 "
        f"#{store_name} "
        "#편스타그램 #コンビニグルメ #오늘뭐먹지 #kconbini"
    )

    html = f"""
<div style="max-width: 820px;margin: 0 auto;font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif">

  <!-- 상단 히어로 -->
  <div style="background: radial-gradient(circle at top, #667eea 0%, #764ba2 45%, #ffffff 100%);padding: 42px 34px 34px;border-radius: 26px;margin-bottom: 36px;text-align: center;box-shadow: 0 12px 36px rgba(103,114,229,0.25)">
    <p style="font-size: 13px;letter-spacing: 4px;color: rgba(255,255,255,0.7);margin: 0 0 10px 0;">K-CONBINI DAILY PICK</p>
    <h1 style="color: #fff;font-size: 29px;margin: 0 0 10px 0;font-weight: 700">🛒 {title_kor}</h1>
    <p style="color: rgba(255,255,255,0.88);font-size: 16px;margin: 0">コンビニ新商品レビュー 🇰🇷🇯🇵 | {store_name}</p>
  </div>

  <!-- 인사말 -->
  <div style="background: #fff7fb;padding: 26px 24px;border-radius: 18px;margin-bottom: 28px;border: 1.4px solid rgba(252,95,168,0.25)">
    <p style="font-size: 15.5px;line-height: 1.7;margin: 0;color: #222">
      <strong style="font-size: 17px">안녕 편스타그램 친구들 💖</strong><br>
      오늘은 <strong>{store_name}</strong>에서 꼭 먹어봐야 할 신상만 골라서 가져왔어!
      아래에 한국어 설명이랑 일본어 요약 같이 넣어놨으니까, 한국/일본 팔로워한테 둘 다 보여줄 수 있어 ✨
    </p>
  </div>

  <!-- AI가 생성한 본문 -->
  <div style="background: #ffffff;padding: 26px 24px;border-radius: 18px;margin-bottom: 32px;box-shadow: 0 6px 18px rgba(0,0,0,0.03);border: 1px solid #f0f1ff">
    {main_content}
  </div>

  <!-- 해시태그 -->
  <div style="background: linear-gradient(120deg, #f8f9ff 0%, #fff1f4 100%);padding: 24px 20px;border-radius: 16px;text-align: center;border: 1px dashed rgba(118,75,162,0.3)">
    <p style="margin: 0 0 10px 0;font-weight: 600;color: #6a4fbf;">📱 해시태그 / ハッシュタグ</p>
    <p style="margin: 0;font-size: 14.5px;line-height: 2;color: #555">{hashtags}</p>
  </div>

</div>
"""
    return html

# ========================================
# 📱 인스타 캡션 만들기 (귀염 ver.)
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
        "🇰🇷 한국어도 OK / 🇯🇵 일본어도 OK",
        "",
        " ".join(hashtags)
    ]
    return "\n".join(cap)

# ========================================
# 🤖 AI 호출 AUTO
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
                {"role": "system", "content": "당신은 한국/일본 편의점 신상 블로거입니다. JSON으로만 답하세요."},
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
                {"role": "system", "content": "당신은 한국/일본 편의점 신상 블로거입니다. JSON으로만 답하세요."},
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
# 📨 슬랙 공통
# ========================================
def send_slack(payload: dict):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass

# 개별 인스타 업로드 안내
def send_slack_insta_reminder(caption: str, store_name: str, scheduled_dt: datetime):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📷 인스타 올릴 시간 미리 알려줄게 💖", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{store_name}* 글이 *{scheduled_dt.strftime('%Y-%m-%d %H:%M')}* 에 올라가요.\n지금 이 캡션 복붙해서 인스타에 올리면 끝이야 😎"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{caption}```"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🟩 워드프레스"}, "url": SLACK_LINK_WORDPRESS},
                {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타"}, "url": SLACK_LINK_INSTA},
            ]
        }
    ]
    send_slack({"text": "인스타 업로드 알림", "blocks": blocks})

# 전체 요약
def send_slack_summary(total, kr_count, jp_count, schedule_list):
    sch_text = "\n".join([f"• {title} → {dt.strftime('%Y-%m-%d %H:%M')}" for title, dt in schedule_list]) or "내일 예약이 없어요 😂"
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🎉 한일 편의점 예약발행 완료!", "emoji": True}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*📝 총 {total}개 글 자동 예약*\n🇰🇷 한국: {kr_count}개\n🇯🇵 일본: {jp_count}개"}
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": "⏰ *발행 스케줄*\n" + sch_text}
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": "📱 *바로가기*\n원하는 채널 골라서 확인해줘 💖"}},
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

# 예약발행 된 시각에 보내는 “발행됨!” 알림
def send_slack_published(slot_label: str):
    emojis = {
        "morning": "🌅",
        "noon": "🌤",
        "evening": "🌙"
    }
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
# 🧠 글 생성 + 내일 예약 (00:00용)
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

        # 1) AI 글 생성
        if store_info['country'] == 'kr':
            prompt = f"""
한국 편의점 블로거처럼 JSON으로 글을 만들어줘.
편의점: {store_info['name_kr']}
요구: 제목(title), 본문(content=HTML), 태그(tags=[...])
본문에는 제품 2~3개, 가격, 맛 포인트, 꿀조합, 일본어 요약 포함.
"""
        else:
            prompt = f"""
韓国コンビニの新商品を紹介するブロガーとしてJSONを作成してください。
コンビニ: {store_info['name_jp']}
"title","content","tags" を含めてください。
"""

        post_data = generate_with_auto(prompt)
        if not post_data:
            print(f"❌ {store_info['name_kr']} 생성 실패")
            continue

        post_data = _ensure_dict(post_data)
        html_content = build_wp_html(post_data, store_info)
        post_data['content'] = html_content
        post_data['category'] = store_info['category']

        # 2) 워드프레스 예약
        post_id = publish_to_wordpress(
            title=post_data.get('title', f"{store_info['name_kr']} 신상 리뷰"),
            content=post_data['content'],
            tags=post_data.get('tags', []),
            category=post_data.get('category', 'convenience'),
            scheduled_dt_kst=slot_dt
        )

        if post_id:
            success_count += 1
            if store_info['country'] == 'kr':
                kr_count += 1
            else:
                jp_count += 1
            schedule_list.append((post_data.get('title', store_info['name_kr']), slot_dt))

            # 3) 인스타 복붙 캡션 슬랙으로 보내기
            insta_caption = build_insta_caption(post_data, store_info, slot_dt)
            send_slack_insta_reminder(insta_caption, store_info['name_kr'], slot_dt)

        time.sleep(1)

    # 4) 마지막 요약
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
        # 00:00에 돌릴 것
        generate_and_schedule()
    elif mode == "remind":
        # 09:00 / 12:00 / 18:00 에 돌릴 것
        slot = os.environ.get("SLOT", "")  # morning / noon / evening
        send_slack_published(slot)
    else:
        # 기본은 generate
        generate_and_schedule()


if __name__ == "__main__":
    main()
