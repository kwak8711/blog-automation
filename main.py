# ========================================
# 이미지 불러오기 (ChatGPT 수동 생성 → 자동 업로드)
# ========================================
def get_local_image(store_name):
    """
    ChatGPT로 미리 만든 이미지를 로컬에서 찾아서 반환 (무료 버전용)
    예: images/GS25_20251029.jpg  또는  images/GS25.jpg
    """
    import os
    from datetime import datetime
    base_dir = "images"
    date_tag = datetime.now(KST).strftime("%Y%m%d")

    candidates = [
        f"{base_dir}/{store_name}_{date_tag}.jpg",
        f"{base_dir}/{store_name}.jpg"
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "rb") as f:
                print(f"  ✅ 로컬 이미지 사용: {path}")
                return f.read()
    print(f"  ⚠️ 로컬 이미지 없음: {store_name} — 크롤링 이미지로 대체")
    return None


# ========================================
# 블로그 콘텐츠 생성 (무료 이미지 방식)
# ========================================
def generate_blog_post(store_name):
    try:
        print(f"  📝 {store_name} 블로그 글 생성 중...")
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}

        prompt = f"""당신은 편의점 신상을 매일 소개하는 인기 블로거입니다.
{store_name}의 최신 신상 제품을 리뷰하는 블로그 글을 작성해주세요.
... (기존 프롬프트 동일) ...
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

        # ✅ 이미지 처리 (무료 버전)
        local_image = get_local_image(store_name)
        if local_image:
            img_url = upload_image_to_wordpress(local_image, f'{store_name}_{datetime.now(KST).strftime("%Y%m%d")}.jpg')
            result['featured_image'] = img_url or ''
        else:
            # 로컬에 없으면 크롤링된 이미지 중 첫 번째 사용
            image_urls = crawl_product_images(store_name)
            if image_urls:
                img_data = download_image(image_urls[0])
                if img_data:
                    img_url = upload_image_to_wordpress(img_data, f'{store_name}_{datetime.now(KST).strftime("%Y%m%d")}.jpg')
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


# ========================================
# 인스타그램 캡션 생성 (무료 이미지 방식)
# ========================================
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

        # ✅ 이미지 처리 (무료 버전)
        local_image = get_local_image(store_name)
        if local_image:
            img_url = upload_image_to_wordpress(local_image, f'{store_name}_{datetime.now(KST).strftime("%Y%m%d")}.jpg')
            result['image_urls'] = [img_url] if img_url else []
        else:
            result['image_urls'] = crawl_product_images(store_name)

        print(f"  ✅ 완료")
        return result

    except Exception as e:
        print(f"  ❌ 실패: {e}")
        traceback.print_exc()
        return None
