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

# 새로 추가: 버튼 링크용
INSTAGRAM_PROFILE_URL = os.environ.get('INSTAGRAM_PROFILE_URL', 'https://instagram.com/')
NAVER_BLOG_URL        = os.environ.get('NAVER_BLOG_URL', 'https://blog.naver.com/')

POSTS_PER_DAY = 2
INSTAGRAM_POSTS_PER_DAY = 2

# 편의점 공식 사이트 URL
STORE_URLS = {
    'GS25': 'https://gs25.gsretail.com/gscvs/ko/products/youus-freshfood',
    'CU': 'https://cu.bgfretail.com/product/product.do?category=product&depth=1&sf=N',
    '세븐일레븐': 'https://www.7-eleven.co.kr/product/presentList.asp'
}

JST = ZoneInfo('Asia/Tokyo')

# ========================================
# 예약 슬롯 계산: 오늘/내일 08:00, 20:00
# ========================================
def next_slots_8am_8pm(count=2):
    """
    지금 시각 기준으로 가장 가까운 08:00, 20:00부터 순서대로 count개 반환 (JST)
    반환: [datetime(JST), ...]
    """
    now = datetime.now(JST)
    today_8 = now.replace(hour=8,  minute=0, second=0, microsecond=0)
    today_20 = now.replace(hour=20, minute=0, second=0, microsecond=0)

    candidates = []
    if now <= today_8:
        candidates.append(today_8)
        candidates.append(today_20)
    elif now <= today_20:
        candidates.append(today_20)
        candidates.append(today_8 + timedelta(days=1))
    else:
        candidates.append(today_8 + timedelta(days=1))
        candidates.append(today_20 + timedelta(days=1))

    # 필요 개수 초과 시 자른다. 부족하면 다음날 슬롯 추가
    while len(candidates) < count:
        base = candidates[-2] + timedelta(days=1)
        candidates.extend([base.replace(hour=8), base.replace(hour=20)])
    return candidates[:count]

