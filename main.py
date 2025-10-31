import os
import json
import time
import re
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

# ========================================
# 🌏 환경변수
# ========================================
OPENAI_API_KEY       = os.environ.get('OPENAI_API_KEY')
GROQ_API_KEY         = os.environ.get('GROQ_API_KEY')
GEMINI_API_KEY       = os.environ.get('GEMINI_API_KEY')
SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL')

WORDPRESS_URL        = os.environ.get('WORDPRESS_URL')
WORDPRESS_USERNAME   = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD   = os.environ.get('WORDPRESS_PASSWORD')

SLACK_LINK_WORDPRESS = os.environ.get('SLACK_LINK_WORDPRESS', 'https://your-wordpress-site.com')
SLACK_LINK_INSTA     = os.environ.get('SLACK_LINK_INSTA', 'https://instagram.com/')
SLACK_LINK_NAVER     = os.environ.get('SLACK_LINK_NAVER', 'https://blog.naver.com/')

POSTS_PER_DAY = 3
KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")

# ========================================
# 🏪 편의점 목록
# ========================================
STORES = {
    "gs25": {"name_kr": "GS25", "name_jp": "GS25", "country": "kr"},
    "cu": {"name_kr": "CU", "name_jp": "CU", "country": "kr"},
    "7eleven": {"name_kr": "세븐일레븐", "name_jp": "セブンイレブン", "country": "kr"},
    "familymart": {"name_kr": "패밀리마트", "name_jp": "ファミリーマート", "country": "jp"},
    "lawson": {"name_kr": "로손", "name_jp": "ローソン", "country": "jp"},
}

# ========================================
# 공통 유틸
# ========================================
def _ensure_dict(result):
    if isinstance(result, list):
        return result[0] if result else None
    return result

def strip_images(html: str) -> str:
    """이미지 태그 제거 (공주님이 수동으로 넣을 거라서)"""
    if not html:
        return ""
    html = re.sub(r"<img[^>]*>", "", html)
    html = re.sub(r"<figure[^>]*>.*?</figure>", "", html, flags=re.DOTALL)
    return html

# ========================================
# 🇰🇷🇯🇵 이중 박스 구조
# ========================================
def split_kr_jp(html_part: str):
    if "🇯🇵" in html_part:
        before, after = html_part.split("🇯🇵", 1)
        return before, "🇯🇵" + after
    return html_part, ""

def ensure_bilingual_content(html: str, store_name: str) -> str:
    html = strip_images(html)

    def kr_box(body):
        return f"""
        <div style="background:#fffaf1;border:1px solid rgba(255,166,0,0.25);
        padding:16px 18px 14px;border-radius:16px;margin:0 0 10px 0;
        line-height:1.65;color:#3a2a1f;font-size:14.3px;">{body}</div>"""

    def jp_box(body):
        return f"""
        <div style="background:#ffe5cf;border:1px solid rgba(255,151,94,0.35);
        padding:14px 16px 12px;border-radius:16px;margin:0 0 12px 0;
        line-height:1.6;color:#4d3422;font-size:13.5px;">
        <div style='font-weight:600;margin-bottom:4px;'>🇯🇵 日本語要約</div>{body}</div>"""

    parts = re.split(r'(<h2.*?>|<h3.*?>)', html)
    result = ""
    for seg in parts:
        if seg.startswith("<h2") or seg.startswith("<h3"):
            seg = re.sub(r'(<\/?h[23].*?>)', '', seg)
            result += f"<h2 style='font-size:26px;margin:32px 0 16px 0;font-weight:700;color:#2f3542;'>{seg.strip()}</h2>"
        else:
            kr, jp = split_kr_jp(seg)
            if kr.strip():
                result += kr_box(kr)
            if jp.strip():
                result += jp_box(jp)
    return result

