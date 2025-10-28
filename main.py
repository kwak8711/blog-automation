import os
import json
import traceback
import requests
from datetime import datetime
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.compat import xmlrpc_client

# 설정
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')

POSTS_PER_DAY = 3
INSTAGRAM_POSTS_PER_DAY = 3


def generate_blog_post(store_name):
    """AI로 블로그 글 생성"""
    try:
        print(f"  📝 {store_name} 블로그 글 생성 중...")
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 신상 전문 블로거입니다."},
                {"role": "user", "content": f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{store_name}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내)
2. 본문: 800-1200자, 친근한 말투
3. 실제 있을법한 제품 2-3개 소개 (제품명 + 가격 1500-5000원)
4. SEO 키워드 포함: 편의점신상, {store_name}, 꿀조합

JSON 형식:
{{"title": "제목", "content": "본문", "tags": ["태그1", "태그2", "태그3"]}}"""}
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
        
        # 이미지
        img_data = get_free_image()
        if img_data:
            img_url = upload_image_to_wordpress(img_data)
            result['image_url'] = img_url or ''
        else:
            result['image_url'] = ''
        
        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return None


def generate_instagram_post(store_name):
    """AI로 인스타 캡션 생성"""
    try:
        print(f"  📱 {store_name} 인스타 생성 중...")
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 인스타 전문가입니다."},
                {"role": "user", "content": f"""{store_name} 신상 인스타 캡션 작성.
3-5줄, 이모지 사용, MZ세대 말투, 해시태그 15개.
JSON: {{"caption": "내용", "hashtags": "#태그들"}}"""}
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
        
        print(f"  ✅ 완료")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return None


def get_free_image():
    """무료 이미지"""
    try:
        url = "https://source.unsplash.com/800x600/?food,snack"
        response = requests.get(url, timeout=10)
        return response.content if response.status_code == 200 else None
    except:
        return None


def upload_image_to_wordpress(image_data):
    """이미지 업로드"""
    try:
        from wordpress_xmlrpc.methods import media
        
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        data = {
            'name': f'img_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg',
            'type': 'image/jpeg',
            'bits': xmlrpc_client.Binary(image_data)
        }
        
        response = wp.call(media.UploadFile(data))
        return response['url']
    except:
        return None


def publish_to_wordpress(title, content, tags, image_url=''):
    """워드프레스 발행"""
    try:
        print(f"  📤 발행 중: {title[:30]}...")
        
        if image_url:
            content = f'<img src="{image_url}" style="width:100%"/><br><br>{content}'
        
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {'post_tag': tags, 'category': ['편의점']}
        post.post_status = 'publish'
        
        post_id = wp.call(NewPost(post))
        url = f"{WORDPRESS_URL}/?p={post_id}"
        
        print(f"  ✅ 성공: {url}")
        return {'success': True, 'url': url}
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return {'success': False}


def send_slack(message):
    """슬랙 전송"""
    try:
        requests.post(SLACK_WEBHOOK_URL, json={'text': message}, timeout=10)
        return True
    except:
        return False


def send_instagram_to_slack(caption, hashtags, store):
    """인스타 슬랙 전송"""
    msg = f"📱 *{store} 인스타*\n\n{caption}\n\n{hashtags}"
    return send_slack(msg)


def main():
    """메인"""
    print("🚀 시작:", datetime.now())
    
    stores = ['GS25', 'CU', '세븐일레븐']
    wp_success = 0
    ig_success = 0
    
    # 워드프레스
    print(f"\n📝 블로그 {POSTS_PER_DAY}개 생성 중...")
    for i in range(POSTS_PER_DAY):
        store = stores[i % len(stores)]
        print(f"\n[{i+1}/{POSTS_PER_DAY}] {store}")
        
        content = generate_blog_post(store)
        if content:
            result = publish_to_wordpress(content['title'], content['content'], 
                                         content['tags'], content.get('image_url', ''))
            if result['success']:
                wp_success += 1
    
    # 인스타
    print(f"\n📱 인스타 {INSTAGRAM_POSTS_PER_DAY}개 생성 중...")
    for i in range(INSTAGRAM_POSTS_PER_DAY):
        store = stores[i % len(stores)]
        print(f"\n[{i+1}/{INSTAGRAM_POSTS_PER_DAY}] {store}")
        
        content = generate_instagram_post(store)
        if content:
            if send_instagram_to_slack(content.get('caption', ''), content.get('hashtags', ''), store):
                ig_success += 1
    
    # 완료
    summary = f"✅ 완료!\n워드프레스: {wp_success}개\n인스타: {ig_success}개"
    send_slack(summary)
    print(f"\n{summary}")


if __name__ == "__main__":
    main()
