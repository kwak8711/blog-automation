"""
크롤링 + AI 통합 시스템
실제 제품 정보 + AI 리뷰 생성
"""
import os
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from crawler import ConvenienceStoreCrawler

# 환경변수
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
AI_PROVIDER = os.environ.get('AI_PROVIDER', 'GEMINI')  # GEMINI 또는 OPENAI

KST = ZoneInfo('Asia/Seoul')


def generate_review_with_real_products(store_key, products):
    """실제 제품 정보로 AI 리뷰 생성"""
    
    store_info = {
        'GS25': {'name': 'GS25', 'country': 'kr', 'category': '한국편의점'},
        'CU': {'name': 'CU', 'country': 'kr', 'category': '한국편의점'},
        '세븐일레븐_한국': {'name': '세븐일레븐', 'country': 'kr', 'category': '한국편의점'},
        '세븐일레븐_일본': {'name': '세븐일레븐', 'name_jp': 'セブンイレブン', 'country': 'jp', 'category': '일본편의점'},
        '패밀리마트': {'name': '패밀리마트', 'name_jp': 'ファミリーマート', 'country': 'jp', 'category': '일본편의점'},
        '로손': {'name': '로손', 'name_jp': 'ローソン', 'country': 'jp', 'category': '일본편의점'},
    }
    
    info = store_info[store_key]
    name = info['name']
    country = info['country']
    
    # 제품 정보를 텍스트로 변환
    products_text = ""
    for i, p in enumerate(products, 1):
        products_text += f"\n{i}. {p['name']} - {p['price']}"
        if country == 'jp' and 'name_jp' in p:
            products_text += f" ({p['name_jp']})"
    
    # 짧은 프롬프트 (토큰 절약)
    if country == 'kr':
        prompt = f"""당신은 편의점 블로거입니다.
{name}의 실제 신상 제품으로 블로그 글을 작성하세요.

**제품 정보 (실제):**{products_text}

요구사항:
1. 제목: 클릭하고 싶은 제목 (이모지 포함, 한일 병기)
2. 본문: 각 제품마다 구체적인 리뷰 (맛, 식감, 꿀조합)
3. HTML 형식, MZ세대 스타일
4. 일본어 요약 포함

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["편의점신상", "{name}"]}}
"""
    else:
        prompt = f"""당신은 일본 편의점 블로거입니다.
{name}의 실제 신상 제품으로 블로그 글을 작성하세요.

**제품 정보 (실제):**{products_text}

요구사항:
1. 제목: 클릭하고 싶은 제목 (한일 병기)
2. 본문: 각 제품마다 구체적인 리뷰 (일본 문화 팁 포함)
3. HTML 형식
4. 일본 여행 가이드 느낌

JSON 형식:
{{"title": "제목", "content": "HTML 본문", "tags": ["일본편의점", "{name}"]}}
"""
    
    print(f"  📝 AI 리뷰 생성 중... (프롬프트 길이: {len(prompt)} 자)")
    
    try:
        if AI_PROVIDER == 'GEMINI':
            result = _call_gemini(prompt)
        else:
            result = _call_openai(prompt)
        
        if result:
            result['category'] = info['category']
            result['country'] = country
            result['store_key'] = store_key
            result['products'] = products  # 실제 제품 정보 저장
            
            print(f"  ✅ 생성 완료: {result['title'][:40]}...")
            return result
        
    except Exception as e:
        print(f"  ❌ 실패: {e}")
    
    return None


def _call_gemini(prompt):
    """Gemini API 호출"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
    
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }
    
    response = requests.post(url, json=data, timeout=90)
    response.raise_for_status()
    
    result_text = response.json()['candidates'][0]['content']['parts'][0]['text']
    return json.loads(result_text)


def _call_openai(prompt):
    """OpenAI API 호출"""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    
    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "당신은 편의점 전문 블로거입니다."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
        "response_format": {"type": "json_object"}
    }
    
    response = requests.post("https://api.openai.com/v1/chat/completions", 
                           headers=headers, json=data, timeout=90)
    response.raise_for_status()
    
    return json.loads(response.json()['choices'][0]['message']['content'])


def crawl_and_generate_all():
    """모든 편의점 크롤링 + AI 생성"""
    
    print("=" * 60)
    print(f"🚀 크롤링 + AI 시스템 시작: {datetime.now(KST)}")
    print("=" * 60)
    
    crawler = ConvenienceStoreCrawler()
    
    # 크롤링 매핑
    crawl_map = {
        'GS25': lambda: crawler.crawl_gs25(),
        'CU': lambda: crawler.crawl_cu(),
        '세븐일레븐_한국': lambda: crawler.crawl_seven_eleven_kr(),
        '세븐일레븐_일본': lambda: crawler.crawl_japan_store('세븐일레븐'),
        '패밀리마트': lambda: crawler.crawl_japan_store('패밀리마트'),
        '로손': lambda: crawler.crawl_japan_store('로손'),
    }
    
    results = []
    
    for store_key, crawl_func in crawl_map.items():
        print(f"\n{'='*60}")
        print(f"[{len(results)+1}/6] {store_key}")
        print(f"{'='*60}")
        
        try:
            # 1단계: 크롤링
            print("  🕷️ 제품 정보 크롤링...")
            products = crawl_func()
            
            if not products:
                print("  ⚠️ 크롤링 실패, 건너뜀")
                continue
            
            print(f"  ✅ {len(products)}개 제품 수집:")
            for p in products:
                print(f"     - {p['name']} ({p['price']})")
            
            # 2단계: AI 리뷰 생성
            result = generate_review_with_real_products(store_key, products)
            
            if result:
                results.append(result)
                print(f"  💾 저장 완료 (총 {len(results)}개)")
            
            # Rate Limit 방지
            if len(results) < 6:
                print("  ⏱️ 30초 대기...")
                import time
                time.sleep(30)
        
        except Exception as e:
            print(f"  ❌ 에러: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*60}")
    print(f"🎉 완료! 총 {len(results)}개 글 생성")
    print(f"{'='*60}")
    
    # 결과 요약
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['store_key']}: {r['title'][:50]}...")
    
    return results


# ========================================
# 테스트
# ========================================
if __name__ == "__main__":
    # 전체 크롤링 + 생성
    results = crawl_and_generate_all()
    
    # 결과 저장
    if results:
        output_file = f"/tmp/crawl_result_{datetime.now(KST).strftime('%Y%m%d_%H%M')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 결과 저장: {output_file}")
        print(f"✅ {len(results)}개 글 생성 완료!")
    else:
        print("\n❌ 생성된 글이 없습니다.")
