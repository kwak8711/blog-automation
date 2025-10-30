import os
import json
import traceback
import requests
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
import time

# =========================
# 설정 (환경변수)
# =========================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')
WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')

# 버튼 링크용
INSTAGRAM_PROFILE_URL = os.environ.get('INSTAGRAM_PROFILE_URL', 'https://instagram.com/')
NAVER_BLOG_URL        = os.environ.get('NAVER_BLOG_URL', 'https://blog.naver.com/')

POSTS_PER_DAY = 6  # 한국 3개 + 일본 3개

KST = ZoneInfo('Asia/Seoul')

# =========================
# 편의점 설정 (한국 + 일본)
# =========================
STORES = {
    'GS25': {
        'country': 'kr',
        'name_kr': 'GS25',
        'name_jp': None,
        'category': '한국편의점',
        'currency': '원'
    },
    'CU': {
        'country': 'kr',
        'name_kr': 'CU',
        'name_jp': None,
        'category': '한국편의점',
        'currency': '원'
    },
    '세븐일레븐_한국': {
        'country': 'kr',
        'name_kr': '세븐일레븐',
        'name_jp': None,
        'category': '한국편의점',
        'currency': '원'
    },
    '세븐일레븐_일본': {
        'country': 'jp',
        'name_kr': '세븐일레븐',
        'name_jp': 'セブンイレブン',
        'category': '일본편의점',
        'currency': '엔'
    },
    '패밀리마트': {
        'country': 'jp',
        'name_kr': '패밀리마트',
        'name_jp': 'ファミリーマート',
        'category': '일본편의점',
        'currency': '엔'
    },
    '로손': {
        'country': 'jp',
        'name_kr': '로손',
        'name_jp': 'ローソン',
        'category': '일본편의점',
        'currency': '엔'
    }
}

# ========================================
# HTML → 텍스트 변환 (인스타용)
# ========================================
def create_text_version(html_content):
    """HTML을 인스타용 순수 텍스트로 변환"""
    # HTML 태그 제거
    text = re.sub(r'<div[^>]*>', '\n', html_content)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'<h1[^>]*>', '\n━━━━━━━━━━━━━━━━\n', text)
    text = re.sub(r'</h1>', '\n━━━━━━━━━━━━━━━━\n', text)
    text = re.sub(r'<h2[^>]*>', '\n\n📍 ', text)
    text = re.sub(r'</h2>', '\n', text)
    text = re.sub(r'<p[^>]*>', '', text)
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'<strong[^>]*>', '✨ ', text)
    text = re.sub(r'</strong>', ' ✨', text)
    text = re.sub(r'<hr[^>]*>', '\n━━━━━━━━━━━━━━━━\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<span[^>]*>', '', text)
    text = re.sub(r'</span>', '', text)
    text = re.sub(r'<[^>]+>', '', text)  # 남은 모든 HTML 태그 제거
    
    # 공백 정리
    text = re.sub(r'\n{3,}', '\n\n', text)  # 3줄 이상 → 2줄
    text = re.sub(r'[ \t]+', ' ', text)      # 연속 공백 → 1개
    text = text.strip()
    
    return text

# ========================================
# 예약 슬롯 계산: 08, 09, 12, 13, 20, 21시
# ========================================
def next_slots_korean_japanese(count=6):
    """
    한국/일본 번갈아가며 6개 슬롯 반환
    08(한) → 09(일) → 12(한) → 13(일) → 20(한) → 21(일)
    """
    now = datetime.now(KST)
    slot_hours = [8, 9, 12, 13, 20, 21]
    
    candidates = []
    
    # 오늘 남은 슬롯 찾기
    for hour in slot_hours:
        slot_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now < slot_time:
            candidates.append(slot_time)
    
    # 부족하면 다음날 슬롯 추가
    days_ahead = 1
    while len(candidates) < count:
        next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        for hour in slot_hours:
            if len(candidates) >= count:
                break
            slot_time = next_day.replace(hour=hour, minute=0, second=0, microsecond=0)
            candidates.append(slot_time)
        days_ahead += 1
    
    return candidates[:count]

