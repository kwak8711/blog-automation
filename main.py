import os
import json
import traceback
import requests
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
import time

# =========================
# 설정 (환경변수)
# =========================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
GEMINI_API_KEY       = os.environ.get('GEMINI_API_KEY')
GROQ_API_KEY         = os.environ.get('GROQ_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')

# AI 선택 (AUTO = Gemini→Groq→OpenAI 순)
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'AUTO')

# 버튼 링크용
INSTAGRAM_PROFILE_URL = os.environ.get('INSTAGRAM_PROFILE_URL', 'https://instagram.com/')
NAVER_BLOG_URL        = os.environ.get('NAVER_BLOG_URL', 'https://blog.naver.com/')

POSTS_PER_DAY = 1  # 1개씩

KST = ZoneInfo('Asia/Seoul')

# =========================
# 편의점 설정
# =========================
STORES = {
    'GS25': {'country': 'kr', 'name_kr': 'GS25', 'name_jp': None, 'category': '한국편의점', 'currency': '원'},
    'CU': {'country': 'kr', 'name_kr': 'CU', 'name_jp': None, 'category': '한국편의점', 'currency': '원'},
    '세븐일레븐_한국': {'country': 'kr', 'name_kr': '세븐일레븐', 'name_jp': None, 'category': '한국편의점', 'currency': '원'},
    '세븐일레븐_일본': {'country': 'jp', 'name_kr': '세븐일레븐', 'name_jp': 'セブンイレブン', 'category': '일본편의점', 'currency': '엔'},
    '패밀리마트': {'country': 'jp', 'name_kr': '패밀리마트', 'name_jp': 'ファミリーマート', 'category': '일본편의점', 'currency': '엔'},
    '로손': {'country': 'jp', 'name_kr': '로손', 'name_jp': 'ローソン', 'category': '일본편의점', 'currency': '엔'}
}

# ========================================
# 본문 저장/불러오기
# ========================================
def save_post_content(hour, post_data):
    """예약된 글의 본문을 시간별로 저장"""
    try:
        filename = f"/tmp/post_content_{hour}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(post_data, f, ensure_ascii=False, indent=2)
        print(f"  💾 본문 저장: {filename}")
    except Exception as e:
        print(f"  ⚠️ 본문 저장 실패: {e}")

def load_post_content(hour):
    """저장된 글의 본문 불러오기"""
    try:
        filename = f"/tmp/post_content_{hour}.json"
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"  ⚠️ 본문 불러오기 실패: {e}")
    return None

# ========================================
# HTML → 텍스트 변환
# ========================================
def create_text_version(html_content):
    """HTML을 인스타용 순수 텍스트로 변환"""
    text = re.sub(r'<div[^>]*>', '\n', html_content)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'<h1[^>]*>', '\n━━━━━━━━━━━━━━━━\n', text)
    text = re.sub(r'</h1>', '\n━━━━━━━━━━━━━━━━\n', text)
    text = re.sub(r'<h2[^>]*>', '\n\n📍 ', text)
    text = re.sub(r'</h2>', '\n', text)
    text = re.sub(r'<p[^>]*>', '', text)
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'<strong[^>]*>', '✨ ', text)
    text = re.sub(r'</strong>', ' ✨', text)
    text = re.sub(r'<hr[^>]*>', '\n━━━━━━━━━━━━━━━━\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<span[^>]*>', '', text)
    text = re.sub(r'</span>', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

# ========================================
# 예약 슬롯 계산
# ========================================
def next_slots_korean_japanese(count=6):
    """한국/일본 번갈아가며 6개 슬롯 반환"""
    now = datetime.now(KST)
    test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
    
    if test_mode:
        print("  🧪 테스트 모드: 1시간 간격으로 예약")
        candidates = []
        for i in range(count):
            slot_time = now + timedelta(hours=i+1)
            candidates.append(slot_time.replace(minute=0, second=0, microsecond=0))
        return candidates
    
    slot_hours = [8, 9, 12, 13, 20, 21]
    candidates = []
    
    for hour in slot_hours:
        slot_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now < slot_time:
            candidates.append(slot_time)
    
    days_ahead = 1
    while len(candidates) < count:
        next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        for hour in slot_hours:
            if len(candidates) >= count:
                break
            slot_time = next_day.replace(hour=hour, minute=0, second=0, microsecond=0)
            candidates.append(slot_time)
        days_ahead += 1
    
    return candidates[:count]

# ========================================
# AI 호출 함수들
# ========================================
def call_gemini(prompt):
    """Gemini API 호출 (1순위 - 무료, RPM 15)"""
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
        
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        
        result_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        result = json.loads(result_text)
        
        print("  ✅ Gemini 성공!")
        return result
        
    except Exception as e:
        print(f"  ⚠️ Gemini 실패: {str(e)[:100]}")
        return None


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


def call_openai(prompt):
    """OpenAI API 호출 (3순위 - 최후의 수단, RPM 3)"""
    if not OPENAI_API_KEY:
        print("  ⚠️ OpenAI API 키 없음")
        return None
    
    try:
        print("  🟠 OpenAI 시도 중...")
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", 
                               headers=headers, json=data, timeout=120)
        
        if response.status_code == 429:
            print("  ⚠️ OpenAI Rate Limit!")
            return None
            
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])
        
        print("  ✅ OpenAI 성공!")
        return result
        
    except Exception as e:
        print(f"  ⚠️ OpenAI 실패: {str(e)[:100]}")
        return None


