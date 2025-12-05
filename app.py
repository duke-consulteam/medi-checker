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
    st.caption("Google Vertex AI Direct")
    st.divider()
    menu = st.radio("메뉴 선택", ["✨ 검수 및 보정", "📊 기록 대시보드"])
    st.divider()
    if google_ready:
        st.success("✅ 구글 엔진 연결됨")
    else:
        st.error("⚠️ 구글 키 설정 필요")

# --------------------------------------------------------
# [메뉴 A] 검수 및 보정
# --------------------------------------------------------
if menu == "✨ 검수 및 보정":
    st.header("✨ 의료기기 광고 심의 & 자동 보정")
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 보정"])

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
        st.info("💡 **자동 보정**: 이미지를 올리면 AI가 알아서 피/혐오 요소를 제거합니다.")
        uploaded_file = st.file_uploader("이미지 업로드", type=["jpg", "png"])

        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                uploaded_file.seek(0)
                st.image(uploaded_file, caption="원본", use_container_width=True)
            
            if st.button("AI 자동 분석 및 보정", type="primary"):
                if not google_ready:
                    st.error("구글 키 설정이 안 되어 있습니다.")
                else:
                    # 1. GPT 분석
                    with st.spinner("1. 이미지 분석 중..."):
                        b64_img = encode_image(uploaded_file)
                        prompt = """
                        이 이미지에서 피(Blood), 상처(Wound), 공포(Horror) 요소를 찾아서,
                        구글 Imagen에게 내릴 '수정 명령어(EDIT_CMD)'를 작성하세요.
                        
                        [규칙]
                        - 금지어: Blood, Wound, Horror, Red liquid (사용 X)
                        - 대체어: Clean skin, Smooth texture, Blue background (사용 O)
                        
                        형식:
                        VISUAL_DESC: (인물 상세 묘사)
                        EDIT_CMD: (수정 명령어)
                        """
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                        )
                        res_text = resp.choices[0].message.content
                        
                        visual_desc = "Professional portrait"
                        edit_cmd = "Make skin clean"
                        try:
                            if "EDIT_CMD:" in res_text:
                                parts = res_text.split("EDIT_CMD:")
                                edit_cmd = parts[1].strip()
                                visual_desc = parts[0].replace("VISUAL_DESC:", "").strip()
                        except:
                            pass
                        
                        # 안전 세탁
                        edit_cmd = edit_cmd.lower().replace("blood", "red paint").replace("wound", "blemish")

                        with col1:
                            st.caption("✅ 분석 완료")
                            with st.expander("분석 내용 보기"):
                                st.write(f"명령: {edit_cmd}")
                            save_log("이미지", uploaded_file.name, res_text)

                    # 2. 구글 엔진 호출
                    with col2:
                        with st.spinner("2. 구글 엔진이 보정 중..."):
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                # 시도 1: 수정 (Edit)
                                response = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=edit_cmd,
                                    number_of_images=1,
                                    guidance_scale=20,
                                )
                                
                                # ★★★ 에러 수정 완료 ★★★
                                # len(response)가 아니라 response.images를 확인해야 합니다.
                                if response.images:
                                    st.image(response.images[0]._image_bytes, caption="AI 보정본 (Edit)", use_container_width=True)
                                    st.success("보정 성공!")
                                else:
                                    raise Exception("이미지가 반환되지 않았습니다.")

                            except Exception as e:
                                # 시도 2: 새로 그리기 (Generate)
                                st.warning("⚠️ 부분 수정 대신 새로 그리기를 시도합니다.")
                                try:
                                    final_prompt = f"Professional photo. {visual_desc}. {edit_cmd}. High quality."
                                    response = imagen_model.generate_images(
                                        prompt=final_prompt,
                                        number_of_images=1
                                    )
                                    # 여기도 수정 완료
                                    if response.images:
                                        st.image(response.images[0]._image_bytes, caption="AI 생성본 (Generate)", use_container_width=True)
                                        st.success("대체 이미지 생성 성공!")
                                except Exception as e2:
                                    st.error("❌ 최종 실패")
                                    st.caption(f"에러: {str(e2)}")

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
