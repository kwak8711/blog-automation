import os
import json
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

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
        
        # Gemini가 배열로 리턴하면 첫번째 항목 사용
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
        
        # 배열로 리턴하면 첫번째 항목 사용
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
        
        # 배열로 리턴하면 첫번째 항목 사용
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
- 본문: 아래 HTML 디자인 그대로 사용
- 각 제품: 제품명, 가격(원), 맛 후기, 꿀조합, 별점, 일본어 요약
- 친근한 MZ 말투

HTML 디자인:
<div style="max-width: 800px;margin: 0 auto;font-family: 'Malgun Gothic', sans-serif">

<!-- 헤더 -->
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);padding: 40px 30px;border-radius: 20px;margin-bottom: 40px;text-align: center;box-shadow: 0 10px 30px rgba(0,0,0,0.2)">
<h1 style="color: white;font-size: 28px;margin: 0 0 15px 0;font-weight: bold">🛒 {name} 신상 제품 리뷰!</h1>
<p style="color: rgba(255,255,255,0.9);font-size: 16px;margin: 0">コンビニ新商品レビュー 🇰🇷🇯🇵</p>
</div>

<!-- 인사말 -->
<div style="background: #f8f9ff;padding: 30px;border-radius: 15px;margin-bottom: 40px;border-left: 5px solid #667eea">
<p style="font-size: 17px;line-height: 1.8;margin: 0;color: #222;font-weight: 500">
<strong style="font-size: 19px">안녕하세요, 편스타그램 친구들!</strong> 오늘은 {name}에서 새롭게 나온 신상 제품들을 소개해드릴게요! 🎉 [인사말 추가]
</p>
</div>

<!-- 제품 1 -->
<div style="background: white;padding: 35px;border-radius: 20px;margin-bottom: 35px;box-shadow: 0 5px 20px rgba(0,0,0,0.08);border: 2px solid #f0f0f0">
<h2 style="color: #667eea;font-size: 26px;margin: 0 0 20px 0;font-weight: bold;border-bottom: 3px solid #667eea;padding-bottom: 15px">1. [제품명] [이모지]</h2>

<div style="background: #fff5f5;padding: 20px;border-radius: 12px;margin-bottom: 20px">
<p style="font-size: 18px;margin: 0;color: #e63946"><strong style="font-size: 22px">💰 가격: [가격]원</strong></p>
</div>

<p style="font-size: 16px;line-height: 1.9;color: #222;margin-bottom: 20px;font-weight: 500">
[맛 후기 - 식감, 맛, 향 구체적으로]
</p>

<div style="background: #e8f5e9;padding: 18px;border-radius: 10px;margin-bottom: 20px">
<p style="font-size: 16px;margin: 0;color: #2e7d32"><strong>🍯 꿀조합:</strong> [꿀조합 설명]</p>
</div>

<p style="font-size: 17px;margin-bottom: 20px"><strong>별점:</strong> ⭐⭐⭐⭐⭐</p>

<div style="background: linear-gradient(to right, #fff3e0, #ffe0b2);padding: 20px;border-radius: 12px;border-left: 4px solid #ff9800">
<p style="margin: 0 0 8px 0;font-size: 15px;color: #e65100"><strong>🇯🇵 日本語要約</strong></p>
<p style="font-size: 14px;line-height: 1.7;color: #555;margin: 0">[일본어 요약 3-4줄]</p>
</div>
</div>

<!-- 제품 2 동일 구조 -->

<!-- 마무리 -->
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);padding: 35px;border-radius: 20px;margin-bottom: 40px;text-align: center;box-shadow: 0 10px 30px rgba(0,0,0,0.2)">
<p style="color: white;font-size: 18px;line-height: 1.8;margin: 0">
오늘 소개해드린 {name} 신상 제품들, 어떠셨나요? 가성비도 좋고 맛있으니 꼭 한 번 드셔보세요! 여러분의 편의점 꿀조합도 댓글로 남겨주세요! 😊<br><br>
<span style="font-size: 16px;opacity: 0.9">今日紹介した{name}の新商品、ぜひ試してみてください！🎌</span>
</p>
</div>

<!-- 해시태그 -->
<hr style="border: none;border-top: 3px solid #667eea;margin: 50px 0 30px 0">

<div style="background: linear-gradient(to right, #f8f9ff, #fff5f8);padding: 30px;border-radius: 15px;text-align: center">
<p style="margin: 0 0 15px 0;font-size: 16px;color: #667eea;font-weight: bold">📱 해시태그 / ハッシュタグ</p>
<p style="margin: 0;font-size: 15px;color: #667eea;line-height: 2">
#편의점신상 #コンビニ新商品 #{name} #꿀조합 #美味しい組み合わせ #편스타그램 #コンビニグルメ #MZ추천 #韓国コンビニ #편의점디저트 #コンビニデザート
</p>
</div>

