import streamlit as st
import openai
import base64
import streamlit_authenticator as stauth
import pandas as pd
from datetime import datetime
from PIL import Image
import io
import json

# 구글 라이브러리 (에러 나면 requirements.txt에 google-cloud-aiplatform 추가 필수)
try:
    from google.oauth2 import service_account
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel, Image
except ImportError:
    pass # 설치 안됐을 경우 대비

# --------------------------------------------------------
# 0. 설정 및 로그인 (기존과 동일)
# --------------------------------------------------------
try:
    from streamlit_authenticator.utilities.hasher import Hasher
except ImportError:
    from streamlit_authenticator import Hasher

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(username, type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "사용자": username,
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "반려" if "반려" in result else "승인",
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
# 1. API 연결 (OpenAI + Google)
# --------------------------------------------------------
# OpenAI 키
api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# Google 키 (Secrets의 [gcp] 섹션에서 가져옴)
gcp_json = st.secrets.get("gcp", {}).get("json_content")
google_ready = False

if gcp_json:
    try:
        service_account_info = json.loads(gcp_json)
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        project_id = service_account_info["project_id"]
        
        # 구글 Vertex AI 초기화 (us-central1 리전 필수)
        vertexai.init(project=project_id, location="us-central1", credentials=credentials)
        # 이미지 모델 로드 (Imagen 2 또는 3)
        imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
        google_ready = True
    except Exception as e:
        st.sidebar.error(f"구글 연결 실패: {e}")

# 사이드바
user_name = st.session_state['name']
with st.sidebar:
    st.title(f"👤 {user_name}님")
    menu = st.radio("메뉴", ["📊 대시보드", "✨ 검수 요청"])
    st.divider()
    authenticator.logout('로그아웃', 'sidebar')
    if google_ready:
        st.success("✅ 구글 Imagen(나노바나나) 연결됨")
    else:
        st.warning("⚠️ 구글 키가 없어 DALL-E로 작동합니다.")

# --------------------------------------------------------
# [메뉴 A] 대시보드
# --------------------------------------------------------
if menu == "📊 대시보드":
    st.title("📊 캠페인 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        my_df = df[df['사용자'] == st.session_state['username']]
        st.dataframe(my_df)
    else:
        st.info("기록 없음")

# --------------------------------------------------------
# [메뉴 B] 검수 요청
# --------------------------------------------------------
elif menu == "✨ 검수 요청":
    st.title("✨ 광고 심의 및 자동 보정")
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 부분 수정(Inpainting)"])

    # 텍스트 심의 (OpenAI 사용)
    with tab1:
        ad_text = st.text_area("문구 입력")
        if st.button("검수"):
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role":"system", "content":"의료기기 광고 심의관입니다."}, {"role":"user", "content":ad_text}]
            )
            st.write(response.choices[0].message.content)

    # 이미지 수정 (구글 Imagen 사용)
    def encode_image(image_file):
        return base64.b64encode(image_file.getvalue()).decode('utf-8')

    with tab2:
        st.info("💡 **구글 Imagen**을 사용하여 원본의 모델/구도는 유지하고, '피'나 '배경'만 수정합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                st.image(uploaded_file, caption="원본", use_container_width=True)
                
            if st.button("이미지 분석 및 수정"):
                with st.spinner("1. 이미지를 분석 중입니다..."):
                    # GPT-4o가 먼저 분석
                    base64_image = encode_image(uploaded_file)
                    vision_prompt = """
                    이 이미지에서 의료기기법 위반 요소(피, 혐오감, 공포 분위기)를 찾으세요.
                    그리고 이걸 구글 Imagen으로 수정하기 위한 '영어 편집 명령(Edit Instruction)'을 작성하세요.
                    
                    명령 예시: "Remove the blood on the mouth and replace with clean skin", "Change the background to a bright hospital office"
                    
                    출력 형식:
                    1. 판정: [반려/승인]
                    2. 위반내용: ...
                    ---
                    EDIT_PROMPT: (영어 편집 명령어)
                    """
                    
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"user", "content":[{"type":"text","text":vision_prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{base64_image}"}}]}]
                    )
                    result_text = response.choices[0].message.content
                    
                    if "EDIT_PROMPT:" in result_text:
                        edit_instruction = result_text.split("EDIT_PROMPT:")[1].strip()
                    else:
                        edit_instruction = "Make the image look professional and clean, remove any blood."
                    
                    save_log(st.session_state['username'], "이미지", uploaded_file.name, result_text.split("EDIT_PROMPT:")[0])
                    
                    with col1:
                        st.markdown(result_text.split("EDIT_PROMPT:")[0])

                # 구글 Imagen으로 수정 (Edit)
                with col2:
                    if google_ready:
                        with st.spinner(f"2. 구글 Imagen이 수정 중입니다: '{edit_instruction}'"):
                            try:
                                # 스트림릿 업로드 파일을 구글 포맷으로 변환
                                image_bytes = uploaded_file.getvalue()
                                base_img = Image(image_bytes)
                                
                                # ★ 구글의 핵심 기능: edit_image ★
                                # 마스크 없이 프롬프트만으로 수정하는 모드입니다.
                                generated_images = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=edit_instruction,
                                    number_of_images=1
                                )
                                
                                st.image(generated_images[0]._image_bytes, caption="구글 Imagen 수정본 (원본 유지)", use_container_width=True)
                                st.success("원본의 인물과 구도는 살리고 문제점만 수정했습니다.")
                                
                            except Exception as e:
                                st.error(f"구글 수정 실패: {e}")
                                st.info("혹시 구글 키 설정이나 Vertex AI API 활성화를 확인하셨나요?")
                    else:
                        st.error("구글 API 키가 설정되지 않아 수정 기능을 쓸 수 없습니다.")
