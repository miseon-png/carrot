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
st.title("🥕 당근라페 원부재료 수불 및 생산 관리 시스템")

SPREADSHEET_ID = "1vfDcssJtoq79GGirW4aBcpXN-0_NjhVOkJbG-I609PY"

@st.cache_resource
def get_gspread_client():
    try:
        # Secrets 딕셔너리를 가져와 private_key의 \\n을 실제 줄바꿈 문자로 변환 (PEM 에러 방지)
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

def load_data(worksheet_name):
    client = get_gspread_client()
    if client:
        try:
            doc = client.open_by_key(SPREADSHEET_ID)
            sheet = doc.worksheet(worksheet_name)
            data = sheet.get_all_records()
            return pd.DataFrame(data), sheet
        except Exception as e:
            st.warning(f"'{worksheet_name}' 시트를 불러오지 못했습니다: {e}")
            return pd.DataFrame(), None
    return pd.DataFrame(), None

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
    "카톤박스(특소)",
    "파우치(200*250)",
    "당근 400 스티커",
    "카톤박스(소)",
    "파우치(200*160)"
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
    "카톤박스(특소)": "개",
    "파우치(200*250)": "개",
    "당근 400 스티커": "개",
    "카톤박스(소)": "개",
    "파우치(200*160)": "개"
}

VENDORS = ["케이앤에스", "은성특수산업", "제이원글로벌", "기타 / 직접입력"]

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
# TAB 1: 입고 등록 (구글 시트 저장 연동)
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
        input_qty = st.number_input("입고 수량", min_value=0.000, step=0.001, format="%.3f")
        unit_price = st.number_input("단가 (원 / 입력단위당)", min_value=0, step=100)
    
    base_qty = input_qty
    base_unit = unit_type
    if unit_type in ["kg", "L"]:
        base_qty = round(input_qty * 1000, 2)
        base_unit = "g" if unit_type == "kg" else "ml"
        st.info(f"💡 시스템 내부 데이터베이스에는 **{base_qty:,.2f} {base_unit}** 로 환산되어 저장됩니다.")
    
    total_amount = int(input_qty * unit_price)
    st.write(f"💰 총 구매 금액: **{total_amount:,.0f} 원**")
    
    if st.button("입고 저장"):
        if input_qty <= 0:
            st.warning("입고 수량을 입력해주세요.")
        elif not vendor_name:
            st.warning("거래처명을 입력해주세요.")
        else:
            _, sheet = load_data("입고기록")
            if sheet:
                sheet.append_row([
                    str(in_date), vendor_name, category, item_name, 
                    input_qty, unit_type, base_qty, base_unit, unit_price, total_amount
                ])
                st.success(f"✅ **[{in_date}]** 거래처 **[{vendor_name}]** / **{item_name}** {input_qty}{unit_type} 구글 시트 저장 완료!")
                st.cache_resource.clear()
            else:
                st.error("구글 시트 저장에 실패했습니다.")

    st.divider()

    st.markdown("### 🕒 최근 입고 내역 (실제 구글 시트 데이터)")
    df_in, _ = load_data("입고기록")
    if not df_in.empty:
        st.dataframe(
            df_in.tail(8).iloc[::-1].style.format({
                "입고수량": "{:,.2f}",
                "DB환산수량": "{:,.2f}",
                "단가": "{:,d}",
                "총금액": "{:,d}"
            }),
            use_container_width=True
        )
    else:
        st.info("등록된 입고 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 2: 당근라페 완제품 생산 (구글 시트 저장 연동)
# ---------------------------------------------------------
with tab2:
    st.subheader("당근라페 완제품 생산 등록 (BOM 자동 차감)")
    prod_date = st.date_input("생산 일자", datetime.date.today(), key="prod_date")
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        product = st.radio("생산 제품 규격", ["당근라페 200g (6개 단위 입력)", "당근라페 400g (8개 단위 입력)"])
    with col_p2:
        step_val = 6 if "200g" in product else 8
        count = st.number_input("생산 수량 (개)", min_value=step_val, step=step_val)
    
    st.markdown("#### 🔍 자동 차감 예정 원부재료 소요량")
    batches = count // step_val
    
    if "200g" in product:
        preview_data = {
            "원부재료명": [
                "소금 (백설 꽃소금)", "시타 프리올리바 올리브 오일", "홀그레인 머스타드(르네디종)", 
                "홀그레인 머스타드(오뚜기)", "라임 주스(레이지)", "설탕(백설)", "후추(오뚜기)",
                "당근200트레이", "당근200탑실링지", "당근200표시사항 스티커", "카톤박스(특소)"
            ],
            "차감 수량": [
                f"{24 * batches} g", f"{223 * batches} ml", f"{95 * batches} g",
                f"{95 * batches} g", f"{32 * batches} ml", f"{32 * batches} g", f"{1 * batches} g",
                f"{count} 개", f"{count} 개", f"{math.ceil(count / 5)} 장", f"{count // 6} 개"
            ]
        }
        box_str = f"{count // 6} 박스(특소)"
    else:
        preview_data = {
            "원부재료명": [
                "소금 (백설 꽃소금)", "시타 프리올리바 올리브 오일", "홀그레인 머스타드(르네디종)", 
                "홀그레인 머스타드(오뚜기)", "라임 주스(레이지)", "설탕(백설)", "후추(오뚜기)",
                "파우치(200*250)", "당근 400 스티커", "카톤박스(소)"
            ],
            "차감 수량": [
                f"{65 * batches} g", f"{594 * batches} ml", f"{254 * batches} g",
                f"{254 * batches} g", f"{84 * batches} ml", f"{84 * batches} g", f"{2 * batches} g",
                f"{count} 개", f"{count} 개", f"{count // 8} 개"
            ]
        }
        box_str = f"{count // 8} 박스(소)"
    st.table(pd.DataFrame(preview_data))
    
    if st.button("생산 실적 저장 및 레시피 자동 출고"):
        _, sheet = load_data("생산기록")
        if sheet:
            prod_name_clean = "당근라페 200g" if "200g" in product else "당근라페 400g"
            sheet.append_row([str(prod_date), prod_name_clean, count, box_str, "생산완료"])
            st.success(f"🎉 **[{prod_date}]** **{product}** {count}개 생산 등록이 구글 시트에 완료되었습니다!")
            st.cache_resource.clear()
        else:
            st.error("구글 시트 저장 실패")

    st.divider()

    st.markdown("### 🥣 최근 생산 내역 ")
    df_prod, _ = load_data("생산기록")
    if not df_prod.empty:
        st.dataframe(df_prod.tail(8).iloc[::-1], use_container_width=True)
    else:
        st.info("등록된 생산 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 3: 수기 출고 (구글 시트 저장 연동 & 단위 자동 표시)
# ---------------------------------------------------------
with tab3:
    st.subheader("수기 출고 등록 (타 용도 사용)")
    out_date = st.date_input("출고 일자", datetime.date.today(), key="out_date")
    
    col_out1, col_out2 = st.columns(2)
    with col_out1:
        전체 수정 코드를 제공해 드리기 위해 **기존 코드**와 **어떤 부분의 수정(또는 기능 추가/버그 수정)이 필요한지** 말씀해 주셔야 합니다.

원하시는 내용(예: 특정 프로그래밍 언어, 오류 내용, 구현하려는 기능 등)을 자세히 알려주시면 완전하게 작성된 전체 수정 코드를 바로 작성해 드리겠습니다!