</div>

JSON 형식:
{{"title": "제목", "content": "위 HTML 전체", "tags": ["편의점신상", "{name}", "꿀조합"]}}
"""
        else:
            prompt = f"""당신은 일본 편의점 블로거입니다. {name} 신상 제품 2개를 소개하세요.

요구사항:
- 제목: 클릭하고 싶은 제목 (한일 병기)
- 본문: 아래 HTML 디자인 그대로 사용
- 각 제품: 제품명(한일), 가격(엔), 리뷰, 일본 문화 팁, 별점

HTML 디자인:
<div style="max-width: 800px;margin: 0 auto;font-family: 'Malgun Gothic', sans-serif">

<!-- 헤더 -->
<div style="background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);padding: 40px 30px;border-radius: 20px;margin-bottom: 40px;text-align: center;box-shadow: 0 10px 30px rgba(0,0,0,0.2)">
<h1 style="color: white;font-size: 28px;margin: 0 0 15px 0;font-weight: bold">🇯🇵 {name} 신상 제품 리뷰!</h1>
<p style="color: rgba(255,255,255,0.9);font-size: 18px;margin: 0">{store_info.get('name_jp', name)} 新商品レビュー</p>
</div>

<!-- 인사말 -->
<div style="background: #fff5f5;padding: 30px;border-radius: 15px;margin-bottom: 40px;border-left: 5px solid #ff6b6b">
<p style="font-size: 17px;line-height: 1.8;margin: 0;color: #222;font-weight: 500">
<strong style="font-size: 19px">안녕하세요! 일본 편의점 탐험대입니다!</strong> 🇯🇵 오늘은 일본 {name}의 신상 제품을 소개해드릴게요! [인사말 추가]
</p>
</div>

<!-- 제품 1 -->
<div style="background: white;padding: 35px;border-radius: 20px;margin-bottom: 35px;box-shadow: 0 5px 20px rgba(0,0,0,0.08);border: 2px solid #f0f0f0">
<h2 style="color: #ff6b6b;font-size: 26px;margin: 0 0 20px 0;font-weight: bold;border-bottom: 3px solid #ff6b6b;padding-bottom: 15px">1. [제품명] ([일본어]) [이모지]</h2>

<div style="background: #fff5f5;padding: 20px;border-radius: 12px;margin-bottom: 20px">
<p style="font-size: 18px;margin: 0;color: #e63946"><strong style="font-size: 22px">💴 가격: [가격]엔</strong></p>
</div>

<p style="font-size: 16px;line-height: 1.9;color: #222;margin-bottom: 20px;font-weight: 500">
[맛 후기 - 한국과 비교하며 설명]
</p>

<div style="background: #fff3cd;padding: 18px;border-radius: 10px;margin-bottom: 20px;border-left: 4px solid #ffc107">
<p style="font-size: 16px;margin: 0;color: #856404"><strong>🎌 일본 팁:</strong> [일본 편의점 문화 팁]</p>
</div>

<p style="font-size: 17px;margin-bottom: 20px"><strong>별점:</strong> ⭐⭐⭐⭐⭐</p>
</div>

<!-- 제품 2 동일 구조 -->

<!-- 마무리 -->
<div style="background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%);padding: 35px;border-radius: 20px;margin-bottom: 40px;text-align: center;box-shadow: 0 10px 30px rgba(0,0,0,0.2)">
<p style="color: white;font-size: 18px;line-height: 1.8;margin: 0">
일본 여행 가시면 {name} 꼭 들러보세요! 한국에서는 맛볼 수 없는 특별한 제품들이 가득해요! 🎌<br><br>
<span style="font-size: 16px;opacity: 0.9">日本旅行の際は、ぜひ{store_info.get('name_jp', name)}に立ち寄ってみてください！</span>
</p>
</div>

<!-- 해시태그 -->
<hr style="border: none;border-top: 3px solid #ff6b6b;margin: 50px 0 30px 0">

<div style="background: linear-gradient(to right, #fff5f5, #ffe0e0);padding: 30px;border-radius: 15px;text-align: center">
<p style="margin: 0 0 15px 0;font-size: 16px;color: #ff6b6b;font-weight: bold">📱 해시태그 / ハッシュタグ</p>
<p style="margin: 0;font-size: 15px;color: #ff6b6b;line-height: 2">
#일본편의점 #日本コンビニ #{name} #{store_info.get('name_jp', name)} #일본여행 #日本旅行 #편의점투어 #コンビニ巡り
</p>
</div>

</div>

