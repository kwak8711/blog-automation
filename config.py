import os

# API 키들 (GitHub Secrets에서 가져옴)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# 워드프레스 설정
WORDPRESS_URL = os.environ.get('WORDPRESS_URL')  # 예: https://yourblog.com
WORDPRESS_USERNAME = os.environ.get('WORDPRESS_USERNAME')
WORDPRESS_PASSWORD = os.environ.get('WORDPRESS_PASSWORD')

# 크롤링 대상 URL들
CRAWL_URLS = {
    'GS25': 'https://gs25.gsretail.com/gscvs/ko/products/youus-freshfood',
    'CU': 'https://cu.bgfretail.com/product/product.do?category=product&depth=1&sf=N',
    'SEVENELEVEN': 'https://www.7-eleven.co.kr/product/presentList.asp'
}

# 블로그 설정
POSTS_PER_DAY = 2  # 하루에 발행할 워드프레스 글 개수
INSTAGRAM_POSTS_PER_DAY = 2  # 하루에 준비할 인스타 콘텐츠 개수
