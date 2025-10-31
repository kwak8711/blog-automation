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
# 환경변수
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
# 편의점 매핑
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
# 공통 유틸
# ========================================
def _ensure_dict(result):
    if isinstance(result, list):
        return result[0] if result else None
    return result


# ========================================
# HTML 템플릿
# ========================================
def build_wp_html(ai_result: dict, store_info: dict) -> str:
    store_name = store_info.get('name_kr', '편의점')
    title_kor = ai_result.get('title') or f"{store_name} 신상 제품 리뷰!"
    main_content = ai_result.get('content') or ""

    # 해시태그는 인스타 복붙용이지만, 워드프레스에도 보여주자
    tags_joined = "#편의점신상 #コンビニ新商品 #" + store_name.replace(" ", "") + " #편스타그램 #コンビニグルメ"

    html = f"""
<div style="max-width: 800px;margin: 0 auto;font-family: 'Malgun Gothic', sans-serif">

  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);padding: 40px 30px;border-radius: 20px;margin-bottom: 40px;text-align: center;box-shadow: 0 10px 30px rgba(0,0,0,0.2)">
    <h1 style="color: white;font-size: 28px;margin: 0 0 15px 0;font-weight: bold">🛒 {title_kor}</h1>
    <p style="color: rgba(255,255,255,0.9);font-size: 16px;margin: 0">コンビニ新商品レビュー 🇰🇷🇯🇵</p>
  </div>

  <div style="background: #f8f9ff;padding: 30px;border-radius: 15px;margin-bottom: 40px;border-left: 5px solid #667eea">
    <p style="font-size: 17px;line-height: 1.8;margin: 0;color: #222;font-weight: 500">
      <strong style="font-size: 19px">안녕하세요, 편스타그램 친구들!</strong> 오늘은 {store_name}에서 새롭게 나온 신상 제품들을 소개해드릴게요! 🎉
      요즘 간편하게 즐길 수 있는 맛있는 간식들이 많아서 고르는 재미가 있더라구요 😋
    </p>
  </div>

  <div style="background: white;padding: 25px 20px;border-radius: 15px;margin-bottom: 35px;box-shadow: 0 4px 16px rgba(0,0,0,0.03);border: 1px solid #f1f1f1">
    {main_content}
  </div>

  <hr style="border: none;border-top: 3px solid #667eea;margin: 50px 0 30px 0">
  <div style="background: linear-gradient(to right, #f8f9ff, #fff5f8);padding: 30px;border-radius: 15px;text-align: center">
    <p style="margin: 0 0 15px 0;font-size: 16px;color: #667eea;font-weight: bold">📱 해시태그 / ハッシュタグ</p>
    <p style="margin: 0;font-size: 15px;color: #667eea;line-height: 2">
      {tags_joined}
    </p>
  </div>

</div>
"""
    return html


# ========================================
# 인스타 캡션 만들기
# ========================================
def build_insta_caption(ai_result: dict, store_info: dict, scheduled_time_kst: datetime) -> str:
    store_name = store_info.get('name_kr', '편의점')
    title = ai_result.get('title') or f"{store_name} 신상 리뷰!"
    # 인스타에서 바로 보이게 최대한 짧게
    base = []
    base.append(f"🛒 {title}")
    base.append(f"{store_name} 신상 모아봤어 💛")
    base.append("")
    base.append("🇰🇷 + 🇯🇵 둘 다 올릴 수 있는 버전이야!")
    base.append(f"⏰ 발행시간: {scheduled_time_kst.strftime('%Y-%m-%d %H:%M')}")
    base.append("")
    # 해시태그
    hashtags = [
        "#편의점신상", "#コンビニ新商品",
        f"#{store_name}",
        "#편스타그램", "#コンビニグルメ",
        "#신상품", "#오늘은이거", "#kconbini"
    ]
    base.append(" ".join(hashtags))
    return "\n".join(base)


