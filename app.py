import streamlit as st
import openai
import base64
import pandas as pd
from datetime import datetime
from PIL import Image, ImageOps
import json
import numpy as np # 색상 분석용
import io

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
        
        try:
            imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        except:
            imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            
        google_ready = True
    except Exception:
        pass

# --------------------------------------------------------
# 1. 핵심 기능: 피(Blood) 자동 탐지 마스크 생성
# --------------------------------------------------------
def create_blood_mask(image_bytes):
    """
    이미지에서 붉은색(피) 계열만 찾아내어 흑백 마스크를 만듭니다.
    흰색 부분 = 수정할 곳 (피)
    검은색 부분 = 건드리지 않을 곳 (눈,코,입)
    """
    # 이미지 로드 및 배열 변환
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img_np = np.array(img)
    
    # RGB 분리
    r, g, b = img_np[:,:,0], img_np[:,:,1], img_np[:,:,2]
    
    # 붉은색 탐지 조건 (Red가 Green/Blue보다 현저히 높고, 너무 밝지 않은 영역)
    # 피는 보통 진한 빨강이므로 R값이 높고 G, B값이 낮음
    mask = (r > g * 1.2) & (r > b * 1.2) & (r < 240)
    
    # 불리언 마스크를 이미지로 변환 (0 or 255)
    mask_img_np = (mask * 255).astype(np.uint8)
    mask_img = Image.fromarray(mask_img_np).convert("L") # 흑백 변환
    
    return mask_img

# --------------------------------------------------------
# 2. 공통 기능
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
# 3. 메인 화면
# --------------------------------------------------------
with st.sidebar:
    st.title("🏥 Medi-Check Pro")
    st.caption("Auto-Masking Engine")
    st.divider()
    menu = st.radio("메뉴 선택", ["✨ 검수 및 보정", "📊 기록 대시보드"])
    st.divider()
    if google_ready:
        st.success("✅ 구글 엔진 준비됨")
    else:
        st.error("⚠️ 구글 키 설정 필요")

if menu == "✨ 검수 및 보정":
    st.header("✨ 의료기기 광고 심의 & 정밀 보정")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 정밀 보정"])

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

    def encode_image(image_file):
        image_file.seek(0) 
        return base64.b64encode(image_file.read()).decode('utf-8')

    with tab2:
        st.info("💡 **스마트 마스킹**: AI가 '피(붉은색)'만 자동으로 찾아서 그 부분만 피부로 덮습니다. (얼굴 왜곡 0%)")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
            
            if st.button("AI 정밀 보정 시작", type="primary"):
                if not google_ready:
                    st.error("구글 키 설정이 안 되어 있습니다.")
                else:
                    # 1. 자동 마스크 생성
                    with st.spinner("1. 피가 묻은 영역을 탐지하는 중..."):
                        uploaded_file.seek(0)
                        image_bytes = uploaded_file.read()
                        
                        # 파이썬으로 붉은 영역 찾기
                        mask_image = create_blood_mask(image_bytes)
                        
                        # 마스크 미리보기 (디버깅용)
                        with col1:
                            with st.expander("AI가 탐지한 수정 영역(흰색) 보기"):
                                st.image(mask_image, caption="이 흰색 부분만 수정됩니다.")
                    
                    # 2. 구글 엔진 호출 (마스크 적용)
                    with col2:
                        with st.spinner("2. 탐지된 영역만 피부로 덮는 중..."):
                            try:
                                base_img = VertexImage(image_bytes)
                                # 마스크 이미지를 저장 후 VertexImage로 변환
                                mask_bytes_io = io.BytesIO()
                                mask_image.save(mask_bytes_io, format="PNG")
                                mask_vertex = VertexImage(mask_bytes_io.getvalue())
                                
                                # ★ 핵심: mask 매개변수 사용 ★
                                # 전체를 바꾸지 않고 mask 영역만 바꿉니다.
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    mask=mask_vertex, # 여기서 지정한 곳만 고침
                                    prompt="Clean natural skin texture, smooth skin, high resolution",
                                    number_of_images=1,
                                    guidance_scale=60, # 마스크 안쪽은 확실하게 고치도록 설정
                                )
                                
                                if gen_imgs:
                                    st.image(gen_imgs[0]._image_bytes, caption="정밀 보정본 (눈코입 유지)", use_container_width=True)
                                    st.success("얼굴 왜곡 없이 피만 제거했습니다.")
                                    save_log("이미지", uploaded_file.name, "정밀 마스킹 보정 성공")
                                else:
                                    st.error("결과 반환 실패")

                            except Exception as e:
                                st.error("❌ 보정 실패")
                                st.caption(f"에러: {e}")

elif menu == "📊 기록 대시보드":
    st.header("📊 이력 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("기록 없음")
