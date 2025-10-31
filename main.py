import os
import json
import traceback
import requests
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.compat import xmlrpc_client

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

# 슬랙 버튼용 링크 (없으면 기본값)
SLACK_LINK_WORDPRESS = os.environ.get('SLACK_LINK_WORDPRESS', 'https://your-wordpress-site.com')
SLACK_LINK_INSTA     = os.environ.get('SLACK_LINK_INSTA', 'https://instagram.com/')
SLACK_LINK_NAVER     = os.environ.get('SLACK_LINK_NAVER', 'https://blog.naver.com/')

# 하루 발행(예약) 개수
POSTS_PER_DAY = int(os.environ.get('POSTS_PER_DAY', '3'))

# 한국 시간대
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
# 공통: 응답 보정 유틸
# ========================================
def _ensure_dict(result):
    """AI 응답이 리스트일 때 첫 번째 요소를 꺼내 딕셔너리로 맞춰준다."""
    if isinstance(result, list):
        return result[0] if result else None
    return result

# ========================================
# HTML 템플릿 만들기
# ========================================
def build_wp_html(ai_result: dict, store_info: dict) -> str:
    """
    공주님이 준 HTML 레이아웃으로 워드프레스 본문 생성.
    ai_result 안에 content가 있어도 이 템플릿 안에 녹여서 넣는다.
    """
    store_name = store_info.get('name_kr', '편의점')
    # AI가 준 값이 없을 때 대비
    title_kor = ai_result.get('title') or f"{store_name} 신상 제품 리뷰!"
    main_content = ai_result.get('content') or ""  # AI가 준 본문 (있으면 중간에 붙임)

    # 해시태그 기본
    tags_joined = "#편의점신상 #コンビニ新商品 #"+store_name.replace(" ", "")+" #편스타그램 #コンビニグルメ"

    html = f"""
<div style="max-width: 800px;margin: 0 auto;font-family: 'Malgun Gothic', sans-serif">

  <!-- 헤더 -->
  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);padding: 40px 30px;border-radius: 20px;margin-bottom: 40px;text-align: center;box-shadow: 0 10px 30px rgba(0,0,0,0.2)">
    <h1 style="color: white;font-size: 28px;margin: 0 0 15px 0;font-weight: bold">🛒 {title_kor}</h1>
    <p style="color: rgba(255,255,255,0.9);font-size: 16px;margin: 0">コンビニ新商品レビュー 🇰🇷🇯🇵</p>
  </div>

  <!-- 인사말 -->
  <div style="background: #f8f9ff;padding: 30px;border-radius: 15px;margin-bottom: 40px;border-left: 5px solid #667eea">
    <p style="font-size: 17px;line-height: 1.8;margin: 0;color: #222;font-weight: 500">
      <strong style="font-size: 19px">안녕하세요, 편스타그램 친구들!</strong> 오늘은 {store_name}에서 새롭게 나온 신상 제품들을 소개해드릴게요! 🎉
      요즘 간편하게 즐길 수 있는 맛있는 간식들이 많아서 고르는 재미가 있더라구요 😋
    </p>
  </div>

  <!-- AI 본문 영역 -->
  <div style="background: white;padding: 25px 20px;border-radius: 15px;margin-bottom: 35px;box-shadow: 0 4px 16px rgba(0,0,0,0.03);border: 1px solid #f1f1f1">
    {main_content}
  </div>

  <!-- 해시태그 -->
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
# AUTO 모드
# ========================================
def generate_with_auto(prompt):
    """AUTO 모드: Gemini → Groq → OpenAI 순서로 시도"""
    print("  🤖 AUTO 모드: Gemini → Groq → OpenAI")

    # 1순위: Gemini
    result = call_gemini(prompt)
    result = _ensure_dict(result)
    if result:
        return result

    # 2순위: Groq
    result = call_groq(prompt)
    result = _ensure_dict(result)
    if result:
        return result

    # 3순위: OpenAI
    result = call_openai(prompt)
    result = _ensure_dict(result)
    if result:
        return result

    return None

# ========================================
# Gemini 호출
# ========================================
def call_gemini(prompt):
    if not GEMINI_API_KEY:
        print("  ⚠️ Gemini API 키 없음")
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
        result_text = resp.json()['candidates'][0]['content']['parts'][0]['text']
        result = json.loads(result_text)
        print("  ✅ Gemini 성공!")
        return result
    except Exception as e:
        print(f"  ⚠️ Gemini 실패: {str(e)[:120]}")
        return None

# ========================================
# Groq 호출
# ========================================
def call_groq(prompt):
    if not GROQ_API_KEY:
        print("  ⚠️ Groq API 키 없음")
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
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다. JSON 형식으로만 답변하세요."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=data, timeout=120)
        resp.raise_for_status()
        result = json.loads(resp.json()['choices'][0]['message']['content'])
        print("  ✅ Groq 성공!")
        return result
    except Exception as e:
        print(f"  ⚠️ Groq 실패: {str(e)[:120]}")
        return None

# ========================================
# OpenAI 호출
# ========================================
def call_openai(prompt):
    if not OPENAI_API_KEY:
        print("  ⚠️ OpenAI API 키 없음")
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
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다. JSON 형식으로만 답변하세요."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=data, timeout=120)
        resp.raise_for_status()
        result = json.loads(resp.json()['choices'][0]['message']['content'])
        print("  ✅ OpenAI 성공!")
        return result
    except Exception as e:
        print(f"  ⚠️ OpenAI 실패: {str(e)[:120]}")
        return None

# ========================================
# 텍스트 버전 만들기 (필요시)
# ========================================
def create_text_version(html_content: str) -> str:
    if not html_content:
        return ""
    return (html_content
            .replace("<br>", "\n")
            .replace("<br/>", "\n")
            .replace("<p>", "")
            .replace("</p>", "\n"))

# ========================================
# 실제 글 생성
# ========================================
def generate_blog_post(store_key):
    try:
        store_info = STORES[store_key]
        country = store_info['country']
        name_kr = store_info['name_kr']
        name_jp = store_info['name_jp']

        print(f"  📝 {name_kr} ({'🇯🇵' if country=='jp' else '🇰🇷'}) 블로그 글 생성 중...")

        # 프롬프트
        if country == 'kr':
            prompt = f"""
