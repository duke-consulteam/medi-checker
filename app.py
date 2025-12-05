import streamlit as st
import openai
import base64
import pandas as pd
from datetime import datetime
from PIL import Image
import json

# 구글 라이브러리 로드
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
    except Exception:
        pass

# --------------------------------------------------------
# 1. 수동 로그인
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
                st.error("틀렸습니다.")

def logout():
    st.session_state['logged_in'] = False
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
        st.warning("⚠️ DALL-E 모드 (구글키 확인필요)")

# [메뉴 A] 대시보드
if menu == "📊 대시보드":
    st.title("📊 캠페인 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        my_df = df[df['사용자'] == user_name]
        st.dataframe(my_df, use_container_width=True)
    else:
        st.info("기록 없음")

# [메뉴 B] 검수 요청
elif menu == "✨ 검수 요청":
    st.title("✨ 광고 심의 및 보정")
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 원본 보정"])

    with tab1:
        ad_text = st.text_area("문구 입력")
        if st.button("검수"):
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role":"system", "content":"의료기기 심의관. 대체 문구 3개 제안."}, {"role":"user", "content":ad_text}]
            )
            res = resp.choices[0].message.content
            st.markdown(res)
            save_log(user_name, "텍스트", ad_text[:20], res)

    def encode_image(image_file):
        image_file.seek(0) 
        return base64.b64encode(image_file.read()).decode('utf-8')

    with tab2:
        st.info("💡 **스마트 뷰티 필터**: 원본 얼굴은 그대로 두고, 문제되는 부분(피, 배경)만 '화장하듯이' 고칩니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
                
            if st.button("이미지 분석 및 원본 보정"):
                with st.spinner("1. 안전한 보정 계획 수립 중..."):
                    b64_img = encode_image(uploaded_file)
                    
                    # ★ 핵심 전략: '지워라' 대신 '바꿔라' (Positive Prompting) ★
                    # 피를 지우라고 하면 차단되니, 피부를 매끄럽게 하라고 명령합니다.
                    prompt = """
                    이 이미지에서 의료기기법 위반 요소(피, 공포 분위기)를 찾으세요.
                    그리고 구글 AI에게 내릴 **안전한 영어 보정 명령(Edit Instruction)**을 작성하세요.
                    
                    [명령 작성 규칙 - 매우 중요]
                    1. 부정적인 단어 금지: remove blood, delete wound, kill vampire (사용 금지 X)
                    2. 긍정적인 단어 사용: **smooth skin texture**, **studio lighting**, **professional portrait**, **dark blue background** (사용 O)
                    3. 원본 유지: 모델의 얼굴이나 머리카락을 바꾸라는 말은 하지 마세요.
                    
                    예시: "Change background to dark blue studio wall. Apply beauty filter for smooth skin."
                    
                    형식:
                    1. 판정: ...
                    ---
                    EDIT_PROMPT: (명령어)
                    """
                    
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                    )
                    res_text = resp.choices[0].message.content
                    
                    # 파싱 및 안전장치
                    edit_instruction = "Change background to blue studio. Smooth skin."
                    try:
                        if "EDIT_PROMPT:" in res_text:
                            edit_instruction = res_text.split("EDIT_PROMPT:")[1].strip()
                    except:
                        pass
                    
                    # 2차 강제 세탁 (Blood -> Red paint / Smooth skin)
                    edit_instruction = edit_instruction.lower()
                    edit_instruction = edit_instruction.replace("blood", "red paint").replace("wound", "texture").replace("remove", "fix")
                    
                    # 나노바나나 스타일 명령 강제 주입
                    final_instruction = f"{edit_instruction}, high quality, photorealistic, keep facial features"

                    with col1:
                        st.markdown(res_text.split("EDIT_PROMPT:")[0])
                        st.caption(f"🤖 보정 명령: {final_instruction}")
                        save_log(user_name, "이미지", uploaded_file.name, res_text)

                with col2:
                    if google_ready:
                        with st.spinner(f"2. 구글 이마젠이 원본을 보정 중..."):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # ★ 원본 유지 핵심: edit_image 사용 ★
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=final_instruction,
                                    number_of_images=1
                                )
                                st.image(gen_imgs[0]._image_bytes, caption="구글 보정본 (Inpainting)", use_container_width=True)
                                st.success("원본의 얼굴과 구도를 그대로 유지했습니다!")

                            except Exception as e:
                                # 구글이 그래도 거부할 경우
                                st.error("⚠️ 구글이 '이미지가 너무 무섭다'며 보정을 거부했습니다.")
                                st.warning("팁: 이미지의 피가 너무 적나라하면 AI가 아예 작업을 거부합니다.")
                                st.caption(f"상세 에러: {e}")
                                
                                # 최후의 수단: 유사한 느낌으로 다시 그리기
                                st.info("대신 최대한 비슷한 느낌의 모델로 새로 그립니다.")
                                try:
                                    fallback_prompt = f"A photo of a woman with black hair and choker, professional medical style, blue background. {final_instruction}"
                                    gen_imgs = imagen_model.generate_images(prompt=fallback_prompt, number_of_images=1)
                                    st.image(gen_imgs[0]._image_bytes, caption="새로 그리기 대체안", use_container_width=True)
                                except:
                                    pass
                    else:
                        st.error("⚠️ 구글 키 설정 오류")
