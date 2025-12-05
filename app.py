import streamlit as st
import openai
import base64
import pandas as pd
from datetime import datetime
from PIL import Image
import json

# 구글 라이브러리 (필수)
try:
    from google.oauth2 import service_account
    import vertexai
    from vertexai.preview.vision_models import ImageGenerationModel, Image as VertexImage
except ImportError:
    pass

st.set_page_config(page_title="Medi-Check Pro", page_icon="🏥", layout="wide")

# --------------------------------------------------------
# 0. 구글 연결 설정 (Vertex AI = 나노바나나 엔진)
# --------------------------------------------------------
google_ready = False
imagen_model = None

if "gcp" in st.secrets:
    try:
        service_account_info = dict(st.secrets["gcp"])
        if "private_key" in service_account_info:
            service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
        # 필수 필드 자동 보정
        if "token_uri" not in service_account_info:
            service_account_info["token_uri"] = "https://oauth2.googleapis.com/token"
        if "type" not in service_account_info:
            service_account_info["type"] = "service_account"

        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        project_id = service_account_info["project_id"]
        
        # 구글 서버 접속
        vertexai.init(project=project_id, location="us-central1", credentials=credentials)
        
        # 모델 로드: 최신 버전 우선 시도
        try:
            # Imagen 3 (최신)
            imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        except:
            # Imagen 2 (안정형)
            imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            
        google_ready = True
    except Exception as e:
        print(f"구글 연결 에러: {e}")

# --------------------------------------------------------
# 1. 기록 저장 기능
# --------------------------------------------------------
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "완료",
        "상세결과": result
    })

api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# --------------------------------------------------------
# 2. 메인 화면
# --------------------------------------------------------
with st.sidebar:
    st.title("🏥 Medi-Check Pro")
    st.caption("Google Vertex AI Direct")
    st.divider()
    menu = st.radio("메뉴", ["✨ 검수 및 보정", "📊 대시보드"])
    st.divider()
    if google_ready:
        st.success("✅ 구글 엔진 가동 중")
    else:
        st.error("⚠️ 구글 키 설정 필요")

if menu == "✨ 검수 및 보정":
    st.header("✨ 의료기기 광고 심의 & 보정")
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 보정 (구글 직통)"])

    # --- 1. 텍스트 ---
    with tab1:
        ad_text = st.text_area("문구 입력", height=150)
        if st.button("텍스트 검수"):
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role":"system", "content":"의료기기 심의관. 대체 문구 3개 제안."}, {"role":"user", "content":ad_text}]
            )
            res = resp.choices[0].message.content
            st.markdown(res)
            save_log("텍스트", ad_text[:20], res)

    # --- 2. 이미지 (구글 Vertex AI 직통) ---
    with tab2:
        st.info("💡 **AI 개입 최소화**: 복잡한 프롬프트 없이 구글 엔진에 사진을 직접 보냅니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                st.image(uploaded_file, caption="원본", use_container_width=True)
            
            # 사용자 선택 옵션 (AI가 멋대로 판단하지 않게 함)
            correction_type = st.radio(
                "보정 방식을 선택하세요:",
                ["🩸 피부/잡티 제거 (Blood/Blemish Removal)", 
                 "🏙️ 배경 변경 (Change Background)", 
                 "🎨 전체 화질 개선 (Upscaling/Cleanup)"],
                horizontal=True
            )
            
            if st.button("구글 엔진으로 보정 시작", type="primary"):
                if not google_ready:
                    st.error("구글 키 설정이 안 되어 있습니다.")
                else:
                    with col2:
                        with st.spinner("구글 Vertex AI가 작업 중..."):
                            try:
                                # 1. 파일 준비
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # 2. 명령 프롬프트 설정 (GPT 거치지 않고 직접 명령)
                                if "피부" in correction_type:
                                    # 피, 상처라는 단어 대신 '부드러운 피부' 강조
                                    prompt = "Smooth and clean skin texture, professional portrait photography, soft lighting. Keep the face features exactly the same."
                                elif "배경" in correction_type:
                                    prompt = "Change background to clean bright blue hospital office blurred. Keep the person exactly the same."
                                else:
                                    prompt = "High quality, sharp focus, professional lighting, clean image."

                                # 3. 구글 엔진 호출 (edit_image)
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=prompt,
                                    number_of_images=1,
                                    guidance_scale=30, # 원본 유지 강도 조절
                                )
                                
                                st.image(gen_imgs[0]._image_bytes, caption="구글 보정 결과", use_container_width=True)
                                st.success("보정 완료")
                                save_log("이미지", uploaded_file.name, f"보정 완료: {correction_type}")

                            except Exception as e:
                                st.error("⚠️ 구글 안전 정책 위반 또는 처리 실패")
                                st.warning("이미지에 붉은 영역(피)이 너무 많으면 구글이 작업을 거부할 수 있습니다.")
                                st.caption(f"Error: {e}")

elif menu == "📊 대시보드":
    st.header("📊 이력 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("기록 없음")
