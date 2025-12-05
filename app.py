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
# 1. 수동 로그인 시스템 (라이브러리 미사용 - 에러 없음)
# --------------------------------------------------------
# 세션 초기화
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
            # ★ 아이디/비번 설정 (여기서 수정 가능) ★
            if username == "admin" and password == "123":
                st.session_state['logged_in'] = True
                st.session_state['username'] = "김대표"
                st.rerun() # 화면 새로고침
            else:
                st.error("아이디 또는 비밀번호가 틀렸습니다.")

def logout():
    st.session_state['logged_in'] = False
    st.session_state['username'] = ""
    st.rerun()

# 로그인이 안 되어 있으면 로그인 화면만 보여주고 중단
if not st.session_state['logged_in']:
    login()
    st.stop()

# ========================================================
# 여기서부터는 로그인이 성공해야만 보입니다
# ========================================================

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
        # 내 기록만 보기
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
                with st.spinner("1. 안전한 수정 명령 생성 중..."):
                    b64_img = encode_image(uploaded_file)
                    
                    prompt = """
                    이 이미지에서 의료기기법 위반 요소(피, 공포감 등)를 찾으세요.
                    그리고 이를 구글 AI로 수정하기 위한 '영어 프롬프트(Edit Instruction)'를 작성하세요.
                    
                    🚨 [단어 금지 규칙]
                    - 금지: Blood, Wound, Injury, Scar, Horror, Vampire, Kill, Death
                    - 사용: Clean skin, Professional doctor, Bright background
                    
                    형식:
                    1. 판정: ...
                    ---
                    EDIT_PROMPT: (안전한 영어 단어만 사용한 수정 명령)
                    """
                    
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                    )
                    res_text = resp.choices[0].message.content
                    
                    if "EDIT_PROMPT:" in res_text:
                        edit_instruction = res_text.split("EDIT_PROMPT:")[1].strip()
                    else:
                        edit_instruction = "Make the person look professional and clean"
                    
                    # 파이썬 이중 필터링
                    forbidden_words = ["blood", "wound", "horror", "kill", "injury", "scar"]
                    for word in forbidden_words:
                        edit_instruction = edit_instruction.lower().replace(word, "blemish")
                    
                    with col1:
                        st.markdown(res_text.split("EDIT_PROMPT:")[0])
                        st.caption(f"🤖 명령: '{edit_instruction}'")
                        save_log(user_name, "이미지", uploaded_file.name, res_text)

                with col2:
                    if google_ready:
                        with st.spinner(f"2. 구글이 수정 중..."):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=edit_instruction,
                                    number_of_images=1
                                )
                                st.image(gen_imgs[0]._image_bytes, caption="구글 수정본", use_container_width=True)
                                st.success("수정 완료!")

                            except Exception as e:
                                st.warning("⚠️ 부분 수정 실패. 새로 그리기로 전환합니다.")
                                try:
                                    safe_gen_prompt = f"Professional medical photo. {edit_instruction}. Clean atmosphere."
                                    gen_imgs = imagen_model.generate_images(
                                        prompt=safe_gen_prompt, number_of_images=1
                                    )
                                    st.image(gen_imgs[0]._image_bytes, caption="구글 생성본", use_container_width=True)
                                except Exception as e2:
                                    st.error(f"생성 실패: {e2}")
                    else:
                        st.error("⚠️ 구글 키 설정 오류")
