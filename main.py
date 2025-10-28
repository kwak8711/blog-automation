import os
import json
import traceback
import requests
from datetime import datetime
from openai import OpenAI
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

# ========================================
# 설정값 가져오기
# ========================================
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY, timeout=60.0, max_retries=2)

# 설정
POSTS_PER_DAY = 2  # 워드프레스 글 개수
INSTAGRAM_POSTS_PER_DAY = 2  # 인스타 콘텐츠 개수


# ========================================
# 1. AI 콘텐츠 생성
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
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 편의점 신상 전문 블로거입니다. 매일 새로운 제품을 리뷰하며, 독자들에게 유용한 정보를 제공합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
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
2. MZ세대 말투 (ㄹㅇ, 진짜, 미쳤다, 너무 맛있어서 등)
3. 구체적인 제품 1-2개 언급 (제품명 + 가격)
4. 해시태그: 15-20개 (편의점신상, {store_name}, 편스타그램, 꿀조합 등 포함)

JSON 형식으로 답변:
{{
  "caption": "캡션 내용 (이모지 포함)",
  "hashtags": "#편의점신상 #태그2 #태그3 ..."
}}
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 편의점 신상 전문 인스타그래머입니다. 매일 새로운 제품을 소개하며 팔로워들의 반응이 뜨겁습니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.95,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        print(f"  ✅ 인스타 캡션 생성 완료")
        return result
        
    except Exception as e:
        print(f"  ❌ 인스타 캡션 생성 실패: {e}")
        traceback.print_exc()
        return None


# ========================================
# 2. 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags):
    """워드프레스에 글 발행"""
    try:
        print(f"  📤 워드프레스 발행 중: {title[:30]}...")
        
        # 워드프레스 클라이언트 생성
        wp_url = f"{WORDPRESS_URL}/xmlrpc.php"
        wp = Client(wp_url, WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        # 글 작성
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {
            'post_tag': tags,
            'category': ['편의점']
        }
        post.post_status = 'publish'  # 즉시 발행
        
        # 발행
        post_id = wp.call(NewPost(post))
        
        post_url = f"{WORDPRESS_URL}/?p={post_id}"
        print(f"  ✅ 워드프레스 발행 성공: {post_url}")
        return {'success': True, 'url': post_url, 'post_id': post_id}
        
    except Exception as e:
        print(f"  ❌ 워드프레스 발행 실패: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


# ========================================
# 3. 슬랙 알림
# ========================================
def send_slack_message(message):
    """슬랙으로 메시지 전송"""
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
    """슬랙으로 인스타그램 콘텐츠 전송"""
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
        print(f"  ❌ 인스타 콘텐츠 슬랙 전송 실패: {e}")
        return False


# ========================================
# 4. 메인 실행 함수
# ========================================
def main():
    """메인 실행 함수"""
    print("=" * 60)
    print(f"🚀 편의점 블로그 자동화 시작: {datetime.now()}")
    print("=" * 60)
    
    # 통계
    wordpress_success = 0
    wordpress_failed = 0
    instagram_success = 0
    instagram_failed = 0
    
    try:
        # 편의점 리스트
        stores = ['GS25', 'CU', '세븐일레븐', 'emart24']
        
        # ========================================
        # 워드프레스 글 발행
        # ========================================
        print(f"\n📝 1단계: 워드프레스 블로그 글 {POSTS_PER_DAY}개 생성 중...")
        print("-" * 60)
        
        for i in range(POSTS_PER_DAY):
            store = stores[i % len(stores)]
            print(f"\n[{i+1}/{POSTS_PER_DAY}] {store} 글 작성 중...")
            
            # AI로 글 생성
            blog_content = generate_blog_post(store)
            
            if blog_content:
                # 워드프레스 발행
                result = publish_to_wordpress(
                    blog_content['title'],
                    blog_content['content'],
                    blog_content['tags']
                )
                
                if result['success']:
                    wordpress_success += 1
                else:
                    wordpress_failed += 1
            else:
                wordpress_failed += 1
        
        # ========================================
        # 인스타그램 콘텐츠 준비
        # ========================================
        print(f"\n📱 2단계: 인스타그램 콘텐츠 {INSTAGRAM_POSTS_PER_DAY}개 생성 중...")
        print("-" * 60)
        
        for i in range(INSTAGRAM_POSTS_PER_DAY):
            store = stores[i % len(stores)]
            print(f"\n[{i+1}/{INSTAGRAM_POSTS_PER_DAY}] {store} 인스타 콘텐츠 작성 중...")
            
            # AI로 캡션 생성
            instagram_content = generate_instagram_post(store)
            
            if instagram_content:
                # 슬랙으로 전송
                success = send_instagram_to_slack(
                    instagram_content['caption'],
                    instagram_content['hashtags'],
                    store
                )
                
                if success:
                    instagram_success += 1
                else:
                    instagram_failed += 1
            else:
                instagram_failed += 1
        
        # ========================================
        # 최종 결과 알림
        # ========================================
        print("\n" + "=" * 60)
        print("✅ 자동화 완료!")
        print("=" * 60)
        print(f"📝 워드프레스: {wordpress_success}개 성공, {wordpress_failed}개 실패")
        print(f"📱 인스타그램: {instagram_success}개 준비 완료, {instagram_failed}개 실패")
        
        # 슬랙 최종 알림
        summary = f"""
🎉 *오늘의 자동화 작업 완료!*

📝 *워드프레스:* {wordpress_success}개 발행 성공
📱 *인스타그램:* {instagram_success}개 콘텐츠 준비 완료

⏰ 완료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        send_slack_message(summary)
        
    except Exception as e:
        error_message = f"🚨 *자동화 실행 중 오류 발생*\n\n```{str(e)}```"
        send_slack_message(error_message)
        print(f"\n❌ 치명적 오류: {e}")
        traceback.print_exc()
        raise


# ========================================
# 실행
# ========================================
if __name__ == "__main__":
    main()