def generate_with_auto(prompt):
    """AUTO 모드: Gemini → Groq → OpenAI 순서로 시도"""
    
    print("  🤖 AUTO 모드: Gemini → Groq → OpenAI")
    
    # 1순위: Gemini
    result = call_gemini(prompt)
    if result:
        return result
    
    # 2순위: Groq
    result = call_groq(prompt)
    if result:
        return result
    
    # 3순위: OpenAI
    result = call_openai(prompt)
    if result:
        return result
    
    print("  ❌ 모든 AI 실패!")
    return None

# ========================================
# AI 콘텐츠 생성
# ========================================
def generate_blog_post(store_key):
    """AI로 블로그 글 생성"""
    try:
        store_info = STORES[store_key]
        country = store_info['country']
        name_kr = store_info['name_kr']
        name_jp = store_info['name_jp']
        
        print(f"  📝 {name_kr} {'🇯🇵' if country == 'jp' else '🇰🇷'} 블로그 글 생성 중...")
        
        # 프롬프트 생성 (간단하게)
        if country == 'kr':
            prompt = f"""당신은 편의점 블로거입니다. {name_kr} 신상 제품 2-3개를 소개하는 블로그 글을 작성하세요.

요구사항:
- 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
- 본문: HTML 형식, 1200-1800자
- 각 제품: 제품명, 가격(원), 맛 후기, 꿀조합, 별점, 일본어 요약
- 친근한 MZ 스타일

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["편의점신상", "{name_kr}", "꿀조합"]}}
"""
        else:
            prompt = f"""당신은 일본 편의점 블로거입니다. {name_kr}({name_jp}) 신상 제품 2-3개를 소개하는 블로그 글을 작성하세요.

요구사항:
- 제목: 클릭하고 싶은 제목 (한일 병기)
- 본문: HTML 형식, 1200-1800자
- 각 제품: 제품명(한일), 가격(엔), 리뷰, 일본 문화 팁, 별점
- 여행 가이드 느낌

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["일본편의점", "{name_kr}", "{name_jp}"]}}
"""
        
        # AUTO 모드로 생성
        result = generate_with_auto(prompt)
        
        if not result:
            return None
        
        # 추가 정보
        result['category'] = store_info['category']
        result['country'] = country
        result['store_key'] = store_key
        result['text_version'] = create_text_version(result.get('content', ''))
        
        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
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
        post.terms_names = {'post_tag': tags, 'category': [category]}
        
        if scheduled_dt_kst:
            dt_utc = scheduled_dt_kst.astimezone(timezone.utc)
            post.post_status = 'future'
            post.date = dt_utc.replace(tzinfo=None)
            post.date_gmt = dt_utc.replace(tzinfo=None)
            action = '예약발행'
        else:
            post.post_status = 'publish'
            action = '즉시발행'
        
        post_id = wp.call(NewPost(post))
        url = f"{WORDPRESS_URL}/?p={post_id}"
        print(f"  ✅ {action} 성공: {url}")
        return {'success': True, 'url': url, 'post_id': post_id, 'action': action}
        
    except Exception as e:
        print(f"  ❌ 발행 실패: {e}")
        traceback.print_exc()
        return {'success': False}

