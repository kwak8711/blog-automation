import os
import json
import traceback
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.compat import xmlrpc_client
from bs4 import BeautifulSoup
import time

# =========================
# 설정 (환경변수)
# =========================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')
PEXELS_API_KEY       = os.environ.get('PEXELS_API_KEY')  # 추가!

# 버튼 링크용
INSTAGRAM_PROFILE_URL = os.environ.get('INSTAGRAM_PROFILE_URL', 'https://instagram.com/')
NAVER_BLOG_URL        = os.environ.get('NAVER_BLOG_URL', 'https://blog.naver.com/')

POSTS_PER_DAY = 3
INSTAGRAM_POSTS_PER_DAY = 3

# 편의점 공식 사이트 URL
STORE_URLS = {
    'GS25': 'https://gs25.gsretail.com/gscvs/ko/products/youus-freshfood',
    'CU': 'https://cu.bgfretail.com/product/product.do?category=product&depth=1&sf=N',
    '세븐일레븐': 'https://www.7-eleven.co.kr/product/presentList.asp'
}

KST = ZoneInfo('Asia/Seoul')

# 제품 카테고리별 최적 검색어 (Pexels용)
PRODUCT_KEYWORDS = {
    '라면': 'ramen noodles instant',
    '김밥': 'kimbap rice roll sushi',
    '도시락': 'korean lunch box bento',
    '샌드위치': 'sandwich deli',
    '삼각김밥': 'onigiri rice ball',
    '케이크': 'cake dessert pastry',
    '과자': 'snacks chips crackers',
    '음료': 'beverage drink juice',
    '아이스크림': 'ice cream dessert',
    '치킨': 'fried chicken',
    '핫도그': 'hot dog sausage',
    '피자': 'pizza slice',
    '떡볶이': 'tteokbokki korean food',
    '만두': 'dumplings gyoza',
    '우유': 'milk dairy drink',
    '커피': 'coffee beverage',
    '초콜릿': 'chocolate candy',
    '빵': 'bread pastry',
    '주스': 'juice beverage',
}

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
# Pexels 이미지 검색
# ========================================
def extract_product_category(title, content):
    """제목과 본문에서 제품 카테고리 추출"""
    text = (title + ' ' + content).lower()
    
    # 키워드 매칭
    for category, keyword in PRODUCT_KEYWORDS.items():
        if category in text:
            return keyword
    
    # 기본값
    return 'convenience store food snacks'


