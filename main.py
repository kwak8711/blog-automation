import os
import json
import traceback
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
import base64
from io import BytesIO
from PIL import Image
import google.generativeai as genai

# ========================================
# 설정값
# ========================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')
GOOGLE_SHEETS_CREDS = os.environ.get('GOOGLE_SHEETS_CREDS')
GOOGLE_SHEET_URL = os.environ.get('GOOGLE_SHEET_URL')

# Gemini 설정
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

POSTS_PER_DAY = 3
INSTAGRAM_POSTS_PER_DAY = 3

MODE = os.environ.get('MODE', 'generate')


# ========================================
# Google Sheets 연동
# ========================================
def get_sheets_client():
    """Google Sheets 클라이언트 생성"""
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        # JSON 키를 파일로 저장
        creds_dict = json.loads(GOOGLE_SHEETS_CREDS)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        return client
    except Exception as e:
        print(f"❌ Google Sheets 연결 실패: {e}")
        return None


def save_to_sheets(content_list):
    """생성된 콘텐츠를 Google Sheets에 저장"""
    try:
        print("\n📊 Google Sheets에 저장 중...")
        
        client = get_sheets_client()
        if not client:
            return False
        
        # 스프레드시트 열기
        sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1
        
        # 각 콘텐츠를 행으로 추가
        for content in content_list:
            row = [
                datetime.now().strftime('%Y-%m-%d %H:%M'),
                content['store'],
                content['title'],
                content['content'],
                ','.join(content['tags']),
                content.get('image_url', ''),
                '',  # 승인 컬럼 (비어있음)
                '',  # 발행완료 컬럼
                ''   # 발행URL 컬럼
            ]
            sheet.append_row(row)
        
        print(f"✅ {len(content_list)}개 콘텐츠 저장 완료")
        return True
        
    except Exception as e:
        print(f"❌ Google Sheets 저장 실패: {e}")
        traceback.print_exc()
        return False


def get_approved_posts():
    """승인된 글 가져오기"""
    try:
        print("\n📊 승인된 글 확인 중...")
        
        client = get_sheets_client()
        if not client:
            return []
        
        sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1
        rows = sheet.get_all_values()
        
        approved = []
        for idx, row in enumerate(rows[1:], start=2):  # 헤더 제외
            if len(row) >= 7 and row[6].strip().lower() in ['o', 'x', '✓', '✅', 'yes', 'y']:
                # 승인되었고 아직 발행 안 된 글
                if len(row) < 8 or not row[7]:  # 발행완료 컬럼이 비어있음
                    approved.append({
                        'row_index': idx,
                        'store': row[1],
                        'title': row[2],
                        'content': row[3],
                        'tags': row[4].split(','),
                        'image_url': row[5] if len(row) > 5 else ''
                    })
        
        print(f"✅ 승인된 글 {len(approved)}개 발견")
        return approved
        
    except Exception as e:
        print(f"❌ 승인된 글 확인 실패: {e}")
        traceback.print_exc()
        return []


def mark_as_published(row_index, post_url):
    """발행 완료 표시"""
    try:
        client = get_sheets_client()
        if not client:
            return False
        
        sheet = client.open_by_url(GOOGLE_SHEET_URL).sheet1
        sheet.update_cell(row_index, 8, '발행완료')
        sheet.update_cell(row_index, 9, post_url)
        
        return True
    except Exception as e:
        print(f"❌ 발행 완료 표시 실패: {e}")
        return False


# ========================================
# 이미지 처리
# ========================================
def get_free_image():
    """무료 이미지 가져오기 (Unsplash)"""
    try:
        print("  🖼️ 이미지 다운로드 중...")
        
        # Unsplash에서 랜덤 음식 이미지
        url = "https://source.unsplash.com/800x600/?food,snack,convenience"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("  ✅ 이미지 다운로드 완료")
            return response.content
        else:
            return None
            
    except Exception as e:
        print(f"  ❌ 이미지 다운로드 실패: {e}")
        return None


