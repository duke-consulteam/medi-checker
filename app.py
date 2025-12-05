import streamlit as st
import openai
import base64
import streamlit_authenticator as stauth
import pandas as pd # 데이터 관리용
from datetime import datetime # 날짜 기록용
from PIL import Image

# --------------------------------------------------------
# ★ 비밀번호 암호화 도구
# --------------------------------------------------------
try:
    from streamlit_authenticator.utilities.hasher import Hasher
except ImportError:
    from streamlit_authenticator import Hasher

# 페이지 설정
st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# ==========================================
# 0. 데이터 저장소 (세션 스테이트 활용)
# ==========================================
# 앱이 켜져 있는 동안 데이터를 저장할 '가상의 엑셀'을 만듭니다.
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(username, type, input_summary, result):
    """검수 결과를 저장하는 함수"""
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "사용자": username,
        "유형": type, # 텍스트 or 이미지
        "입력내용": input_summary, # 광고 문구 앞부분 등
        "판정결과": "반려" if "반려" in result else ("주의" if "주의" in result else "승인"),
        "상세결과": result
    })

# ==========================================
# 1. 로그인 시스템
# ==========================================
passwords_to_hash = ['123']
hashed_passwords = Hasher(passwords_to_hash).generate()

user_data = {
    'credentials': {
        'usernames': {
            'admin': {
                'name': '김대표',
                'password': hashed_passwords[0],
                'email': 'admin@consul.team',
            },
            'user1': { # 테스트용 고객 ID 추가
                'name': '박원장',
                'password': hashed_passwords[0],
                'email': 'park@clinic.com',
            }
        }
    },
    'cookie': {'expiry_days': 0, 'key': 'secret_key', 'name': 'medi_cookie'},
    'preauthorized': {'emails': []}
}

authenticator = stauth.Authenticate(
    user_data['credentials'],
    user_data['cookie']['name'],
    user_data['cookie']['key'],
    user_data['cookie']['expiry_days'],
    user_data['preauthorized']
)

authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('아이디 또는 비밀번호가 틀렸습니다.')
    st.stop()
elif st.session_state["authentication_status"] is None:
    st.stop()

# ==========================================
# 2. 메인 화면 구성 (대시보드 vs 새 검수)
# ==========================================
user_name = st.session_state['name']
user_id = st.session_state['username']

# 사이드바 메뉴
with st.sidebar:
    st.title(f"👤 {user_name}님")
    st.caption(f"ID: {user_id}")
    
    # 메뉴 선택
    menu = st.radio("메뉴 선택", ["📊 나의 대시보드", "✨ 새로운 검수 요청"])
    
    st.divider()
    authenticator.logout('로그아웃', 'sidebar')
    st.info("💡 창을 닫으면 기록이 초기화됩니다.")

# API 키 확인
api_key = st.secrets.get("OPENAI_API_KEY")
if not api_key:
    st.error("API 키 설정을 확인해주세요.")
    st.stop()
client = openai.OpenAI(api_key=api_key)


# ------------------------------------------------
# [메뉴 A] 나의 대시보드 (고객별 관리 화면)
# ------------------------------------------------
if menu == "📊 나의 대시보드":
    st.title("📊 캠페인 관리 대시보드")
    st.write(f"**{user_name}**님의 최근 검수 이력입니다.")

    # 저장된 데이터 가져오기
    df = pd.DataFrame(st.session_state['history'])

    if not df.empty:
        # 내 아이디로 된 기록만 필터링
        my_df = df[df['사용자'] == user_id]

        if not my_df.empty:
            # 1. 요약 지표 (Metrics)
            col1, col2, col3 = st.columns(3)
            col1.metric("총 검수 건수", f"{len(my_df)}건")
            col2.metric("반려/주의", f"{len(my_df[my_df['판정결과'] != '승인'])}건")
            col3.metric("오늘 날짜", datetime.now().strftime("%Y-%m-%d"))

            # 2. 데이터 테이블 표시
            st.subheader("📋 상세 이력")
            # 보기 좋게 컬럼 순서 정리
            display_df = my_df[["날짜", "유형", "판정결과", "입력내용"]]
            st.dataframe(display_df, use_container_width=True)

            # 3. 엑셀 다운로드 버튼
            csv = my_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                "📥 엑셀로 내역 다운로드",
                csv,
                "my_ad_history.csv",
                "text/csv",
                key='download-csv'
            )
            
            # 4. 상세 내용 보기 (Expandable)
            st.subheader("🔍 최근 분석 결과 다시보기")
            for index, row in my_df.iterrows():
                with st.expander(f"[{row['날짜']}] {row['유형']} - {row['판정결과']}"):
                    st.write("**분석 내용:**")
                    st.markdown(row['상세결과'])
        else:
            st.info("아직 검수 기록이 없습니다.")
    else:
        st.info("아직 검수 기록이 없습니다. '새로운 검수 요청' 메뉴에서 검수를 진행해보세요.")