# ========================================
# 🧁 워드프레스 HTML
# ========================================
def build_wp_html(ai_result, store_info):
    store_name_kr = store_info.get('name_kr', '편의점')
    store_name_jp = store_info.get('name_jp', store_name_kr)
    title_kor = ai_result.get('title') or f"{store_name_kr} 신상 리뷰!"
    title_jp = f"{store_name_jp} の新商品レビュー"
    main_content = ensure_bilingual_content(ai_result.get('content', ''), store_name_kr)

    hashtags = " ".join([
        "#편의점신상", "#편의점", "#コンビニ", "#コンビニ新商品", "#韓国コンビニ",
        "#コンビニグルメ", "#오늘뭐먹지", "#오늘간식", "#kconbini", f"#{store_name_kr}"
    ])

    return f"""
<div style="max-width:840px;margin:0 auto;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;">
  <div style="background:linear-gradient(120deg,#fff0f5 0%,#edf1ff 100%);
              border:1px solid rgba(248,132,192,0.25);padding:18px 20px;
              border-radius:18px;margin-bottom:18px;display:flex;gap:12px;">
    <div style="font-size:30px;">🛒</div>
    <div>
      <p style="margin:0 0 4px 0;font-weight:700;color:#d62976;font-size:14px;">K-CONBINI DAILY</p>
      <p style="margin:0;font-size:17px;color:#222;font-weight:700;">{title_kor}</p>
      <p style="margin:0;font-size:14px;color:#555;">{title_jp}</p>
    </div>
  </div>

  <h1 style="font-size:32px;margin:6px 0 4px 0;font-weight:700;color:#2f3542;">{title_kor}</h1>
  <p style="margin:0 0 12px 0;font-size:14px;color:#555;">{title_jp}</p>

  <div style="background:#fff7fb;padding:20px;border-radius:16px;margin-bottom:18px;
              border:1.4px solid rgba(252,95,168,0.25);">
    <p style="font-size:15px;line-height:1.7;margin:0;color:#222;">
      안녕하세요! 오늘은 <strong>{store_name_kr}</strong> 신상품들을 소개할게요 😋<br>
      한국어 설명 아래에는 일본어 요약도 넣어뒀어요 💛
    </p>
  </div>

  <div style="background:#fff;border-radius:16px;margin-bottom:28px;">{main_content}</div>

  <div style="background:linear-gradient(135deg,#5f63f2 0%,#7a4fff 60%,#c6b8ff 100%);
              padding:24px 22px;border-radius:18px;margin-bottom:26px;
              box-shadow:0 12px 30px rgba(95,99,242,0.25);">
    <p style="color:#fff;font-size:15px;line-height:1.8;margin:0 0 6px 0;">
      오늘 소개해드린 {store_name_kr} 신상품 중에 뭐가 제일 맛있어 보였는지 댓글로 알려줘요 💜
    </p>
    <p style="color:rgba(255,255,255,0.9);font-size:14px;line-height:1.6;margin:0;">
      今日紹介した{store_name_jp}の新商品もぜひチェックしてね ✨
    </p>
  </div>

  <div style="background:linear-gradient(to right,#f8f9ff 0%,#fff5f8 100%);
              padding:23px 20px;border-radius:16px;text-align:center;
              border:1px dashed rgba(118,75,162,0.3);">
    <p style="margin:0 0 10px 0;font-size:15px;color:#667eea;font-weight:600;">📎 해시태그 / ハッシュタグ</p>
    <p style="margin:0;font-size:13.5px;line-height:2;color:#4b4b4b;">{hashtags}</p>
  </div>
</div>
"""

# ========================================
# 🌐 워드프레스 발행
# ========================================
def publish_to_wordpress(title, content, tags, category="convenience", scheduled_dt_kst=None):
    try:
        wp = Client(f"{WORDPRESS_URL}/xmlrpc.php", WORDPRESS_USERNAME, WORDPRESS_PASSWORD)
        post = WordPressPost()
        post.title = title
        post.content = content
        post.terms_names = {"post_tag": tags, "category": [category]}

        if scheduled_dt_kst:
            dt_utc = scheduled_dt_kst.astimezone(UTC)
            post.date = scheduled_dt_kst
            post.date_gmt = dt_utc
            post.post_status = 'future'
        else:
            post.post_status = 'publish'

        post_id = wp.call(NewPost(post))
        post_url = f"{WORDPRESS_URL}/?p={post_id}"
        print(f"✅ 워드프레스 예약 성공: {post_url}")
        return post_id, post_url
    except Exception as e:
        print(f"❌ 워드프레스 실패: {e}")
        return None, None

# ========================================
# 📨 슬랙
# ========================================
def send_slack(payload):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass

def send_slack_insta_only(insta_caption, store_name, scheduled_dt, post_url):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "📷 인스타 올릴 시간 미리 알려줄게 💖"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*{store_name}* 글이 *{scheduled_dt.strftime('%Y-%m-%d %H:%M')}* 에 올라가요.\n이 캡션 복붙해서 인스타에 올려봐 😎"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"```{insta_caption}```"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "🟩 워드프레스 보기"}, "url": post_url},
            {"type": "button", "text": {"type": "plain_text", "text": "📷 인스타 바로가기"}, "url": SLACK_LINK_INSTA}
        ]}
    ]
    send_slack({"text": "인스타 캡션", "blocks": blocks})

# ========================================
# 🧠 생성 & 예약
# ========================================
def generate_and_schedule():
    now = datetime.now(KST)
    tomorrow = (now + timedelta(days=1)).date()
    slots = [datetime(tomorrow.year, tomorrow.month, tomorrow.day, h, 0, tzinfo=KST) for h in [9, 12, 18]]
    stores = list(STORES.keys())

    for i, key in enumerate(stores[:POSTS_PER_DAY]):
        info = STORES[key]
        slot = slots[i]

        prompt = f"{info['name_kr']} 편의점 신상품 소개 블로그를 JSON으로 만들어줘. 한국어 설명 뒤에 🇯🇵 일본어 요약도 붙여줘."
        data = {"title": f"{info['name_kr']} 신상 리뷰!", "content": f"<p>{info['name_kr']} 신상 테스트 컨텐츠</p> 🇯🇵 <p>{info['name_jp']} の新商品まとめ</p>"}

        html = build_wp_html(data, info)
        post_id, post_url = publish_to_wordpress(data['title'], html, ["편의점신상"], "convenience", slot)

        caption = f"🛒 {data['title']}\n\n{info['name_kr']} 신상이에요 💖\n\n⏰ {slot.strftime('%H:%M')} 발행 예정!"
        send_slack_insta_only(caption, info['name_kr'], slot, post_url or SLACK_LINK_WORDPRESS)

# ========================================
# MAIN
# ========================================
if __name__ == "__main__":
    generate_and_schedule()