# ========================================
# 슬랙 알림
# ========================================
def send_slack(message):
    """슬랙 텍스트 전송"""
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={'text': message}, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_slack_quick_actions(title="📱 바로가기"):
    """예쁜 버튼 3개"""
    try:
        payload = {
            "text": title,
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*\n\n가고 싶은 채널을 선택해 주세요 💖"}},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "📝 워드프레스", "emoji": True}, "style": "primary", "url": f"{WORDPRESS_URL}/wp-admin/edit.php"},
                    {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타", "emoji": True}, "url": INSTAGRAM_PROFILE_URL},
                    {"type": "button", "text": {"type": "plain_text", "text": "✍️ 네이버", "emoji": True}, "style": "danger", "url": NAVER_BLOG_URL}
                ]}
            ]
        }
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"  ❌ 슬랙 버튼 전송 실패: {e}")
        return False

# ========================================
# 모드 1: 콘텐츠 생성 및 예약발행
# ========================================
def generate_and_schedule():
    """콘텐츠 생성 및 예약발행"""
    print("=" * 60)
    print(f"🚀 한일 편의점 콘텐츠 생성: {datetime.now(KST)}")
    print("=" * 60)
    
    # 시간대별 발행 순서
    current_hour = datetime.now(KST).hour
    
    if current_hour == 23:
        store_order = ['GS25']
    elif current_hour == 1:
        store_order = ['세븐일레븐_일본']
    elif current_hour == 3:
        store_order = ['CU']
    elif current_hour == 5:
        store_order = ['패밀리마트']
    elif current_hour == 7:
        store_order = ['세븐일레븐_한국']
    else:
        store_order = ['로손']
    
    wp_results = []
    slots = next_slots_korean_japanese(count=POSTS_PER_DAY)
    
    print(f"\n🕗 예약 슬롯:")
    for i, slot in enumerate(slots):
        store_key = store_order[i % len(store_order)]
        store_info = STORES[store_key]
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"   {slot.strftime('%Y-%m-%d %H:%M')} - {store_info['name_kr']} {flag}")
    
    print(f"\n📝 블로그 {POSTS_PER_DAY}개 예약발행 시작...")
    print("-" * 60)
    
    for i in range(POSTS_PER_DAY):
        store_key = store_order[i % len(store_order)]
        store_info = STORES[store_key]
        scheduled_at = slots[i]
        
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"\n{'='*60}")
        print(f"[{i+1}/{POSTS_PER_DAY}] {store_info['name_kr']} {flag} @ {scheduled_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")
        
        try:
            print(f"  🤖 AI 콘텐츠 생성 시작...")
            content = generate_blog_post(store_key)
            
            if not content:
                print(f"  ❌ [{i+1}] 콘텐츠 생성 실패!")
                continue
            
            print(f"  ✅ 콘텐츠 생성 완료: {content['title'][:30]}...")
            print(f"  📤 워드프레스 발행 시작...")
            
            result = publish_to_wordpress(
                content['title'],
                content['content'],
                content['tags'],
                content['category'],
                scheduled_dt_kst=scheduled_at
            )
            
            if result.get('success'):
                print(f"  ✅ [{i+1}] 워드프레스 발행 성공!")
                post_data = {
                    'store': store_info['name_kr'],
                    'country': store_info['country'],
                    'title': content['title'],
                    'url': result['url'],
                    'when': scheduled_at.strftime('%Y-%m-%d %H:%M'),
                    'post_id': result['post_id'],
                    'text_version': content.get('text_version', '')[:500],
                    'hour': scheduled_at.hour,
                    'full_text': content.get('text_version', '')
                }
                wp_results.append(post_data)
                print(f"  💾 결과 저장 완료 (총 {len(wp_results)}개)")
                save_post_content(scheduled_at.hour, post_data)
            else:
                print(f"  ❌ [{i+1}] 워드프레스 발행 실패!")
                
        except Exception as e:
            print(f"  ❌ [{i+1}] 에러 발생: {e}")
            traceback.print_exc()
            continue
    
    print(f"\n{'='*60}")
    print(f"🎉 완료! 총 {len(wp_results)}개 글 발행 성공!")
    print(f"{'='*60}")
    
    # 완료 알림
    korean_posts = [r for r in wp_results if r['country'] == 'kr']
    japanese_posts = [r for r in wp_results if r['country'] == 'jp']
    
    summary = f"""🎉 *한일 편의점 예약발행 완료!*

📝 *총 {len(wp_results)}개 글 자동 예약*
🇰🇷 한국: {len(korean_posts)}개
🇯🇵 일본: {len(japanese_posts)}개

━━━━━━━━━━━━━━━━━━
"""
    
    for r in wp_results:
        flag = '🇯🇵' if r['country'] == 'jp' else '🇰🇷'
        summary += f"\n{flag} *{r['store']}* - {r['when']}"
        summary += f"\n   📝 {r['title'][:50]}..."
        summary += f"\n   🔗 {r['url']}\n"
    
    summary += """
━━━━━━━━━━━━━━━━━━
⏰ 예약 시간에 자동 발행됩니다!
"""
    
    send_slack(summary)
    send_slack_quick_actions(title="📱 바로가기")
    
    print(f"\n✅ 예약발행 완료!")