JSON 형식:
{{"title": "제목", "content": "위 HTML 전체", "tags": ["일본편의점", "{name}"]}}
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
        
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {'post_tag': tags, 'category': [category]}
        
        dt_utc = scheduled_dt_kst.astimezone(timezone.utc)
        post.post_status = 'future'
        post.date = dt_utc.replace(tzinfo=None)
        post.date_gmt = dt_utc.replace(tzinfo=None)
        
        print(f"  📅 예약 시간: {scheduled_dt_kst.strftime('%Y-%m-%d %H:%M')} (KST)")
        print(f"  📅 예약 시간: {dt_utc.strftime('%Y-%m-%d %H:%M')} (UTC)")
        
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
        print(f"  📤 슬랙 전송 시도...")
        print(f"  📝 메시지 길이: {len(message)} 자")
        print(f"  🔗 Webhook URL: {SLACK_WEBHOOK_URL[:50]}...")
        
        response = requests.post(SLACK_WEBHOOK_URL, json={'text': message}, timeout=10)
        
        print(f"  📊 응답 코드: {response.status_code}")
        print(f"  📄 응답 내용: {response.text[:200]}")
        
        if response.status_code == 200:
            print(f"  ✅ 슬랙 전송 성공!")
            return True
        else:
            print(f"  ❌ 슬랙 전송 실패!")
            return False
            
    except Exception as e:
        print(f"  ❌ 슬랙 전송 에러: {e}")
        import traceback
        traceback.print_exc()
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
            # AI 콘텐츠 생성
            content = generate_blog_post(store_info)
            
            if not content:
                print(f"  ❌ [{i+1}] 콘텐츠 생성 실패!")
                continue
            
            # 워드프레스 예약발행
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
    
    # 슬랙 알림
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



# ======================================================================
# 🟣 Couchmallow 이미지 자동첨부 + 워터마크 (ADD-ON)
#  - 기존 코드 건드리지 말고 이 블록만 맨 아래 붙이세요.
#  - assets/ 폴더에 올려둔 PNG 중에서 랜덤으로 1개 뽑아서 씁니다.
#  - 없으면 None 리턴해서 기존 로직이 그냥 자기 방식대로 가도록.
#  - 워터마크는 "복제금지 / couchmallow" 로 아주 연하게 찍음.
#  - Pillow가 필요하니까 requirements.txt에 pillow 한 줄만 추가해 주세요.
# ======================================================================
import os
import random

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False


# 1) 에셋 폴더 & 파일 목록 정의
COUCHMALLOW_ASSETS_DIR = os.path.join(
    os.path.dirname(__file__),
    "assets"
)

# 공주님이 올릴 파일들 이름만 여기 추가해가면 됨
COUCHMALLOW_CANDIDATES = [
    "Couchmallow_AM_01_360_ivory.png",
    "Couchmallow_AM_04_360_ivory.png",
    "Couchmallow_AM_07_360_ivory.png",
]

# 2) 랜덤으로 1개 뽑기
def pick_couchmallow_image() -> str | None:
    """assets/ 안에 실제로 존재하는 파일만 모아서 랜덤으로 1개 리턴"""
    available = []
    for name in COUCHMALLOW_CANDIDATES:
        path = os.path.join(COUCHMALLOW_ASSETS_DIR, name)
        if os.path.exists(path):
            available.append(path)
    if not available:
        return None
    return random.choice(available)


# 3) 워터마크 찍기
def add_watermark(input_path: str,
                  text: str = "Do not copy/ couchmallow",
                  opacity: int = 60) -> str:
    """
    input_path 이미지를 열어서 오른쪽 아래에 연한 워터마크를 찍고
    ./assets/_out/ 안에 새 파일로 저장한 뒤 그 경로를 리턴.
    Pillow가 없으면 원본 경로 그대로 리턴.
    """
    if not _PIL_AVAILABLE:
        # PIL 없으면 그냥 원본 사용
        return input_path

    # 출력 폴더
    out_dir = os.path.join(COUCHMALLOW_ASSETS_DIR, "_out")
    os.makedirs(out_dir, exist_ok=True)

    base = Image.open(input_path).convert("RGBA")
    w, h = base.size

    # 워터마크 레이어
    txt_layer = Image.new("RGBA", base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)

    # 폰트: 깃허브 액션/리눅스에서도 돌아가게 기본 폰트로
    try:
        # 시스템에 폰트 있으면 이걸로
        font = ImageFont.truetype("arial.ttf", int(h * 0.035))
    except Exception:
        font = ImageFont.load_default()

    text_w, text_h = draw.textsize(text, font=font)

    # 오른쪽 아래 살짝 띄워서
    margin = int(min(w, h) * 0.03)
    x = w - text_w - margin
    y = h - text_h - margin

    # 연보라(공주님 톤) + 투명
    watermark_color = (94, 73, 133, opacity)  # RGBA

    draw.text((x, y), text, font=font, fill=watermark_color)

    # 합치기
    out = Image.alpha_composite(base, txt_layer)

    # 파일 이름 만들기
    base_name = os.path.basename(input_path)
    name_wo_ext, _ = os.path.splitext(base_name)
    out_path = os.path.join(out_dir, f"{name_wo_ext}_wm.png")

    out.convert("RGB").save(out_path, "PNG")
    return out_path


