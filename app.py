import streamlit as st
import openai
import base64
import streamlit_authenticator as stauth
import pandas as pd
from datetime import datetime
from PIL import Image
import json

# 구글 라이브러리
try:
    from google.oauth2 import service_account
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel, Image
except ImportError:
    pass

# 비밀번호 해시
try:
    from streamlit_authenticator.utilities.hasher import Hasher
except ImportError:
    from streamlit_authenticator import Hasher

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# --------------------------------------------------------
# 0. 구글 연결 설정 (자동 보정 기능 탑재)
# --------------------------------------------------------
google_ready = False
imagen_model = None
google_error_msg = ""

if "gcp" in st.secrets:
    try:
        # 1. Secrets 정보를 가져옵니다. (수정 가능한 딕셔너리로 변환)
        service_account_info = dict(st.secrets["gcp"])

        # ★ 핵심 수정 1: 줄바꿈 문자(\n) 자동 복구 ★
        if "private_key" in service_account_info:
            service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")

        # ★ 핵심 수정 2: 빠진 필수 항목(token_uri) 자동 주입 ★
        # 이 부분이 없어서 방금 에러가 난 것입니다. 코드가 알아서 채워넣습니다.
        if "token_uri" not in service_account_info:
            service_account_info["token_uri"] = "https://oauth2.googleapis.com/token"
        if "type" not in service_account_info:
            service_account_info["type"] = "service_account"

        # 2. 구글 인증
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        
        # 3. Vertex AI 초기화
        project_id = service_account_info["project_id"]
        vertexai.init(project=project_id, location="us-central1", credentials=credentials)
        
        # 4. 모델 로드
        imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
        google_ready = True
        
    except Exception as e:
        google_error_msg = str(e)
else:
    google_error_msg = "Secrets에 [gcp] 섹션이 없습니다."


# --------------------------------------------------------
# 1. 데이터 저장 및 로그인
# --------------------------------------------------------
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(username, type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "사용자": username,
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "반려" if "반려" in result else ("주의" if "주의" in result else "승인"),
        "상세결과": result
    })

passwords_to_hash = ['123']
hashed_passwords = Hasher(passwords_to_hash).generate()

user_data = {
    'credentials': {
        'usernames': {
            'admin': {'name': '김대표', 'password': hashed_passwords[0], 'email': 'admin@consul.team'}
        }
    },
    'cookie': {'expiry_days': 0, 'key': 'secret_key', 'name': 'medi_cookie'},
    'preauthorized': {'emails': []}
}

authenticator = stauth.Authenticate(
    user_data['credentials'], user_data['cookie']['name'], user_data['cookie']['key'], 0, []
)
authenticator.login()

if st.session_state["authentication_status"] is False:
    st.error('비번 틀림'); st.stop()
elif st.session_state["authentication_status"] is None:
    st.stop()

# --------------------------------------------------------
# 2. 메인 화면
# --------------------------------------------------------
api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

user_name = st.session_state['name']
with st.sidebar:
    st.title(f"👤 {user_name}님")
    menu = st.radio("메뉴", ["📊 대시보드", "✨ 검수 요청"])
    st.divider()
    authenticator.logout('로그아웃', 'sidebar')
    
    # 연결 상태 표시
    if google_ready:
        st.success("✅ 구글 Imagen 연결됨")
    else:
        st.warning("⚠️ DALL-E 모드 동작 중")
        if google_error_msg:
            st.error(f"오류: {google_error_msg}")


# [메뉴 A] 대시보드
if menu == "📊 대시보드":
    st.title("📊 캠페인 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        my_df = df[df['사용자'] == st.session_state['username']]
        st.dataframe(my_df, use_container_width=True)
    else:
        st.info("기록 없음")

# [메뉴 B] 검수 요청
elif menu == "✨ 검수 요청":
    st.title("✨ 광고 심의 및 보정")
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 부분 수정(Inpainting)"])

    # 텍스트 심의
    with tab1:
        ad_text = st.text_area("문구 입력")
        if st.button("검수"):
            with st.spinner("분석 중..."):
                resp = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role":"system", "content":"의료기기 심의관입니다. 위반시 대체 문구 3개 제안."}, {"role":"user", "content":ad_text}]
                )
                res = resp.choices[0].message.content
                st.markdown(res)
                save_log(st.session_state['username'], "텍스트", ad_text[:20], res)

    # 이미지 수정 (구글 Imagen 사용)
    def encode_image(image_file):
        return base64.b64encode(image_file.getvalue()).decode('utf-8')

    with tab2:
        st.info("💡 **구글 Imagen**을 사용하여 원본을 유지하며 문제점만 수정합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                st.image(uploaded_file, caption="원본", use_container_width=True)
                
            if st.button("이미지 분석 및 수정"):
                with st.spinner("1. 분석 중..."):
                    # GPT-4o 분석
                    b64_img = encode_image(uploaded_file)
                    prompt = """
                    이 이미지의 의료기기법 위반 요소(피, 공포감)를 찾고,
                    구글 Imagen용 영어 수정 명령(Edit Instruction)을 작성하세요.
                    형식:
                    1. 판정: ...
                    ---
                    EDIT_PROMPT: (예: Remove blood from lips, Make background bright blue)
                    """
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                    )
                    res_text = resp.choices[0].message.content
                    
                    if "EDIT_PROMPT:" in res_text:
                        edit_instruction = res_text.split("EDIT_PROMPT:")[1].strip()
                    else:
                        edit_instruction = "Make it clean and professional"
                    
                    with col1:
                        st.markdown(res_text.split("EDIT_PROMPT:")[0])
                        save_log(st.session_state['username'], "이미지", uploaded_file.name, res_text)

                # 구글 Imagen 수정
                with col2:
                    if google_ready:
                        with st.spinner(f"2. 구글이 수정 중... '{edit_instruction}'"):
                            try:
                                img_bytes = uploaded_file.getvalue()
                                base_img = Image(img_bytes)
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=edit_instruction,
                                    number_of_images=1
                                )
                                st.image(gen_imgs[0]._image_bytes, caption="구글 수정본", use_container_width=True)
                                st.success("수정 완료!")
                            except Exception as e:
                                st.error(f"구글 수정 실패: {e}")
                    else:
                        st.error("⚠️ 구글 연결 오류 (사이드바 확인)")