# ========================================
# 모드 2: 발행 알림
# ========================================
def send_publish_notification():
    """지금 시간에 발행된 글 알림"""
    print("=" * 60)
    print(f"🔔 발행 알림: {datetime.now(KST)}")
    print("=" * 60)
    
    now = datetime.now(KST)
    current_hour = now.hour
    
    time_slot_map = {
        8: ("아침 8시", "GS25", "kr"),
        9: ("아침 9시", "세븐일레븐", "jp"),
        12: ("점심 12시", "CU", "kr"),
        13: ("점심 1시", "패밀리마트", "jp"),
        20: ("저녁 8시", "세븐일레븐", "kr"),
        21: ("저녁 9시", "로손", "jp")
    }
    
    if current_hour not in time_slot_map:
        print("⚠️ 알림 시간이 아닙니다.")
        return
    
    time_slot, store_name, country = time_slot_map[current_hour]
    flag = "🇯🇵" if country == "jp" else "🇰🇷"
    
    post_content = load_post_content(current_hour)
    
    message = f"""🎉 *{time_slot} 글 발행 완료!*

{flag} *{store_name}* 글이 방금 발행되었어요!
"""
    
    if post_content:
        message += f"""
━━━━━━━━━━━━━━━━━━
📝 *제목:* {post_content['title']}
🔗 *링크:* {post_content['url']}
━━━━━━━━━━━━━━━━━━
"""
    
    message += """
📌 *할 일:*
1️⃣ 아래 본문 확인
2️⃣ 복사 → 인스타 붙여넣기
3️⃣ 사진 첨부 후 업로드!
"""
    
    send_slack(message)
    
    if post_content and post_content.get('full_text'):
        text_content = post_content['full_text']
        if len(text_content) > 2800:
            text_content = text_content[:2800] + "\n\n... (이하 생략)"
        
        text_message = f"""📄 *인스타 복사용 본문*

{text_content}

━━━━━━━━━━━━━━━━━━
💡 위 내용 전체를 복사해서 인스타에 붙여넣으세요!
"""
        send_slack(text_message)
    
    send_slack_quick_actions(title=f"📱 {time_slot} 바로가기")
    print(f"✅ {time_slot} 알림 완료!")

# ========================================
# 메인 함수
# ========================================
def main():
    mode = os.environ.get('MODE', 'generate')
    
    if mode == 'notify':
        send_publish_notification()
    else:
        generate_and_schedule()

if __name__ == "__main__":
    main()
