import os
import json
import traceback
import requests
from datetime import datetime
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.compat import xmlrpc_client
from bs4 import BeautifulSoup
import time

# 설정
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')

POSTS_PER_DAY = 3
INSTAGRAM_POSTS_PER_DAY = 3

# 편의점 공식 사이트 URL
STORE_URLS = {
    'GS25': 'https://gs25.gsretail.com/gscvs/ko/products/youus-freshfood',
    'CU': 'https://cu.bgfretail.com/product/product.do?category=product&depth=1&sf=N',
    '세븐일레븐': 'https://www.7-eleven.co.kr/product/presentList.asp'
}


# ========================================
# 이미지 크롤링
# ========================================
def crawl_product_images(store_name):
    """편의점 공식 사이트에서 신상 이미지 크롤링"""
    try:
        print(f"  🖼️ {store_name} 공식 사이트 크롤링 중...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        url = STORE_URLS.get(store_name)
        if not url:
            print(f"  ⚠️ {store_name} URL 없음")
            return []
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 이미지 URL 찾기 (각 편의점마다 다름)
        images = []
        
        if store_name == 'GS25':
            # GS25 구조에 맞게 수정 필요
            img_tags = soup.find_all('img', limit=5)
            for img in img_tags:
                src = img.get('src') or img.get('data-src')
                if src and 'http' in src:
                    images.append(src)
        
        elif store_name == 'CU':
            # CU 구조
            img_tags = soup.find_all('img', limit=5)
            for img in img_tags:
                src = img.get('src')
                if src and 'product' in src.lower():
                    if not src.startswith('http'):
                        src = 'https://cu.bgfretail.com' + src
                    images.append(src)
        
        elif store_name == '세븐일레븐':
            # 세븐일레븐 구조
            img_tags = soup.find_all('img', limit=5)
            for img in img_tags:
                src = img.get('src')
                if src and 'product' in src.lower():
                    if not src.startswith('http'):
                        src = 'https://www.7-eleven.co.kr' + src
                    images.append(src)
        
        print(f"  ✅ {len(images)}개 이미지 발견")
        return images[:3]  # 최대 3개
        
    except Exception as e:
        print(f"  ❌ 크롤링 실패: {e}")
        return []


def download_image(image_url):
    """이미지 다운로드"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
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
        
        data = {
            'name': filename,
            'type': 'image/jpeg',
            'bits': xmlrpc_client.Binary(image_data)
        }
        
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
    """AI로 블로그 글 생성"""
    try:
        print(f"  📝 {store_name} 블로그 글 생성 중...")
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
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

<h2>3. 제주 한라봉 에이드 🍊</h2>
<p>마지막은 제주 한라봉 에이드예요! 가격은 <strong>2,500원</strong>. 상큼한 한라봉의 향이 가득해서 한 모금 마시면 기분이 확 좋아져요. 탄산이 살짝 들어가 있어서 청량감도 최고! 요즘처럼 건조한 날씨에 딱 좋은 음료랍니다.</p>
<p><strong>꿀조합:</strong> 치킨이나 튀김류랑 같이 먹으면 느끼함을 싹 날려줘요! 별점은 <strong>⭐⭐⭐⭐⭐</strong>!</p>

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
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])
        
        # 이미지 크롤링
        image_urls = crawl_product_images(store_name)
        result['crawled_images'] = image_urls
        
        # 첫 번째 이미지 다운로드 & 업로드
        if image_urls:
            img_data = download_image(image_urls[0])
            if img_data:
                img_url = upload_image_to_wordpress(img_data, f'{store_name}_{datetime.now().strftime("%Y%m%d")}.jpg')
                result['featured_image'] = img_url
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
    """AI로 인스타 캡션 생성"""
    try:
        print(f"  📱 {store_name} 인스타 생성 중...")
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""당신은 팔로워 10만 이상의 인기 편의점 인스타그램 계정 운영자입니다.
{store_name}의 신상 제품을 소개하는 인스타그램 게시물을 작성해주세요.

요구사항:
1. 캡션: 3-5줄, 이모지 풍부하게 사용, MZ세대 말투
2. 구체적인 제품 1-2개 언급 (제품명 + 가격)
3. 해시태그: 15-20개 (편의점, 신상, 꿀조합 관련)

예시:
오늘 {store_name}에서 대박 신상 발견했어요! 🔥
딸기 생크림 케이크 (3,500원) 완전 맛있더라구요 🍰
케이크 + 아메리카노 조합은 진짜 레전드... 💕
여러분도 꼭 드셔보세요! 후회 안 해요 ✨

JSON 형식:
{{"caption": "캡션", "hashtags": "#편의점신상 #태그2 ...", "product_images": ["크롤링한 이미지 URL들"]}}
"""
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 인스타 전문가입니다."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.95,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])
        
        # 이미지 크롤링
        image_urls = crawl_product_images(store_name)
        result['image_urls'] = image_urls
        
        print(f"  ✅ 완료")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None


# ========================================
# 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags, image_url=''):
    """워드프레스 발행"""
    try:
        print(f"  📤 발행 중: {title[:30]}...")
        
        if image_url:
            content = f'<img src="{image_url}" alt="{title}" style="width:100%; height:auto; margin-bottom:30px; border-radius:10px;"/><br>{content}'
        
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {'post_tag': tags, 'category': ['편의점']}
        post.post_status = 'publish'
        
        post_id = wp.call(NewPost(post))
        url = f"{WORDPRESS_URL}/?p={post_id}"
        
        print(f"  ✅ 성공: {url}")
        return {'success': True, 'url': url, 'post_id': post_id}
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
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
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                },
                {
                    "type": "image",
                    "image_url": image_url,
                    "alt_text": "제품 이미지"
                }
            ]
        }
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"  ❌ 슬랙 이미지 전송 실패: {e}")
        return False