# ========================================
# AI 콘텐츠 생성 (한국/일본 통합)
# ========================================
def generate_blog_post(store_key):
    """AI로 블로그 글 생성 (한국/일본 자동 구분)"""
    try:
        store_info = STORES[store_key]
        country = store_info['country']
        name_kr = store_info['name_kr']
        name_jp = store_info['name_jp']
        currency = store_info['currency']
        
        print(f"  📝 {name_kr} {'🇯🇵' if country == 'jp' else '🇰🇷'} 블로그 글 생성 중...")
        
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

        if country == 'kr':
            # 한국 편의점 프롬프트
            prompt = f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{name_kr}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 30자 이내, 한일 병기)
   예: "🛒{name_kr} 신상! 나도 몰랐던 꿀조합✨ (コンビニ新商品)"

2. 본문: 1200-1800자
   - 첫 문단: 친근한 인사 (한국어)
   - 각 제품마다:
     * <h2> 태그로 큰 제목 (번호 + 제품명 + 이모지) - 큰 글씨
     * 가격은 <strong> 태그로 강조 (원 단위)
     * 맛 후기 구체적으로 (식감, 맛, 향) - 한국어
     * 꿀조합 팁
     * 별점 ⭐ 이모지
     * 🇯🇵 일본어 요약: 각 제품마다 일본어로 간단히 요약 (3-4줄)
   - 마지막: 구매 추천

3. 친근한 말투, MZ세대 스타일

4. 실제 있을법한 제품 2-3개
   - 가격: 1,500원~5,000원

5. HTML 형식 예시:
<div style="max-width: 800px; margin: 0 auto; font-family: 'Malgun Gothic', sans-serif;">

<!-- 헤더 -->
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px 30px; border-radius: 20px; margin-bottom: 40px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
<h1 style="color: white; font-size: 28px; margin: 0 0 15px 0; font-weight: bold;">🛒 {name_kr} 신상 제품 리뷰!</h1>
<p style="color: rgba(255,255,255,0.9); font-size: 16px; margin: 0;">コンビニ新商品レビュー 🇰🇷🇯🇵</p>
</div>

<!-- 인사말 -->
<div style="background: #f8f9ff; padding: 30px; border-radius: 15px; margin-bottom: 40px; border-left: 5px solid #667eea;">
<p style="font-size: 17px; line-height: 1.8; margin: 0; color: #222; font-weight: 500;">
<strong style="font-size: 19px;">안녕하세요, 편스타그램 친구들!</strong> 오늘은 {name_kr}에서 새롭게 나온 신상 제품들을 소개해드릴게요! 🎉 요즘 날씨도 쌀쌀해지고, 간편하게 즐길 수 있는 간식들이 정말 많이 나왔어요!
</p>
</div>

<!-- 제품 1 -->
<div style="background: white; padding: 35px; border-radius: 20px; margin-bottom: 35px; box-shadow: 0 5px 20px rgba(0,0,0,0.08); border: 2px solid #f0f0f0;">
<h2 style="color: #667eea; font-size: 26px; margin: 0 0 20px 0; font-weight: bold; border-bottom: 3px solid #667eea; padding-bottom: 15px;">1. 딸기 생크림 케이크 🍰</h2>

<div style="background: #fff5f5; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
<p style="font-size: 18px; margin: 0; color: #e63946;"><strong style="font-size: 22px;">💰 가격: 3,500원</strong></p>
</div>

<p style="font-size: 16px; line-height: 1.9; color: #222; margin-bottom: 20px; font-weight: 500;">
첫 번째는 딸기 생크림 케이크예요! 한 입 베어물면 신선한 딸기와 부드러운 생크림이 입 안에서 폭발! 달콤한 맛이 정말 일품이에요. 케이크 스펀지도 촉촉하고, 생크림도 너무 느끼하지 않아서 후식으로 딱 좋답니다. 진짜 편의점 디저트 맞나 싶을 정도로 퀄리티가 좋아요!
</p>

