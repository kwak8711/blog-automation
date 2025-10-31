import os
import json
import traceback
import requests
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
# 💡 NewPost 외에 GetPost를 추가로 import 합니다.
from wordpress_xmlrpc.methods.posts import NewPost, EditPost, GetPost
from wordpress_xmlrpc.methods.taxonomies import GetTerms
import time
from typing import Optional, Dict, List, Any

# =========================
# 설정 (환경변수)
# =========================
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')

# AI 선택 (AUTO = Gemini→Groq→OpenAI 순)
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'AUTO')

# 버튼 링크용
INSTAGRAM_PROFILE_URL = os.environ.get('INSTAGRAM_PROFILE_URL', 'https://instagram.com/')
NAVER_BLOG_URL = os.environ.get('NAVER_BLOG_URL', 'https://blog.naver.com/')

POSTS_PER_DAY = 1 # 1개씩

KST = ZoneInfo('Asia/Seoul')

# =========================
# 편의점 설정 (유지)
# =========================
STORES = {
    'GS25': {'country': 'kr', 'name_kr': 'GS25', 'name_jp': '', 'category': '한국편의점'},
    'CU': {'country': 'kr', 'name_kr': 'CU', 'name_jp': '', 'category': '한국편의점'},
    'SEVENELEVEN_KR': {'country': 'kr', 'name_kr': '세븐일레븐', 'name_jp': '', 'category': '한국편의점'},
    'SEVENELEVEN_JP': {'country': 'jp', 'name_kr': '세븐일레븐', 'name_jp': 'セブンイレブン', 'category': '일본편의점'},
    'FAMILYMART_JP': {'country': 'jp', 'name_kr': '패밀리마트', 'name_jp': 'ファミリーマート', 'category': '일본편의점'},
    'LAWSON_JP': {'country': 'jp', 'name_kr': '로손', 'name_jp': 'ローソン', 'category': '일본편의점'},
}

# =========================
# 콘텐츠 정리 함수 (유지)
# =========================

def clean_content_for_wordpress(content: str) -> str:
    """
    AI가 생성한 텍스트의 줄바꿈을 워드프레스용 HTML 단락 태그로 변환하여
    콘텐츠가 '이상하게' 보이는 것을 방지합니다.
    """
    if not content:
        return ""
    
    # 1. 이미 HTML 태그가 포함되어 있다면 (AI가 잘 만들었다고 가정) 그대로 반환합니다.
    if re.search(r'<(p|h[1-6]|div|ul|ol|table|br)', content, re.IGNORECASE):
        return content.replace('\r\n', '\n')
    
    # 2. 순수 텍스트인 경우: 이중 줄바꿈(\n\n)을 단락(<p>)으로 변환합니다.
    content = content.replace('\r\n', '\n')
    paragraphs = content.split('\n\n')
    
    html_content = ""
    for p in paragraphs:
        p_trimmed = p.strip()
        if p_trimmed:
            p_with_br = p_trimmed.replace('\n', '<br>')
            html_content += f"<p>{p_with_br}</p>\n"
            
    return html_content.strip()


# =========================
# 워드프레스 발행 함수 (URL 획득 로직 강화)
# =========================