def send_instagram_to_slack(caption, hashtags, store, image_urls):
    """인스타그램 콘텐츠를 슬랙으로 전송 (이미지 포함)"""
    try:
        message = f"""📱 *{store} 인스타그램 콘텐츠 준비 완료*

*캡션:*
{caption}

*해시태그:*
{hashtags}

*이미지:* {len(image_urls)}개 발견

---
✅ 승인하려면 아래 이미지 확인 후 스마트폰에서 인스타 앱으로 업로드하세요!
"""
        
        # 첫 번째 이미지와 함께 전송
        if image_urls:
            return send_slack_with_image(message, image_urls[0])
        else:
            return send_slack(message)
        
    except Exception as e:
        print(f"  ❌ 슬랙 전송 실패: {e}")
        return False


# ========================================
# 메인 함수
# ========================================
def main():
    """메인"""
    print("=" * 60)
    print(f"🚀 편의점 신상 자동화 시작: {datetime.now()}")
    print("=" * 60)
    
    stores = ['GS25', 'CU', '세븐일레븐']
    wp_results = []
    ig_results = []
    
    # ========================================
    # 1단계: 워드프레스 블로그 자동 발행
    # ========================================
    print(f"\n📝 워드프레스 블로그 {POSTS_PER_DAY}개 생성 및 발행 중...")
    print("-" * 60)
    
    for i in range(POSTS_PER_DAY):
        store = stores[i % len(stores)]
        print(f"\n[{i+1}/{POSTS_PER_DAY}] {store}")
        
        content = generate_blog_post(store)
        if content:
            result = publish_to_wordpress(
                content['title'], 
                content['content'], 
                content['tags'], 
                content.get('featured_image', '')
            )
            
            if result['success']:
                wp_results.append({
                    'store': store,
                    'title': content['title'],
                    'url': result['url']
                })
        
        time.sleep(3)  # API 제한 방지
    
    # ========================================
    # 2단계: 인스타그램 콘텐츠 슬랙 전송 (승인 대기)
    # ========================================
    print(f"\n📱 인스타그램 콘텐츠 {INSTAGRAM_POSTS_PER_DAY}개 생성 및 슬랙 전송 중...")
    print("-" * 60)
    
    for i in range(INSTAGRAM_POSTS_PER_DAY):
        store = stores[i % len(stores)]
        print(f"\n[{i+1}/{INSTAGRAM_POSTS_PER_DAY}] {store}")
        
        content = generate_instagram_post(store)
        if content:
            success = send_instagram_to_slack(
                content.get('caption', ''), 
                content.get('hashtags', ''), 
                store,
                content.get('image_urls', [])
            )
            
            if success:
                ig_results.append({
                    'store': store,
                    'status': '슬랙 전송 완료 (승인 대기)'
                })
        
        time.sleep(3)
    
    # ========================================
    # 3단계: 완료 알림
    # ========================================
    summary = f"""
🎉 *자동화 완료!*

📝 *워드프레스 발행:* {len(wp_results)}개
"""
    
    for result in wp_results:
        summary += f"\n   • {result['store']}: {result['title'][:30]}...\n     → {result['url']}"
    
    summary += f"\n\n📱 *인스타그램 준비:* {len(ig_results)}개 (슬랙에서 확인 후 수동 업로드)"
    
    for result in ig_results:
        summary += f"\n   • {result['store']}: {result['status']}"
    
    summary += f"\n\n⏰ 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    send_slack(summary)
    print(f"\n✅ 전체 작업 완료!")
    print(summary)


if __name__ == "__main__":
    main()