<div style="background: #e8f5e9; padding: 18px; border-radius: 10px; margin-bottom: 20px;">
<p style="font-size: 16px; margin: 0; color: #2e7d32;"><strong>🍯 꿀조합:</strong> 아메리카노와 함께 먹으면 커피의 쌉싸름한 맛과 케이크의 달콤함이 환상적인 조합! 꼭 시도해보세요!</p>
</div>

<p style="font-size: 17px; margin-bottom: 20px;"><strong>별점:</strong> ⭐⭐⭐⭐⭐</p>

<div style="background: linear-gradient(to right, #fff3e0, #ffe0b2); padding: 20px; border-radius: 12px; border-left: 4px solid #ff9800;">
<p style="margin: 0 0 8px 0; font-size: 15px; color: #e65100;"><strong>🇯🇵 日本語要約</strong></p>
<p style="font-size: 14px; line-height: 1.7; color: #555; margin: 0;">
いちご生クリームケーキ、3,500ウォン！新鮮ないちごとふわふわの生クリームが絶品です。スポンジもしっとりしていて、コンビニのデザートとは思えないクオリティ。アメリカーノと一緒に食べるのがおすすめ！⭐⭐⭐⭐⭐
</p>
</div>
</div>

<!-- 제품 2 -->
<div style="background: white; padding: 35px; border-radius: 20px; margin-bottom: 35px; box-shadow: 0 5px 20px rgba(0,0,0,0.08); border: 2px solid #f0f0f0;">
<h2 style="color: #667eea; font-size: 26px; margin: 0 0 20px 0; font-weight: bold; border-bottom: 3px solid #667eea; padding-bottom: 15px;">2. 불닭치즈볶음면 김밥 🌶️</h2>

<div style="background: #fff5f5; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
<p style="font-size: 18px; margin: 0; color: #e63946;"><strong style="font-size: 22px;">💰 가격: 2,800원</strong></p>
</div>

<p style="font-size: 16px; line-height: 1.9; color: #222; margin-bottom: 20px; font-weight: 500;">
매콤한 불닭볶음면에 치즈가 듬뿍 들어가서 맵지만 고소한 맛이 일품! 김밥 안에 불닭면이 들어있어서 한 입 베어물 때마다 쫄깃한 식감과 함께 매콤달콤한 맛이 입 안 가득 퍼집니다. 가성비도 완전 끝내주고, 한 끼 식사로도 충분해요!
</p>

<div style="background: #e8f5e9; padding: 18px; border-radius: 10px; margin-bottom: 20px;">
<p style="font-size: 16px; margin: 0; color: #2e7d32;"><strong>🍯 꿀조합:</strong> 우유랑 같이 먹으면 매운맛을 중화시켜주면서도 고소함이 배가 돼요!</p>
</div>

<p style="font-size: 17px; margin-bottom: 20px;"><strong>별점:</strong> ⭐⭐⭐⭐</p>

<div style="background: linear-gradient(to right, #fff3e0, #ffe0b2); padding: 20px; border-radius: 12px; border-left: 4px solid #ff9800;">
<p style="margin: 0 0 8px 0; font-size: 15px; color: #e65100;"><strong>🇯🇵 日本語要約</strong></p>
<p style="font-size: 14px; line-height: 1.7; color: #555; margin: 0;">
プルダック炒め麺キンパ、2,800ウォン！辛いけどチーズがたっぷり入っているから、マイルドで美味しいです。もちもちした食感と甘辛い味が最高。牛乳と一緒に食べるのがベスト！⭐⭐⭐⭐
</p>
</div>
</div>

<!-- 마무리 -->
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 35px; border-radius: 20px; margin-bottom: 40px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
<p style="color: white; font-size: 18px; line-height: 1.8; margin: 0;">
오늘 소개해드린 {name_kr} 신상 제품들, 어떠셨나요? 모두 가성비도 좋고 맛도 보장되는 제품들이니 꼭 한번 드셔보세요! 여러분의 편의점 꿀조합도 댓글로 알려주세요! 😊<br><br>
<span style="font-size: 16px; opacity: 0.9;">今日紹介した{name_kr}の新商品、ぜひ試してみてください！🎌</span>
</p>
</div>