# ========================================
# AI 호출 (AUTO)
# ========================================
def generate_with_auto(prompt):
    print("  🤖 AUTO 모드: Gemini → Groq → OpenAI")

    # 1. Gemini
    res = call_gemini(prompt)
    res = _ensure_dict(res)
    if res:
        return res

    # 2. Groq
    res = call_groq(prompt)
    res = _ensure_dict(res)
    if res:
        return res

    # 3. OpenAI
    res = call_openai(prompt)
    res = _ensure_dict(res)
    if res:
        return res

    return None


def call_gemini(prompt):
    if not GEMINI_API_KEY:
        return None
    try:
        print("  🟢 Gemini 시도 중...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            }
        }
        resp = requests.post(url, json=data, timeout=120)
        resp.raise_for_status()
        text = resp.json()['candidates'][0]['content']['parts'][0]['text']
        result = json.loads(text)
        print("  ✅ Gemini 성공")
        return result
    except Exception as e:
        print(f"  ⚠️ Gemini 실패: {str(e)[:120]}")
        return None


def call_groq(prompt):
    if not GROQ_API_KEY:
        return None
    try:
        print("  🔵 Groq 시도 중...")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다. JSON으로만 답하세요."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=data, timeout=120)
        resp.raise_for_status()
        result = json.loads(resp.json()['choices'][0]['message']['content'])
        print("  ✅ Groq 성공")
        return result
    except Exception as e:
        print(f"  ⚠️ Groq 실패: {str(e)[:120]}")
        return None


def call_openai(prompt):
    if not OPENAI_API_KEY:
        return None
    try:
        print("  🟣 OpenAI 시도 중...")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다. JSON으로만 답하세요."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=data, timeout=120)
        resp.raise_for_status()
        result = json.loads(resp.json()['choices'][0]['message']['content'])
        print("  ✅ OpenAI 성공")
        return result
    except Exception as e:
        print(f"  ⚠️ OpenAI 실패: {str(e)[:120]}")
        return None


# ========================================
# 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags, category, scheduled_dt_kst=None):
    try:
        print(f"  📤 워드프레스 발행 준비: {title[:30]}...")
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
        print(f"  ✅ 워드프레스 발행 성공! ({post_id})")
        return post_id
    except Exception as e:
        print(f"  ❌ 워드프레스 발행 실패: {str(e)[:120]}")
        return None


# ========================================
# 슬랙 보내기
# ========================================
def send_slack(payload: dict):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass


