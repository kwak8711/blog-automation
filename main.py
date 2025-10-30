import os
import json
import traceback
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
import time

# =========================
# 설정 (환경변수)
# =========================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')

# 버튼 링크용
INSTAGRAM_PROFILE_URL = os.environ.get('INSTAGRAM_PROFILE_URL', 'https://instagram.com/')
NAVER_BLOG_URL        = os.environ.get('NAVER_BLOG_URL', 'https://blog.naver.com/')

POSTS_PER_DAY = 6  # 한국 3개 + 일본 3개

KST = ZoneInfo('Asia/Seoul')

# =========================
# 편의점 설정 (한국 + 일본)
# =========================
STORES = {
    'GS25': {
        'country': 'kr',
        'name_kr': 'GS25',
        'name_jp': None,
        'category': '한국편의점',
        'currency': '원'
    },
    'CU': {
        'country': 'kr',
        'name_kr': 'CU',
        'name_jp': None,
        'category': '한국편의점',
        'currency': '원'
    },
    '세븐일레븐_한국': {
        'country': 'kr',
        'name_kr': '세븐일레븐',
        'name_jp': None,
        'category': '한국편의점',
        'currency': '원'
    },
    '세븐일레븐_일본': {
        'country': 'jp',
        'name_kr': '세븐일레븐',
        'name_jp': 'セブンイレブン',
        'category': '일본편의점',
        'currency': '엔'
    },
    '패밀리마트': {
        'country': 'jp',
        'name_kr': '패밀리마트',
        'name_jp': 'ファミリーマート',
        'category': '일본편의점',
        'currency': '엔'
    },
    '로손': {
        'country': 'jp',
        'name_kr': '로손',
        'name_jp': 'ローソン',
        'category': '일본편의점',
        'currency': '엔'
    }
}

# ========================================
# 예약 슬롯 계산: 08, 09, 12, 13, 20, 21시
# ========================================
def next_slots_korean_japanese(count=6):
    """
    한국/일본 번갈아가며 6개 슬롯 반환
    08(한) → 09(일) → 12(한) → 13(일) → 20(한) → 21(일)
    """
    now = datetime.now(KST)
    today_slots = [
        now.replace(hour=8, minute=0, second=0, microsecond=0),
        now.replace(hour=9, minute=0, second=0, microsecond=0),
        now.replace(hour=12, minute=0, second=0, microsecond=0),
        now.replace(hour=13, minute=0, second=0, microsecond=0),
        now.replace(hour=20, minute=0, second=0, microsecond=0),
        now.replace(hour=21, minute=0, second=0, microsecond=0),
    ]
    
    candidates = []
    
    # 현재 시각 이후의 슬롯만 추가
    for slot in today_slots:
        if now < slot:
            candidates.append(slot)
    
    # 부족하면 다음날 슬롯 추가
    while len(candidates) < count:
        next_day = (candidates[-1] if candidates else now) + timedelta(days=1)
        for hour in [8, 9, 12, 13, 20, 21]:
            if len(candidates) >= count:
                break
            candidates.append(next_day.replace(hour=hour, minute=0, second=0, microsecond=0))
    
    return candidates[:count]

# ========================================
# AI 콘텐츠 생성 (한국/일본 통합)
# ========================================
def generate_blog_post(store_key):
    """AI로 블로그 글 생성 (한국/일본 자동 구분)"""
    try:
        store_info = STORES[store_key]
        country = store_info['country']
        name_kr = store_info['name_kr']
        name_jp = store_info['name_jp']
        currency = store_info['currency']
        
        print(f"  📝 {name_kr} {'🇯🇵' if country == 'jp' else '🇰🇷'} 블로그 글 생성 중...")
        
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

        if country == 'kr':
            # 한국 편의점 프롬프트
            prompt = f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{name_kr}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
   예: "🛒{name_kr} 신상! 나도 몰랐던 꿀조합✨"

2. 본문: 1000-1500자
   - 첫 문단: 친근한 인사
   - 각 제품마다:
     * <h2> 태그로 큰 제목 (번호 + 제품명 + 이모지)
     * 가격은 <strong> 태그로 강조 (원 단위)
     * 맛 후기 구체적으로 (식감, 맛, 향)
     * 조합 꿀팁
     * 별점 ⭐ 이모지
   - 마지막: 구매 추천

3. 친근한 말투, MZ세대 스타일

4. 실제 있을법한 제품 2-3개
   - 가격: 1,500원~5,000원

5. HTML 형식 예시:
<p><strong>안녕하세요, 편스타그램 친구들!</strong> 오늘은 {name_kr}에서 새롭게 나온 신상 제품들을 소개해드릴게요! 🎉</p>

<h2>1. 딸기 생크림 케이크 🍰</h2>
<p>가격은 <strong>3,500원</strong>! 달콤한 딸기와 부드러운 생크림의 조화가 환상적이에요.</p>
<p><strong>꿀조합:</strong> 아메리카노와 함께! 별점 <strong>⭐⭐⭐⭐⭐</strong></p>