<!-- 해시태그 (한국어 + 일본어) -->
<hr style="border: none; border-top: 3px solid #667eea; margin: 50px 0 30px 0;">

<div style="background: linear-gradient(to right, #f8f9ff, #fff5f8); padding: 30px; border-radius: 15px; text-align: center;">
<p style="margin: 0 0 15px 0; font-size: 16px; color: #667eea; font-weight: bold;">📱 해시태그 / ハッシュタグ</p>
<p style="margin: 0; font-size: 15px; color: #667eea; line-height: 2; word-break: break-all;">
#편의점신상 #コンビニ新商品 #{name_kr} #꿀조합 #美味しい組み合わせ #편스타그램 #コンビニグルメ #MZ추천 #韓国コンビニ #편의점디저트 #コンビニデザート #편의점케이크 #ケーキ #데일리디저트 #デイリー #오늘뭐먹지 #今日何食べる #편의점투어 #コンビニ巡り #편의점맛집 #コンビニグルメ #먹스타그램 #グルメスタグラム #디저트스타그램 #デザートスタグラム #간식추천 #おやつ #편의점꿀템 #コンビニおすすめ
</p>
</div>

</div>

JSON 형식으로 답변:
{{"title": "제목", "content": "HTML 본문 전체", "tags": ["편의점신상", "コンビニ新商品", "{name_kr}", "꿀조합", "美味しい組み合わせ"]}}
"""
        else:
            # 일본 편의점 프롬프트
            prompt = f"""당신은 일본 편의점을 소개하는 인기 블로거입니다.
일본 {name_kr}({name_jp})의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 한일 병기)
   예: "🇯🇵{name_kr} 신상! 프리미엄 오니기리 완전 대박 ({name_jp})✨"

2. 본문: 1200-1800자
   - 첫 문단: 친근한 인사 + 일본 편의점 특징 소개
   - 각 제품마다:
     * <h2> 태그로 큰 제목 (번호 + 제품명(한국어) + 일본어 + 이모지) - 큰 글씨
     * 가격은 <strong> 태그로 강조 (엔 단위만, 원화 환산 X)
     * 일본 특유의 제품 특징 설명
     * 일본 편의점 문화 팁
     * 별점 ⭐ 이모지
   - 마지막: 일본 여행 시 추천

3. 친근하고 여행 가이드 느낌

4. 실제 일본 편의점 제품 2-3개
   - 가격: 100엔~500엔
   - 제품 예시: 오니기리, 벤또, 디저트, 음료

5. HTML 형식 예시:
<div style="max-width: 800px; margin: 0 auto; font-family: 'Malgun Gothic', sans-serif;">

<!-- 헤더 -->
<div style="background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%); padding: 40px 30px; border-radius: 20px; margin-bottom: 40px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
<h1 style="color: white; font-size: 28px; margin: 0 0 15px 0; font-weight: bold;">🇯🇵 {name_kr} 신상 제품 리뷰!</h1>
<p style="color: rgba(255,255,255,0.9); font-size: 18px; margin: 0;">{name_jp} 新商品レビュー</p>
</div>

<!-- 인사말 -->
<div style="background: #fff5f5; padding: 30px; border-radius: 15px; margin-bottom: 40px; border-left: 5px solid #ff6b6b;">
<p style="font-size: 17px; line-height: 1.8; margin: 0; color: #222; font-weight: 500;">
<strong style="font-size: 19px;">안녕하세요! 일본 편의점 탐험대입니다!</strong> 🇯🇵 오늘은 일본 {name_kr}({name_jp})의 신상 제품을 소개해드릴게요! 일본 편의점은 한국과 다르게 퀄리티가 정말 높은 걸로 유명하죠! 여행 가시면 꼭 들러보세요!
</p>
</div>

<!-- 제품 1 -->
<div style="background: white; padding: 35px; border-radius: 20px; margin-bottom: 35px; box-shadow: 0 5px 20px rgba(0,0,0,0.08); border: 2px solid #f0f0f0;">
<h2 style="color: #ff6b6b; font-size: 26px; margin: 0 0 20px 0; font-weight: bold; border-bottom: 3px solid #ff6b6b; padding-bottom: 15px;">1. 프리미엄 참치마요 오니기리 (ツナマヨおにぎり) 🍙</h2>

