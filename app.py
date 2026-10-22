import streamlit as st
import pandas as pd
import datetime
import math
import gspread
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------
# 0. 페이지 기본 설정 & 구글 시트 연동 설정
# ---------------------------------------------------------
st.set_page_config(page_title="당근라페 원부자재 수불부", layout="wide")
st.title("🥕 당근라페 원재료 / 부재료 / 부자재 수불")

# 인쇄/PDF 출력용 커스텀 CSS
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
                
                # 데이터 안의 콤마 및 공백 제거
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
                        
                date_col = next((c for c in df.columns if "일자" in c or "날짜" in c or "Date" in c), None)
                if date_col:
                    df["일자_dt"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
                return df
            else:
                return pd.DataFrame(columns=data[0] if len(data) > 0 else [])
        except Exception as e:
            if worksheet_name != "기초정보":
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

def to_csv(df):
    return df.to_csv(index=False).encode('utf-8-sig')

def get_item_col(df):
    for col in ["재료명", "입고 재료", "품목명", "원부자재명", "원부재료명", "재료"]:
        if col in df.columns:
            return col
    return None

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
            u_type = str(row.get("입고단위", row.get("단위", ""))).strip()
            item_n = str(row.get("재료명", row.get("입고 재료", ""))).strip()
            
            if u_type in ["kg", "L"]:
                total_qty += in_qty * 1000
            elif u_type in ["개", "통", "장"] and item_n in ITEM_PACKAGE_SIZES:
                total_qty += in_qty * ITEM_PACKAGE_SIZES[item_n]["size"]
            else:
                total_qty += in_qty
    return total_qty

def load_master_data():
    """기초정보(거래처, 부재료, 부자재) 동적 데이터 로드"""
    df = load_data("기초정보")
    added_subs = []  # 부재료 (드레싱 등)
    added_pkgs = []  # 부자재 (포장재 등)
    added_vendors = []
    added_units = {}
    
    if not df.empty and "구분" in df.columns and "이름" in df.columns:
        for _, row in df.iterrows():
            cat = str(row.get("구분", "")).strip()
            name = str(row.get("이름", "")).strip()
            unit = str(row.get("단위", "")).strip() if "단위" in df.columns else ""
            
            if cat == "부재료" and name:
                added_subs.append(name)
                if unit: added_units[name] = unit
            elif cat == "부자재" and name:
                added_pkgs.append(name)
                if unit: added_units[name] = unit
            elif cat == "거래처" and name:
                added_vendors.append(name)
                
    return added_subs, added_pkgs, added_vendors, added_units

# ---------------------------------------------------------
# 1. 품목 및 거래처/단위 표준 매핑 정의 (기본값 + 동적 병합)
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

# ✅ 부재료 (드레싱 등)
BASE_SUB_MATERIALS = [
    "오리엔탈 드레싱 25g"
]

# ✅ 부자재 (포장 용품 등)
BASE_PKG_MATERIALS = [
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

BASE_ITEM_UNITS = {
    "소금 (백설 꽃소금)": "g", "시타 프리올리바 올리브 오일": "ml",
    "홀그레인 머스타드(르네디종)": "g", "홀그레인 머스타드(오뚜기)": "g",
    "라임 주스(레이지)": "ml", "설탕(백설)": "g", "후추(오뚜기)": "g",
    "오리엔탈 드레싱 25g": "개",
    "당근200트레이": "개", "당근200탑실링지": "개", "당근200표시사항 스티커": "장",
    "당근 400 스티커": "개", "파우치(200*250)": "개", "파우치 (300*400)": "개",
    "파우치 (400*600)": "개", "파우치(200*160)": "개",
    "카톤박스(특소)": "개", "카톤박스(소)": "개", "카톤박스(중)": "개", "카톤박스(대)": "개"
}

ITEM_PACKAGE_SIZES = {
    "시타 프리올리바 올리브 오일": {"size": 5000, "unit": "ml"},
    "홀그레인 머스타드(르네디종)": {"size": 5000, "unit": "g"}
}

BASE_VENDORS = ["케이앤에스", "은성특수산업", "제이원글로벌", "삼보판지", "기타 / 직접입력"]

# 📌 동적 데이터 적용 (중복 제거 유지)
added_subs, added_pkgs, added_vendors, added_units = load_master_data()
DYNAMIC_SUB_MATERIALS = list(dict.fromkeys(BASE_SUB_MATERIALS + added_subs))
DYNAMIC_PKG_MATERIALS = list(dict.fromkeys(BASE_PKG_MATERIALS + added_pkgs))
DYNAMIC_VENDORS = list(dict.fromkeys(BASE_VENDORS + added_vendors))
ITEM_UNITS = BASE_ITEM_UNITS.copy()
ITEM_UNITS.update(added_units)

# ---------------------------------------------------------
# 2. 탭 구성 (총 9개로 분리)
# ---------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📦 입고 등록", 
    "🥣 당근라페 생산 (자동)", 
    "📤 수기 출고", 
    "🛠️ 재고 조정", 
    "📊 원재료 수불부", 
    "🍶 부재료 수불부", 
    "📦 부자재 수불부", 
    "🏪 거래처 현황",
    "⚙️ 기초정보 관리"
])

