import os
import json
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.methods import media
import random

# PIL 이미지 처리
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except:
    PIL_AVAILABLE = False
    print("⚠️ Pillow가 설치되지 않았습니다. 워터마크 기능이 비활성화됩니다.")

# =========================
# 환경변수
# =========================
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')

MODE = os.environ.get('MODE', 'generate')

KST = ZoneInfo('Asia/Seoul')

# Couchmallow 캐릭터 이미지 설정
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
CHARACTER_IMAGES = [
    "Couchmallow_AM_01_360_ivory.png",
    "Couchmallow_AM_04_360_ivory.png",
    "Couchmallow_AM_07_360_ivory.png",
]

# 환경변수 체크
print("=" * 60)
print("🔑 환경변수 체크")
print("=" * 60)
print(f"GEMINI_API_KEY: {'✅ 설정됨' if GEMINI_API_KEY else '❌ 없음'}")
print(f"GROQ_API_KEY: {'✅ 설정됨' if GROQ_API_KEY else '⚠️ 없음 (선택)'}")
print(f"OPENAI_API_KEY: {'✅ 설정됨' if OPENAI_API_KEY else '⚠️ 없음 (선택)'}")
print(f"SLACK_WEBHOOK_URL: {'✅ 설정됨' if SLACK_WEBHOOK_URL else '❌ 없음'}")
print(f"WORDPRESS_URL: {'✅ 설정됨' if WORDPRESS_URL else '❌ 없음'}")
print(f"WORDPRESS_USERNAME: {'✅ 설정됨' if WORDPRESS_USERNAME else '❌ 없음'}")
print(f"WORDPRESS_PASSWORD: {'✅ 설정됨' if WORDPRESS_PASSWORD else '❌ 없음'}")
print("=" * 60)
print()

# 필수 환경변수 체크
if not SLACK_WEBHOOK_URL:
    print("❌ SLACK_WEBHOOK_URL이 설정되지 않았습니다!")
    print("   GitHub Secrets에 추가해주세요.")
    
if not WORDPRESS_URL or not WORDPRESS_USERNAME or not WORDPRESS_PASSWORD:
    print("❌ 워드프레스 정보가 설정되지 않았습니다!")
    print("   WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_PASSWORD를 확인하세요.")

if not GEMINI_API_KEY and not GROQ_API_KEY and not OPENAI_API_KEY:
    print("❌ AI API 키가 하나도 설정되지 않았습니다!")
    print("   최소한 GEMINI_API_KEY는 설정해야 합니다.")
    exit(1)

# =========================
# 편의점 정보
# =========================
STORES = [
    {'key': 'GS25', 'name': 'GS25', 'country': 'kr', 'category': '한국편의점'},
    {'key': 'CU', 'name': 'CU', 'country': 'kr', 'category': '한국편의점'},
    {'key': '세븐일레븐', 'name': '세븐일레븐', 'name_jp': 'セブンイレブン', 'country': 'jp', 'category': '일본편의점'},
]

# =========================
# 🎨 Couchmallow 이미지 처리
# =========================
def pick_character_image():
    """assets에서 랜덤으로 캐릭터 이미지 선택"""
    available = []
    for img in CHARACTER_IMAGES:
        path = os.path.join(ASSETS_DIR, img)
        if os.path.exists(path):
            available.append(path)
    
    if not available:
        print("⚠️ assets 폴더에 이미지가 없습니다!")
        return None
    
    selected = random.choice(available)
    print(f"🎨 선택된 캐릭터: {os.path.basename(selected)}")
    return selected