<h2>2. 불닭치즈볶음면 김밥 🌶️</h2>
<p>가격은 <strong>2,800원</strong>! 매콤하지만 치즈가 느끼함을 잡아줘요.</p>
<p><strong>꿀조합:</strong> 우유랑 함께! 별점 <strong>⭐⭐⭐⭐</strong></p>

<p>오늘 소개한 {name_kr} 신상들, 꼭 드셔보세요! 😊</p>

<hr style="border: none; border-top: 2px solid #ddd; margin: 40px 0;">

<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">
<p style="margin: 0; font-size: 14px; color: #667eea; line-height: 1.8;">
#편의점신상 #{name_kr} #꿀조합 #편스타그램 #MZ추천 #편의점디저트 #편의점케이크 #데일리디저트 #오늘뭐먹지 #편의점투어 #편의점맛집 #먹스타그램 #디저트스타그램 #간식추천 #편의점꿀템
</p>
</div>

JSON 형식으로 답변:
{{"title": "제목", "content": "HTML 본문 전체", "tags": ["편의점신상", "{name_kr}", "꿀조합", "편스타그램", "MZ추천"]}}
"""
        else:
            # 일본 편의점 프롬프트
            prompt = f"""당신은 일본 편의점을 소개하는 인기 블로거입니다.
일본 {name_kr}({name_jp})의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 한일 병기)
   예: "🇯🇵{name_kr} 신상! 프리미엄 오니기리 완전 대박 ({name_jp})✨"

2. 본문: 1000-1500자
   - 첫 문단: 친근한 인사 + 일본 편의점 특징 소개
   - 각 제품마다:
     * <h2> 태그로 큰 제목 (번호 + 제품명(한국어) + 일본어 + 이모지)
       예: <h2>1. 프리미엄 참치마요 오니기리 (ツナマヨおにぎり) 🍙</h2>
     * 가격은 <strong> 태그로 강조 (엔 단위만, 원화 환산 X)
       예: <strong>200엔</strong>
     * 일본 특유의 제품 특징 설명
     * 일본 편의점 문화 팁
     * 별점 ⭐ 이모지
   - 마지막: 일본 여행 시 추천

3. 친근하고 여행 가이드 느낌

4. 실제 일본 편의점 제품 2-3개
   - 가격: 100엔~500엔
   - 제품 예시:
     * 오니기리 (おにぎり) 100-200엔
     * 벤또 (弁当) 300-500엔
     * 디저트 200-400엔
     * 음료 100-200엔

5. HTML 형식 예시:
<p><strong>안녕하세요! 일본 편의점 탐험대입니다!</strong> 🇯🇵 오늘은 일본 {name_kr}({name_jp})의 신상 제품을 소개해드릴게요! 일본 편의점은 한국과 다르게 퀄리티가 정말 높은 걸로 유명하죠!</p>

<h2>1. 프리미엄 참치마요 오니기리 (ツナマヨおにぎり) 🍙</h2>
<p>가격은 <strong>200엔</strong>! 한국 편의점 삼각김밥과 비슷하지만 밥알이 더 찰지고 김이 바삭해요. 참치마요 소스가 진짜 듬뿍!</p>
<p><strong>일본 팁:</strong> 편의점에서 "아타타메떼 쿠다사이(温めてください)"라고 하면 데워줘요! 별점 <strong>⭐⭐⭐⭐⭐</strong></p>

<h2>2. 카레맛 치킨 오니기리 (カレーチキンおにぎり) 🍛</h2>
<p>가격은 <strong>180엔</strong>! 일본식 카레맛 치킨이 들어있어서 한 끼 식사로도 충분해요.</p>
<p><strong>일본 팁:</strong> 편의점 오니기리는 새벽에 가면 할인해요! 별점 <strong>⭐⭐⭐⭐</strong></p>

<p>일본 여행 가시면 {name_kr} 꼭 들러보세요! 한국에서는 맛볼 수 없는 특별한 제품들이 가득해요! 🎌</p>

<hr style="border: none; border-top: 2px solid #ddd; margin: 40px 0;">

<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">
<p style="margin: 0; font-size: 14px; color: #667eea; line-height: 1.8;">
#일본편의점 #{name_kr} #일본여행 #오니기리 #편의점투어 #일본맛집 #도쿄여행 #오사카여행 #일본출장 #편의점신상 #일본음식 #먹스타그램 #일본일주 #여행스타그램 #일본정보
</p>
</div>

