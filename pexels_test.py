#!/usr/bin/env python3
"""
Pexels API 테스트 스크립트
- 실제로 이미지를 검색해서 결과를 보여줍니다
"""

import requests
import json

# =========================
# 여기에 Pexels API 키 입력
# =========================
PEXELS_API_KEY = "SXNImZYth3FGh36DDOp1RoRd5Hg9rGBYR0tWbfZf4P9AzfRa6FsAASHi"  # https://www.pexels.com/api/ 에서 발급

# 테스트할 제품 카테고리
TEST_KEYWORDS = {
    '라면': 'ramen noodles instant',
    '김밥': 'kimbap rice roll',
    '케이크': 'cake dessert pastry',
    '샌드위치': 'sandwich deli',
    '음료': 'beverage drink juice',
    '과자': 'snacks chips',
}


def search_pexels(keyword, count=3):
    """Pexels에서 이미지 검색"""
    try:
        print(f"\n🔍 검색어: '{keyword}'")
        print("-" * 60)
        
        headers = {"Authorization": PEXELS_API_KEY}
        url = "https://api.pexels.com/v1/search"
        params = {
            "query": keyword,
            "per_page": count,
            "orientation": "landscape"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        total = data.get('total_results', 0)
        photos = data.get('photos', [])
        
        print(f"📊 총 {total:,}개 결과 중 {len(photos)}개 표시\n")
        
        if not photos:
            print("❌ 결과 없음\n")
            return []
        
        results = []
        for i, photo in enumerate(photos, 1):
            result = {
                'id': photo['id'],
                'photographer': photo['photographer'],
                'url': photo['src']['large'],
                'thumbnail': photo['src']['small'],
                'alt': photo.get('alt', 'No description'),
                'width': photo['width'],
                'height': photo['height']
            }
            results.append(result)
            
            print(f"[{i}] {result['alt'][:60]}")
            print(f"    👤 작가: {result['photographer']}")
            print(f"    📐 크기: {result['width']}x{result['height']}")
            print(f"    🔗 {result['url']}")
            print()
        
        return results
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("❌ API 키가 유효하지 않습니다!")
            print("   https://www.pexels.com/api/ 에서 키를 발급받으세요.")
        else:
            print(f"❌ HTTP 에러: {e}")
        return []
    except Exception as e:
        print(f"❌ 에러: {e}")
        return []


def test_all_categories():
    """모든 카테고리 테스트"""
    print("=" * 60)
    print("🖼️  PEXELS API 테스트")
    print("=" * 60)
    
    if PEXELS_API_KEY == "YOUR_API_KEY_HERE":
        print("\n❌ API 키를 입력하세요!")
        print("1. https://www.pexels.com/api/ 접속")
        print("2. 이메일로 가입 (무료)")
        print("3. API Key 복사")
        print("4. 이 파일의 PEXELS_API_KEY에 붙여넣기")
        return
    
    all_results = {}
    
    for category, keyword in TEST_KEYWORDS.items():
        print(f"\n\n{'='*60}")
        print(f"📦 카테고리: {category}")
        print(f"{'='*60}")
        
        results = search_pexels(keyword, count=3)
        all_results[category] = results
        
        # API 제한 방지
        import time
        time.sleep(1)
    
    # 요약
    print("\n\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)
    
    for category, results in all_results.items():
        status = "✅" if results else "❌"
        print(f"{status} {category}: {len(results)}개 이미지 발견")
    
    print("\n✅ 테스트 완료!")
    print("\n💡 Pexels는 완전 무료이고 상업적 사용 가능합니다!")
    print("   이미지 품질도 높고, 편의점 블로그에 딱 좋아요! 👍")


def quick_test():
    """빠른 테스트 (라면 1개만)"""
    print("=" * 60)
    print("⚡ 빠른 테스트: 라면 이미지 검색")
    print("=" * 60)
    
    if PEXELS_API_KEY == "YOUR_API_KEY_HERE":
        print("\n❌ API 키를 입력하세요!")
        print("스크립트 맨 위의 PEXELS_API_KEY를 수정하세요.")
        return
    
    results = search_pexels("ramen noodles", count=5)
    
    if results:
        print("\n✅ 성공! Pexels API가 정상 작동합니다!")
        print(f"\n🎉 {len(results)}개의 고품질 라면 사진을 찾았어요!")
        print("\n💡 이런 식으로 자동화 시스템이 이미지를 찾아줍니다!")
    else:
        print("\n❌ 실패! API 키를 확인하세요.")


if __name__ == "__main__":
    import sys
    
    print("\n🚀 Pexels API 테스트를 시작합니다!\n")
    
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        quick_test()
    else:
        test_all_categories()
    
    print("\n" + "=" * 60)