def upload_image_to_wordpress(image_data):
    """워드프레스에 이미지 업로드"""
    try:
        from wordpress_xmlrpc.methods import media
        from wordpress_xmlrpc.compat import xmlrpc_client
        
        print("  📤 이미지 업로드 중...")
        
        wp_url = f"{WORDPRESS_URL}/xmlrpc.php"
        wp = Client(wp_url, WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        # 이미지 업로드
        data = {
            'name': f'convenience_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg',
            'type': 'image/jpeg',
            'bits': xmlrpc_client.Binary(image_data)
        }
        
        response = wp.call(media.UploadFile(data))
        image_url = response['url']
        
        print(f"  ✅ 이미지 업로드 완료")
        return image_url
        
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
        
        prompt = f"""
당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{store_name}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
2. 본문: 800-1200자
3. 친근한 말투, MZ세대 스타일
4. 실제 있을법한 구체적인 제품 2-3개 소개
   - 제품명 예: "딸기 생크림 케이크", "불닭치즈볶음면 김밥", "제주 한라봉 에이드"
   - 가격대: 1,500원~5,000원
5. 각 제품마다 맛 후기, 조합 꿀팁, 별점 포함
6. SEO 키워드 자연스럽게 포함: 편의점신상, {store_name}, 꿀조합, 편스타그램

JSON 형식으로 답변:
{{
  "title": "제목 (이모지 포함)",
  "content": "본문 (HTML 태그 사용: <h2>, <p>, <strong>, <br> 등)",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"]
}}
"""
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 신상 전문 블로거입니다."},
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
        
        # 이미지 다운로드
        image_data = get_free_image()
        if image_data:
            image_url = upload_image_to_wordpress(image_data)
            result['image_url'] = image_url or ''
        else:
            result['image_url'] = ''
        
        print(f"  ✅ 블로그 글 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 블로그 글 생성 실패: {e}")
        traceback.print_exc()
        return None


def generate_instagram_post(store_name):
    """AI로 인스타그램 캡션 생성"""
    try:
        print(f"  📱 {store_name} 인스타 캡션 생성 중...")
        
        prompt = f"""
당신은 팔로워 10만 이상의 인기 편의점 인스타그램 계정 운영자입니다.
{store_name}의 신상 제품을 소개하는 인스타그램 게시물을 작성해주세요.

요구사항:
1. 캡션: 3-5줄, 이모지 풍부하게 사용
2. MZ세대 말투
3. 구체적인 제품 1-2개 언급 (제품명 + 가격)
4. 해시태그: 15-20개

JSON 형식으로 답변:
{{
  "caption": "캡션 내용",
  "hashtags": "#편의점신상 #태그2 ..."
}}
"""
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 신상 전문 인스타그래머입니다."},
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
        
        print(f"  ✅ 인스타 캡션 생성 완료")
        return result
        
    except Exception as e:
        print(f"  ❌ 인스타 캡션 생성 실패: {e}")
        traceback.print_exc()
        return None


# ========================================
# 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags, image_url=''):
    """워드프레스에 글 발행"""
    try:
        print(f"  📤 워드프레스 발행 중: {title[:30]}...")
        
        # 이미지가 있으면 본문 맨 위에 추가
        if image_url:
            content = f'<img src="{image_url}" alt="{title}" style="width:100%; height:auto; margin-bottom:20px;" />\n\n{content}'
        
        wp_url = f"{WORDPRESS_URL}/xmlrpc.php"
        wp = Client(wp_url, WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {
            'post_tag': tags,
            'category': ['편의점']
        }
        post.post_status = 'publish'
        
        post_id = wp.call(NewPost(post))
        post_url = f"{WORDPRESS_URL}/?p={post_id}"
        
        print(f"  ✅ 워드프레스 발행 성공: {post_url}")
        return {'success': True, 'url': post_url, 'post_id': post_id}
        
    except Exception as e:
        print(f"  ❌ 워드프레스 발행 실패: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


# ========================================
# 슬랙 알림
# ========================================
def send_slack_message(message):
    """슬랙 메시지 전송"""
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json={'text': message},
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"  ❌ 슬랙 전송 실패: {e}")
        return False


def send_instagram_to_slack(caption, hashtags, store_name):
    """인스타그램 콘텐츠를 슬랙으로 전송"""
    try:
        message = f"""
📱 *인스타그램 콘텐츠 준비 완료* ({store_name})

*캡션:*
{caption}

*해시태그:*
{hashtags}

---
✅ 스마트폰에서 인스타그램 앱을 열어 위 내용을 복사/붙여넣기 하세요!
"""
        return send_slack_message(message)
        
    except Exception as e:
        print(f"  ❌ 슬랙 전송 실패: {e}")
        return False


# ========================================
# 메인 함수
# ========================================
def generate_mode():
    """콘텐츠 생성 모드"""
    print("=" * 60)
    print(f"🚀 콘텐츠 생성 시작: {datetime.now()}")
    print("=" * 60)
    
    stores = ['GS25', 'CU', '세븐일레븐', 'emart24']
    blog_contents = []
    instagram_success = 0
    
    try:
        # 워드프레스 콘텐츠 생성
        print(f"\n📝 워드프레스 블로그 글 {POSTS_PER_DAY}개 생성 중...")
        print("-" * 60)
        
        for i in range(POSTS_PER_DAY):
            store = stores[i % len(stores)]
            print(f"\n[{i+1}/{POSTS_PER_DAY}] {store} 글 작성 중...")
            
            content = generate_blog_post(store)
            if content:
                content['store'] = store
                blog_contents.append(content)
        
        # Google Sheets에 저장
        if blog_contents:
            save_to_sheets(blog_contents)
        
        # 인스타그램 콘텐츠 생성
        print(f"\n📱 인스타그램 콘텐츠 {INSTAGRAM_POSTS_PER_DAY}개 생성 중...")
        print("-" * 60)
        
        for i in range(INSTAGRAM_POSTS_PER_DAY):
            store = stores[i % len(stores)]
            print(f"\n[{i+1}/{INSTAGRAM_POSTS_PER_DAY}] {store} 인스타 콘텐츠 작성 중...")
            
            instagram_content = generate_instagram_post(store)
            if instagram_content:
                if send_instagram_to_slack(instagram_content['caption'], instagram_content['hashtags'], store):
                    instagram_success += 1
        
        # 슬랙 알림
        summary = f"""
🎉 *콘텐츠 생성 완료!*

📝 *워드프레스:* {len(blog_contents)}개 생성 완료
   → Google Sheets에서 확인 후 승인하세요!
   → {GOOGLE_SHEET_URL}

📱 *인스타그램:* {instagram_success}개 준비 완료

⏰ 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        send_slack_message(summary)
        
        print("\n✅ 콘텐츠 생성 완료!")
        print(f"📊 Google Sheets에서 확인하세요: {GOOGLE_SHEET_URL}")
        
    except Exception as e:
        error_msg = f"🚨 *콘텐츠 생성 중 오류*\n\n```{str(e)}```"
        send_slack_message(error_msg)
        print(f"\n❌ 오류: {e}")
        traceback.print_exc()


def publish_mode():
    """승인된 글 발행 모드"""
    print("=" * 60)
    print(f"📤 승인된 글 발행 시작: {datetime.now()}")
    print("=" * 60)
    
    try:
        approved_posts = get_approved_posts()
        
        if not approved_posts:
            print("✅ 승인된 글이 없습니다.")
            return
        
        published = 0
        for post in approved_posts:
            print(f"\n발행 중: {post['title'][:30]}...")
            
            result = publish_to_wordpress(
                post['title'],
                post['content'],
                post['tags'],
                post.get('image_url', '')
            )
            
            if result['success']:
                mark_as_published(post['row_index'], result['url'])
                published += 1
                
                # 슬랙 알림
                msg = f"✅ *발행 완료*\n제목: {post['title']}\nURL: {result['url']}"
                send_slack_message(msg)
        
        print(f"\n✅ {published}개 글 발행 완료!")
        
    except Exception as e:
        error_msg = f"🚨 *발행 중 오류*\n\n```{str(e)}```"
        send_slack_message(error_msg)
        print(f"\n❌ 오류: {e}")
        traceback.print_exc()


def main():
    """메인 함수"""
    if MODE == 'publish':
        publish_mode()
    else:
        generate_mode()


if __name__ == "__main__":
    main()