JSON 형식으로 답변:
{{"title": "제목", "content": "HTML 본문 전체", "tags": ["일본편의점", "{name_kr}", "일본여행", "오니기리", "편의점투어"]}}
"""

        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다. 친근하고 재미있는 글을 씁니다."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])

        # 카테고리 추가
        result['category'] = store_info['category']
        result['country'] = country
        result['store_key'] = store_key

        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None

# ========================================
# 워드프레스 발행 (예약 발행 지원)
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
            # 예약 발행
            dt_kst = scheduled_dt_kst.astimezone(KST)
            dt_utc = dt_kst.astimezone(timezone.utc)
            post.post_status = 'future'
            post.date = dt_kst.replace(tzinfo=None)
            post.date_gmt = dt_utc.replace(tzinfo=None)
            action = '예약발행'
        else:
            # 즉시 발행
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
    """예쁜 버튼 3개 (워드프레스 / 인스타 / 네이버블로그)"""
    try:
        payload = {
            "text": title,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{title}*\n\n가고 싶은 채널을 선택해 주세요 💖"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📝 워드프레스", "emoji": True},
                            "style": "primary",
                            "url": f"{WORDPRESS_URL}/wp-admin/edit.php"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📷 인스타", "emoji": True},
                            "url": INSTAGRAM_PROFILE_URL
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✍️ 네이버", "emoji": True},
                            "style": "danger",
                            "url": NAVER_BLOG_URL
                        }
                    ]
                }
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
    """한국 + 일본 편의점 콘텐츠 생성 및 예약발행"""
    print("=" * 60)
    print(f"🚀 한일 편의점 콘텐츠 생성: {datetime.now(KST)}")
    print("=" * 60)

    # 발행 순서 (한국/일본 번갈아)
    store_order = [
        'GS25',              # 08시 (한국)
        '세븐일레븐_일본',    # 09시 (일본)
        'CU',                # 12시 (한국)
        '패밀리마트',        # 13시 (일본)
        '세븐일레븐_한국',    # 20시 (한국)
        '로손'               # 21시 (일본)
    ]
    
    wp_results = []

    # 예약 슬롯 계산
    slots = next_slots_korean_japanese(count=POSTS_PER_DAY)
    print(f"\n🕗 예약 슬롯:")
    for i, slot in enumerate(slots):
        store_key = store_order[i % len(store_order)]
        store_info = STORES[store_key]
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"   {slot.strftime('%Y-%m-%d %H:%M')} - {store_info['name_kr']} {flag}")

    # 워드프레스 글 생성 + 예약발행
    print(f"\n📝 블로그 {POSTS_PER_DAY}개 예약발행 중...")
    print("-" * 60)
    
    for i in range(POSTS_PER_DAY):
        store_key = store_order[i % len(store_order)]
        store_info = STORES[store_key]
        scheduled_at = slots[i]
        
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"\n[{i+1}/{POSTS_PER_DAY}] {store_info['name_kr']} {flag} @ {scheduled_at.strftime('%Y-%m-%d %H:%M')}")

        content = generate_blog_post(store_key)
        if content:
            result = publish_to_wordpress(
                content['title'],
                content['content'],
                content['tags'],
                content['category'],
                scheduled_dt_kst=scheduled_at
            )
            if result.get('success'):
                wp_results.append({
                    'store': store_info['name_kr'],
                    'country': store_info['country'],
                    'title': content['title'],
                    'url': result['url'],
                    'when': scheduled_at.strftime('%Y-%m-%d %H:%M'),
                    'post_id': result['post_id']
                })
        time.sleep(10)

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
        summary += f"\n   {r['title'][:40]}..."
        summary += f"\n   {r['url']}\n"
    
    summary += f"""
━━━━━━━━━━━━━━━━━━
📌 *사용 방법:*
1️⃣ 워드프레스 열기
2️⃣ 맨 아래 해시태그 복사
3️⃣ 인스타/네이버에 붙여넣기
4️⃣ 사진 첨부 후 업로드!

⏰ 예약 시간에 자동 발행됩니다!
"""
    
    send_slack(summary)
    
    # 퀵액션 버튼
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
    
    # 현재 시간대 확인
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
    
    # 워드프레스 발행 알림
    message = f"""🎉 *{time_slot} 글 발행 완료!*

{flag} *{store_name}* 글이 방금 발행되었어요!

━━━━━━━━━━━━━━━━━━
📌 *할 일:*
1️⃣ 워드프레스에서 글 확인
2️⃣ 맨 아래 해시태그 복사
3️⃣ 인스타에 붙여넣기
4️⃣ 사진 첨부 후 업로드!

✨ 간단하죠? 30초 컷!
"""
    send_slack(message)
    
    # 퀵액션 버튼
    send_slack_quick_actions(title=f"📱 {time_slot} 바로가기")
    
    print(f"✅ {time_slot} 알림 완료!")


# ========================================
# 메인 함수 (모드 선택)
# ========================================
def main():
    mode = os.environ.get('MODE', 'generate')
    
    if mode == 'notify':
        send_publish_notification()
    else:
        generate_and_schedule()


if __name__ == "__main__":
    main()