# ------------------------------------------------
# [메뉴 B] 새로운 검수 요청 (기존 기능)
# ------------------------------------------------
elif menu == "✨ 새로운 검수 요청":
    st.title("✨ 새로운 광고 심의 요청")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 정밀 분석"])

    # --- 1. 텍스트 심의 ---
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            ad_text = st.text_area("광고 문구를 입력하세요:", height=300)
        with col2:
            if st.button("텍스트 검수", type="primary"):
                if not ad_text:
                    st.warning("문구를 입력하세요.")
                else:
                    with st.spinner("분석 중..."):
                        try:
                            response = client.chat.completions.create(
                                model="gpt-4o",
                                messages=[
                                    {"role": "system", "content": "당신은 깐깐한 의료기기 심의관입니다. 과대광고, 절대적 표현(최고 등), 부작용 미기재를 찾아내세요."},
                                    {"role": "user", "content": ad_text}
                                ]
                            )
                            result = response.choices[0].message.content
                            st.success("분석 완료")
                            st.markdown(result)
                            
                            # ★ 대시보드에 자동 저장
                            save_log(user_id, "텍스트", ad_text[:30]+"...", result)
                            st.toast("대시보드에 저장되었습니다!", icon="💾")
                            
                        except Exception as e:
                            st.error(f"오류: {e}")

    # --- 2. 이미지 정밀 분석 ---
    def encode_image(image_file):
        return base64.b64encode(image_file.getvalue()).decode('utf-8')

    with tab2:
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png", "jpeg"])

        if uploaded_file:
            col_img1, col_img2 = st.columns(2)
            with col_img1:
                st.image(uploaded_file, caption='업로드 이미지', use_container_width=True)
                analyze_btn = st.button("이미지 정밀 분석 시작", type="primary")

            if analyze_btn:
                with st.spinner("AI가 시각 요소를 분석 중입니다..."):
                    try:
                        base64_image = encode_image(uploaded_file)
                        vision_prompt = """
                        당신은 식약처 의료기기 심의관입니다. 이미지를 '단계별로' 분석하여 규정 위반을 찾아내세요.
                        출력:
                        1. 상세 관찰
                        2. 심의 판정 (승인/반려/주의 포함)
                        3. 위반 사유
                        4. 수정 가이드
                        ---
                        PROMPT: (DALL-E 3용 영어 프롬프트)
                        """

                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": vision_prompt},
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                    ],
                                }
                            ],
                        )
                        result_text = response.choices[0].message.content
                        
                        # ★ 대시보드에 자동 저장
                        save_log(user_id, "이미지", uploaded_file.name, result_text.split("PROMPT:")[0])
                        st.toast("대시보드에 저장되었습니다!", icon="💾")

                        # 이미지 생성 로직
                        base_prompt = "A hyper-realistic 8k photography of a medical device marketing image. Canon EOS R5 style, minimal, bright clinical lighting, clear focus, professional Korean model looking trustworthy and smiling naturally. No text overlays."
                        if "PROMPT:" in result_text:
                            extracted = result_text.split("PROMPT:")[1].strip()
                            dalle_prompt = f"{extracted}, {base_prompt}"
                        else:
                            dalle_prompt = base_prompt

                        with col_img1:
                            st.markdown("### 📋 분석 결과")
                            st.markdown(result_text.split("PROMPT:")[0])

                        with col_img2:
                            st.markdown("### ✨ AI 추천 대체 이미지")
                            if "반려" in result_text or "주의" in result_text or "위반" in result_text:
                                with st.spinner("고화질 이미지 생성 중..."):
                                    img_response = client.images.generate(
                                        model="dall-e-3", prompt=dalle_prompt, size="1024x1024", quality="hd", style="natural", n=1
                                    )
                                    st.image(img_response.data[0].url, caption="Safe & High Quality Image")
                            else:
                                st.success("문제가 없는 이미지입니다.")

                    except Exception as e:
                        st.error(f"오류: {e}")