당신은 한국 편의점 신상 리뷰를 쓰는 블로거입니다.
{store_info['name_kr']} 신상품 2~3개를 소개하는 JSON을 만들어 주세요.

요구사항:
- title: 한국어로 30자 이내, 이모지 포함
- content: HTML 형식 (h2, div, p 섞어서), 제품명/가격/맛/꿀조합/일본어요약 포함
- tags: ["편의점신상","{store_info['name_kr']}","신상품","コンビニ新商品"]

JSON 예시:
{"{"}"title":"세븐일레븐 겨울 간식 모음","content":"<p>...</p>","tags":["편의점신상","세븐일레븐","コンビニ新商品"]{"}"}"""
        else:
            prompt = f"""
あなたは韓国のコンビニ新商品を紹介する韓国人ブロガーです。
{store_info['name_jp']} の新商品を2〜3つ紹介するJSONを作成してください。

要件:
- title: 韓国語または日本語、絵文字OK
- content: HTML形式で、商品名・価格・味のポイント・おすすめの食べ方・日本語まとめを含める
- tags: ["コンビニ新商品","{store_info['name_jp']}","韓国コンビニ"]

JSON例:
{"{"}"title":"ローソン冬の新商品まとめ","content":"<p>...</p>","tags":["コンビニ新商品","ローソン"]{"}"}"""
        result = generate_with_auto(prompt)
        if not result:
            return None

        if isinstance(result, list):
            if not result:
                return None
            result = result[0]

        # 템플릿으로 감싸기
        html_content = build_wp_html(result, store_info)

        # 최종 객체
        result['content'] = html_content
        result['category'] = store_info['category']
        result['country'] = country
        result['store_key'] = store_key
        result['text_version'] = create_text_version(html_content)

        print(f"  ✅ 생성 완료: {result.get('title','(제목없음)')[:30]}...")
        return result

    except Exception as e:
        print(f"  ❌ 글 생성 실패: {str(e)[:120]}")
        traceback.print_exc()
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
        print(f"  ✅ 워드프레스 발행 성공! (post_id={post_id})")
        return post_id
    except Exception as e:
        print(f"  ❌ 워드프레스 발행 실패: {str(e)[:120]}")
        return None

# ========================================
# 슬랙 알림 (블록)
# ========================================
def send_slack_summary(total, kr_count, jp_count):
    if not SLACK_WEBHOOK_URL:
        return
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🎉 한일 편의점 예약발행 완료!",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📝 총 {total}개 글 자동 예약*\n🇰🇷 한국: {kr_count}개\n🇯🇵 일본: {jp_count}개"
            }
        },
        { "type": "divider" },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⏰ 예약 시간에 자동 발행됩니다!\n\n📱 *바로가기*\n가고 싶은 채널을 선택해 주세요 💖"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": { "type": "plain_text", "text": "🟩 워드프레스" },
                    "style": "primary",
                    "url": SLACK_LINK_WORDPRESS
                },
                {
                    "type": "button",
                    "text": { "type": "plain_text", "text": "📷 인스타" },
                    "url": SLACK_LINK_INSTA
                },
                {
                    "type": "button",
                    "text": { "type": "plain_text", "text": "✍️ 네이버" },
                    "url": SLACK_LINK_NAVER
                }
            ]
        }
    ]
    payload = {
        "text": f"총 {total}개 글 예약발행 완료",
        "blocks": blocks
    }
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass

# ========================================
# 예약 시간 계산
# ========================================
def get_scheduled_times_for_today(count: int):
    times = []
    now = datetime.now(KST).replace(minute=0, second=0, microsecond=0)
    for i in range(count):
        slot_time = now + timedelta(hours=i+1)
        times.append(slot_time)
    return times

# ========================================
# 전체 생성 → 예약발행
# ========================================
def generate_and_schedule():
    print("=" * 60)
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M')}] AI 콘텐츠 생성 시작...")
    print("=" * 60)

    store_keys = list(STORES.keys())
    scheduled_times = get_scheduled_times_for_today(POSTS_PER_DAY)

    success_count = 0
    kr_count = 0
    jp_count = 0

    # store 개수가 POSTS_PER_DAY보다 많으면 앞에서부터 채움
    for i, store_key in enumerate(store_keys[:POSTS_PER_DAY]):
        scheduled_dt = scheduled_times[i] if i < len(scheduled_times) else None

        store_info = STORES[store_key]

        print("-" * 60)
        print(f"[{i+1}/{POSTS_PER_DAY}] {store_info['name_kr']} ({'🇯🇵' if store_info['country']=='jp' else '🇰🇷'}) @ {scheduled_dt.strftime('%Y-%m-%d %H:%M') if scheduled_dt else '즉시'}")

        post_data = generate_blog_post(store_key)
        if not post_data:
            print(f"❌ [{i+1}] 콘텐츠 생성 실패!")
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

        time.sleep(2)

    print("=" * 60)
    print(f"🎉 완료! 총 {success_count}개 글 발행(예약) 성공!")
    print("=" * 60)

    # 슬랙 요약 보내기
    send_slack_summary(success_count, kr_count, jp_count)

# ========================================
# 메인
# ========================================
def main():
    mode = os.environ.get('MODE', 'generate')
    if mode == 'notify':
        # 나중에 발행 알림용
        send_slack_summary(0, 0, 0)
    else:
        generate_and_schedule()

if __name__ == "__main__":
    main()
