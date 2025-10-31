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

# 예약 발행 갯수
POSTS_PER_DAY = int(os.environ.get('POSTS_PER_DAY', '3'))

# 한국 시간대
KST = ZoneInfo("Asia/Seoul")

# ========================================
# 편의점 매핑 (예시)
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
    "lawson": {
        "name_kr": "로손",
        "name_jp": "ローソン",
        "country": "jp",
        "category": "convenience"
    },
    "familymart": {
        "name_kr": "패밀리마트",
        "name_jp": "ファミリーマート",
        "country": "jp",
        "category": "convenience"
    }
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
    """Gemini API 호출 (1순위 - 무료, RPM 15)"""
    if not GEMINI_API_KEY:
        print("  ⚠️ Gemini API 키 없음")
        return None

    try:
        print("  🟢 Gemini 시도 중...")
        # 네 실제 레포에서는 전체 URL이 있을 거야. 여긴 가려진 부분이라 그대로 둘게.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"

        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            }
        }

        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()

        # Gemini는 우리가 "application/json"을 달라고 하면 text 안에 JSON을 문자열로 넣어줘
        result_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        result = json.loads(result_text)

        print("  ✅ Gemini 성공!")
        return result

    except Exception as e:
        print(f"  ⚠️ Gemini 실패: {str(e)[:100]}")
        return None

# ========================================
# Groq 호출
# ========================================
def call_groq(prompt):
    """Groq API 호출 (2순위 - 무료, RPM 30, 초고속!)"""
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

        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()

        result = json.loads(response.json()['choices'][0]['message']['content'])

        print("  ✅ Groq 성공!")
        return result

    except Exception as e:
        print(f"  ⚠️ Groq 실패: {str(e)[:100]}")
        return None

# ========================================
# OpenAI 호출
# ========================================
def call_openai(prompt):
    """OpenAI API 호출 (3순위 - 유료)"""
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

        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()

        result = json.loads(response.json()['choices'][0]['message']['content'])

        print("  ✅ OpenAI 성공!")
        return result

    except Exception as e:
        print(f"  ⚠️ OpenAI 실패: {str(e)[:100]}")
        return None

# ========================================
# 텍스트 버전 만들기
# ========================================
def create_text_version(html_content: str) -> str:
    """HTML 본문을 텍스트 버전으로 단순화"""
    if not html_content:
        return ""
    # 아주 단순한 버전
    return html_content.replace("<br>", "\n").replace("<br/>", "\n").replace("<p>", "").replace("</p>", "\n")

# ========================================
# 실제 글 생성
# ========================================
def generate_blog_post(store_key):
    """AI로 블로그 글 생성"""
    try:
        store_info = STORES[store_key]
        country = store_info['country']
        name_kr = store_info['name_kr']
        name_jp = store_info['name_jp']

        print(f"  📝 {name_kr} {'🇯🇵' if country == 'jp' else '🇰🇷'} 블로그 글 생성 중...")

        # 프롬프트 생성
        if country == 'kr':
            prompt = f"""당신은 편의점 블로거입니다. {name_kr} 신상 제품 2-3개를 소개하는 블로그 글을 작성하세요.

요구사항:
- 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
- 본문: HTML 형식, 1200-1800자
- 각 제품: 제품명, 가격(원), 맛 후기, 꿀조합, 별점, 일본어 요약
- 친근한 MZ 스타일

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["편의점신상","{name_kr}","신상품"]}}
"""
        else:
            prompt = f"""あなたはコンビニ新商品を紹介する韓国人ブロガーです。{name_jp} の新商品を2〜3つブログ形式で紹介してください。

要件:
- タイトル：クリックしたくなる題名（絵文字OK、30文字以内、韓国語でもOK）
- 本文：HTML形式、1200〜1800文字
- 各商品：商品名、価格(円), 味の感想, おすすめの食べ方, 韓国人向けポイント
- 全体をフレンドリーに

JSON形式:
{{"title": "タイトル", "content": "HTML本文", "tags": ["コンビニ","{name_jp}","新商品"]}}
"""

        # AUTO 모드로 생성
        result = generate_with_auto(prompt)

        if not result:
            return None

        # 혹시 리스트로 온 경우를 대비해 한 번 더 가드
        if isinstance(result, list):
            if not result:
                return None
            result = result[0]

        # 추가 정보
        result['category'] = store_info['category']
        result['country'] = country
        result['store_key'] = store_key
        result['text_version'] = create_text_version(result.get('content', ''))

        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result

    except Exception as e:
        print(f"  ❌ 글 생성 실패: {str(e)[:120]}")
        traceback.print_exc()
        return None

# ========================================
# 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags, category, scheduled_dt_kst=None):
    """워드프레스 발행/예약발행"""
    try:
        print(f"  📤 발행 준비: {title[:30]}...")

        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)

        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {
            'post_tag': tags,
            'category': [category]
        }

        if scheduled_dt_kst:
            # 워드프레스는 naive datetime (서버 시간) 기준일 수 있음
            post.date = scheduled_dt_kst

        post_id = wp.call(NewPost(post))
        print(f"  ✅ 발행 성공! (post_id={post_id})")
        return post_id

    except Exception as e:
        print(f"  ❌ 워드프레스 발행 실패: {str(e)[:120]}")
        return None

# ========================================
# 슬랙 알림
# ========================================
def send_slack_message(text):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        payload = {"text": text}
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass

# ========================================
# 예약 시간 계산
# ========================================
def get_scheduled_times_for_today(count: int):
    """오늘 날짜 기준으로 n개 시간 만들어주기"""
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

    for i, store_key in enumerate(store_keys[:POSTS_PER_DAY]):
        scheduled_dt = scheduled_times[i] if i < len(scheduled_times) else None

        print("-" * 60)
        print(f"[{i+1}/{len(store_keys)}] {STORES[store_key]['name_kr']} {'🇯🇵' if STORES[store_key]['country']=='jp' else '🇰🇷'} @ {scheduled_dt.strftime('%Y-%m-%d %H:%M') if scheduled_dt else '즉시'}")

        post_data = generate_blog_post(store_key)

        if not post_data:
            print(f"❌ [ {i+1} ] 콘텐츠 생성 실패!")
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
            send_slack_message(f"✅ {post_data['title']} 발행(예약) 완료!")
        else:
            send_slack_message(f"❌ {post_data['title']} 발행 실패")

        time.sleep(2)

    print("=" * 60)
    print(f"🎉 완료! 총 {success_count}개 글 발행 성공!")
    print("=" * 60)

# ========================================
# 발행 알림 모드
# ========================================
def send_publish_notification():
    print("=" * 60)
    print(f"🔔 발행 알림: {datetime.now(KST)}")
    print("=" * 60)
    # 여기는 실제 워드프레스 발행 내역을 읽어오도록 나중에 확장

# ========================================
# 메인
# ========================================
def main():
    mode = os.environ.get('MODE', 'generate')

    if mode == 'notify':
        send_publish_notification()
    else:
        generate_and_schedule()

if __name__ == "__main__":
    main()
