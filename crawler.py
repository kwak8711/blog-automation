"""
한번에 6개 글 생성 - 초고속 버전
실제 크롤링 로직은 main_crawl.py에 정의되어 있지만, 이 파일은 AI 생성 테스트를 위해 사용됩니다.
"""
import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List, Any

# =========================
# 설정 (환경변수)
# =========================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
KST = ZoneInfo('Asia/Seoul')

# 6개 편의점 정보 (이 정보가 AI 모델의 입력으로 사용됩니다)
STORES = [
    {'key': 'GS25', 'name': 'GS25', 'country': 'kr', 'time': '08:00', 'category': '한국편의점'},
    {'key': '세븐일레븐_일본', 'name': '세븐일레븐', 'name_jp': 'セブンイレブン', 'country': 'jp', 'time': '09:00', 'category': '일본편의점'},
    {'key': 'CU', 'name': 'CU', 'country': 'kr', 'time': '12:00', 'category': '한국편의점'},
    {'key': '패밀리마트', 'name': '패밀리마트', 'name_jp': 'ファミリーマート', 'country': 'jp', 'time': '13:00', 'category': '일본편의점'},
    {'key': '세븐일레븐_한국', 'name': '세븐일레븐', 'country': 'kr', 'time': '20:00', 'category': '한국편의점'},
    {'key': '로손', 'name': '로손', 'name_jp': 'ローソン', 'country': 'jp', 'time': '21:00', 'category': '일본편의점'},
]

# 실제 크롤링 데이터가 없으므로 더미 데이터를 사용합니다.
# 실제 운영 시에는 이 부분이 크롤링 결과로 대체되어야 합니다.
DUMMY_PRODUCTS = {
    'GS25': [{'name': '혜자로운 집밥 제육볶음', 'price': '4,500원', 'description': '가성비 최고 도시락'}, {'name': '아메리카노 라지', 'price': '2,000원', 'description': 'GS25의 시그니처 커피'}],
    '세븐일레븐_일본': [{'name': 'もちとろイチゴミルク', 'price': '150엔', 'description': '부드러운 딸기 크림 모찌'}, {'name': '金のハンバーグ', 'price': '398엔', 'description': '고급진 함박 스테이크'}],
    'CU': [{'name': '쫀득한 마카롱 5종', 'price': '3,500원', 'description': '인기 폭발 디저트 세트'}, {'name': '자이언트 떡볶이', 'price': '3,000원', 'description': '매콤한 가성비 떡볶이'}],
    '패밀리마트': [{'name': 'ファミチキ', 'price': '180엔', 'description': '패미마 대표 치킨'}, {'name': '濃厚チーズケーキ', 'price': '280엔', 'description': '진한 치즈 케이크'}],
    '세븐일레븐_한국': [{'name': '치즈인더함박', 'price': '5,000원', 'description': '치즈 듬뿍 함박스테이크'}, {'name': 'PB 캔커피', 'price': '1,200원', 'description': '세븐일레븐 자체 브랜드 커피'}],
    '로손': [{'name': 'プレミアムロールケーキ', 'price': '190엔', 'description': '촉촉한 크림 롤케이크'}, {'name': 'からあげクン', 'price': '238엔', 'description': '로손의 대표 치킨 너겟'}],
}


def generate_all_posts_at_once():
    """1번 요청으로 6개 글 모두 생성"""
    
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY가 환경 변수에 설정되어 있지 않습니다.")
        return None
    
    print("🚀 한번에 6개 글 생성 시작!")
    print("=" * 60)
    
    stores_to_generate = []
    
    for store in STORES:
        store_key = store['key']
        # 더미 데이터에서 해당 편의점의 제품 정보를 가져와 AI에 전달합니다.
        products = DUMMY_PRODUCTS.get(store_key, [])
        
        stores_to_generate.append({
            'store_key': store_key,
            'store_name': store['name'],
            'country': store['country'],
            'products_to_review': products,
            'category': store['category'],
            'time': store['time'],
            # 일본 편의점의 경우 일본어 이름도 포함
            'name_jp': store.get('name_jp', '')
        })

    # ========================================================
    # 💡 [수정] AI 프롬프트: HTML 포맷 요구사항 명확히 지정
    # ========================================================
    prompt = f"""
    당신은 한국과 일본 편의점 신상 리뷰 전문 블로거입니다.
    오늘 발행할 6개의 글을 한번에 생성해야 합니다.
    글의 내용은 전문적이고 독자들이 흥미를 가질 수 있도록 작성해주세요.

    각 글은 아래 JSON 스키마를 따르며, 총 6개의 JSON 객체를 포함하는 배열을 반환해야 합니다.

    # JSON 스키마
    - "store_key": (string) 편의점 키 (예: GS25, 세븐일레븐_일본)
    - "title": (string) 50자 이내의 흥미로운 제목.
    - "content": (string) 워드프레스 본문입니다.
    - "full_text": (string) 인스타그램 본문으로 사용할 텍스트 (해시태그 포함).
    - "category": (string) 카테고리 (예: 디저트, 도시락)
    - "country_category": (string) 국가 카테고리 (예: 한국편의점, 일본편의점)

    # 생성할 데이터 (크롤링된 제품 정보 포함)
    {json.dumps(stores_to_generate, ensure_ascii=False, indent=2)}

    # 주의사항
    1. 'title': 50자 이내의 흥미로운 제목을 붙여주세요.
    2. 'content': 워드프레스 본문입니다. **모든 단락은 반드시 <p> 태그로 감싸고, 소제목은 <h2> 태그, 목록은 <ul> 또는 <ol> 태그를 사용하여** 가독성 높은 HTML 형식으로 작성해야 합니다. 일반 텍스트만 사용하지 마세요. (이미지 태그도 포함 가능)
    3. 'full_text': 인스타그램 본문으로, 해시태그를 포함한 전문 텍스트 (HTML 태그 금지, 줄바꿈은 \n 사용).
    4. 데이터는 오직 JSON 배열만 반환하며, 다른 설명이나 주석은 절대 포함하지 마세요.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "config": {
            "systemInstruction": {
                "parts": [{"text": "You are a professional blog post generator. Your response must be a valid JSON array only, following the user's instructions and schema exactly."}]
            },
            "generationConfig": {
                "temperature": 0.9,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 32768,  # 긴 응답을 위해 증가
                "responseMimeType": "application/json"
            }
        }
    }
    
    try:
        print("📡 Gemini API 호출 중... (최대 120초 대기)")
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        
        result_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        posts = json.loads(result_text)
        
        print(f"✅ 성공! {len(posts)}개 글 생성 완료!")
        print("=" * 60)
        
        # 각 글 정보 출력
        for i, post in enumerate(posts, 1):
            print(f"[{i}/6] {post.get('store_key', 'Unknown')}")
            print(f"   제목: {post.get('title', 'No title')[:50]}...")
            print(f"   길이: {len(post.get('content', ''))} 자 (HTML 포맷 확인)")
            print()
        
        # 임시 파일에 저장 (main_batch.py/main_crawl.py와 통합 시 필요)
        output_file = f"/tmp/ai_generated_posts_{datetime.now(KST).strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=4)
        print(f"💾 생성된 글 임시 저장 완료: {output_file}")

        return posts
        
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # 테스트 실행
    posts = generate_all_posts_at_once()
    
    if posts:
        print("\n" + "=" * 60)
        print("💡 워드프레스 문제 해결을 위해 'content' 필드에 <p>, <h2> 등이 잘 들어갔는지 확인하세요.")
        print("=" * 60)
