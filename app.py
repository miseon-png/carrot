import streamlit as st
import pandas as pd
import datetime
import math
import gspread
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------
# 0. 페이지 기본 설정 & 구글 시트 연동 설정
# ---------------------------------------------------------
st.set_page_config(page_title="당근라페 원부재료 수불부", layout="wide")
st.title("🥕 당근라페 원재료 & 부재료 수불")

# 인쇄/PDF 출력용 커스텀 CSS (인쇄 시 불필요한 UI 숨김)
st.markdown("""
    <style>
    @media print {
        header, footer, [data-testid="stSidebar"], .stButton, div[data-testid="stToolbar"] {
            display: none !important;
        }
        .main .block-container {
            padding: 0 !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

SPREADSHEET_ID = "1vfDcssJtoq79GGirW4aBcpXN-0_NjhVOkJbG-I609PY"

@st.cache_resource
def get_gspread_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"구글 서비스 계정 인증 실패: Secrets를 확인하세요. ({e})")
        return None

@st.cache_data(ttl=60)
def load_data(worksheet_name):
    client = get_gspread_client()
    if client:
        try:
            doc = client.open_by_key(SPREADSHEET_ID)
            sheet = doc.worksheet(worksheet_name)
            data = sheet.get_all_values()
            if len(data) > 1:
                headers = data[0]
                headers = [str(h).strip() if h != "" else f"Unnamed_{i}" for i, h in enumerate(headers)]
                df = pd.DataFrame(data[1:], columns=headers)
                
                # 데이터 안의 콤마 제거 및 공백 제거
                for col in df.columns:
                    df[col] = df[col].astype(str).str.strip().str.replace(',', '')
                
                numeric_cols = [
                    "입고수량", "DB환산수량", "공급가액(VAT별도)", "VAT(10%)", 
                    "총합계금액", "개당단가", "총금액", "단가", "출고수량", "조정수량", "생산수량",
                    "기월이월", "기초재고", "안전재고"
                ]
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                        
                if "일자" in df.columns:
                    df["일자_dt"] = pd.to_datetime(df["일자"], errors="coerce").dt.date
                return df
            else:
                return pd.DataFrame()
        except Exception as e:
            st.warning(f"'{worksheet_name}' 시트를 불러오지 못했습니다: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def append_data(worksheet_name, row_data):
    client = get_gspread_client()
    if client:
        try:
            doc = client.open_by_key(SPREADSHEET_ID)
            sheet = doc.worksheet(worksheet_name)
            sheet.append_row(row_data)
            st.cache_data.clear()
            return True
        except Exception as e:
            st.error(f"저장 실패: {e}")
            return False
    return False

# CSV 인코딩 (한글 깨짐 방지 utf-8-sig)
def to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

# 입고 데이터에서 DB환산수량을 안전하게 추출하는 보조 함수
def get_converted_in_qty(df_in_filtered):
    if df_in_filtered.empty:
        return 0.0
    
    total_qty = 0.0
    for _, row in df_in_filtered.iterrows():
        db_qty = float(row.get("DB환산수량", 0))
        if db_qty > 0:
            total_qty += db_qty
        else:
            in_qty = float(row.get("입고수량", 0))
            u_type = str(row.get("입고단위", "")).strip()
            if u_type in ["kg", "L"]:
                total_qty += in_qty * 1000
            else:
                total_qty += in_qty
    return total_qty

# ---------------------------------------------------------
# 1. 원부재료 및 거래처/단위 표준 매핑 정의
# ---------------------------------------------------------
RAW_MATERIALS = [
    "소금 (백설 꽃소금)",
    "시타 프리올리바 올리브 오일",
    "홀그레인 머스타드(르네디종)",
    "홀그레인 머스타드(오뚜기)",
    "라임 주스(레이지)",
    "설탕(백설)",
    "후추(오뚜기)"
]

SUB_MATERIALS = [
    "당근200트레이",
    "당근200탑실링지",
    "당근200표시사항 스티커",
    "파우치(200*250)",
    "파우치 (300*400)",
    "파우치 (400*600)",
    "파우치(200*160)",
    "당근 400 스티커",
    "카톤박스(특소)",
    "카톤박스(소)",
    "카톤박스(중)",
    "카톤박스(대)"
]

ITEM_UNITS = {
    "소금 (백설 꽃소금)": "g",
    "시타 프리올리바 올리브 오일": "ml",
    "홀그레인 머스타드(르네디종)": "g",
    "홀그레인 머스타드(오뚜기)": "g",
    "라임 주스(레이지)": "ml",
    "설탕(백설)": "g",
    "후추(오뚜기)": "g",
    "당근200트레이": "개",
    "당근200탑실링지": "개",
    "당근200표시사항 스티커": "장",
    "당근 400 스티커": "개",
    "파우치(200*250)": "개",
    "파우치 (300*400)": "개",
    "파우치 (400*600)": "개",
    "파우치(200*160)": "개",
    "카톤박스(특소)": "개",
    "카톤박스(소)": "개",
    "카톤박스(중)": "개",
    "카톤박스(대)": "개"
}

VENDORS = ["케이앤에스", "은성특수산업", "제이원글로벌", "삼보판지", "기타 / 직접입력"]

# ---------------------------------------------------------
# 2. 탭 구성
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📦 입고 등록", 
    "🥣 당근라페 생산 (자동)", 
    "📤 수기 출고", 
    "🛠️ 재고 조정", 
    "📊 원부재료 수불부 현황",
    "🏪 거래처별 입고 현황"
])

# ---------------------------------------------------------
# TAB 1: 입고 등록
# ---------------------------------------------------------
with tab1:
    st.subheader("원부재료 입고 등록")
    
    in_date = st.date_input("입고 일자", datetime.date.today(), key="in_date")
    
    col1, col2 = st.columns(2)
    with col1:
        vendor_name = st.selectbox("거래처(공급업체) 선택", VENDORS, key="in_vendor")
        if vendor_name == "기타 / 직접입력":
            vendor_name = st.text_input("거래처명 직접 입력", placeholder="예: OO유통")
            
        category = st.selectbox("구분", ["원재료", "부재료"])
        if category == "원재료":
            item_name = st.selectbox("입고 재료 선택", RAW_MATERIALS, key="in_raw")
        else:
            item_name = st.selectbox("입고 재료 선택", SUB_MATERIALS, key="in_sub")
            
    with col2:
        unit_type = st.selectbox("입고 단위", ["kg", "g", "L", "ml", "개", "장"])
        input_qty = st.number_input("입고 수량", min_value=0, step=1, format="%d")
        supply_amount = st.number_input("총 금액 (VAT 별도 / 원)", min_value=0, step=100, format="%d")
    
    base_qty = int(input_qty)
    base_unit = unit_type
    if unit_type in ["kg", "L"]:
        base_qty = int(input_qty * 1000)
        base_unit = "g" if unit_type == "kg" else "ml"
        st.info(f"💡 시스템 내부 데이터베이스에는 **{base_qty:,d} {base_unit}** 로 환산되어 저장됩니다.")
    
    vat_amount = int(supply_amount * 0.1)
    total_with_vat = supply_amount + vat_amount
    unit_price = int(supply_amount / input_qty) if input_qty > 0 else 0
    
    if st.button("입고 저장"):
        if input_qty <= 0:
