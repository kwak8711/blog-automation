name: Blog Automation (한국 + 일본 편의점)

on:
  schedule:
    # 밤 11시 (23:00) - 1차 배치 (GS25, 세븐일레븐일본)
    - cron: '0 14 * * *'  # KST 23:00 = UTC 14:00
    
    # 새벽 1시 (01:00) - 2차 배치 (CU, 패밀리마트)
    - cron: '0 16 * * *'  # KST 01:00 = UTC 16:00
    
    # 새벽 3시 (03:00) - 3차 배치 (세븐일레븐한국, 로손)
    - cron: '0 18 * * *'  # KST 03:00 = UTC 18:00
    
    # 아침 08:00 (KST) → UTC 23:00 (전날)에 알림 (한국 - GS25)
    - cron: '0 23 * * *'
    
    # 아침 09:00 (KST) → UTC 00:00에 알림 (일본 - 세븐일레븐)
    - cron: '0 0 * * *'
    
    # 점심 12:00 (KST) → UTC 03:00에 알림 (한국 - CU)
    - cron: '0 3 * * *'
    
    # 점심 13:00 (KST) → UTC 04:00에 알림 (일본 - 패밀리마트)
    - cron: '0 4 * * *'
    
    # 저녁 20:00 (KST) → UTC 11:00에 알림 (한국 - 세븐일레븐)
    - cron: '0 11 * * *'
    
    # 저녁 21:00 (KST) → UTC 12:00에 알림 (일본 - 로손)
    - cron: '0 12 * * *'
    
  workflow_dispatch:
    inputs:
      mode:
        description: '실행 모드'
        required: true
        default: 'generate'
        type: choice
        options:
          - generate  # 콘텐츠 생성 및 예약발행 (한국 3개 + 일본 3개)
          - notify    # 발행 알림만

jobs:
  run-automation:
    runs-on: ubuntu-latest
    
    steps:
    - name: 코드 체크아웃
      uses: actions/checkout@v3
    
    - name: Python 3.11 설치
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: 의존성 설치
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: 실행 모드 결정
      id: set-mode
      run: |
        if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
          # 수동 실행: 사용자가 선택한 모드 사용
          echo "MODE=${{ github.event.inputs.mode }}" >> $GITHUB_ENV
        elif [ "${{ github.event_name }}" = "schedule" ]; then
          # 스케줄 실행: 시간에 따라 모드 결정
          if [ "${{ github.event.schedule }}" = "0 14 * * *" ] || [ "${{ github.event.schedule }}" = "0 16 * * *" ] || [ "${{ github.event.schedule }}" = "0 18 * * *" ]; then
            echo "MODE=generate" >> $GITHUB_ENV
          else
            echo "MODE=notify" >> $GITHUB_ENV
          fi
        else
          # 기타: generate 모드
          echo "MODE=generate" >> $GITHUB_ENV
        fi
    
    - name: 한일 편의점 자동화 실행
      env:
        OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        WORDPRESS_URL: ${{ secrets.WORDPRESS_URL }}
        WORDPRESS_USERNAME: ${{ secrets.WORDPRESS_USERNAME }}
        WORDPRESS_PASSWORD: ${{ secrets.WORDPRESS_PASSWORD }}
        INSTAGRAM_PROFILE_URL: ${{ secrets.INSTAGRAM_PROFILE_URL }}
        NAVER_BLOG_URL: ${{ secrets.NAVER_BLOG_URL }}
        MODE: ${{ env.MODE }}
      run: python main.py