def add_watermark(image_path, text="복제금지 / couchmallow / DO NOT COPY", opacity=68):
    """이미지에 워터마크 추가"""
    if not PIL_AVAILABLE:
        return image_path
    
    try:
        # 출력 디렉토리
        out_dir = os.path.join(ASSETS_DIR, "_watermarked")
        os.makedirs(out_dir, exist_ok=True)
        
        # 이미지 열기
        img = Image.open(image_path).convert("RGBA")
        width, height = img.size
        
        # 워터마크 레이어
        watermark = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(watermark)
        
        # 폰트 설정
        try:
            font_size = int(height * 0.034)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # 텍스트 크기 계산
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # 오른쪽 아래 위치
        margin = int(min(width, height) * 0.03)
        x = width - text_width - margin
        y = height - text_height - margin
        
        # 워터마크 그리기 (연보라색)
        draw.text((x, y), text, font=font, fill=(94, 73, 133, opacity))
        
        # 합성
        final = Image.alpha_composite(img, watermark)
        
        # 저장
        basename = os.path.basename(image_path)
        name, ext = os.path.splitext(basename)
        out_path = os.path.join(out_dir, f"{name}_wm.png")
        final.convert("RGB").save(out_path, "PNG")
        
        print(f"  ✅ 워터마크 추가 완료: {out_path}")
        return out_path
        
    except Exception as e:
        print(f"  ⚠️ 워터마크 실패, 원본 사용: {e}")
        return image_path


def upload_image_to_wordpress(wp_client, image_path):
    """워드프레스에 이미지 업로드"""
    try:
        with open(image_path, 'rb') as f:
            data = {
                'name': os.path.basename(image_path),
                'type': 'image/png',
                'bits': f.read(),
            }
        
        response = wp_client.call(media.UploadFile(data))
        url = response.get('url')
        print(f"  📤 이미지 업로드 성공: {url}")
        return url
        
    except Exception as e:
        print(f"  ❌ 이미지 업로드 실패: {e}")
        return None


# =========================
# AI 호출 (Gemini → Groq → OpenAI)
# =========================
def call_gemini(prompt):
    if not GEMINI_API_KEY:
        return None
    
    try:
        print("  🟢 Gemini 시도...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            }
        }
        
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        
        result_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        result = json.loads(result_text)
        
        if isinstance(result, list):
            result = result[0] if result else None
        
        print("  ✅ Gemini 성공!")
        return result
        
    except Exception as e:
        print(f"  ⚠️ Gemini 실패: {str(e)[:100]}")
        return None


def call_groq(prompt):
    if not GROQ_API_KEY:
        return None
    
    try:
        print("  🔵 Groq 시도...")
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "편의점 블로거. JSON으로만 답해."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        
        result = json.loads(response.json()['choices'][0]['message']['content'])
        
        if isinstance(result, list):
            result = result[0] if result else None
        
        print("  ✅ Groq 성공!")
        return result
        
    except Exception as e:
        print(f"  ⚠️ Groq 실패: {str(e)[:100]}")
        return None


def call_openai(prompt):
    if not OPENAI_API_KEY:
        return None
    
    try:
        print("  🟠 OpenAI 시도...")
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "편의점 블로거"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", 
                               headers=headers, json=data, timeout=120)
        
        if response.status_code == 429:
            print("  ⚠️ OpenAI Rate Limit!")
            return None
            
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])
        
        if isinstance(result, list):
            result = result[0] if result else None
        
        print("  ✅ OpenAI 성공!")
        return result
        
    except Exception as e:
        print(f"  ⚠️ OpenAI 실패: {str(e)[:100]}")
        return None


def generate_with_auto(prompt):
    print("  🤖 AUTO 모드: Gemini → Groq → OpenAI")
    
    result = call_gemini(prompt)
    if result:
        return result
    
    result = call_groq(prompt)
    if result:
        return result
    
    result = call_openai(prompt)
    if result:
        return result
    
    print("  ❌ 모든 AI 실패!")
    return None


