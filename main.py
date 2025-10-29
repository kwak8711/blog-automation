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

POSTS_PER_DAY = 3

KST = ZoneInfo('Asia/Seoul')

# ========================================
# 예약 슬롯 계산: 다음날 08:00, 12:00, 20:00
# ========================================
def next_slots_8_12_20(count=3):
    """
    지금 시각 기준으로 가장 가까운 08:00, 12:00, 20:00부터 순서대로 count개 반환 (KST)
    반환: [datetime(KST), ...]
    """
    now = datetime.now(KST)
    today_8 = now.replace(hour=8,  minute=0, second=0, microsecond=0)
    today_12 = now.replace(hour=12, minute=0, second=0, microsecond=0)
    today_20 = now.replace(hour=20, minute=0, second=0, microsecond=0)

    candidates = []
    
    # 현재 시각 기준으로 다음 슬롯부터 추가
    if now <= today_8:
        candidates.extend([today_8, today_12, today_20])
    elif now <= today_12:
        candidates.extend([today_12, today_20, today_8 + timedelta(days=1)])
    elif now <= today_20:
        candidates.extend([today_20, today_8 + timedelta(days=1), today_12 + timedelta(days=1)])
    else:
        # 다음날로
        candidates.extend([
            today_8 + timedelta(days=1), 
            today_12 + timedelta(days=1), 
            today_20 + timedelta(days=1)
        ])

    # 필요 개수만큼 채우기
    while len(candidates) < count:
        base = candidates[-3] + timedelta(days=1)
        candidates.extend([
            base.replace(hour=8), 
            base.replace(hour=12), 
            base.replace(hour=20)
        ])
    
    return candidates[:count]

# ========================================
# AI 콘텐츠 생성
# ========================================
def generate_blog_post(store_name):
    """AI로 블로그 글 생성 (본문 끝에 해시태그)"""
    try:
        print(f"  📝 {store_name} 블로그 글 생성 중...")
        
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

        prompt = f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{store_name}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
   예: "🛒CU 신상! 나도 몰랐던 꿀조합✨"

2. 본문: 1000-1500자
   - 첫 문단: 친근한 인사
   - 각 제품마다:
     * <h2> 태그로 큰 제목 (번호 + 제품명 + 이모지)
     * 가격은 <strong> 태그로 강조
     * 맛 후기 구체적으로 (식감, 맛, 향)
     * 조합 꿀팁
     * 별점 ⭐ 이모지
   - 마지막: 구매 추천

3. 친근한 말투, MZ세대 스타일 ("요즘", "완전", "진짜", "대박")

4. 실제 있을법한 제품 2-3개
   - 가격: 1,500원~5,000원

5. 본문 마지막에 구분선 + 인스타용 해시태그 15개 추가

6. HTML 형식 예시:
<p><strong>안녕하세요, 편스타그램 친구들!</strong> 오늘은 {store_name} 편의점에서 새롭게 출시된 맛있는 신상 제품들을 소개해드릴게요. 요즘 날씨도 쌀쌀해지고, 간편하게 즐길 수 있는 간식들이 정말 많이 나왔어요! 그럼 바로 시작해볼까요?</p>

<h2>1. 딸기 생크림 케이크 🍰</h2>
<p>첫 번째는 딸기 생크림 케이크예요! 가격은 <strong>3,500원</strong>으로 부담 없이 즐길 수 있는 간식이죠. 한 입 베어물면 신선한 딸기와 부드러운 생크림이 입 안에서 폭발! 달콤한 맛이 정말 일품이에요.</p>
<p><strong>꿀조합:</strong> 아메리카노와 함께! 별점 <strong>⭐⭐⭐⭐⭐</strong></p>

<h2>2. 불닭치즈볶음면 김밥 🌶️</h2>
<p>매콤한 불닭에 치즈가 듬뿍! 가격은 <strong>2,800원</strong>으로 가성비 끝내줘요.</p>
<p><strong>꿀조합:</strong> 우유랑 함께! 별점 <strong>⭐⭐⭐⭐</strong></p>

<p>오늘 소개한 {store_name} 신상, 어떠셨나요? 꼭 드셔보세요! 😊</p>

<hr style="border: none; border-top: 2px solid #ddd; margin: 40px 0;">

