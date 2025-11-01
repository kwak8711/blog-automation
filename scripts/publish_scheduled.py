# scripts/publish_scheduled.py
from datetime import datetime
import os, glob, frontmatter
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods import posts

today = datetime.now().strftime("%Y-%m-%d")

# 워드프레스 연결
client = Client(
    os.getenv("WORDPRESS_URL"),
    os.getenv("WORDPRESS_USERNAME"),
    os.getenv("WORDPRESS_PASSWORD")
)

# posts 폴더 내 모든 마크다운 파일 검사
for path in glob.glob("posts/*.md"):
    post = frontmatter.load(path)
    publish_date = post.get("publish_date")
    title = post.get("title", os.path.basename(path))
    
    if publish_date == today:
        wp_post = WordPressPost()
        wp_post.title = title
        wp_post.content = post.content
        wp_post.post_status = "publish"

        try:
            client.call(posts.NewPost(wp_post))
            print(f"✅ Published: {title}")
        except Exception as e:
            print(f"❌ Failed to publish {title}: {e}")
    else:
        print(f"⏳ Skipped: {title} (publish_date={publish_date})")