# ========================================
# 이미지 크롤링
# ========================================
def crawl_product_images(store_name):
    """여러 소스에서 신상 이미지 크롤링 (편의점 공식 + 구글 이미지)"""
    try:
        print(f"  🖼️ {store_name} 이미지 검색 중...")
        all_images = []

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        # 1) 편의점 공식
        url = STORE_URLS.get(store_name)
        if url:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                soup = BeautifulSoup(response.content, 'html.parser')
                img_tags = soup.find_all('img', limit=10)
                for img in img_tags:
                    src = img.get('src') or img.get('data-src')
                    if not src:
                        continue
                    if not src.startswith('http'):
                        if store_name == 'CU':
                            src = 'https://cu.bgfretail.com' + src
                        elif store_name == '세븐일레븐':
                            src = 'https://www.7-eleven.co.kr' + src
                        elif store_name == 'GS25':
                            src = 'https://gs25.gsretail.com' + src
                    if 'product' in src.lower() or 'item' in src.lower():
                        all_images.append(src)
            except:
                pass

        # 2) 구글 이미지 (백업)
        try:
            search_query = f"{store_name} 편의점 신상"
            google_url = f"https://www.google.com/search?q={search_query}&tbm=isch"
            response = requests.get(google_url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            img_tags = soup.find_all('img', limit=5)
            for img in img_tags:
                src = img.get('src') or img.get('data-src')
                if src and src.startswith('http') and 'gstatic' not in src:
                    all_images.append(src)
        except:
            pass

        # 3) Unsplash 백업
        try:
            unsplash_url = "https://source.unsplash.com/800x600/?convenience,store,snack,food"
            all_images.append(unsplash_url)
        except:
            pass

        # 중복 제거
        all_images = list(dict.fromkeys(all_images))
        print(f"  ✅ {len(all_images)}개 이미지 발견")
        return all_images[:5]
    except Exception as e:
        print(f"  ❌ 크롤링 실패: {e}")
        return []

def download_image(image_url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(image_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.content
        return None
    except:
        return None

def upload_image_to_wordpress(image_data, filename='product.jpg'):
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
    try:
        print(f"  📝 {store_name} 블로그 글 생성 중...")
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

        prompt = f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{store_name}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.
... (중략: 기존 프롬프트 동일) ...
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

        # 이미지
        image_urls = crawl_product_images(store_name)
        result['crawled_images'] = image_urls

        if image_urls:
            img_data = download_image(image_urls[0])
            if img_data:
                img_url = upload_image_to_wordpress(img_data, f'{store_name}_{datetime.now(JST).strftime("%Y%m%d")}.jpg')
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
        result['image_urls'] = crawl_product_images(store_name)
        print(f"  ✅ 완료")
        return result
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None

# ========================================
# 워드프레스 발행 (예약 발행 지원)
# ========================================
def publish_to_wordpress(title, content, tags, image_url='', scheduled_dt_jst=None):
    """워드프레스 발행/예약발행
       - scheduled_dt_jst: Asia/Tokyo 기준 예약 시각 (datetime, tz-aware) 주면 예약 발행
    """
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

        if scheduled_dt_jst:
            # WordPress는 로컬(post.date)과 GMT(post.date_gmt) 모두 세팅하면 안전
            dt_jst = scheduled_dt_jst.astimezone(JST)
            dt_utc = dt_jst.astimezone(timezone.utc)
            post.post_status = 'future'
            post.date = dt_jst.replace(tzinfo=None)      # 라이브러리 특성상 naive로 전달
            post.date_gmt = dt_utc.replace(tzinfo=None)  # GMT도 명시
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
# 슬랙 알림 (텍스트/이미지/버튼)
# ========================================
def send_slack(message):
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={'text': message}, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_slack_with_image(message, image_url):
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

def send_slack_quick_actions(title="오늘의 업로드 바로가기 ✨"):
    """
    공주님 요청: 예쁜 버튼 2개 (인스타 / 네이버블로그)
    - Incoming Webhook + Block Kit 버튼(URL) 사용
    """
    try:
        payload = {
            "text": title,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{title}*\n\n가고 싶은 채널을 선택해 주세요 💖"
                    },
                    "accessory": {
                        "type": "image",
                        "image_url": "https://i.imgur.com/2q8hZ6T.png",
                        "alt_text": "Couchmallow"
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
        ok = (r.status_code == 200)
        print("  ✅ 슬랙 버튼 카드 전송" if ok else f"  ❌ 슬랙 버튼 실패: {r.text}")
        return ok
    except Exception as e:
        print(f"  ❌ 슬랙 버튼 전송 실패: {e}")
        return False

def send_instagram_to_slack(caption, hashtags, store, image_urls):
    try:
        image_text = ""
        if image_urls:
            for idx, url in enumerate(image_urls[:3], 1):
                image_text += f"\n🖼️ <{url}|이미지 {idx} 다운로드>"
        else:
            image_text = "\n⚠️ 이미지를 찾지 못했습니다."

        message = f"""📱 *{store} 인스타그램 콘텐츠*

*캡션:*
{caption}

*해시태그:*
{hashtags}

*이미지:*{image_text}

---
✅ *업로드 방법:*
1. 위 링크 클릭해서 이미지 다운로드
2. 인스타그램 앱 열기
3. 캡션 + 해시태그 복사
4. 이미지와 함께 업로드!
"""
        return send_slack(message)
    except Exception as e:
        print(f"  ❌ 슬랙 전송 실패: {e}")
        return False

# ========================================
# 메인
# ========================================
def main():
    print("=" * 60)
    print(f"🚀 편의점 신상 자동화 시작: {datetime.now(JST)}")
    print("=" * 60)

    stores = ['GS25', 'CU', '세븐일레븐']
    wp_results = []
    ig_results = []

    # 1) 오늘 기준 예약 슬롯 계산 (08:00, 20:00)
    slots = next_slots_8am_8pm(count=POSTS_PER_DAY)
    print(f"\n🕗 예약 슬롯: {[dt.strftime('%Y-%m-%d %H:%M') for dt in slots]} (JST)")

    # 2) 워드프레스 글 생성 + 예약발행
    print(f"\n📝 워드프레스 블로그 {POSTS_PER_DAY}개 *예약발행* 설정 중...")
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
                scheduled_dt_jst=scheduled_at
            )
        if result['success']:
            wp_results.append({
                'store': store,
                'title': content['title'],
                'url': result['url'],
                'post_id': result['post_id']
            })

            # ✅ 🔗 구글시트 즉시 로깅
            log_wp_post_to_sheet(
                post_id=result['post_id'],
                status='publish',
                title=content['title'],
                store=store,
                scheduled_at='',
                published_at=datetime.now(JST).strftime('%Y-%m-%d %H:%M'),
                url=result['url'],
                featured_image=content.get('featured_image', ''),
                tags=content.get('tags', [])
            )

        time.sleep(10)

    # 3) 인스타그램 콘텐츠 슬랙 전송 (승인 대기)
    print(f"\n📱 인스타그램 콘텐츠 {INSTAGRAM_POSTS_PER_DAY}개 생성 및 슬랙 전송 중...")
    print("-" * 60)
    for i in range(INSTAGRAM_POSTS_PER_DAY):
        store = stores[i % len(stores)]
        print(f"\n[{i+1}/{INSTAGRAM_POSTS_PER_DAY}] {store}")
        content = generate_instagram_post(store)
        if content:
            if send_instagram_to_slack(
                content.get('caption', ''),
                content.get('hashtags', ''),
                store,
                content.get('image_urls', [])
            ):
                ig_results.append({'store': store, 'status': '슬랙 전송 완료 (승인 대기)'})
        time.sleep(3)

    # 4) 요약 + 퀵액션 버튼
    summary = f"🎉 *자동화 완료!*\n\n📝 *워드프레스 예약발행:* {len(wp_results)}개"
    for r in wp_results:
        summary += f"\n   • {r['store']}: {r['title'][:30]}... ⏰ {r['when']}\n     → {r['url']}"
    summary += f"\n\n📱 *인스타그램 준비:* {len(ig_results)}개 (슬랙에서 확인 후 수동 업로드)"
    for r in ig_results:
        summary += f"\n   • {r['store']}: {r['status']}"
    summary += f"\n\n⏰ 완료 시간: {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')}"

    send_slack(summary)
    send_slack_quick_actions(title="업로드 채널 바로가기 ✨")
    print(f"\n✅ 전체 작업 완료!")
    print(summary)

if __name__ == "__main__":
    main()

    # =========================
# Google Sheets 로깅 유틸
# =========================
import gspread
from google.oauth2.service_account import Credentials

GOOGLE_SHEETS_ID = os.environ.get('GOOGLE_SHEETS_ID')
GOOGLE_SA_JSON   = os.environ.get('GOOGLE_SA_JSON')  # 서비스계정 JSON 파일 경로

SHEET_NAME = 'WP_POSTS'  # 시트 탭 이름

def _get_sheets_client():
    if not (GOOGLE_SHEETS_ID and GOOGLE_SA_JSON):
        raise RuntimeError('환경변수 GOOGLE_SHEETS_ID 또는 GOOGLE_SA_JSON 미설정')
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(GOOGLE_SA_JSON, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEETS_ID)
    try:
        ws = sh.worksheet(SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_NAME, rows=1000, cols=20)
        ws.append_row([
            "logged_at(JST)","post_id","status","title","store","scheduled_at(JST)",
            "published_at(JST)","url","featured_image","tags_csv"
        ])
    return ws

def log_wp_post_to_sheet(post_id:int, status:str, title:str, store:str, 
                         scheduled_at:str, published_at:str, url:str, featured_image:str, tags:list):
    """
    status: publish | future
    scheduled_at/published_at: 'YYYY-MM-DD HH:MM' 또는 '' 
    """
    try:
        ws = _get_sheets_client()
        ws.append_row([
            datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S'),
            str(post_id),
            status,
            title,
            store or '',
            scheduled_at or '',
            published_at or '',
            url or '',
            featured_image or '',
            ",".join(tags or [])
        ])
        print("  ✅ 구글시트 로깅 완료")
    except Exception as e:
        print("  ❌ 구글시트 로깅 실패:", e)

# =========================
# 과거 글 백필(전체 동기화)
# - WordPress REST API 사용
# =========================
from urllib.parse import urljoin
import math
import base64

def _wp_rest_get(path, page=1, per_page=100):
    """
    WordPress Application Password(또는 기본 비번)로 Basic Auth 권장
    - WORDPRESS_USERNAME, WORDPRESS_PASSWORD 사용
    """
    api_base = urljoin(WORDPRESS_URL if WORDPRESS_URL.endswith('/') else WORDPRESS_URL+'/', 'wp-json/wp/v2/')
    url = f"{api_base}{path}?per_page={per_page}&page={page}"
    auth = (WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
    r = requests.get(url, auth=auth, timeout=20)
    if r.status_code == 200:
        total = int(r.headers.get('X-WP-Total', '0') or 0)
        total_pages = int(r.headers.get('X-WP-TotalPages', '1') or 1)
        return r.json(), total, total_pages
    else:
        raise RuntimeError(f"REST 호출 실패 {r.status_code}: {r.text}")

def sync_all_wp_posts_to_sheet():
    """
    게시글 전체를 시트에 백필(중복 허용; 필요시 시트에서 post_id로 중복 제거)
    - 상태: publish/future/draft 등도 가져옴(필요시 상태 필터링 가능)
    """
    try:
        ws = _get_sheets_client()
        # 헤더가 없으면 생성 (안전장치)
        if ws.cell(1,1).value != "logged_at(JST)":
            ws.update('A1', [[
                "logged_at(JST)","post_id","status","title","store","scheduled_at(JST)",
                "published_at(JST)","url","featured_image","tags_csv"
            ]])
        page = 1
        per_page = 100
        while True:
            posts, total, total_pages = _wp_rest_get('posts', page=page, per_page=per_page)
            if not posts:
                break
            rows = []
            for p in posts:
                post_id = p.get('id')
                status  = p.get('status')  # 'publish'/'future'/'draft'
                title   = (p.get('title') or {}).get('rendered','').strip()
                link    = p.get('link','')
                # 날짜
                date_local = (p.get('date') or '')[:16].replace('T',' ')     # 워드프레스 로컬
                date_gmt   = (p.get('date_gmt') or '')[:16].replace('T',' ')
                scheduled_at = date_local if status == 'future' else ''
                published_at = date_local if status == 'publish' else ''
                # 대표 이미지
                feat = ''
                if p.get('featured_media'):
                    # 미디어 상세까지 내려면 /media/{id} 추가 호출 필요하지만, 간단히 링크 칼럼만
                    feat = str(p.get('featured_media'))
                # 태그 CSV
                tags_csv = ''
                tag_ids = p.get('tags') or []
                if tag_ids:
                    # 간단히 ID 리스트만 CSV로; 이름이 필요하면 /tags?include=... 추가 호출
                    tags_csv = ",".join(map(str, tag_ids))
                rows.append([
                    datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S'),
                    str(post_id), status, title, "",  # store는 알 수 없으니 공란
                    scheduled_at, published_at, link, feat, tags_csv
                ])
            if rows:
                ws.append_rows(rows, value_input_option='USER_ENTERED')
                print(f"  ✅ {page}/{total_pages} 페이지 기록 완료 ({len(rows)}건)")
            if page >= total_pages:
                break
            page += 1
        print("🎉 과거 글 백필 완료!")
    except Exception as e:
        print("❌ 백필 실패:", e)