<div style="background: #fff5f5; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
<p style="font-size: 18px; margin: 0; color: #e63946;"><strong style="font-size: 22px;">💴 가격: 200엔</strong></p>
</div>

<p style="font-size: 16px; line-height: 1.9; color: #222; margin-bottom: 20px; font-weight: 500;">
한국 편의점 삼각김밥과 비슷하지만 밥알이 더 찰지고 김이 바삭해요! 참치마요 소스가 진짜 듬뿍 들어있어서 한 입 베어물면 고소하고 짭조름한 맛이 입 안 가득! 일본 편의점 오니기리는 밥을 꾹꾹 눌러 만들지 않아서 식감이 훨씬 부드러워요. 한국 삼각김밥이랑 비교하면 차이가 확 느껴져요!
</p>

<div style="background: #fff3cd; padding: 18px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
<p style="font-size: 16px; margin: 0; color: #856404;"><strong>🎌 일본 팁:</strong> 편의점에서 "아타타메떼 쿠다사이(温めてください)"라고 하면 데워줘요! 따뜻한 오니기리도 별미!</p>
</div>

<p style="font-size: 17px; margin-bottom: 20px;"><strong>별점:</strong> ⭐⭐⭐⭐⭐</p>
</div>

<!-- 제품 2 -->
<div style="background: white; padding: 35px; border-radius: 20px; margin-bottom: 35px; box-shadow: 0 5px 20px rgba(0,0,0,0.08); border: 2px solid #f0f0f0;">
<h2 style="color: #ff6b6b; font-size: 26px; margin: 0 0 20px 0; font-weight: bold; border-bottom: 3px solid #ff6b6b; padding-bottom: 15px;">2. 카레맛 치킨 오니기리 (カレーチキンおにぎり) 🍛</h2>

<div style="background: #fff5f5; padding: 20px; border-radius: 12px; margin-bottom: 20px;">
<p style="font-size: 18px; margin: 0; color: #e63946;"><strong style="font-size: 22px;">💴 가격: 180엔</strong></p>
</div>

<p style="font-size: 16px; line-height: 1.9; color: #222; margin-bottom: 20px; font-weight: 500;">
일본식 카레맛 치킨이 들어있어서 한 끼 식사로도 충분해요! 카레 양념이 밥에 스며들어서 매 입마다 풍미가 가득합니다. 치킨도 부드럽고 카레 맛도 진해서 정말 맛있어요. 가격 대비 양도 푸짐하고 든든해서 점심이나 야식으로 완벽!
</p>

<div style="background: #fff3cd; padding: 18px; border-radius: 10px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
<p style="font-size: 16px; margin: 0; color: #856404;"><strong>🎌 일본 팁:</strong> 편의점 오니기리는 새벽에 가면 20-30% 할인해요! 밤샘 여행자 꿀팁!</p>
</div>

<p style="font-size: 17px; margin-bottom: 20px;"><strong>별점:</strong> ⭐⭐⭐⭐</p>
</div>

<!-- 마무리 -->
<div style="background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%); padding: 35px; border-radius: 20px; margin-bottom: 40px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
<p style="color: white; font-size: 18px; line-height: 1.8; margin: 0;">
일본 여행 가시면 {name_kr} 꼭 들러보세요! 한국에서는 맛볼 수 없는 특별한 제품들이 가득해요! 🎌<br><br>
<span style="font-size: 16px; opacity: 0.9;">日本旅行の際は、ぜひ{name_jp}に立ち寄ってみてください！</span>
</p>
</div>

<!-- 해시태그 (한국어 + 일본어) -->
<hr style="border: none; border-top: 3px solid #ff6b6b; margin: 50px 0 30px 0;">