# ---------------------------------------------------------
# TAB 1: 입고 등록
# ---------------------------------------------------------
with tab1:
    st.subheader("원재료 / 부재료 / 부자재 입고 등록")
    
    in_date = st.date_input("입고 일자", datetime.date.today(), key="in_date")
    
    col1, col2 = st.columns(2)
    with col1:
        vendor_name = st.selectbox("거래처(공급업체) 선택", DYNAMIC_VENDORS, key="in_vendor")
        if vendor_name == "기타 / 직접입력":
            vendor_name = st.text_input("거래처명 직접 입력", placeholder="예: OO유통")
            
        category = st.selectbox("구분", ["원재료", "부재료", "부자재"]) 
        if category == "원재료":
            item_name = st.selectbox("입고 품목 선택", RAW_MATERIALS, key="in_raw")
        elif category == "부재료":
            item_name = st.selectbox("입고 품목 선택", DYNAMIC_SUB_MATERIALS, key="in_sub")
        else:
            item_name = st.selectbox("입고 품목 선택", DYNAMIC_PKG_MATERIALS, key="in_pkg")
            
    with col2:
        unit_type = st.selectbox("입고 단위", ["kg", "g", "L", "ml", "개", "장"])
        input_qty = st.number_input("입고 수량", min_value=0, step=1, format="%d")
        supply_amount = st.number_input("총 금액 (VAT 별도 / 원)", min_value=0, step=100, format="%d")
    
    base_qty = int(input_qty)
    base_unit = ITEM_UNITS.get(item_name, unit_type)
    
    if unit_type in ["kg", "L"]:
        base_qty = int(input_qty * 1000)
        base_unit = "g" if unit_type == "kg" else "ml"
        st.info(f"💡 시스템 내부 데이터베이스에는 **{base_qty:,d} {base_unit}** 로 환산되어 저장됩니다.")
    elif unit_type in ["개", "장"] and item_name in ITEM_PACKAGE_SIZES:
        pkg_info = ITEM_PACKAGE_SIZES[item_name]
        base_qty = int(input_qty * pkg_info["size"])
        base_unit = pkg_info["unit"]
        st.info(f"💡 [{item_name}] 1통({pkg_info['size']:,d}{base_unit}) 규격 적용: DB에는 **{base_qty:,d} {base_unit}** 로 저장됩니다.")
    
    vat_amount = int(supply_amount * 0.1)
    total_with_vat = supply_amount + vat_amount
    unit_price = int(supply_amount / input_qty) if input_qty > 0 else 0
    
    if st.button("입고 저장"):
        if input_qty <= 0:
            st.warning("입고 수량을 입력해주세요.")
        elif supply_amount <= 0:
            st.warning("총 금액(VAT 별도)을 입력해주세요.")
        elif not vendor_name:
            st.warning("거래처명을 입력해주세요.")
        else:
            row = [
                str(in_date), vendor_name, category, item_name, 
                int(input_qty), unit_type, int(base_qty), base_unit, 
                int(supply_amount), int(vat_amount), int(total_with_vat), int(unit_price)
            ]
            if append_data("입고기록", row):
                st.success(f"✅ **[{in_date}]** 거래처 **[{vendor_name}]** / **{item_name}** {input_qty:,d}{unit_type} (DB환산: {base_qty:,d}{base_unit}) 저장 완료!")

    st.divider()

    st.markdown("### 🕒 최근 입고 내역")
    df_in = load_data("입고기록")
    if not df_in.empty:
        show_cols = [c for c in df_in.columns if c not in ["DB환산수량", "DB환산단위", "일자_dt"]]
        df_display = df_in[show_cols].tail(8).iloc[::-1]
        
        format_dict = {"입고수량": "{:,d}"}
        for col_name in ["공급가액(VAT별도)", "VAT(10%)", "총합계금액", "개당단가", "총금액", "단가"]:
            if col_name in df_display.columns:
                format_dict[col_name] = "{:,d}"
                
        st.dataframe(
            df_display.style.format(format_dict),
            use_container_width=True
        )
    else:
        st.info("등록된 입고 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 2: 당근라페 완제품 생산
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
    
    st.markdown("#### 🔍 자동 차감 예정 소요량")
    batches = count // step_val
    
    if "200g" in product:
        preview_data = {
            "품목명": [
                "소금 (백설 꽃소금)", "시타 프리올리바 올리브 오일", "홀그레인 머스타드(르네디종)", 
                "홀그레인 머스타드(오뚜기)", "라임 주스(레이지)", "설탕(백설)", "후추(오뚜기)",
                "당근200트레이", "당근200탑실링지", "당근200표시사항 스티커", "카톤박스(특소)"
            ],
            "차감 수량": [
                f"{24.8 * batches} g", f"{228.1 * batches} ml", f"{97.7 * batches} g",
                f"{97.7 * batches} g", f"{32.3 * batches} ml", f"{32.6 * batches} g", f"{0.2 * batches} g",
                f"{count} 개", f"{count} 개", f"{math.ceil(count / 5)} 장", f"{count // 6} 개"
            ]
        }
        box_str = f"{count // 6} 박스(특소)"
    else:
        preview_data = {
            "품목명": [
                "소금 (백설 꽃소금)", "시타 프리올리바 올리브 오일", "홀그레인 머스타드(르네디종)", 
                "홀그레인 머스타드(오뚜기)", "라임 주스(레이지)", "설탕(백설)", "후추(오뚜기)",
                "파우치(200*250)", "당근 400 스티커", "카톤박스(중)"
            ],
            "차감 수량": [
                f"{66.1 * batches} g", f"{608.2 * batches} ml", f"{260.7 * batches} g",
                f"{260.7 * batches} g", f"{86.2 * batches} ml", f"{86.9 * batches} g", f"{0.7 * batches} g",
                f"{count} 개", f"{count} 개", f"{count // 8} 개"
            ]
        }
        box_str = f"{count // 8} 박스(중)"
    st.table(pd.DataFrame(preview_data))
    
    if st.button("생산 실적 저장 및 레시피 자동 출고"):
        prod_name_clean = "당근라페 200g" if "200g" in product else "당근라페 400g"
        row = [str(prod_date), prod_name_clean, count, box_str, "생산완료"]
        if append_data("생산기록", row):
            st.success(f"🎉 **[{prod_date}]** **{product}** {count}개 생산 등록이 구글 시트에 완료되었습니다!")

    st.divider()

    st.markdown("### 🥣 최근 생산 내역")
    df_prod = load_data("생산기록")
    if not df_prod.empty:
        show_cols = [c for c in df_prod.columns if c != "일자_dt"]
        st.dataframe(df_prod[show_cols].tail(8).iloc[::-1], use_container_width=True)
    else:
        st.info("등록된 생산 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 3: 수기 출고
# ---------------------------------------------------------
with tab3:
    st.subheader("수기 출고 등록 (타 용도 사용 및 판매 출고)")
    out_date = st.date_input("출고 일자", datetime.date.today(), key="out_date")
    
    col_out1, col_out2 = st.columns(2)
    with col_out1:
        # 모든 항목 통합해서 선택 가능하게 구성
        all_items = RAW_MATERIALS + DYNAMIC_SUB_MATERIALS + DYNAMIC_PKG_MATERIALS
        target_item_out = st.selectbox("출고 품목 선택", all_items, key="out_item") 
        out_reason = st.selectbox("출고 목적", ["제품 제조 사용", "샘플/테스트 출고", "이벤트/증정용 사용", "발주서 판매 출고", "기타 수기 출고"])
    with col_out2:
        selected_out_unit = ITEM_UNITS.get(target_item_out, "개")
        out_qty = st.number_input(f"출고 수량 ({selected_out_unit})", min_value=0.01, step=1.0, key="out_qty")
        st.caption(f"💡 **[{target_item_out}]**의 출고 적용 단위: **{selected_out_unit}**")
        out_note = st.text_input("상세 비고 (선택사항)", placeholder="예: 쿠팡 발주 출고건 차감", key="out_note")
        
    if st.button("수기 출고 저장"):
        if out_qty <= 0:
            st.warning("출고 수량을 입력해주세요.")
        else:
            row = [str(out_date), target_item_out, out_qty, selected_out_unit, out_reason, out_note]
            if append_data("수기출고", row):
                st.success(f"📤 **[{out_date}]** **[{target_item_out}]** {out_qty} {selected_out_unit} 수기 출고 완료!")

    st.divider()

    st.markdown("### 📤 최근 수기 출고 내역")
    df_out = load_data("수기출고")
    if not df_out.empty:
        show_cols = [c for c in df_out.columns if c != "일자_dt"]
        st.dataframe(
            df_out[show_cols].tail(8).iloc[::-1].style.format({"출고수량": "{:,.2f}"}),
            use_container_width=True
        )
    else:
        st.info("등록된 수기 출고 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 4: 재고 조정
# ---------------------------------------------------------
with tab4:
    st.subheader("재고 조정 등록 (손실 및 실사 반영)")
    adj_date = st.date_input("조정 일자", datetime.date.today(), key="adj_date")
    
    col_adj1, col_adj2 = st.columns(2)
    with col_adj1:
        all_items_adj = RAW_MATERIALS + DYNAMIC_SUB_MATERIALS + DYNAMIC_PKG_MATERIALS
        target_item_adj = st.selectbox("조정 품목 선택", all_items_adj, key="adj_item") 
        adj_type = st.radio("조정 구분", ["파손/불량 손실 (-)", "실사 재고 증가 (+)", "실사 재고 감소 (-)"])
        adj_reason = st.selectbox("조정 사유", ["보관 중 파손/불량", "유통기한 경과 소진", "재고 실사 차이 반영", "기타 수동 조정"])
    with col_adj2:
        selected_adj_unit = ITEM_UNITS.get(target_item_adj, "개")
        adj_qty = st.number_input(f"조정 수량 ({selected_adj_unit})", min_value=0.01, step=1.0, key="adj_qty")
        st.caption(f"💡 **[{target_item_adj}]**의 조정 적용 단위: **{selected_adj_unit}**")
        adj_note = st.text_input("상세 비고", placeholder="예: 창고 이동 중 손실 발생", key="adj_note")
        
    if st.button("재고 조정 저장"):
        if adj_qty <= 0:
            st.warning("조정 수량을 입력해주세요.")
        else:
            row = [str(adj_date), target_item_adj, adj_type, adj_qty, selected_adj_unit, adj_reason, adj_note]
            if append_data("재고조정", row):
                st.success(f"🛠️ **[{adj_date}]** **[{target_item_adj}]** {adj_qty} {selected_adj_unit} 재고 조정 완료!")

    st.divider()

    st.markdown("### 🛠️ 최근 재고 조정 내역")
    df_adj = load_data("재고조정")
    if not df_adj.empty:
        show_cols = [c for c in df_adj.columns if c != "일자_dt"]
        st.dataframe(
            df_adj[show_cols].tail(8).iloc[::-1].style.format({"조정수량": "{:,.2f}"}),
            use_container_width=True
        )
    else:
        st.info("등록된 재고 조정 내역이 없습니다.")

# =========================================================
# 공통 데이터 로드 (수불부 용도)
# =========================================================
df_init = load_data("기초재고")
df_in = load_data("입고기록")
df_prod = load_data("생산기록")
df_out = load_data("수기출고")
df_adj = load_data("재고조정")

in_item_col = get_item_col(df_in)
init_item_col = get_item_col(df_init)
out_item_col = get_item_col(df_out)
adj_item_col = get_item_col(df_adj)

# ---------------------------------------------------------
# TAB 5: 원재료 수불부
# ---------------------------------------------------------
with tab5:
    st.subheader("📊 원재료 일자별 수불부")
    st.info("💡 소금, 오일, 머스타드 등 당근라페 배합에 들어가는 재료입니다.")
    
    today = datetime.date.today()
    first_day = today.replace(day=1)
    
    col_sd1, col_sd2, col_sd3 = st.columns([1, 1, 1])
    with col_sd1: raw_start_d = st.date_input("조회 시작일", first_day, key="raw_start_date")
    with col_sd2: raw_end_d = st.date_input("조회 종료일", today, key="raw_end_date")
    with col_sd3:
        st.write(""); st.write("")
        raw_hide_no_change = st.checkbox("💡 변동 없는 날짜 숨기기", value=True, key="raw_hide_no_change")

    raw_date_list = [raw_start_d + datetime.timedelta(days=i) for i in range((raw_end_d - raw_start_d).days + 1)]
    raw_subul = []
    
    for item in RAW_MATERIALS:
        unit = ITEM_UNITS.get(item, "g")
        clean_item = item.strip()
        
        base_init = 0.0
        safe_qty = 1000
        if not df_init.empty and init_item_col:
            init_row = df_init[df_init[init_item_col].astype(str).str.strip() == clean_item]
            if not init_row.empty:
                val = init_row["기월이월"].values[0] if "기월이월" in init_row.columns else (init_row["기초재고"].values[0] if "기초재고" in init_row.columns else 0)
                base_init = float(val) if pd.notnull(val) else 0.0
                if "안전재고" in init_row.columns:
                    s_val = init_row["안전재고"].values[0]
                    safe_qty = int(round(float(s_val))) if pd.notnull(s_val) else 1000

        prior_in = 0.0
        if not df_in.empty and "일자_dt" in df_in.columns and in_item_col:
            p_in_df = df_in[(df_in[in_item_col].astype(str).str.strip() == clean_item) & (df_in["일자_dt"] < raw_start_d)]
            prior_in = get_converted_in_qty(p_in_df)
        
        prior_auto_out = 0
        if not df_prod.empty and "일자_dt" in df_prod.columns and "생산제품" in df_prod.columns:
            p200_p = df_prod[(df_prod["생산제품"] == "당근라페 200g") & (df_prod["일자_dt"] < raw_start_d)]["생산수량"].sum()
            p400_p = df_prod[(df_prod["생산제품"] == "당근라페 400g") & (df_prod["일자_dt"] < raw_start_d)]["생산수량"].sum()
            if clean_item == "소금 (백설 꽃소금)": prior_auto_out = (p200_p // 6) * 24 + (p400_p // 8) * 65
            elif clean_item == "시타 프리올리바 올리브 오일": prior_auto_out = (p200_p // 6) * 223 + (p400_p // 8) * 594
            elif clean_item in ["홀그레인 머스타드(르네디종)", "홀그레인 머스타드(오뚜기)"]: prior_auto_out = (p200_p // 6) * 95 + (p400_p // 8) * 254
            elif clean_item in ["라임 주스(레이지)", "설탕(백설)"]: prior_auto_out = (p200_p // 6) * 32 + (p400_p // 8) * 84
            elif clean_item == "후추(오뚜기)": prior_auto_out = (p200_p // 6) * 1 + (p400_p // 8) * 2

        prior_manual_out = df_out[(df_out[out_item_col].astype(str).str.strip() == clean_item) & (df_out["일자_dt"] < raw_start_d)]["출고수량"].sum() if not df_out.empty and "일자_dt" in df_out.columns and out_item_col else 0
        
        prior_adj = 0
        if not df_adj.empty and "일자_dt" in df_adj.columns and adj_item_col:
            p_adj_df = df_adj[(df_adj[adj_item_col].astype(str).str.strip() == clean_item) & (df_adj["일자_dt"] < raw_start_d)]
            for _, r in p_adj_df.iterrows():
                prior_adj += int(round(r["조정수량"])) if "증가" in str(r.get("조정구분", "")) else -int(round(r["조정수량"]))

        current_running_stock = int(round(base_init + prior_in - prior_auto_out - prior_manual_out + prior_adj))

        for curr_d in raw_date_list:
            prev_carryover = current_running_stock
            d_in = 0
            if not df_in.empty and "일자_dt" in df_in.columns and in_item_col:
                d_in_df = df_in[(df_in[in_item_col].astype(str).str.strip() == clean_item) & (df_in["일자_dt"] == curr_d)]
                d_in = int(round(get_converted_in_qty(d_in_df)))
            
            d_auto_out = 0
            if not df_prod.empty and "일자_dt" in df_prod.columns:
                p200 = df_prod[(df_prod["생산제품"] == "당근라페 200g") & (df_prod["일자_dt"] == curr_d)]["생산수량"].sum()
                p400 = df_prod[(df_prod["생산제품"] == "당근라페 400g") & (df_prod["일자_dt"] == curr_d)]["생산수량"].sum()
                if clean_item == "소금 (백설 꽃소금)": d_auto_out = (p200 // 6) * 24 + (p400 // 8) * 65
                elif clean_item == "시타 프리올리바 올리브 오일": d_auto_out = (p200 // 6) * 223 + (p400 // 8) * 594
                elif clean_item in ["홀그레인 머스타드(르네디종)", "홀그레인 머스타드(오뚜기)"]: d_auto_out = (p200 // 6) * 95 + (p400 // 8) * 254
                elif clean_item in ["라임 주스(레이지)", "설탕(백설)"]: d_auto_out = (p200 // 6) * 32 + (p400 // 8) * 84
                elif clean_item == "후추(오뚜기)": d_auto_out = (p200 // 6) * 1 + (p400 // 8) * 2

            d_manual_out = int(round(df_out[(df_out[out_item_col].astype(str).str.strip() == clean_item) & (df_out["일자_dt"] == curr_d)]["출고수량"].sum())) if not df_out.empty and "일자_dt" in df_out.columns and out_item_col else 0
            
            d_adj = 0
            if not df_adj.empty and "일자_dt" in df_adj.columns and adj_item_col:
                d_adj_df = df_adj[(df_adj[adj_item_col].astype(str).str.strip() == clean_item) & (df_adj["일자_dt"] == curr_d)]
                for _, r in d_adj_df.iterrows():
                    d_adj += int(round(r["조정수량"])) if "증가" in str(r.get("조정구분", "")) else -int(round(r["조정수량"]))
                    
            day_end_stock = prev_carryover + d_in - d_auto_out - d_manual_out + d_adj
            current_running_stock = day_end_stock
            
            raw_subul.append({
                "일자": str(curr_d), "품목명": item, "단위": unit, "전일이월": prev_carryover,
                "금일입고": d_in, "생산출고(자동)": d_auto_out, "수기출고": d_manual_out,
                "재고조정": d_adj, "당일재고": day_end_stock, "안전재고": safe_qty
            })

    df_raw_calc = pd.DataFrame(raw_subul)
    
    col_raw1, col_raw2, col_raw3 = st.columns([2, 1, 1])
    with col_raw1: selected_raw_item = st.selectbox("조회할 품목", ["전체 품목 보기"] + RAW_MATERIALS, key="s_raw_item")
    with col_raw2: 
        if st.button("🖨️ 인쇄/PDF", key="p_raw", use_container_width=True): st.components.v1.html("<script>window.print();</script>", height=0)
    with col_raw3:
        st.download_button(label="📥 CSV 다운로드", data=to_csv(df_raw_calc), file_name=f"원재료_{raw_start_d}_{raw_end_d}.csv", mime="text/csv", use_container_width=True)

    if selected_raw_item != "전체 품목 보기":
        df_raw_calc = df_raw_calc[df_raw_calc["품목명"] == selected_raw_item]
    if raw_hide_no_change:
        df_raw_calc = df_raw_calc[(df_raw_calc["금일입고"] != 0) | (df_raw_calc["생산출고(자동)"] != 0) | (df_raw_calc["수기출고"] != 0) | (df_raw_calc["재고조정"] != 0)]

    df_raw_calc = df_raw_calc.sort_values(by=["일자", "품목명"]).reset_index(drop=True)
    st.dataframe(
        df_raw_calc.style.format({"전일이월": "{:,d}", "금일입고": "{:,d}", "생산출고(자동)": "{:,d}", "수기출고": "{:,d}", "재고조정": "{:,d}", "당일재고": "{:,d}", "안전재고": "{:,d}"}),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 6: 부재료 수불부
# ---------------------------------------------------------
with tab6:
    st.subheader("🍶 부재료 일자별 수불부")
    st.info("💡 드레싱 등 별도로 동봉되는 부재료 품목입니다.")
    
    col_sub_sd1, col_sub_sd2, col_sub_sd3 = st.columns([1, 1, 1])
    with col_sub_sd1: sub_start_d = st.date_input("조회 시작일", first_day, key="sub_start_date")
    with col_sub_sd2: sub_end_d = st.date_input("조회 종료일", today, key="sub_end_date")
    with col_sub_sd3:
        st.write(""); st.write("")
        sub_hide_no_change = st.checkbox("💡 변동 없는 날짜 숨기기", value=True, key="sub_hide_no_change")

    sub_date_list = [sub_start_d + datetime.timedelta(days=i) for i in range((sub_end_d - sub_start_d).days + 1)]
    sub_subul = []
    
    for item in DYNAMIC_SUB_MATERIALS:
        unit = ITEM_UNITS.get(item, "개")
        clean_item = item.strip()
        
        base_init = 0
        safe_qty = 100
        if not df_init.empty and init_item_col:
            init_row = df_init[df_init[init_item_col].astype(str).str.strip() == clean_item]
            if not init_row.empty:
                val = init_row["기월이월"].values[0] if "기월이월" in init_row.columns else (init_row["기초재고"].values[0] if "기초재고" in init_row.columns else 0)
                base_init = int(round(float(val))) if pd.notnull(val) else 0
                if "안전재고" in init_row.columns:
                    s_val = init_row["안전재고"].values[0]
                    safe_qty = int(round(float(s_val))) if pd.notnull(s_val) else 100

        prior_in = 0
        if not df_in.empty and "일자_dt" in df_in.columns and in_item_col:
            p_in_df = df_in[(df_in[in_item_col].astype(str).str.strip() == clean_item) & (df_in["일자_dt"] < sub_start_d)]
            prior_in = int(round(get_converted_in_qty(p_in_df)))
        
        prior_manual_out = int(round(df_out[(df_out[out_item_col].astype(str).str.strip() == clean_item) & (df_out["일자_dt"] < sub_start_d)]["출고수량"].sum())) if not df_out.empty and "일자_dt" in df_out.columns and out_item_col else 0
        
        prior_adj = 0
        if not df_adj.empty and "일자_dt" in df_adj.columns and adj_item_col:
            p_adj_df = df_adj[(df_adj[adj_item_col].astype(str).str.strip() == clean_item) & (df_adj["일자_dt"] < sub_start_d)]
            for _, r in p_adj_df.iterrows():
                prior_adj += int(round(r["조정수량"])) if "증가" in str(r.get("조정구분", "")) else -int(round(r["조정수량"]))

        current_running_stock = base_init + prior_in - prior_manual_out + prior_adj

        for curr_d in sub_date_list:
            prev_carryover = current_running_stock
            d_in = 0
            if not df_in.empty and "일자_dt" in df_in.columns and in_item_col:
                d_in_df = df_in[(df_in[in_item_col].astype(str).str.strip() == clean_item) & (df_in["일자_dt"] == curr_d)]
                d_in = int(round(get_converted_in_qty(d_in_df)))
            
            d_manual_out = int(round(df_out[(df_out[out_item_col].astype(str).str.strip() == clean_item) & (df_out["일자_dt"] == curr_d)]["출고수량"].sum())) if not df_out.empty and "일자_dt" in df_out.columns and out_item_col else 0
            
            d_adj = 0
            if not df_adj.empty and "일자_dt" in df_adj.columns and adj_item_col:
                d_adj_df = df_adj[(df_adj[adj_item_col].astype(str).str.strip() == clean_item) & (df_adj["일자_dt"] == curr_d)]
                for _, r in d_adj_df.iterrows():
                    d_adj += int(round(r["조정수량"])) if "증가" in str(r.get("조정구분", "")) else -int(round(r["조정수량"]))
                    
            day_end_stock = prev_carryover + d_in - d_manual_out + d_adj
            current_running_stock = day_end_stock
            
            sub_subul.append({
                "일자": str(curr_d), "품목명": item, "단위": unit, "전일이월": prev_carryover,
                "금일입고": d_in, "생산출고(자동)": 0, "수기출고": d_manual_out,
                "재고조정": d_adj, "당일재고": day_end_stock, "안전재고": safe_qty
            })

    df_sub_calc = pd.DataFrame(sub_subul)

    col_sub1, col_sub2, col_sub3 = st.columns([2, 1, 1])
    with col_sub1: selected_sub_item = st.selectbox("조회할 품목", ["전체 품목 보기"] + DYNAMIC_SUB_MATERIALS, key="s_sub_item")
    with col_sub2:
        if st.button("🖨️ 인쇄/PDF", key="print_sub", use_container_width=True): st.components.v1.html("<script>window.print();</script>", height=0)
    with col_sub3:
        st.download_button(label="📥 CSV 다운로드", data=to_csv(df_sub_calc), file_name=f"부재료_{sub_start_d}_{sub_end_d}.csv", mime="text/csv", use_container_width=True)

    if selected_sub_item != "전체 품목 보기":
        df_sub_calc = df_sub_calc[df_sub_calc["품목명"] == selected_sub_item]
    if sub_hide_no_change:
        df_sub_calc = df_sub_calc[(df_sub_calc["금일입고"] != 0) | (df_sub_calc["수기출고"] != 0) | (df_sub_calc["재고조정"] != 0)]

    df_sub_calc = df_sub_calc.sort_values(by=["일자", "품목명"]).reset_index(drop=True)
    st.dataframe(
        df_sub_calc.style.format({"전일이월": "{:,d}", "금일입고": "{:,d}", "생산출고(자동)": "{:,d}", "수기출고": "{:,d}", "재고조정": "{:,d}", "당일재고": "{:,d}", "안전재고": "{:,d}"}),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 7: 부자재 수불부
# ---------------------------------------------------------
with tab7:
    st.subheader("📦 부자재 일자별 수불부")
    st.info("💡 트레이, 실링지, 박스 등 포장 및 용기류 품목입니다.")
    
    col_pkg_sd1, col_pkg_sd2, col_pkg_sd3 = st.columns([1, 1, 1])
    with col_pkg_sd1: pkg_start_d = st.date_input("조회 시작일", first_day, key="pkg_start_date")
    with col_pkg_sd2: pkg_end_d = st.date_input("조회 종료일", today, key="pkg_end_date")
    with col_pkg_sd3:
        st.write(""); st.write("")
        pkg_hide_no_change = st.checkbox("💡 변동 없는 날짜 숨기기", value=True, key="pkg_hide_no_change")

    pkg_date_list = [pkg_start_d + datetime.timedelta(days=i) for i in range((pkg_end_d - pkg_start_d).days + 1)]
    pkg_subul = []
    
    for item in DYNAMIC_PKG_MATERIALS:
        unit = ITEM_UNITS.get(item, "개")
        clean_item = item.strip()
        
        base_init = 0
        safe_qty = 100
        if not df_init.empty and init_item_col:
            init_row = df_init[df_init[init_item_col].astype(str).str.strip() == clean_item]
            if not init_row.empty:
                val = init_row["기월이월"].values[0] if "기월이월" in init_row.columns else (init_row["기초재고"].values[0] if "기초재고" in init_row.columns else 0)
                base_init = int(round(float(val))) if pd.notnull(val) else 0
                if "안전재고" in init_row.columns:
                    s_val = init_row["안전재고"].values[0]
                    safe_qty = int(round(float(s_val))) if pd.notnull(s_val) else 100

        prior_in = 0
        if not df_in.empty and "일자_dt" in df_in.columns and in_item_col:
            p_in_df = df_in[(df_in[in_item_col].astype(str).str.strip() == clean_item) & (df_in["일자_dt"] < pkg_start_d)]
            prior_in = int(round(get_converted_in_qty(p_in_df)))
        
        prior_auto_out = 0
        if not df_prod.empty and "일자_dt" in df_prod.columns and "생산제품" in df_prod.columns:
            p200_p = df_prod[(df_prod["생산제품"] == "당근라페 200g") & (df_prod["일자_dt"] < pkg_start_d)]["생산수량"].sum()
            p400_p = df_prod[(df_prod["생산제품"] == "당근라페 400g") & (df_prod["일자_dt"] < pkg_start_d)]["생산수량"].sum()
            if clean_item in ["당근200트레이", "당근200탑실링지"]: prior_auto_out = p200_p
            elif clean_item == "당근200표시사항 스티커": prior_auto_out = math.ceil(p200_p / 5) if p200_p > 0 else 0
            elif clean_item == "카톤박스(특소)": prior_auto_out = p200_p // 6
            elif clean_item in ["파우치(200*250)", "당근 400 스티커"]: prior_auto_out = p400_p
            elif clean_item == "카톤박스(중)": prior_auto_out = p400_p // 8

        prior_manual_out = int(round(df_out[(df_out[out_item_col].astype(str).str.strip() == clean_item) & (df_out["일자_dt"] < pkg_start_d)]["출고수량"].sum())) if not df_out.empty and "일자_dt" in df_out.columns and out_item_col else 0
        
        prior_adj = 0
        if not df_adj.empty and "일자_dt" in df_adj.columns and adj_item_col:
            p_adj_df = df_adj[(df_adj[adj_item_col].astype(str).str.strip() == clean_item) & (df_adj["일자_dt"] < pkg_start_d)]
            for _, r in p_adj_df.iterrows():
                prior_adj += int(round(r["조정수량"])) if "증가" in str(r.get("조정구분", "")) else -int(round(r["조정수량"]))

        current_running_stock = base_init + prior_in - prior_auto_out - prior_manual_out + prior_adj

        for curr_d in pkg_date_list:
            prev_carryover = current_running_stock
            d_in = 0
            if not df_in.empty and "일자_dt" in df_in.columns and in_item_col:
                d_in_df = df_in[(df_in[in_item_col].astype(str).str.strip() == clean_item) & (df_in["일자_dt"] == curr_d)]
                d_in = int(round(get_converted_in_qty(d_in_df)))
            
            d_auto_out = 0
            if not df_prod.empty and "일자_dt" in df_prod.columns:
                p200 = df_prod[(df_prod["생산제품"] == "당근라페 200g") & (df_prod["일자_dt"] == curr_d)]["생산수량"].sum()
                p400 = df_prod[(df_prod["생산제품"] == "당근라페 400g") & (df_prod["일자_dt"] == curr_d)]["생산수량"].sum()
                if clean_item in ["당근200트레이", "당근200탑실링지"]: d_auto_out = p200
                elif clean_item == "당근200표시사항 스티커": d_auto_out = math.ceil(p200 / 5) if p200 > 0 else 0
                elif clean_item == "카톤박스(특소)": d_auto_out = p200 // 6
                elif clean_item in ["파우치(200*250)", "당근 400 스티커"]: d_auto_out = p400
                elif clean_item == "카톤박스(중)": d_auto_out = p400 // 8

            d_manual_out = int(round(df_out[(df_out[out_item_col].astype(str).str.strip() == clean_item) & (df_out["일자_dt"] == curr_d)]["출고수량"].sum())) if not df_out.empty and "일자_dt" in df_out.columns and out_item_col else 0
            
            d_adj = 0
            if not df_adj.empty and "일자_dt" in df_adj.columns and adj_item_col:
                d_adj_df = df_adj[(df_adj[adj_item_col].astype(str).str.strip() == clean_item) & (df_adj["일자_dt"] == curr_d)]
                for _, r in d_adj_df.iterrows():
                    d_adj += int(round(r["조정수량"])) if "증가" in str(r.get("조정구분", "")) else -int(round(r["조정수량"]))
                    
            day_end_stock = prev_carryover + d_in - d_auto_out - d_manual_out + d_adj
            current_running_stock = day_end_stock
            
            pkg_subul.append({
                "일자": str(curr_d), "품목명": item, "단위": unit, "전일이월": prev_carryover,
                "금일입고": d_in, "생산출고(자동)": d_auto_out, "수기출고": d_manual_out,
                "재고조정": d_adj, "당일재고": day_end_stock, "안전재고": safe_qty
            })

    df_pkg_calc = pd.DataFrame(pkg_subul)

    col_pkg1, col_pkg2, col_pkg3 = st.columns([2, 1, 1])
    with col_pkg1: selected_pkg_item = st.selectbox("조회할 품목", ["전체 품목 보기"] + DYNAMIC_PKG_MATERIALS, key="s_pkg_item")
    with col_pkg2:
        if st.button("🖨️ 인쇄/PDF", key="print_pkg", use_container_width=True): st.components.v1.html("<script>window.print();</script>", height=0)
    with col_pkg3:
        st.download_button(label="📥 CSV 다운로드", data=to_csv(df_pkg_calc), file_name=f"부자재_{pkg_start_d}_{pkg_end_d}.csv", mime="text/csv", use_container_width=True)

    if selected_pkg_item != "전체 품목 보기":
        df_pkg_calc = df_pkg_calc[df_pkg_calc["품목명"] == selected_pkg_item]
    if pkg_hide_no_change:
        df_pkg_calc = df_pkg_calc[(df_pkg_calc["금일입고"] != 0) | (df_pkg_calc["생산출고(자동)"] != 0) | (df_pkg_calc["수기출고"] != 0) | (df_pkg_calc["재고조정"] != 0)]

    df_pkg_calc = df_pkg_calc.sort_values(by=["일자", "품목명"]).reset_index(drop=True)
    st.dataframe(
        df_pkg_calc.style.format({"전일이월": "{:,d}", "금일입고": "{:,d}", "생산출고(자동)": "{:,d}", "수기출고": "{:,d}", "재고조정": "{:,d}", "당일재고": "{:,d}", "안전재고": "{:,d}"}),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 8: 거래처별 입고 현황
# ---------------------------------------------------------
with tab8:
    st.subheader("🏪 거래처별 구매/입고 현황")
    if not df_in.empty and "거래처명" in df_in.columns:
        today = datetime.date.today()
        first_day = today.replace(day=1)
        
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1: v_start_d = st.date_input("조회 시작일 선택", first_day, key="v_start_date")
        with col_v2: v_end_d = st.date_input("조회 종료일 선택", today, key="v_end_date")
        with col_v3:
            vendor_list = ["전체 거래처"] + list(df_in["거래처명"].dropna().unique())
            selected_v = st.selectbox("조회할 거래처 선택", vendor_list, key="v_select")
            
        df_filtered = df_in[(df_in["일자_dt"] >= v_start_d) & (df_in["일자_dt"] <= v_end_d)]
        if selected_v != "전체 거래처":
            df_filtered = df_filtered[df_filtered["거래처명"].astype(str).str.strip() == selected_v.strip()]
            
        st.divider()
        amount_col = "공급가액(VAT별도)" if "공급가액(VAT별도)" in df_filtered.columns else ("총금액" if "총금액" in df_filtered.columns else "")
        
        if not df_filtered.empty and amount_col:
            v_summary = df_filtered.groupby("거래처명")[amount_col].sum().reset_index()
            cols = st.columns(len(v_summary) if len(v_summary) > 0 else 1)
            for idx, row in v_summary.iterrows():
                with cols[idx % len(cols)]:
                    st.metric(f"{row['거래처명']} 누적 공급가액", f"{row[amount_col]:,d} 원")
        else:
            st.info("선택한 조건에 해당하는 입고 데이터가 없습니다.")
            
        st.markdown("### 🔍 거래처별 상세 입고 내역")
        show_cols = [c for c in df_filtered.columns if c not in ["DB환산수량", "DB환산단위", "일자_dt"]]
        df_v_display = df_filtered[show_cols]
        
        format_dict = {"입고수량": "{:,d}"}
        for c in ["공급가액(VAT별도)", "VAT(10%)", "총합계금액", "개당단가", "총금액", "단가"]:
            if c in df_v_display.columns:
                format_dict[c] = "{:,d}"
        st.dataframe(df_v_display.style.format(format_dict), use_container_width=True)
    else:
        st.info("등록된 거래처 입고 기록이 없습니다.")

# ---------------------------------------------------------
# TAB 9: 기초정보 관리
# ---------------------------------------------------------
with tab9:
    st.subheader("⚙️ 기초정보 관리 (항목 및 거래처 추가)")
    st.info("이곳에서 등록한 항목과 거래처는 자동으로 구글 시트에 저장되며, 이후 입고 및 수불 등록 시 드롭다운 목록에 반영됩니다.")
    
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.markdown("#### 📦 새 품목 추가")
        new_item_cat = st.radio("추가할 품목의 종류", ["부재료", "부자재"], horizontal=True)
        new_item_name = st.text_input(f"새 {new_item_cat}명", placeholder="예: SW-002 용기")
        new_item_unit = st.selectbox("단위", ["개", "장", "통", "kg", "g", "L", "ml"])
        
        if st.button(f"{new_item_cat} 추가하기"):
            if new_item_name.strip():
                if new_item_name.strip() in DYNAMIC_SUB_MATERIALS or new_item_name.strip() in DYNAMIC_PKG_MATERIALS:
                    st.warning("이미 등록된 품목입니다.")
                else:
                    if append_data("기초정보", [new_item_cat, new_item_name.strip(), new_item_unit]):
                        st.success(f"✅ '{new_item_name}' ({new_item_cat}) 항목이 추가되었습니다.")
                        st.rerun()
            else:
                st.warning(f"{new_item_cat}명을 입력하세요.")
                
    with col_m2:
        st.markdown("#### 🏪 새 거래처 추가")
        new_vendor_name = st.text_input("새 거래처명", placeholder="예: OO패키징")
        
        if st.button("거래처 추가하기"):
            if new_vendor_name.strip():
                if new_vendor_name.strip() in DYNAMIC_VENDORS:
                    st.warning("이미 등록된 거래처입니다.")
                else:
                    if append_data("기초정보", ["거래처", new_vendor_name.strip(), ""]):
                        st.success(f"✅ '{new_vendor_name}' 거래처가 추가되었습니다.")
                        st.rerun()
            else:
                st.warning("거래처명을 입력하세요.")
                
    st.divider()
    st.markdown("### 📋 현재 추가된 동적 기초정보 목록")
    df_master = load_data("기초정보")
    if not df_master.empty:
        st.dataframe(df_master, use_container_width=True)
    else:
        st.info("현재 동적으로 추가된 기초정보 데이터가 없습니다.")
