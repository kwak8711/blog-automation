import requests
from bs4 import BeautifulSoup
import openai
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
import json
from datetime import datetime
import config
import time
import traceback

# OpenAI 설정
openai.api_key = config.OPENAI_API_KEY

def send_slack_message(message, blocks=None):
    """슬랙으로 메시지 전송"""
    try:
        payload = {"text": message}
        if blocks:
            payload["blocks"] = blocks
        
        response = requests.post(
            config.SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"슬랙 전송 실패: {e}")
        return False

def crawl_convenience_store_with_retry(url, store_name, max_retries=3):
    """편의점 신상 정보 크롤링 (재시도 로직 포함)"""
    for attempt in range(max_retries):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 간단한 텍스트 추출 (실제로는 각 사이트별 맞춤 파싱 필요)
            text_content = soup.get_text()[:2000]  # 처음 2000자
            
            print(f"✅ {store_name} 크롤링 성공 (시도 {attempt + 1})")
            return {
                'store': store_name,
                'content': text_content,
                'url': url,
                'crawled_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ {store_name} 크롤링 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)  # 5초 대기 후 재시도
            else:
                return None
    
    return None

def generate_blog_post(store_data):
    """AI로 블로그 글 생성"""
    try:
        prompt = f"""
당신은 편의점 신상 전문 블로거입니다.
아래 {store_data['store']} 정보를 바탕으로 블로그 글을 작성해주세요.

정보: {store_data['content'][:500]}

요구사항:
1. 제목: 클릭하고 싶은 제목 (30자 이내)
2. 본문: 800-1000자
3. 친근한 말투
4. 실제 제품이 있다면 그것을 중심으로, 없다면 일반적인 편의점 신상 트렌드로 작성
5. SEO 키워드 자연스럽게 포함

JSON 형식으로 답변:
{{
  "title": "제목",
  "content": "본문 내용",
  "tags": ["태그1", "태그2", "태그3"]
}}
"""
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 편의점 신상 전문 블로거입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            timeout=60
        )
        
        result = json.loads(response.choices[0].message.content)
        print(f"✅ AI 글 생성 성공: {result['title']}")
        return result
        
    except Exception as e:
        print(f"❌ AI 글 생성 실패: {e}")
        traceback.print_exc()
        return None

def generate_instagram_post(store_data):
    """AI로 인스타 캡션 생성"""
    try:
        prompt = f"""
당신은 인스타그램 편의점 계정 운영자입니다.
아래 {store_data['store']} 정보를 바탕으로 인스타그램 캡션을 작성해주세요.

정보: {store_data['content'][:500]}

요구사항:
1. 캡션: 3-5줄, 이모지 포함
2. 해시태그: 10-15개
3. 친근하고 MZ세대 감성
4. 실제 제품이 있다면 그것을 중심으로, 없다면 일반적인 편의점 신상으로 작성

JSON 형식으로 답변:
{{
  "caption": "캡션 내용",
  "hashtags": "#편의점신상 #GS25 ..."
}}
"""
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 인스타그램 편의점 계정 운영자입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            timeout=60
        )
        
        result = json.loads(response.choices[0].message.content)
        print(f"✅ 인스타 캡션 생성 성공")
        return result
        
    except Exception as e:
        print(f"❌ 인스타 캡션 생성 실패: {e}")
        return None

def publish_to_wordpress(post_data):
    """워드프레스에 자동 발행"""
    try:
        client = Client(
            f"{config.WORDPRESS_URL}/xmlrpc.php",
            config.WORDPRESS_USERNAME,
            config.WORDPRESS_PASSWORD
        )
        
        post = WordPressPost()
        post.title = post_data['title']
        post.content = post_data['content']
        post.terms_names = {
            'post_tag': post_data['tags'],
            'category': ['편의점']
        }
        post.post_status = 'publish'
        
        post_id = client.call(NewPost(post))
        
        print(f"✅ 워드프레스 발행 성공! Post ID: {post_id}")
        return {'success': True, 'post_id': post_id, 'title': post_data['title']}
        
    except Exception as e:
        print(f"❌ 워드프레스 발행 실패: {e}")
        traceback.print_exc()
        return {'success': False, 'error': str(e)}

