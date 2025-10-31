"""
한번에 6개 글 생성 - 초고속 버전
"""
import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
KST = ZoneInfo('Asia/Seoul')

# 6개 편의점 정보
STORES = [
    {'key': 'GS25', 'name': 'GS25', 'country': 'kr', 'time': '08:00'},
    {'key': '세븐일레븐_일본', 'name': '세븐일레븐', 'name_jp': 'セブンイレブン', 'country': 'jp', 'time': '09:00'},
    {'key': 'CU', 'name': 'CU', 'country': 'kr', 'time': '12:00'},
    {'key': '패밀리마트', 'name': '패밀리마트', 'name_jp': 'ファミリーマート', 'country': 'jp', 'time': '13:00'},
    {'key': '세븐일레븐_한국', 'name': '세븐일레븐', 'country': 'kr', 'time': '20:00'},
    {'key': '로손', 'name': '로손', 'name_jp': 'ローソン', 'country': 'jp', 'time': '21:00'},
]


def generate_all_posts_at_once():
    """1번 요청으로 6개 글 모두 생성"""
    
    print("🚀 한번에 6개 글 생성 시작!")
    print("=" * 60)
    
    # 프롬프트 구성
    prompt = f"""당신은 한국과 일본 편의점을 소개하는 인기 블로거입니다.
오늘 날짜: {datetime.now(KST).strftime('%Y년 %m월 %d일')}

아래 6개 편의점의 신상 제품 블로그 글을 **한번에** 생성해주세요:

1. GS25 (한국) - 발행 시간: 08시
2. 세븐일레븐 (일본, セブンイレブン) - 발행 시간: 09시
3. CU (한국) - 발행 시간: 12시
4. 패밀리마트 (일본, ファミリーマート) - 발행 시간: 13시
5. 세븐일레븐 (한국) - 발행 시간: 20시
6. 로손 (일본, ローソン) - 발행 시간: 21시

요구사항:
- 각 편의점마다 신상 제품 2-3개 소개
- 한국 편의점: 가격 원화, 꿀조합 팁, 일본어 요약 포함
- 일본 편의점: 가격 엔화, 일본 문화 팁 포함
- HTML 형식으로 작성 (이전 예시 참고)
- 친근하고 MZ세대 스타일

JSON 배열로 반환:
[
  {{
    "store_key": "GS25",
    "title": "제목 (이모지 포함, 30자 이내)",
    "content": "HTML 본문 전체",
    "tags": ["편의점신상", "GS25", "꿀조합"],
    "category": "한국편의점",
    "country": "kr"
  }},
  {{
    "store_key": "세븐일레븐_일본",
    "title": "...",
    "content": "...",
    "tags": ["일본편의점", "세븐일레븐", "セブンイレブン"],
    "category": "일본편의점",
    "country": "jp"
  }},
  ... (총 6개)
]

중요: 각 편의점이 서로 다른 제품을 소개하도록 하고, 실제 있을법한 제품으로 작성하세요.
"""

    try:
        # Gemini API 호출
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.9,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 32768,  # 긴 응답을 위해 증가
                "responseMimeType": "application/json"
            }
        }
        
        print("📡 Gemini API 호출 중...")
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
            print(f"   길이: {len(post.get('content', ''))} 자")
            print()
        
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
        print("🎉 테스트 성공!")
        print(f"총 {len(posts)}개 글 생성됨")
        print("=" * 60)
        
        # 결과 저장
        with open('/tmp/batch_result.json', 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        print("📄 결과 저장: /tmp/batch_result.json")
