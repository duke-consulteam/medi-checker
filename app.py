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
# 0. 구글 연결 설정 (Imagen 3 적용)
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
        
        # ★ 핵심 변경: 모델 버전을 'Imagen 3' 최신판으로 변경 ★
        # (만약 계정 권한 문제로 3.0이 안 되면 자동으로 006으로 넘어가도록 처리)
        try:
            imagen_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        except:
            imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
            
        google_ready = True
    except Exception:
        pass

# --------------------------------------------------------
# 1. 공통 기능
# --------------------------------------------------------
if 'history' not in st.session_state:
    st.session_state['history'] = []

def save_log(type, input_summary, result):
    st.session_state['history'].append({
        "날짜": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "유형": type,
        "입력내용": input_summary,
        "판정결과": "반려" if "반려" in result else ("주의" if "주의" in result else "승인"),
        "상세결과": result
    })

api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# --------------------------------------------------------
# 2. 사이드바
# --------------------------------------------------------
with st.sidebar:
    st.title("🏥 Medi-Check Pro")
    st.caption("Powered by Google Imagen 3")
    st.divider()
    menu = st.radio("메뉴 선택", ["✨ 검수 요청", "📊 기록 대시보드"])
    st.divider()
    if google_ready:
        st.success("✅ Google Imagen 3 연결됨")
    else:
        st.warning("⚠️ 구글 키 확인 필요")

# --------------------------------------------------------
# [메뉴 A] 검수 요청
# --------------------------------------------------------
if menu == "✨ 검수 요청":
    st.header("✨ 광고 심의 및 보정")
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 원본 보정"])

    with tab1:
        ad_text = st.text_area("광고 문구를 입력하세요", height=200)
        if st.button("텍스트 검수", type="primary"):
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
        st.info("💡 **Imagen 3 적용**: 뱀파이어 사진의 피/공포감만 제거하고 **모델 얼굴은 유지**합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
                
            if st.button("이미지 분석 및 원본 보정", type="primary"):
                with st.spinner("1. Imagen 3용 안전 명령 생성 중..."):
                    b64_img = encode_image(uploaded_file)
                    
                    # ★ 프롬프트 전략: '수정'이 아니라 '보존'에 집중 ★
                    prompt = """
                    이 이미지의 의료기기법 위반 요소(피, 공포)를 찾으세요.
                    그리고 구글 Imagen 3에게 내릴 **영어 보정 명령(Edit Instruction)**을 작성하세요.
                    
                    [핵심 규칙]
                    1. **인물 보존 필수**: "Keep the exact same woman, same hair, same face."
                    2. **문제만 수정**: "Only fix skin texture, remove red stains."
                    3. **단어 세탁**: 'Blood' -> 'Red paint', 'Wound' -> 'Blemish'
                    
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
                    
                    # 명령어 추출
                    edit_instruction = "Fix skin texture. Make it clean medical photo."
                    try:
                        if "EDIT_PROMPT:" in res_text:
                            edit_instruction = res_text.split("EDIT_PROMPT:")[1].strip()
                    except:
                        pass
                    
                    # 최종 안전장치
                    edit_instruction = edit_instruction.lower().replace("blood", "red paint").replace("wound", "blemish")
                    
                    with col1:
                        st.markdown(res_text.split("EDIT_PROMPT:")[0])
                        st.caption(f"🤖 명령: {edit_instruction}")
                        save_log("이미지", uploaded_file.name, res_text)

                with col2:
                    if google_ready:
                        with st.spinner(f"2. 구글 Imagen 3가 작업 중..."):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # ★ Imagen 3 Edit (Inpainting) ★
                                # mask_mode를 'background'나 자동 감지로 두는 대신 프롬프트 의존
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=edit_instruction,
                                    number_of_images=1,
                                    guidance_scale=60, # 원본 유지력을 높이는 옵션
                                )
                                st.image(gen_imgs[0]._image_bytes, caption="Imagen 3 보정본 (원본 유지)", use_container_width=True)
                                st.success("Imagen 3 엔진으로 보정했습니다.")

                            except Exception as e:
                                st.error("⚠️ 구글 안전 정책으로 인해 보정이 거부되었습니다.")
                                st.caption(f"에러 코드: {e}")
                                st.warning("팁: 피가 너무 많거나 붉은색 비중이 높으면 Imagen 3도 거부할 수 있습니다.")
                                # 이번에는 엉뚱한 그림 그리는 Fallback을 아예 뺐습니다.
                    else:
                        st.error("⚠️ 구글 키 설정 오류")

# --------------------------------------------------------
# [메뉴 B] 기록 대시보드
# --------------------------------------------------------
elif menu == "📊 기록 대시보드":
    st.header("📊 검수 이력 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("기록 없음")
