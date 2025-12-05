import streamlit as st
import openai
import base64
import pandas as pd
from datetime import datetime
from PIL import Image
import json

# 구글 라이브러리
try:
    from google.oauth2 import service_account
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel, Image as VertexImage
except ImportError:
    pass

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# --------------------------------------------------------
# 0. 구글 연결 설정
# --------------------------------------------------------
google_ready = False
imagen_model = None
google_error_msg = ""

if "gcp" in st.secrets:
    try:
        service_account_info = dict(st.secrets["gcp"])
        if "private_key" in service_account_info:
            service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
        if "token_uri" not in service_account_info:
            service_account_info["token_uri"] = "https://oauth2.googleapis.com/token"
        if "type" not in service_account_info:
            service_account_info["type"] = "service_account"

        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        project_id = service_account_info["project_id"]
        vertexai.init(project=project_id, location="us-central1", credentials=credentials)
        imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
        google_ready = True
    except Exception as e:
        google_error_msg = str(e)
else:
    google_error_msg = "Secrets에 [gcp] 섹션이 없습니다."

# --------------------------------------------------------
# 1. 수동 로그인 시스템
# --------------------------------------------------------
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'history' not in st.session_state:
    st.session_state['history'] = []

def login():
    st.title("🏥 Medi-Check Pro 로그인")
    with st.form("login_form"):
        username = st.text_input("아이디")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")
        
        if submitted:
            if username == "admin" and password == "123":
                st.session_state['logged_in'] = True
                st.session_state['username'] = "김대표"
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 틀렸습니다.")

def logout():
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.rerun()

if not st.session_state['logged_in']:
    login()
    st.stop()

def save_log(username, type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "사용자": username,
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "반려" if "반려" in result else ("주의" if "주의" in result else "승인"),
        "상세결과": result
    })

# API 키
api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# 사이드바
user_name = st.session_state['username']
with st.sidebar:
    st.title(f"👤 {user_name}님")
    menu = st.radio("메뉴", ["📊 대시보드", "✨ 검수 요청"])
    st.divider()
    if st.button("로그아웃"):
        logout()
    
    if google_ready:
        st.success("✅ 구글 Imagen 연결됨")
    else:
        st.warning("⚠️ DALL-E 모드 동작 중")
        if google_error_msg:
            st.caption(f"구글 오류: {google_error_msg}")

# [메뉴 A] 대시보드
if menu == "📊 대시보드":
    st.title("📊 캠페인 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        my_df = df[df['사용자'] == user_name]
        st.dataframe(my_df, use_container_width=True)
    else:
        st.info("아직 기록이 없습니다.")

# [메뉴 B] 검수 요청
elif menu == "✨ 검수 요청":
    st.title("✨ 광고 심의 및 보정")
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 부분 수정"])

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
                save_log(user_name, "텍스트", ad_text[:20], res)

    def encode_image(image_file):
        image_file.seek(0) 
        return base64.b64encode(image_file.read()).decode('utf-8')

    with tab2:
        st.info("💡 **구글 Imagen**을 사용하여 원본을 유지하며 문제점만 수정합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
                
            if st.button("이미지 분석 및 수정"):
                with st.spinner("1. 원본 분석 및 수정 계획 수립..."):
                    b64_img = encode_image(uploaded_file)
                    
                    # ★ 핵심 수정: 원본의 생김새를 묘사(Describe)하게 시킴 ★
                    prompt = """
                    이 이미지를 분석하여 다음 3가지를 작성하세요.
                    
                    1. **시각적 묘사(DESCRIPTION)**: 모델의 성별, 머리스타일/색상, 인종, 피부톤, 포즈, 옷차림을 아주 상세한 영어로 묘사하세요. (예: Woman with long wavy black hair, pale skin, wearing black lace choker...)
                    2. **수정 명령(EDIT_PROMPT)**: 피, 상처, 공포 요소를 제거하고 깨끗하게 만들기 위한 영어 명령. (단어 금지: Blood, Wound, Horror -> 대신 Clean skin, Bright background 사용)
                    3. **판정**: 의료기기법 위반 여부.
                    
                    형식:
                    DESCRIPTION: (상세 묘사)
                    EDIT_PROMPT: (수정 명령)
                    판정: ...
                    """
                    
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                    )
                    res_text = resp.choices[0].message.content
                    
                    # 묘사와 명령을 분리해서 추출
                    description = "A professional person"
                    edit_instruction = "Make it clean"
                    
                    if "DESCRIPTION:" in res_text:
                        parts = res_text.split("DESCRIPTION:")[1].split("EDIT_PROMPT:")
                        description = parts[0].strip()
                        if len(parts) > 1:
                            edit_instruction = parts[1].split("판정:")[0].strip()
                    
                    # 이중 필터링
                    forbidden_words = ["blood", "wound", "horror", "kill", "injury", "scar"]
                    for word in forbidden_words:
                        edit_instruction = edit_instruction.lower().repl
