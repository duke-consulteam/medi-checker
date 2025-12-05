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
        
        # 모델 로드
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
    st.caption("Google Vertex AI Auto-Switch")
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
    
    tab1, tab2 = st.tabs(["📄 텍스트 심의", "🖼️ 이미지 보정 (안전모드)"])

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
        st.info("💡 **스마트 안전 모드**: 원본 수정을 시도하되, 구글이 거부하면 '안전한 버전으로 새로 그리기'를 수행합니다.")
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
                    # -------------------------------------------------------
                    # 1단계: GPT-4o가 이미지 분석 및 프롬프트 작성
                    # -------------------------------------------------------
                    with st.spinner("1. 이미지를 분석하고 안전한 묘사를 작성 중..."):
                        b64_img = encode_image(uploaded_file)
                        
                        prompt = """
                        이 이미지를 분석하여 2가지를 작성하세요.
                        
                        1. **VISUAL_DESC**: 인물의 외모(성별, 머리색, 스타일, 인종, 옷, 포즈)를 아주 상세하게 묘사하세요. (단, 피/상처는 묘사하지 말고 깨끗한 피부로 묘사할 것)
                        2. **EDIT_CMD**: 원본을 수정하기 위한 명령어. (예: "Make skin clean and smooth", "Change background to studio")
                        
                        [금지 단어]
                        Blood, Wound, Horror, Red liquid, Vampire, Scar
                        
                        형식:
                        VISUAL_DESC: (상세 묘사)
                        EDIT_CMD: (수정 명령)
                        """
                        
                        resp = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[{"role":"user", "content":[{"type":"text","text":prompt}, {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64_img}"}}]}]
                        )
                        res_text = resp.choices[0].message.content
                        
                        # 파싱
                        visual_desc = "Portrait of a professional woman, clean skin."
                        edit_cmd = "Make skin clean."
                        
                        try:
                            if "VISUAL_DESC:" in res_text:
                                parts = res_text.split("VISUAL_DESC:")[1].split("EDIT_CMD:")
                                visual_desc = parts[0].strip()
                                if len(parts) > 1:
                                    edit_cmd = parts[1].strip()
                        except:
                            pass
                        
                        # 안전 세탁
                        clean_visual_desc = visual_desc.replace("blood", "").replace("wound", "").replace("horror", "")
                        clean_edit_cmd = edit_cmd.replace("blood", "").replace("wound", "")

                        with col1:
                            st.caption("✅ 분석 완료")
                            with st.expander("AI의 분석 내용 보기"):
                                st.write(f"**외모 묘사:** {clean_visual_desc}")
                                st.write(f"**수정 명령:** {clean_edit_cmd}")
                            save_log("이미지", uploaded_file.name, res_text)

                    # -------------------------------------------------------
                    # 2단계: 구글 엔진 호출 (수정 시도 -> 실패시 생성)
                    # -------------------------------------------------------
                    with col2:
                        with st.spinner("2. 구글 엔진 작업 중..."):
                            success = False
                            
                            # 시도 1: 원본 수정 (Edit Image)
                            try:
                                uploaded_file.seek(0)
                                image_bytes = uploaded_file.read()
                                base_img = VertexImage(image_bytes)
                                
                                gen_imgs = imagen_model.edit_image(
                                    base_image=base_img,
                                    prompt=clean_edit_cmd,
                                    number_of_images=1,
                                    guidance_scale=20, # 너무 높으면 거부됨
                                )
                                
                                # ★ 에러 방지 핵심: 결과가 비어있는지 체크 ★
                                if gen_imgs and len(gen_imgs) > 0:
                                    st.image(gen_imgs[0]._image_bytes, caption="AI 부분 수정본 (Edit)", use_container_width=True)
                                    st.success("원본을 유지하며 부분 수정에 성공했습니다!")
                                    success = True
                                else:
                                    raise Exception("구글이 빈 결과값을 반환했습니다 (안전 정책 차단).")

                            except Exception as e:
                                st.warning("⚠️ 원본 사진의 붉은 영역(피) 때문에 '부분 수정'이 거부되었습니다.")
                                st.caption(f"사유: {str(e)}")
                                st.info("🔄 '안전한 버전으로 새로 그리기'를 자동으로 시도합니다...")

                            # 시도 2: 실패 시 새로 그리기 (Generate Image)
                            if not success:
                                try:
                                    # GPT가 써준 '깨끗한 묘사(visual_desc)'를 바탕으로 새로 그림
                                    final_prompt = f"High quality professional portrait. {clean_visual_desc}. Photorealistic, 8k, soft lighting, clean atmosphere."
                                    
                                    gen_imgs = imagen_model.generate_images(
                                        prompt=final_prompt,
                                        number_of_images=1
                                    )
                                    
                                    if gen_imgs and len(gen_imgs) > 0:
                                        st.image(gen_imgs[0]._image_bytes, caption="AI 새로 그리기 (Generate)", use_container_width=True)
                                        st.success("원본의 특징을 살려 안전한 이미지로 새로 그렸습니다.")
                                    else:
                                        st.error("❌ 이미지 생성조차 거부되었습니다. (프롬프트에 금지어가 포함됨)")
                                        
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
