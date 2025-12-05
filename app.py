import streamlit as st
import openai
import base64
import streamlit_authenticator as stauth
from PIL import Image

# --------------------------------------------------------
# ★ 비밀번호 암호화 도구 불러오기 (버전별 호환성 처리)
# --------------------------------------------------------
try:
    from streamlit_authenticator.utilities.hasher import Hasher
except ImportError:
    from streamlit_authenticator import Hasher

# 페이지 설정
st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# ==========================================
# 0. 로그인 시스템
# ==========================================

# 1. 비밀번호 '123'을 암호화된 코드로 변환
# (이렇게 해야 로그인이 됩니다)
passwords_to_hash = ['123']
hashed_passwords = Hasher(passwords_to_hash).generate()

# 2. 사용자 정보 설정
user_data = {
    'credentials': {
        'usernames': {
            'admin': {
                'name': '김대표',
                'password': hashed_passwords[0], # 암호화된 비밀번호 사용
                'email': 'admin@consul.team',
            }
        }
    },
    'cookie': {'expiry_days': 0, 'key': 'secret_key', 'name': 'medi_cookie'},
    'preauthorized': {'emails': []}
}

# 3. 로그인 위젯 초기화
authenticator = stauth.Authenticate(
    user_data['credentials'],
    user_data['cookie']['name'],
    user_data['cookie']['key'],
    user_data['cookie']['expiry_days'],
    user_data['preauthorized']
)

# 4. 로그인 화면 출력
# (최신 버전 호환을 위해 괄호를 비워둡니다)
authenticator.login()

# 5. 로그인 상태 확인
if st.session_state["authentication_status"] is False:
    st.error('아이디 또는 비밀번호가 틀렸습니다.')
    st.stop()
elif st.session_state["authentication_status"] is None:
    # st.warning('아이디...') -> 요청하신 대로 문구를 삭제했습니다.
    st.stop()

# ==========================================
# 로그인 성공 시 보이는 메인 화면
# ==========================================

# 사이드바
with st.sidebar:
    st.title(f"👤 {st.session_state['name']}님 환영합니다")
    # 로그아웃 버튼
    authenticator.logout('로그아웃', 'sidebar')
    st.divider()
    st.info("💡 프로토타입 버전입니다.")

# 메인 내용
st.title("🏥 의료기기 광고 AI 통합 관리")

# API 키 설정
api_key = st.secrets.get("OPENAI_API_KEY")
if not api_key:
    st.error("API 키 설정을 확인해주세요.")
    st.stop()

client = openai.OpenAI(api_key=api_key)

# 탭 구성
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
                        st.success("분석 완료")
                        st.markdown(response.choices[0].message.content)
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
            with st.spinner("AI가 시각 요소를 단계별로 분석 중입니다..."):
                try:
                    base64_image = encode_image(uploaded_file)
                    
                    vision_prompt = """
                    당신은 식약처 의료기기 심의관입니다. 이미지를 '단계별로' 분석하여 규정 위반을 찾아내세요.
                    [분석 단계]
                    1. 시각적 요소 나열: 도구(개구기, 주사기), 신체 반응(피, 상처), 표정 등.
                    2. 규정 대조: '혐오감 조성', '시술 장면', '비포애프터 비교' 금지 조항.
                    3. 판정: 승인/반려 결정.
                    
                    출력:
                    1. 상세 관찰
                    2. 심의 판정
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