<div style="background: linear-gradient(to right, #fff5f5, #ffe0e0); padding: 30px; border-radius: 15px; text-align: center;">
<p style="margin: 0 0 15px 0; font-size: 16px; color: #ff6b6b; font-weight: bold;">📱 해시태그 / ハッシュタグ</p>
<p style="margin: 0; font-size: 15px; color: #ff6b6b; line-height: 2; word-break: break-all;">
#일본편의점 #日本コンビニ #{name_kr} #{name_jp} #일본여행 #日本旅行 #오니기리 #おにぎり #편의점투어 #コンビニ巡り #일본맛집 #日本グルメ #도쿄여행 #東京旅行 #오사카여행 #大阪旅行 #일본출장 #日本出張 #편의점신상 #コンビニ新商品 #일본음식 #和食 #먹스타그램 #グルメスタグラム #일본일주 #日本一周 #여행스타그램 #トラベルスタグラム #일본정보 #日本情報
</p>
</div>

</div>

JSON 형식으로 답변:
{{"title": "제목", "content": "HTML 본문 전체", "tags": ["일본편의점", "日本コンビニ", "{name_kr}", "{name_jp}", "일본여행", "日本旅行"]}}
"""

        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "당신은 편의점 전문 블로거입니다. 친근하고 재미있는 글을 씁니다."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.9,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = json.loads(response.json()['choices'][0]['message']['content'])

        # 카테고리 추가
        result['category'] = store_info['category']
        result['country'] = country
        result['store_key'] = store_key
        
        # 텍스트 버전 생성 (인스타용)
        result['text_version'] = create_text_version(result['content'])

        print(f"  ✅ 생성 완료: {result['title'][:30]}...")
        return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None

# ========================================
# 워드프레스 발행 (예약 발행 지원)
# ========================================
def publish_to_wordpress(title, content, tags, category, scheduled_dt_kst=None):
    """워드프레스 발행/예약발행"""
    try:
        print(f"  📤 발행 준비: {title[:30]}...")

        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)

        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {'post_tag': tags, 'category': [category]}

        if scheduled_dt_kst:
            # 예약 발행 - UTC로 변환
            dt_utc = scheduled_dt_kst.astimezone(timezone.utc)
            post.post_status = 'future'
            # 워드프레스는 UTC 시간 사용
            post.date = dt_utc.replace(tzinfo=None)
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


def send_slack_quick_actions(title="📱 바로가기"):
    """예쁜 버튼 3개 (워드프레스 / 인스타 / 네이버블로그)"""
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
                            "text": {"type": "plain_text", "text": "📝 워드프레스", "emoji": True},
                            "style": "primary",
                            "url": f"{WORDPRESS_URL}/wp-admin/edit.php"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "📷 인스타", "emoji": True},
                            "url": INSTAGRAM_PROFILE_URL
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "✍️ 네이버", "emoji": True},
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

# ========================================
# 모드 1: 콘텐츠 생성 및 예약발행
# ========================================
def generate_and_schedule():
    """한국 + 일본 편의점 콘텐츠 생성 및 예약발행"""
    print("=" * 60)
    print(f"🚀 한일 편의점 콘텐츠 생성: {datetime.now(KST)}")
    print("=" * 60)

    # 발행 순서 (한국/일본 번갈아)
    store_order = [
        'GS25',              # 08시 (한국)
        '세븐일레븐_일본',    # 09시 (일본)
        'CU',                # 12시 (한국)
        '패밀리마트',        # 13시 (일본)
        '세븐일레븐_한국',    # 20시 (한국)
        '로손'               # 21시 (일본)
    ]
    
    wp_results = []

    # 예약 슬롯 계산
    slots = next_slots_korean_japanese(count=POSTS_PER_DAY)
    print(f"\n🕗 예약 슬롯:")
    for i, slot in enumerate(slots):
        store_key = store_order[i % len(store_order)]
        store_info = STORES[store_key]
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"   {slot.strftime('%Y-%m-%d %H:%M')} - {store_info['name_kr']} {flag}")

    # 워드프레스 글 생성 + 예약발행
    print(f"\n📝 블로그 {POSTS_PER_DAY}개 예약발행 중...")
    print("-" * 60)
    
    for i in range(POSTS_PER_DAY):
        store_key = store_order[i % len(store_order)]
        store_info = STORES[store_key]
        scheduled_at = slots[i]
        
        flag = '🇯🇵' if store_info['country'] == 'jp' else '🇰🇷'
        print(f"\n[{i+1}/{POSTS_PER_DAY}] {store_info['name_kr']} {flag} @ {scheduled_at.strftime('%Y-%m-%d %H:%M')}")

        content = generate_blog_post(store_key)
        if content:
            result = publish_to_wordpress(
                content['title'],
                content['content'],
                content['tags'],
                content['category'],
                scheduled_dt_kst=scheduled_at
            )
            if result.get('success'):
                wp_results.append({
                    'store': store_info['name_kr'],
                    'country': store_info['country'],
                    'title': content['title'],
                    'url': result['url'],
                    'when': scheduled_at.strftime('%Y-%m-%d %H:%M'),
                    'post_id': result['post_id']
                })
        time.sleep(10)

    # 완료 알림
    korean_posts = [r for r in wp_results if r['country'] == 'kr']
    japanese_posts = [r for r in wp_results if r['country'] == 'jp']
    
    summary = f"""🎉 *한일 편의점 예약발행 완료!*