# =========================
# 콘텐츠 생성
# =========================
def generate_blog_post(store_info):
    try:
        name = store_info['name']
        country = store_info['country']
        
        print(f"  📝 {name} {'🇯🇵' if country == 'jp' else '🇰🇷'} 블로그 글 생성 중...")
        
        if country == 'kr':
            prompt = f"""당신은 편의점 블로거입니다. {name} 신상 제품 2개를 소개하세요.

요구사항:
- 제목: 클릭하고 싶은 제목 (이모지 포함)
- 본문: HTML 형식 (단, 캐릭터 이미지는 제외, 자동으로 추가됨)
- 각 제품: 제품명, 가격(원), 맛 후기, 꿀조합, 별점, 일본어 요약
- 친근한 MZ 말투

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["편의점신상", "{name}", "꿀조합"]}}
"""
        else:
            prompt = f"""당신은 일본 편의점 블로거입니다. {name} 신상 제품 2개를 소개하세요.

요구사항:
- 제목: 클릭하고 싶은 제목 (한일 병기)
- 본문: HTML 형식
- 각 제품: 제품명(한일), 가격(엔), 리뷰, 일본 문화 팁, 별점

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["일본편의점", "{name}"]}}
"""
        
        result = generate_with_auto(prompt)
        
        if not result:
            return None
        
        result['category'] = store_info['category']
        result['country'] = country
        result['store_key'] = store_info['key']
        
        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        return None


# =========================
# 워드프레스 발행
# =========================
def publish_to_wordpress(title, content, tags, category, scheduled_dt_kst):
    if not WORDPRESS_URL or not WORDPRESS_USERNAME or not WORDPRESS_PASSWORD:
        print("  ⚠️ 워드프레스 정보가 없어서 발행 건너뜀")
        return {'success': False, 'error': '워드프레스 정보 없음'}
        
    try:
        print(f"  📤 발행 준비: {title[:30]}...")
        print(f"  🔗 워드프레스 URL: {WORDPRESS_URL}")
        print(f"  👤 사용자: {WORDPRESS_USERNAME}")
        
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        
        # 🎨 Couchmallow 이미지 처리
        character_img = pick_character_image()
        if character_img:
            print("  🖼️ 캐릭터 이미지 처리 중...")
            watermarked = add_watermark(character_img)
            img_url = upload_image_to_wordpress(wp, watermarked)
            
            if img_url:
                # 본문 맨 위에 이미지 추가
                img_html = f'''<p style="text-align:center;margin-bottom:28px">
<img src="{img_url}" alt="Couchmallow" style="max-width:360px;border-radius:18px;box-shadow:0 4px 16px rgba(0,0,0,.06);" />
</p>
'''
                content = img_html + content
                print("  ✅ 캐릭터 이미지 추가 완료!")
        
        # 워드프레스 포스트 생성
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {'post_tag': tags, 'category': [category]}
        
        dt_utc = scheduled_dt_kst.astimezone(timezone.utc)
        post.post_status = 'future'
        post.date = dt_utc.replace(tzinfo=None)
        post.date_gmt = dt_utc.replace(tzinfo=None)
        
        print(f"  📅 예약 시간: {scheduled_dt_kst.strftime('%Y-%m-%d %H:%M')} (KST)")
        
        post_id = wp.call(NewPost(post))
        url = f"{WORDPRESS_URL}/?p={post_id}"
        
        print(f"  ✅ 예약발행 성공!")
        print(f"  🆔 Post ID: {post_id}")
        print(f"  🔗 URL: {url}")
        
        return {'success': True, 'url': url, 'post_id': post_id, 'hour': scheduled_dt_kst.hour}
        
    except Exception as e:
        print(f"  ❌ 발행 실패: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


# =========================
# 슬랙 알림
# =========================
def send_slack(message):
    if not SLACK_WEBHOOK_URL:
        print("  ⚠️ SLACK_WEBHOOK_URL이 없어서 슬랙 전송 건너뜀")
        return False
        
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={'text': message}, timeout=10)
        
        if response.status_code == 200:
            print(f"  ✅ 슬랙 전송 성공!")
            return True
        else:
            print(f"  ❌ 슬랙 전송 실패!")
            return False
            
    except Exception as e:
        print(f"  ❌ 슬랙 전송 에러: {e}")
        return False


def send_generation_complete_slack(results):
    summary = f"""🎉 한일 편의점 예약발행 완료!

📝 총 {len(results)}개 글 예약 완료

━━━━━━━━━━━━━━━━━━
"""
    
    for r in results:
        flag = '🇯🇵' if r['country'] == 'jp' else '🇰🇷'
        summary += f"\n{flag} {r['store']}"
        summary += f"\n   📝 {r['title'][:40]}..."
        summary += f"\n   🕐 {r['when']}"
        summary += f"\n   🔗 {r['url']}\n"
    
    summary += """
━━━━━━━━━━━━━━━━━━
⏰ 발행 시간:
   • 내일 09:00
   • 내일 12:00
   • 내일 18:00

각 시간에 발행 알림을 다시 보내드릴게요! 📱
"""
    
    send_slack(summary)


