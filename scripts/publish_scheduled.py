# scripts/publish_scheduled.py
from datetime import datetime
import os, glob, frontmatter
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods import posts

# 오늘 날짜 (YYYY-MM-DD)
today = datetime.now().strftime("%Y-%m-%d")

# 워드프레스 로그인 설정
client = Client(
    os.getenv("WORDPRESS_URL"),
    os.getenv("WORDPRESS_USERNAME"),
    os.getenv("WORDPRESS_PASSWORD")
)

# posts 폴더 내 .md 파일에서 publish_date가 오늘인 것만 게시
for path in glob.glob("posts/*.md"):
    post = frontmatter.load(path)
    publish_date = post.get("publish_date")

    if publish_date == today:
        wp_post = WordPressPost()
        wp_post.title = post.get("title", "Untitled Post")
        wp_post.content = post.content
        wp_post.post_status = "publish"

        try:
            client.call(posts.NewPost(wp_post))
            print(f"✅ Published: {wp_post.title}")
        except Exception as e:
            print(f"❌ Failed: {path} — {e}")
    else:
        print(f"⏳ Skipped: {os.path.basename(path)} (publish_date={publish_date})")