def publish_post_to_wordpress(post_data: Dict[str, Any]) -> Optional[str]:
    """워드프레스에 글을 발행하고 정확한 URL을 반환합니다."""
    if not (WORDPRESS_URL and WORDPRESS_USERNAME and WORDPRESS_PASSWORD):
        print("⚠️ 워드프레스 설정(URL/Username/Password)이 누락되었습니다.")
        return None

    try:
        # XML-RPC 클라이언트 초기화 시, WORDPRESS_URL은 블로그의 루트 URL이어야 합니다.
        print(f"🌐 워드프레스 접속 시도: {WORDPRESS_URL}")
        wp = Client(WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        post = WordPressPost()
        post.title = post_data['title']
        post.content = clean_content_for_wordpress(post_data['content'])
        post.post_status = 'publish'
        post.terms_names = {
            'category': [post_data['category'], post_data['country_category']],
            'post_tag': [f"{post_data['store_name']} 신상", post_data['country_category']]
        }
        post.custom_fields = []
        if post_data.get('instagram_keyword'):
             post.custom_fields.append({'key': 'instagram_keyword', 'value': post_data['instagram_keyword']})

        print(f"✍️ 글 발행 시도: {post.title[:50]}...")
        post_id = wp.call(NewPost(post))
        
        # 발행 후 ID로 포스트 객체를 다시 가져옵니다.
        print(f"🔎 발행된 Post ID {post_id}로 정확한 URL 조회 중...")
        published_post = wp.call(GetPost(post_id))
        
        post_url = None
        if published_post and published_post.link:
            post_url = published_post.link
            print(f"✅ URL 조회 성공: {post_url}")
        else:
            # GetPost 실패 또는 link가 없는 경우
            # 이 경우 워드프레스 설정(퍼머링크)에 따라 기본 URL을 구성합니다.
            post_url = f"{WORDPRESS_URL}?p={post_id}"
            print(f"⚠️ GetPost 실패 또는 link 필드 누락. 기본 URL 구성: {post_url}")
            
        if post_url == WORDPRESS_URL or post_url == WORDPRESS_URL + '/':
             # 여전히 메인 페이지 링크라면, 문제가 있음을 명시합니다.
             print(f"❌ 생성된 링크가 메인 URL과 동일합니다. 워드프레스 퍼머링크 설정을 확인하세요.")
             
        return post_url

    except Exception as e:
        # 접속 실패나 XML-RPC 에러 시
        print(f"❌ 워드프레스 발행/접속 중 에러 발생: {e}")
        traceback.print_exc()
        return None

# =========================
# 기타 도우미 함수 (유지)
# =========================

def send_slack(message: str):
    """Slack으로 알림을 보냅니다."""
    if not SLACK_WEBHOOK_URL:
        print("⚠️ Slack Webhook URL이 누락되었습니다. 알림을 건너뜁니다.")
        return

    try:
        payload = {
            "text": message,
            "username": "블로그 자동화 봇",
            "icon_emoji": ":robot_face:"
        }
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()
        print("🔔 Slack 알림 전송 완료.")
    except Exception as e:
        print(f"❌ Slack 알림 전송 실패: {e}")
        traceback.print_exc()

def load_post_content(hour: int) -> Optional[Dict[str, Any]]:
    """시간대에 맞는 발행할 글을 JSON 파일에서 불러옵니다. (임시 로직)"""
    # 실제 시스템에서는 DB나 파일 시스템에서 예약된 글을 조회해야 합니다.
    # 여기서는 임시 JSON 파일을 읽는다고 가정하고 더미 데이터를 반환합니다.
    try:
        print(f"🔍 발행 대기 글 로드 중... (시간대: {hour}시)")
        # 더미 데이터에서는 'url' 필드를 제거했습니다. 이제 발행 시점에 정확히 생성됩니다.
        return {
            'store_key': 'GS25', 
            'title': f'[{hour}시 발행] GS25 신상 대박! - 쫀득한 마카롱 리뷰',
            'content': "안녕하세요! 푸드 블로거입니다.\n\n오늘 GS25에서 역대급 신상이 나왔어요. 바로 쫀득한 마카롱입니다.\n\n겉은 바삭하고 속은 촉촉한 것이 일품입니다. 특히 초코맛은 정말 진해요. 꼭 드셔보세요!\n\n#GS25 #신상리뷰 #마카롱",
            'category': '디저트',
            'country_category': '한국편의점',
            'store_name': 'GS25',
            'full_text': '인스타 본문용 전체 텍스트입니다.'
        }
    except Exception as e:
        print(f"❌ 글 로드 중 에러: {e}")
        return None

# =========================
# 메인 실행 함수 (유지)
# =========================
def main():
    """현재 시간에 맞춰 예약된 글을 발행하고 Slack 알림을 보냅니다."""
    current_time_kst = datetime.now(KST)
    current_hour = current_time_kst.hour
    
    time_slot_map = {
        8: ("아침 8시", "GS25", "kr"),
        9: ("아침 9시", "세븐일레븐", "jp"),
        12: ("점심 12시", "CU", "kr"),
        13: ("점심 1시", "패밀리마트", "jp"),
        20: ("저녁 8시", "세븐일레븐", "kr"),
        21: ("저녁 9시", "로손", "jp")
    }
    
    if current_hour not in time_slot_map:
        print(f"⚠️ 현재 시간({current_hour}시)은 알림 시간이 아닙니다. 종료합니다.")
        return
    
    time_slot, store_name, country = time_slot_map[current_hour]
    flag = "🇯🇵" if country == "jp" else "🇰🇷"
    
    # 1. 발행할 글 로드
    post_data = load_post_content(current_hour)
    
    if not post_data:
        print("❌ 현재 시간대에 발행할 글 내용이 없습니다. 작업 취소.")
        return

    # 2. 워드프레스 발행
    post_url = publish_post_to_wordpress(post_data)
    
    # post_data에 발행 URL 업데이트 (이제 정확한 URL이 할당됨)
    if post_url:
        post_data['url'] = post_url
        
    # 3. Slack 알림 전송
    message = f"🎉 *{time_slot} 글 발행 완료!*\n\n{flag} *{store_name}* 글이 방금 발행되었어요!\n"
    
    if 'url' in post_data and post_data['url']:
        message += f"━━━━━━━━━━━━━━━━━━\n📝 *제목:* {post_data['title']}\n🔗 *링크:* {post_data['url']}\n━━━━━━━━━━━━━━━━━━\n"
    else:
        message += "❌ 워드프레스 발행에 실패했거나 URL을 가져오지 못했습니다.\n"
        
    message += "\n📌 *할 일:*\n1️⃣ 블로그 링크 접속해서 본문 최종 확인\n2️⃣ 아래 인스타 본문 복사 → 인스타에 붙여넣기\n3️⃣ 사진 첨부 후 업로드!\n"
    
    send_slack(message)
    
    # 인스타 본문용 추가 알림 (post_data['full_text']가 있다고 가정)
    if post_data.get('full_text'):
        text_content = post_data['full_text']
        if len(text_content) > 2800:
            text_content = text_content[:2800] + "\n\n... (이하 생략)"
        
        text_message = f"⬇️ *인스타그램 본문 (복사용)* ⬇️\n\n```\n{text_content}\n```"
        send_slack(text_message)
        
    print("\n✅ 모든 작업 완료.")


if __name__ == "__main__":
    main()