def send_publish_notification(hour, store_name):
    time_map = {
        9: "아침 9시",
        12: "점심 12시",
        18: "저녁 6시"
    }
    
    time_str = time_map.get(hour, f"{hour}시")
    
    message = f"""🔔 {time_str} 글 발행 완료!

{store_name} 글이 방금 발행되었습니다! 🎉

📱 인스타에 올릴 시간이에요!
"""
    
    send_slack(message)


# =========================
# 메인 로직
# =========================
def generate_and_schedule():
    """밤 11시 실행: 3개 예약발행"""
    print("=" * 60)
    print(f"🚀 한일 편의점 콘텐츠 생성: {datetime.now(KST)}")
    print("=" * 60)
    
    # 내일 발행 시간
    tomorrow = datetime.now(KST).date() + timedelta(days=1)
    slots = [
        datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0, tzinfo=KST),
        datetime(tomorrow.year, tomorrow.month, tomorrow.day, 12, 0, tzinfo=KST),
        datetime(tomorrow.year, tomorrow.month, tomorrow.day, 18, 0, tzinfo=KST),
    ]
    
    print(f"\n🕗 예약 슬롯:")
    for i, slot in enumerate(slots):
        store = STORES[i]
        flag = '🇯🇵' if store['country'] == 'jp' else '🇰🇷'
        print(f"   {slot.strftime('%Y-%m-%d %H:%M')} - {store['name']} {flag}")
    
    print(f"\n📝 블로그 3개 예약발행 시작...")
    print("-" * 60)
    
    results = []
    
    for i in range(3):
        store_info = STORES[i]
        scheduled_at = slots[i]
        
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"\n{'='*60}")
        print(f"[{i+1}/3] {store_info['name']} {flag} @ {scheduled_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")
        
        try:
            content = generate_blog_post(store_info)
            
            if not content:
                print(f"  ❌ [{i+1}] 콘텐츠 생성 실패!")
                continue
            
            result = publish_to_wordpress(
                content['title'],
                content['content'],
                content['tags'],
                content['category'],
                scheduled_dt_kst=scheduled_at
            )
            
            if result.get('success'):
                results.append({
                    'store': store_info['name'],
                    'country': store_info['country'],
                    'title': content['title'],
                    'url': result['url'],
                    'when': scheduled_at.strftime('%Y-%m-%d %H:%M'),
                    'hour': scheduled_at.hour
                })
                print(f"  ✅ [{i+1}] 성공!")
            else:
                print(f"  ❌ [{i+1}] 실패!")
                
        except Exception as e:
            print(f"  ❌ [{i+1}] 에러: {e}")
            continue
    
    print(f"\n{'='*60}")
    print(f"🎉 완료! 총 {len(results)}개 글 예약 성공!")
    print(f"{'='*60}")
    
    if results:
        send_generation_complete_slack(results)
    
    print(f"\n✅ 예약발행 완료!")


def send_notification():
    """9시, 12시, 18시 실행: 발행 알림"""
    print("=" * 60)
    print(f"🔔 발행 알림: {datetime.now(KST)}")
    print("=" * 60)
    
    current_hour = datetime.now(KST).hour
    
    hour_to_store = {
        9: "GS25",
        12: "CU",
        18: "세븐일레븐"
    }
    
    store_name = hour_to_store.get(current_hour)
    
    if store_name:
        send_publish_notification(current_hour, store_name)
        print(f"✅ {current_hour}시 알림 전송 완료!")
    else:
        print("⚠️ 알림 시간이 아닙니다.")


# =========================
# 메인
# =========================
def main():
    if MODE == 'notify':
        send_notification()
    else:
        generate_and_schedule()


if __name__ == "__main__":
    main()