<div style="background: #f8f9fa; padding: 20px; border-radius: 10px;">
<p style="margin: 0; font-size: 14px; color: #667eea; line-height: 1.8;">
#편의점신상 #{store_name} #꿀조합 #편스타그램 #MZ추천 #편의점디저트 #편의점케이크 #데일리디저트 #오늘뭐먹지 #편의점투어 #편의점맛집 #먹스타그램 #디저트스타그램 #간식추천 #편의점꿀템
</p>
</div>

JSON 형식으로 답변:
{{"title": "제목", "content": "HTML 본문 전체 (해시태그 포함)", "tags": ["편의점신상", "{store_name}", "꿀조합", "편스타그램", "MZ추천"]}}
"""

        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 신상 전문 블로거입니다. 친근하고 재미있는 글을 씁니다."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])

        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None

# ========================================
# 워드프레스 발행 (예약 발행 지원)
# ========================================
def publish_to_wordpress(title, content, tags, scheduled_dt_kst=None):
    """워드프레스 발행/예약발행 (이미지 없음)"""
    try:
        print(f"  📤 발행 준비: {title[:30]}...")

        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)

        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {'post_tag': tags, 'category': ['편의점']}

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
# 모드 1: 콘텐츠 생성 및 예약발행 (저녁 22시)
# ========================================
def generate_and_schedule():
    """콘텐츠 생성 후 다음날 08:00, 12:00, 20:00에 예약발행"""
    print("=" * 60)
    print(f"🚀 콘텐츠 생성 및 예약발행: {datetime.now(KST)}")
    print("=" * 60)

    stores = ['GS25', 'CU', '세븐일레븐']
    wp_results = []

    # 다음날 예약 슬롯 계산
    slots = next_slots_8_12_20(count=POSTS_PER_DAY)
    print(f"\n🕗 예약 슬롯: {[dt.strftime('%Y-%m-%d %H:%M') for dt in slots]} (KST)")

    # 워드프레스 글 생성 + 예약발행
    print(f"\n📝 워드프레스 블로그 {POSTS_PER_DAY}개 예약발행 중...")
    print("-" * 60)
    
    for i in range(POSTS_PER_DAY):
        store = stores[i % len(stores)]
        scheduled_at = slots[i]
        print(f"\n[{i+1}/{POSTS_PER_DAY}] {store} @ {scheduled_at.strftime('%Y-%m-%d %H:%M')}")

        content = generate_blog_post(store)
        if content:
            result = publish_to_wordpress(
                content['title'],
                content['content'],
                content['tags'],
                scheduled_dt_kst=scheduled_at
            )
            if result.get('success'):
                wp_results.append({
                    'store': store,
                    'title': content['title'],
                    'url': result['url'],
                    'when': scheduled_at.strftime('%Y-%m-%d %H:%M'),
                    'post_id': result['post_id']
                })
        time.sleep(10)

    # 완료 알림 (초간단)
    summary = f"""🎉 *예약발행 완료!*

📝 *{len(wp_results)}개 글 자동 예약:*"""
    
    for r in wp_results:
        summary += f"\n✅ *{r['store']}* - {r['when']}"
        summary += f"\n   {r['title'][:40]}..."
        summary += f"\n   {r['url']}\n"
    
    summary += f"""
━━━━━━━━━━━━━━━━━━

⏰ 예약 시간에 자동 발행됩니다!
"""
    
    send_slack(summary)
    
    # 퀵액션 버튼
    send_slack_quick_actions(title="📱 바로가기")
    
    print(f"\n✅ 예약발행 완료!")


# ========================================
# 모드 2: 발행 알림 (08:00, 12:00, 20:00)
# ========================================
def send_publish_notification():
    """지금 시간에 발행된 글 알림"""
    print("=" * 60)
    print(f"🔔 발행 알림: {datetime.now(KST)}")
    print("=" * 60)
    
    now = datetime.now(KST)
    current_hour = now.hour
    
    # 현재 시간대 확인
    if current_hour == 8:
        time_slot = "아침 8시"
        store_name = "GS25"
    elif current_hour == 12:
        time_slot = "점심 12시"
        store_name = "CU"
    elif current_hour == 20:
        time_slot = "저녁 8시"
        store_name = "세븐일레븐"
    else:
        print("⚠️ 알림 시간이 아닙니다.")
        return
    
    # 워드프레스 발행 알림
    message = f"""🎉 *{time_slot} 글 발행 완료!*

📝 *{store_name}* 글이 방금 발행되었어요!

━━━━━━━━━━━━━━━━━━
📌 *할 일:*
1️⃣ 워드프레스에서 글 확인
2️⃣ "인스타그램 복사용" 박스 복사
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