def send_instagram_to_slack(instagram_posts):
    """슬랙으로 인스타 콘텐츠 전송"""
    try:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📱 오늘의 인스타그램 콘텐츠 ({len(instagram_posts)}개)"
                }
            },
            {
                "type": "divider"
            }
        ]
        
        for idx, post in enumerate(instagram_posts, 1):
            blocks.extend([
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*콘텐츠 {idx}*\n\n{post['caption']}\n\n{post['hashtags']}"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 위 내용을 복사해서 인스타그램 앱에 붙여넣으세요"
                        }
                    ]
                },
                {
                    "type": "divider"
                }
            ])
        
        send_slack_message("인스타그램 콘텐츠가 준비되었습니다!", blocks)
        print(f"✅ 슬랙 전송 완료: {len(instagram_posts)}개 콘텐츠")
        
    except Exception as e:
        print(f"❌ 슬랙 전송 실패: {e}")

def main():
    """메인 실행 함수"""
    print("=" * 50)
    print(f"🚀 블로그 자동화 시작: {datetime.now()}")
    print("=" * 50)
    
    try:
        # 1. 편의점 정보 크롤링
        print("\n📡 1단계: 편의점 신상 정보 수집 중...")
        crawled_data = []
        for store_name, url in config.CRAWL_URLS.items():
            data = crawl_convenience_store_with_retry(url, store_name)
            if data:
                crawled_data.append(data)
            time.sleep(2)  # 서버 부담 방지
        
        if not crawled_data:
            raise Exception("모든 크롤링 실패")
        
        print(f"✅ 총 {len(crawled_data)}개 편의점 정보 수집 완료")
        
        # 2. 워드프레스 글 생성 및 발행
        print(f"\n✍️ 2단계: 워드프레스 글 {config.POSTS_PER_DAY}개 생성 및 발행 중...")
        wordpress_results = []
        
        for i in range(min(config.POSTS_PER_DAY, len(crawled_data))):
            store_data = crawled_data[i]
            blog_post = generate_blog_post(store_data)
            
            if blog_post:
                result = publish_to_wordpress(blog_post)
                wordpress_results.append(result)
                time.sleep(3)  # API 제한 방지
        
        # 3. 인스타그램 콘텐츠 생성
        print(f"\n📱 3단계: 인스타그램 콘텐츠 {config.INSTAGRAM_POSTS_PER_DAY}개 생성 중...")
        instagram_posts = []
        
        for i in range(min(config.INSTAGRAM_POSTS_PER_DAY, len(crawled_data))):
            store_data = crawled_data[i]
            insta_post = generate_instagram_post(store_data)
            
            if insta_post:
                instagram_posts.append(insta_post)
                time.sleep(2)
        
        # 4. 슬랙으로 인스타 콘텐츠 전송
        if instagram_posts:
            print(f"\n📤 4단계: 슬랙으로 인스타 콘텐츠 전송 중...")
            send_instagram_to_slack(instagram_posts)
        
        # 5. 결과 요약 전송
        success_count = sum(1 for r in wordpress_results if r['success'])
        summary = f"""
✅ *작업 완료 요약*

📝 워드프레스: {success_count}/{len(wordpress_results)}개 발행 성공
📱 인스타그램: {len(instagram_posts)}개 콘텐츠 준비 완료

발행된 글:
{chr(10).join([f"- {r['title']}" for r in wordpress_results if r['success']])}

⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        send_slack_message(summary)
        
        print("\n" + "=" * 50)
        print("🎉 모든 작업 완료!")
        print("=" * 50)
        
    except Exception as e:
        error_message = f"🚨 *치명적 에러 발생*\n\n```{str(e)}```\n\n{traceback.format_exc()}"
        send_slack_message(error_message)
        print(f"\n❌ 에러 발생: {e}")
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