# 4) 최종: 블로그 포스트에 쓸 이미지 하나 만들어서 경로 리턴
def get_couchmallow_image_for_post() -> str | None:
    """
    1) assets/ 에서 랜덤 선택
    2) 워터마크 찍기
    3) 워드프레스 업로드용 로컬 경로 리턴
    """
    src = pick_couchmallow_image()
    if not src:
        return None
    return add_watermark(src)


# 5) 단독 테스트용 (깃허브 액션 깨지지 않게 if문)
if __name__ == "__main__" and os.environ.get("TEST_COUCHMALLOW") == "1":
    img = get_couchmallow_image_for_post()
    print("generated:", img)



# ======================================================================
# 🟣 6) 워드프레스 발행 시 Couchmallow 이미지 자동 첨부 패치
#  - 위쪽 원본 publish_to_wordpress()는 손대지 않고 아래에서 감싼다.
#  - assets/ 안에 있는 이미지 → 워터마크 → 워드프레스에 업로드 → 본문 맨 위에 <img> 넣기
#  - 이미지 업로드가 실패하면 그냥 원래 함수 호출해서 글만 올림.
# ======================================================================
from wordpress_xmlrpc.methods import media
from wordpress_xmlrpc.compat import xmlrpc_client

# 1. 원래 함수 백업해두기
_original_publish_to_wordpress = publish_to_wordpress  # ← 위에서 정의된 원본

def _upload_image_to_wp(wp_client: Client, image_path: str) -> dict | None:
    """로컬 이미지를 워드프레스에 media로 올리고 결과 dict를 리턴"""
    try:
        with open(image_path, 'rb') as img:
            data = {
                'name': os.path.basename(image_path),
                'type': 'image/png',
                'bits': xmlrpc_client.Binary(img.read()),
            }
        res = wp_client.call(media.UploadFile(data))
        # res 예시: {'id': 123, 'file': '...', 'url': 'https://...png', 'type': 'image/png'}
        return res
    except Exception as e:
        print(f"  ⚠️ 워드프레스 이미지 업로드 실패: {e}")
        return None

def publish_to_wordpress(title, content, tags, category, scheduled_dt_kst):
    """
    기존 publish_to_wordpress 를 덮어쓰는 래퍼.
    1) 쿠치멜로 이미지 뽑기
    2) 워터마크 입힌 파일을 WP에 업로드
    3) 성공하면 본문 맨 위에 <img ...> 한 줄 붙이고
    4) 원래 함수(_original_publish_to_wordpress) 호출
    """
    # 1) 쿠치멜로 이미지 하나 뽑기
    img_path = get_couchmallow_image_for_post()
    if not img_path:
        # 그냥 원래대로
        return _original_publish_to_wordpress(title, content, tags, category, scheduled_dt_kst)

    # 2) 워드프레스 클라이언트 생성 (원래 함수 코드랑 동일하게 맞춰줌)
    if not WORDPRESS_URL or not WORDPRESS_USERNAME or not WORDPRESS_PASSWORD:
        print("  ⚠️ 워드프레스 정보가 없어서 이미지 없이 발행합니다.")
        return _original_publish_to_wordpress(title, content, tags, category, scheduled_dt_kst)

    try:
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)

        # 3) 이미지 먼저 올리기
        img_res = _upload_image_to_wp(wp, img_path)
        if img_res and 'url' in img_res:
            img_url = img_res['url']
            print(f"  🖼️ Couchmallow 이미지 업로드 성공: {img_url}")

            # 4) 본문 맨 위에 이미지 한 줄 추가
            #    스타일은 심플하게, 공주님 톤 맞춰서 여백 조금
            img_html = f'<p><img src="{img_url}" alt="Couchmallow" style="max-width:360px;border-radius:18px;margin-bottom:24px;"></p>\n'
            content = img_html + content
        else:
            print("  ⚠️ 이미지 업로드 결과에 url이 없어서 이미지 없이 발행합니다.")

    except Exception as e:
        print(f"  ⚠️ 이미지 업로드 과정에서 에러. 이미지 없이 발행할게요: {e}")

    # 5) 결국엔 원래 발행 함수 호출
    return _original_publish_to_wordpress(title, content, tags, category, scheduled_dt_kst)