def send_slack_insta_reminder(caption: str, store_name: str, scheduled_dt: datetime):
    """각 글마다: 인스타에 이거 올려! 하고 캡션 던져주는 메시지"""
    text = f"📷 *인스타 업로드 알림*\n{store_name} 글이 {scheduled_dt.strftime('%Y-%m-%d %H:%M')} 에 예약되어 있어요.\n아래 캡션 복사해서 인스타에 올려줘 💖"
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📷 인스타 업로드 알림", "emoji": True}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*{store_name}* 글이 *{scheduled_dt.strftime('%Y-%m-%d %H:%M')}* 에 발행돼요.\n👇 아래 캡션 복사해서 인스타에 올려줘요 💖"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{caption}```"}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🟩 워드프레스"},
                    "url": SLACK_LINK_WORDPRESS
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📷 인스타"},
                    "url": SLACK_LINK_INSTA
                }
            ]
        }
    ]
    send_slack({"text": text, "blocks": blocks})


def send_slack_summary(total, kr_count, jp_count, schedule_list):
    """마지막 요약"""
    if not SLACK_WEBHOOK_URL:
        return
    schedule_txt = "\n".join([f"- {title} → {dt.strftime('%Y-%m-%d %H:%M')}" for (title, dt) in schedule_list])
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
                     "text": "⏰ 내일 발행 시간은 아래와 같아요.\n" + schedule_txt}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": "📱 *바로가기*\n가고 싶은 채널을 선택해 주세요 💖"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "🟩 워드프레스"}, "style": "primary",
                 "url": SLACK_LINK_WORDPRESS},
                {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타"}, "url": SLACK_LINK_INSTA},
                {"type": "button", "text": {"type": "plain_text", "text": "✍️ 네이버"}, "url": SLACK_LINK_NAVER},
            ]
        }
    ]
    send_slack({"text": "편의점 예약발행 완료", "blocks": blocks})


# ========================================
# 실제 글 생성
# ========================================
def generate_blog_post(store_key):
    try:
        store_info = STORES[store_key]
        country = store_info['country']
        name_kr = store_info['name_kr']
        name_jp = store_info['name_jp']

        print(f"  📝 {name_kr} ({'🇯🇵' if country == 'jp' else '🇰🇷'}) 블로그 글 생성 중...")

        if country == 'kr':
            prompt = f"""
당신은 한국 편의점 신상 리뷰 블로거입니다.
{store_info['name_kr']} 신상품 2~3개를 소개하는 블로그 글을 JSON으로 만들어주세요.
"title","content","tags" 필드가 있어야 합니다.
content는 HTML로, 한국어 + 일본어 요약이 들어가면 좋아요.
"""
        else:
            prompt = f"""
あなたは韓国コンビニの新商品を紹介するブロガーです。
{store_info['name_jp']} の新商品を2〜3つ紹介する記事を JSON で作成してください。
"title","content","tags" を含めてください。
"""

        result = generate_with_auto(prompt)
        if not result:
            return None

        if isinstance(result, list):
            if not result:
                return None
            result = result[0]

        # 워드프레스용 HTML로 감싸기
        html_content = build_wp_html(result, store_info)
        result['content'] = html_content
        result['category'] = store_info['category']
        result['country'] = country
        result['store_info'] = store_info

        return result
    except Exception as e:
        print(f"  ❌ 글 생성 실패: {str(e)[:120]}")
        traceback.print_exc()
        return None


# ========================================
# 내일 9/12/18시 예약 시간 만들기
# ========================================
def get_tomorrow_slots_kst():
    now = datetime.now(KST)
    tomorrow = (now + timedelta(days=1)).date()
    slots = [
        datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0, tzinfo=KST),
        datetime(tomorrow.year, tomorrow.month, tomorrow.day, 12, 0, tzinfo=KST),
        datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0, tzinfo=KST),
    ]
    return slots


# ========================================
# 메인 생성/발행
# ========================================
def generate_and_schedule():
    print("=" * 60)
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M')}] AI 콘텐츠 생성 시작")
    print("=" * 60)

    store_keys = list(STORES.keys())
    slots = get_tomorrow_slots_kst()  # 내일 9/12/18
    success_count = 0
    kr_count = 0
    jp_count = 0
    schedule_list = []

    # 앞에서부터 3개만
    for i, store_key in enumerate(store_keys[:POSTS_PER_DAY]):
        scheduled_dt = slots[i]  # 0: 9시, 1: 12시, 2: 18시
        post_data = generate_blog_post(store_key)
        if not post_data:
            print(f"❌ [{i+1}] {store_key} 생성 실패")
            continue

        post_id = publish_to_wordpress(
            title=post_data['title'],
            content=post_data['content'],
            tags=post_data.get('tags', []),
            category=post_data.get('category', 'convenience'),
            scheduled_dt_kst=scheduled_dt
        )

        if post_id:
            success_count += 1
            if post_data['country'] == 'kr':
                kr_count += 1
            else:
                jp_count += 1

            schedule_list.append((post_data['title'], scheduled_dt))

            # ✅ 인스타 복붙용 캡션 슬랙으로 개별 전송
            insta_caption = build_insta_caption(post_data, post_data['store_info'], scheduled_dt)
            send_slack_insta_reminder(insta_caption, post_data['store_info']['name_kr'], scheduled_dt)

        time.sleep(1)

    # ✅ 마지막 전체 요약 슬랙
    send_slack_summary(success_count, kr_count, jp_count, schedule_list)

    print("=" * 60)
    print(f"🎉 완료! 총 {success_count}개 예약!")
    print("=" * 60)


# ========================================
# main
# ========================================
def main():
    # 00:00에 이 파일이 돌도록 cron을 걸어두면
    # 내일 9/12/18시 예약이 자동으로 생긴다.
    generate_and_schedule()


if __name__ == "__main__":
    main()