def search_pexels_images(keyword, count=3):
    """Pexels API로 이미지 검색"""
    if not PEXELS_API_KEY:
        print("  ⚠️ PEXELS_API_KEY 없음, Unsplash로 폴백")
        return []
    
    try:
        print(f"  🔍 Pexels 검색: '{keyword}'")
        
        headers = {"Authorization": PEXELS_API_KEY}
        url = "https://api.pexels.com/v1/search"
        params = {
            "query": keyword,
            "per_page": count,
            "orientation": "landscape"  # 가로 이미지
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        photos = response.json().get('photos', [])
        image_urls = [photo['src']['large'] for photo in photos]
        
        print(f"  ✅ {len(image_urls)}개 이미지 발견")
        return image_urls
        
    except Exception as e:
        print(f"  ❌ Pexels 검색 실패: {e}")
        return []


def get_product_images_smart(store_name, title='', content=''):
    """
    스마트 이미지 검색 (Pexels + 폴백)
    1순위: Pexels API (제품 카테고리 기반)
    2순위: Pexels 일반 검색 (편의점)
    3순위: Unsplash 백업
    """
    all_images = []
    
    # 1) Pexels - 제품 카테고리 검색
    if title or content:
        category_keyword = extract_product_category(title, content)
        images = search_pexels_images(category_keyword, count=3)
        all_images.extend(images)
    
    # 2) Pexels - 편의점 일반 검색
    if len(all_images) < 3:
        general_keywords = [
            "convenience store food",
            "korean snacks food",
            f"{store_name} food"
        ]
        for kw in general_keywords:
            images = search_pexels_images(kw, count=2)
            all_images.extend(images)
            if len(all_images) >= 3:
                break
    
    # 3) Unsplash 백업
    if len(all_images) == 0:
        print("  ⚠️ Pexels 결과 없음, Unsplash 사용")
        all_images.append("https://source.unsplash.com/800x600/?convenience,store,food")
        all_images.append("https://source.unsplash.com/800x600/?korean,food,snack")
        all_images.append("https://source.unsplash.com/800x600/?asian,food,meal")
    
    # 중복 제거
    all_images = list(dict.fromkeys(all_images))
    
    print(f"  ✅ 최종 {len(all_images)}개 이미지 선택")
    return all_images[:5]


def download_image(image_url):
    """이미지 다운로드"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(image_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
        return None
    except:
        return None


def upload_image_to_wordpress(image_data, filename='product.jpg'):
    """워드프레스에 이미지 업로드"""
    try:
        from wordpress_xmlrpc.methods import media
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        data = {'name': filename, 'type': 'image/jpeg', 'bits': xmlrpc_client.Binary(image_data)}
        response = wp.call(media.UploadFile(data))
        print(f"  ✅ 이미지 업로드 완료: {response['url']}")
        return response['url']
    except Exception as e:
        print(f"  ❌ 이미지 업로드 실패: {e}")
        return None

# ========================================
# AI 콘텐츠 생성
# ========================================
def generate_blog_post(store_name):
    """AI로 블로그 글 생성 (Pexels 이미지 통합)"""
    try:
        print(f"  📝 {store_name} 블로그 글 생성 중...")
        
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

        prompt = f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{store_name}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
   예: "🛒CU 신상! 나도 몰랐던 꿀조합✨"

2. 본문: 1000-1500자
   - 첫 문단: 친근한 인사 + 오늘 소개할 제품 미리보기
   - 각 제품마다:
     * <h2> 태그로 큰 제목 (번호 + 제품명 + 이모지)
     * 가격은 <strong> 태그로 강조
     * 맛 후기는 구체적으로 (식감, 맛, 향 등)
     * 조합 꿀팁 (다른 제품과 함께 먹으면 좋은 것)
     * 별점은 ⭐ 이모지 5개 만점으로
   - 마지막 문단: 구매 추천 멘트

3. 친근한 말투, MZ세대 스타일 ("요즘", "완전", "진짜", "대박" 등)

4. 실제 있을법한 제품 2-3개 소개
   - 제품명 예: "딸기 생크림 케이크", "불닭치즈볶음면 김밥", "제주 한라봉 에이드"
   - 가격대: 1,500원~5,000원

5. HTML 형식 예시:
<p><strong>안녕하세요, 편스타그램 친구들!</strong> 오늘은 {store_name} 편의점에서 새롭게 출시된 맛있는 신상 제품들을 소개해드릴게요. 요즘 날씨도 쌀쌀해지고, 간편하게 즐길 수 있는 간식들이 정말 많이 나왔어요! 그럼 바로 시작해볼까요?</p>

<h2>1. 딸기 생크림 케이크 🍰</h2>
<p>첫 번째는 딸기 생크림 케이크예요! 가격은 <strong>3,500원</strong>으로 부담 없이 즐길 수 있는 간식이죠. 한 입 베어물면 신선한 딸기와 부드러운 생크림이 입 안에서 폭발! 달콤한 맛이 정말 일품이에요. 케이크가 생크림도 너무 느끼하지 않고 적당히 가벼워서 후식으로 딱 좋답니다.</p>
<p><strong>꿀조합:</strong> 이 케이크는 아메리카노와의 조합이 최고예요! 커피의 쌉싸름한 맛과 케이크의 달콤함이 환상적인 꿀조합을 만들어줍니다. 별점은 <strong>⭐⭐⭐⭐⭐</strong>!</p>

<h2>2. 불닭치즈볶음면 김밥 🌶️</h2>
<p>다음은 불닭치즈볶음면 김밥! 가격은 <strong>2,800원</strong>으로 가성비가 완전 끝내줘요. 매콤한 불닭볶음면에 치즈가 듬뿍 들어가서 맵지만 고소한 맛이 일품이에요. 김밥 안에 불닭면이 들어있어서 한 입 베어물 때마다 쫄깃한 식감과 함께 매콤달콤한 맛이 입 안 가득 퍼집니다!</p>
<p><strong>꿀조합:</strong> 우유랑 같이 먹으면 매운맛을 중화시켜주면서도 고소함이 배가 돼요! 별점은 <strong>⭐⭐⭐⭐</strong>!</p>

<p>오늘 소개해드린 {store_name} 신상 제품들, 어떠셨나요? 모두 가성비도 좋고 맛도 보장되는 제품들이니 꼭 한번 드셔보세요! 여러분의 편의점 꿀조합도 댓글로 알려주세요! 😊</p>

JSON 형식으로 답변:
{{"title": "제목", "content": "HTML 본문", "tags": ["편의점신상", "{store_name}", "꿀조합", "편스타그램", "MZ추천"]}}
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

        # Pexels 이미지 검색 (제목/본문 기반)
        image_urls = get_product_images_smart(
            store_name, 
            result.get('title', ''),
            result.get('content', '')
        )
        result['crawled_images'] = image_urls

        # 첫 번째 이미지 다운로드 & 업로드
        if image_urls:
            img_data = download_image(image_urls[0])
            if img_data:
                img_url = upload_image_to_wordpress(
                    img_data, 
                    f'{store_name}_{datetime.now(KST).strftime("%Y%m%d")}.jpg'
                )
                result['featured_image'] = img_url or ''
            else:
                result['featured_image'] = ''
        else:
            result['featured_image'] = ''

        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None


def generate_instagram_post(store_name):
    """AI로 인스타 캡션 생성 (Pexels 이미지 통합)"""
    try:
        print(f"  📱 {store_name} 인스타 생성 중...")
        
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        prompt = f"""{store_name} 편의점 신상 제품 인스타그램 캡션 작성.
요즘 핫한 신상 1-2개 소개, 이모지 사용, MZ세대 말투, 3-5줄.
해시태그 15개 포함.
JSON 형식: {{"caption": "캡션 내용", "hashtags": "#편의점신상 #태그들..."}}"""
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])
        
        # Pexels 이미지 검색 (캡션 기반)
        image_urls = get_product_images_smart(
            store_name,
            result.get('caption', ''),
            ''
        )
        result['image_urls'] = image_urls
        
        print(f"  ✅ 완료")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None

# ========================================
# 워드프레스 발행 (예약 발행 지원)
# ========================================
def publish_to_wordpress(title, content, tags, image_url='', scheduled_dt_kst=None):
    """워드프레스 발행/예약발행"""
    try:
        print(f"  📤 발행 준비: {title[:30]}...")

        if image_url:
            content = (
                f'<img src="{image_url}" alt="{title}" '
                f'style="width:100%; height:auto; margin-bottom:30px; border-radius:10px;"/><br>{content}'
            )

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


def send_slack_with_image(message, image_url):
    """슬랙 이미지 포함 전송"""
    try:
        payload = {
            "text": message,
            "blocks": [
                {"type": "section","text": {"type": "mrkdwn","text": message}},
                {"type": "image","image_url": image_url,"alt_text": "제품 이미지"}
            ]
        }
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"  ❌ 슬랙 이미지 전송 실패: {e}")
        return False


def send_slack_quick_actions(title="업로드 채널 바로가기 ✨"):
    """예쁜 버튼 2개 (인스타 / 네이버블로그)"""
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
                            "text": {"type": "plain_text", "text": "📷 인스타로 가기", "emoji": True},
                            "style": "primary",
                            "url": INSTAGRAM_PROFILE_URL
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✍️ 네이버블로그로 가기", "emoji": True},
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


def send_instagram_to_slack(caption, hashtags, store, image_urls):
    """인스타그램 콘텐츠를 슬랙으로 전송"""
    try:
        # 이미지 다운로드 링크들
        image_text = ""
        if image_urls:
            for idx, url in enumerate(image_urls[:3], 1):
                image_text += f"\n🔵 *<{url}|📷 이미지 {idx} 다운로드>*"
        else:
            image_text = "\n⚠️ 이미지를 찾지 못했습니다."

        message = f"""
📱 *{store} 인스타그램 콘텐츠 준비 완료!*

*캡션:*
{caption}

*해시태그:*
{hashtags}

━━━━━━━━━━━━━━━━━━
*📸 제품 이미지 다운로드:*{image_text}

━━━━━━━━━━━━━━━━━━
✅ *업로드 방법:*
1️⃣ 위 링크 클릭해서 이미지 다운로드
2️⃣ 인스타그램 앱 열기  
3️⃣ 캡션 + 해시태그 복사
4️⃣ 이미지와 함께 업로드!
"""
        
        return send_slack(message)
        
    except Exception as e:
        print(f"  ❌ 슬랙 전송 실패: {e}")
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
                content.get('featured_image', ''),
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

    # 완료 알림
    summary = f"🎉 *예약발행 완료!*\n\n📝 *워드프레스 예약:* {len(wp_results)}개"
    for r in wp_results:
        summary += f"\n   • {r['store']}: {r['title'][:30]}... ⏰ {r['when']}\n     → {r['url']}"
    summary += f"\n\n⏰ 예약 시간에 자동으로 알림 드릴게요!"
    summary += f"\n📸 Pexels API로 고품질 이미지 자동 검색 완료!"
    
    send_slack(summary)
    print(f"\n✅ 예약발행 완료!")


# ========================================
# 모드 2: 발행 알림 (08:00, 12:00, 20:00)
# ========================================
def send_publish_notification():
    """지금 시간에 발행된 글 알림 + 인스타 콘텐츠 생성"""
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

📝 *{store_name}* 편의점 신상 글이 방금 발행되었어요!

✅ 워드프레스에서 확인하고 수정할 부분 있으면 수정하세요.
✅ 아래 버튼을 눌러 인스타/네이버에 업로드하세요!
"""
    send_slack(message)
    
    # 인스타그램 콘텐츠 생성
    print(f"\n📱 {store_name} 인스타그램 콘텐츠 생성 중...")
    content = generate_instagram_post(store_name)
    
    if content:
        send_instagram_to_slack(
            content.get('caption', ''),
            content.get('hashtags', ''),
            store_name,
            content.get('image_urls', [])
        )
    
    # 퀵액션 버튼
    send_slack_quick_actions(title=f"{time_slot} 업로드 바로가기 ✨")
    
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