📝 *총 {len(wp_results)}개 글 자동 예약*
🇰🇷 한국: {len(korean_posts)}개
🇯🇵 일본: {len(japanese_posts)}개

━━━━━━━━━━━━━━━━━━
"""
    
    for r in wp_results:
        flag = '🇯🇵' if r['country'] == 'jp' else '🇰🇷'
        summary += f"\n{flag} *{r['store']}* - {r['when']}"
        summary += f"\n   {r['title'][:40]}..."
        summary += f"\n   📝 {r['url']}"
        if 'text_url' in r:
            summary += f"\n   📱 인스타용: {r['text_url']}"
        summary += "\n"
    
    summary += f"""
━━━━━━━━━━━━━━━━━━
📌 *사용 방법:*
1️⃣ 워드프레스 열기
2️⃣ 본문 전체를 "미리보기"에서 복사
3️⃣ 인스타/네이버에 붙여넣기
4️⃣ 사진 첨부 후 업로드!

💡 *TIP:* 미리보기로 복사하면 HTML 태그 없이 깔끔!

⏰ 예약 시간에 자동 발행됩니다!
"""
    
    send_slack(summary)
    
    # 퀵액션 버튼
    send_slack_quick_actions(title="📱 바로가기")
    
    print(f"\n✅ 예약발행 완료!")


# ========================================
# 모드 2: 발행 알림
# ========================================
def send_publish_notification():
    """지금 시간에 발행된 글 알림"""
    print("=" * 60)
    print(f"🔔 발행 알림: {datetime.now(KST)}")
    print("=" * 60)
    
    now = datetime.now(KST)
    current_hour = now.hour
    
    # 현재 시간대 확인
    time_slot_map = {
        8: ("아침 8시", "GS25", "kr"),
        9: ("아침 9시", "세븐일레븐", "jp"),
        12: ("점심 12시", "CU", "kr"),
        13: ("점심 1시", "패밀리마트", "jp"),
        20: ("저녁 8시", "세븐일레븐", "kr"),
        21: ("저녁 9시", "로손", "jp")
    }
    
    if current_hour not in time_slot_map:
        print("⚠️ 알림 시간이 아닙니다.")
        return
    
    time_slot, store_name, country = time_slot_map[current_hour]
    flag = "🇯🇵" if country == "jp" else "🇰🇷"
    
    # 워드프레스 발행 알림
    message = f"""🎉 *{time_slot} 글 발행 완료!*

{flag} *{store_name}* 글이 방금 발행되었어요!

━━━━━━━━━━━━━━━━━━
📌 *할 일:*
1️⃣ 워드프레스에서 글 확인
2️⃣ 맨 아래 해시태그 복사
3️⃣ 인스타에 붙여넣기
4️⃣ 사진 첨부 후 업로드!

✨ 간단하죠? 30초 컷!
"""
    send_slack(message)
    
    # 퀵액션 버튼
    send_slack_quick_actions(title=f"📱 {time_slot} 바로가기")
    
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
