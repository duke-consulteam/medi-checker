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
        
        # 모델 로드 (최신 버전 시도)
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
        "판정결과": "완료",
        "상세결과": result
    })

api_key = st.secrets.get("OPENAI_API_KEY")
client = openai.OpenAI(api_key=api_key)

# --------------------------------------------------------
# 2. 사이드바
# --------------------------------------------------------
with st.sidebar:
    st.title("🏥 Medi-Check Pro")
    st.caption("Google Vertex AI")
    st.divider()
    menu = st.radio("메뉴 선택", ["✨ 검수 및 보정", "📊 기록 대시보드"])
    st.divider()
    if google_ready:
        st.success("✅ 구글 엔진 연결됨")
    else:
        st.error("⚠️ 구글 키 설정 필요")

# --------------------------------------------------------
# [메뉴 A] 검수 및 보정 (자동화)
# --------------------------------------------------------
if menu == "✨ 검수 및 보정":
    st.header("✨ 의료기기 광고 심의 & 자동 보정")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 보정 (자동)"])

    # 1. 텍스트
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

    # 2. 이미지
    def encode_image(image_file):
        image_file.seek(0) 
        return base64.b64encode(image_file.read()).decode('utf-8')

    with tab2:
        st.info("💡 이미지를 올리면 AI가 알아서 문제점(피, 혐오감)을 찾고 깨끗하게 보정합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
            
            # 버튼 하나로 통합 (선택지 삭제)
            if st.button("AI 자동 분석 및 보정", type="primary"):
                if not google_ready:
                    st.error("구글 키 설정이 안 되어 있습니다.")
                else:
                    with st.spinner("1. 이미지를 분석하고 안전한 묘사를 작성 중..."):
                        b64_img = encode_image(uploaded_file)
                        
                        # ★ 핵심 전략: 원본의 '깨끗한 버전'을 묘사하게 시킴 ★
                        prompt = """
                        이 이미지를 분석해서 구글 Imagen 3에게 줄 '이미지 생성 프롬프트'를 작성하세요.
                        
                        [목표]
                        원본의 인물(성별, 머리스타일, 옷, 포즈, 장신구)은 100% 똑같이 묘사하되,
                        **피(Blood), 상처(Wound), 공포(Horror) 요소만 제거하고 깨끗한 상태로 묘사**하세요.
                        
                        [규칙]
                        1. **절대 금지 단어**: Blood, Wound, Red liquid, Horror, Vampire, Scar, Injury.
                        2. **대체 표현**:
                           - 피 묻은 입 -> "Clean natural lips with red lipstick"
                           - 피 묻은 피부 -> "Pale and smooth skin"
                           - 공포 배경 -> "Dark moody studio background"
                        3. **의료/병원 금지**: Doctor, Nurse, Hospital, Mask, Surgery 단어 쓰지 마세요. (이미지 왜곡됨)
                        
                        형식:
                        PROMPT: (상세한 영어 묘사)
                        """
                        
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                        )
                        res_text = resp.choices[0].message.content
                        
                        # 프롬프트 추출
                        final_prompt = "Portrait of a woman with black hair, clean skin."
                        try:
                            if "PROMPT:" in res_text:
                                final_prompt = res_text.split("PROMPT:")[1].strip()
                        except:
                            pass
                        
                        # 2차 안전 세탁 (파이썬 강제 치환)
                        final_prompt = final_prompt.replace("blood", "").replace("wound", "").replace("horror", "")
                        final_prompt += ", photorealistic, 8k, highly detailed, exact facial features"

                        with col1:
                            st.caption("✅ 분석 완료")
                            with st.expander("AI가 작성한 보정 설계도 보기"):
                                st.write(final_prompt)
                            save_log("이미지", uploaded_file.name, final_prompt)

                    with col2:
                        with st.spinner("2. 구글 엔진이 깨끗하게 복원 중..."):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # edit_image를 쓰되, 프롬프트를 '전체 묘사'로 줌
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=final_instruction if 'final_instruction' in locals() else final_prompt,
                                    number_of_images=1,
                                    guidance_scale=20, # 원본 의존도 조절 (너무 높으면 왜곡됨)
                                )
                                
                                st.image(gen_imgs[0]._image_bytes, caption="AI 자동 보정본", use_container_width=True)
                                st.success("피/공포 요소를 제거하고 깨끗하게 복원했습니다.")

                            except Exception as e:
                                st.error("⚠️ 보정 실패 (구글 안전 정책)")
                                st.caption(f"사유: {e}")
                                st.info("팁: 원본의 붉은색 영역이 너무 넓으면 AI가 거부할 수 있습니다.")

# --------------------------------------------------------
# [메뉴 B] 대시보드
# --------------------------------------------------------
elif menu == "📊 기록 대시보드":
    st.header("📊 이력 관리")
    df = pd.DataFrame(st.session_state['history'])
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("기록 없음")
