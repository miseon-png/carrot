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
            # 헤더 빈셀/중복 에러 방지를 위해 get_all_values 사용
            data = sheet.get_all_values()
            if len(data) > 1:
                headers = data[0]
                headers = [h if h != "" else f"Unnamed_{i}" for i, h in enumerate(headers)]
                df = pd.DataFrame(data[1:], columns=headers)
                
                # 숫자형 데이터 안전 변환
                numeric_cols = [
                    "입고수량", "DB환산수량", "공급가액(VAT별도)", "VAT(10%)", 
                    "총합계금액", "개당단가", "총금액", "단가", "출고수량", "조정수량", "생산수량"
                ]
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
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
# TAB 1: 입고 등록 (DB환산수량/단위 UI 제외 처리)
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
    
    # 단위 정수 환산
    base_qty = int(input_qty)
    base_unit = unit_type
    if unit_type in ["kg", "L"]:
        base_qty = int(input_qty * 1000)
        base_unit = "g" if unit_type == "kg" else "ml"
        st.info(f"💡 시스템 내부 데이터베이스에는 **{base_qty:,d} {base_unit}** 로 환산되어 저장됩니다.")
    
    # 내부 연산
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
                st.success(f"✅ **[{in_date}]** 거래처 **[{vendor_name}]** / **{item_name}** {input_qty:,d}{unit_type} (공급가액: {supply_amount:,.0f}원) 저장 완료!")

    st.divider()

    st.markdown("### 🕒 최근 입고 내역")
    df_in = load_data("입고기록")
    if not df_in.empty:
        # DB환산수량, DB환산단위 숨김 처리
        show_cols = [c for c in df_in.columns if c not in ["DB환산수량", "DB환산단위"]]
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
        prod_name_clean = "당근라페 200g" if "200g" in product else "당근라페 400g"
        row = [str(prod_date), prod_name_clean, count, box_str, "생산완료"]
        if append_data("생산기록", row):
            st.success(f"🎉 **[{prod_date}]** **{product}** {count}개 생산 등록이 구글 시트에 완료되었습니다!")

    st.divider()

    st.markdown("### 🥣 최근 생산 내역")
    df_prod = load_data("생산기록")
    if not df_prod.empty:
        st.dataframe(df_prod.tail(8).iloc[::-1], use_container_width=True)
    else:
        st.info("등록된 생산 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 3: 수기 출고
# ---------------------------------------------------------
with tab3:
    st.subheader("수기 출고 등록 (타 용도 사용)")
    out_date = st.date_input("출고 일자", datetime.date.today(), key="out_date")
    
    col_out1, col_out2 = st.columns(2)
    with col_out1:
        target_item_out = st.selectbox("출고 원부재료 선택", RAW_MATERIALS + SUB_MATERIALS, key="out_item")
        out_reason = st.selectbox("출고 목적", ["타 제품 제조 사용", "샘플/테스트 출고", "이벤트/증정용 사용", "기타 수기 출고"])
    with col_out2:
        selected_out_unit = ITEM_UNITS.get(target_item_out, "단위")
        out_qty = st.number_input(f"출고 수량 ({selected_out_unit})", min_value=0.01, step=1.0, key="out_qty")
        st.caption(f"💡 **[{target_item_out}]**의 출고 적용 단위: **{selected_out_unit}**")
        out_note = st.text_input("상세 비고 (선택사항)", placeholder="예: B제품 포장용 카톤박스 10개 사용", key="out_note")
        
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
        st.dataframe(
            df_out.tail(8).iloc[::-1].style.format({"출고수량": "{:,.2f}"}),
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
        target_item_adj = st.selectbox("조정 원부재료 선택", RAW_MATERIALS + SUB_MATERIALS, key="adj_item")
        adj_type = st.radio("조정 구분", ["파손/불량 손실 (-)", "실사 재고 증가 (+)", "실사 재고 감소 (-)"])
        adj_reason = st.selectbox("조정 사유", ["보관 중 파손/불량", "유통기한 경과 소진", "재고 실사 차이 반영", "기타 수동 조정"])
    with col_adj2:
        selected_adj_unit = ITEM_UNITS.get(target_item_adj, "단위")
        adj_qty = st.number_input(f"조정 수량 ({selected_adj_unit})", min_value=0.01, step=1.0, key="adj_qty")
        st.caption(f"💡 **[{target_item_adj}]**의 조정 적용 단위: **{selected_adj_unit}**")
        adj_note = st.text_input("상세 비고", placeholder="예: 창고 이동 중 스티커 오염 손실 발생", key="adj_note")
        
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
        st.dataframe(
            df_adj.tail(8).iloc[::-1].style.format({"조정수량": "{:,.2f}"}),
            use_container_width=True
        )
    else:
        st.info("등록된 재고 조정 내역이 없습니다.")

# ---------------------------------------------------------
# TAB 5: 수불부 현황판
# ---------------------------------------------------------
with tab5:
    st.subheader("📋 원부재료 수불현황판")
    st.info("💡 구글 시트에 추가된 실제 입고/생산/출고/조정 기록을 집계하여 실시간 수불부를 산출합니다.")
    
    df_in = load_data("입고기록")
    df_prod = load_data("생산기록")
    df_out = load_data("수기출고")
    df_adj = load_data("재고조정")
    
    # 1. 원재료 수불 계산
    raw_subul = []
    for item in RAW_MATERIALS:
        unit = ITEM_UNITS[item]
        init_qty = 0.0
        safe_qty = 1000.0
        
        in_sum = 0.0
        if not df_in.empty and "재료명" in df_in.columns and "DB환산수량" in df_in.columns:
            in_sum = df_in[df_in["재료명"] == item]["DB환산수량"].sum()
            
        auto_out_sum = 0.0
        if not df_prod.empty and "생산제품" in df_prod.columns:
            prod_200_count = df_prod[df_prod["생산제품"] == "당근라페 200g"]["생산수량"].sum()
            prod_400_count = df_prod[df_prod["생산제품"] == "당근라페 400g"]["생산수량"].sum()
            
            if item == "소금 (백설 꽃소금)":
                auto_out_sum = (prod_200_count // 6) * 24 + (prod_400_count // 8) * 65
            elif item == "시타 프리올리바 올리브 오일":
                auto_out_sum = (prod_200_count // 6) * 223 + (prod_400_count // 8) * 594
            elif item in ["홀그레인 머스타드(르네디종)", "홀그레인 머스타드(오뚜기)"]:
                auto_out_sum = (prod_200_count // 6) * 95 + (prod_400_count // 8) * 254
            elif item in ["라임 주스(레이지)", "설탕(백설)"]:
                auto_out_sum = (prod_200_count // 6) * 32 + (prod_400_count // 8) * 84
            elif item == "후추(오뚜기)":
                auto_out_sum = (prod_200_count // 6) * 1 + (prod_400_count // 8) * 2
                
        manual_out_sum = 0.0
        if not df_out.empty and "재료명" in df_out.columns:
            manual_out_sum = df_out[df_out["재료명"] == item]["출고수량"].sum()
            
        adj_sum = 0.0
        if not df_adj.empty and "재료명" in df_adj.columns:
            adj_df_item = df_adj[df_adj["재료명"] == item]
            for _, row in adj_df_item.iterrows():
                if "증가" in str(row["조정구분"]):
                    adj_sum += row["조정수량"]
                else:
                    adj_sum -= row["조정수량"]
                    
        curr_stock = init_qty + in_sum - auto_out_sum - manual_out_sum + adj_sum
        
        raw_subul.append({
            "재료명": item, "단위": unit, "기월이월": init_qty, "금월입고": in_sum,
            "생산출고(자동)": auto_out_sum, "수기출고": manual_out_sum, "재고조정": adj_sum,
            "현재재고": curr_stock, "안전재고": safe_qty
        })

    st.markdown("### 🥕 원재료 수불부")
    df_raw_calc = pd.DataFrame(raw_subul)
    st.dataframe(
        df_raw_calc.style.format({
            "기월이월": "{:,.2f}", "금월입고": "{:,.2f}", "생산출고(자동)": "{:,.2f}",
            "수기출고": "{:,.2f}", "재고조정": "{:,.2f}", "현재재고": "{:,.2f}", "안전재고": "{:,.2f}"
        }),
        use_container_width=True
    )

    st.divider()

    # 2. 부재료 수불 계산
    sub_subul = []
    for item in SUB_MATERIALS:
        unit = ITEM_UNITS[item]
        init_qty = 0
        safe_qty = 100
        
        in_sum = 0
        if not df_in.empty and "재료명" in df_in.columns and "DB환산수량" in df_in.columns:
            in_sum = int(df_in[df_in["재료명"] == item]["DB환산수량"].sum())
            
        auto_out_sum = 0
        if not df_prod.empty and "생산제품" in df_prod.columns:
            p200 = df_prod[df_prod["생산제품"] == "당근라페 200g"]["생산수량"].sum()
            p400 = df_prod[df_prod["생산제품"] == "당근라페 400g"]["생산수량"].sum()
            
            if item in ["당근200트레이", "당근200탑실링지"]:
                auto_out_sum = p200
            elif item == "당근200표시사항 스티커":
                auto_out_sum = math.ceil(p200 / 5) if p200 > 0 else 0
            elif item == "카톤박스(특소)":
                auto_out_sum = p200 // 6
            elif item in ["파우치(200*250)", "당근 400 스티커"]:
                auto_out_sum = p400
            elif item == "카톤박스(소)":
                auto_out_sum = p400 // 8

        manual_out_sum = 0
        if not df_out.empty and "재료명" in df_out.columns:
            manual_out_sum = int(df_out[df_out["재료명"] == item]["출고수량"].sum())
            
        adj_sum = 0
        if not df_adj.empty and "재료명" in df_adj.columns:
            adj_df_item = df_adj[df_adj["재료명"] == item]
            for _, row in adj_df_item.iterrows():
                if "증가" in str(row["조정구분"]):
                    adj_sum += int(row["조정수량"])
                else:
                    adj_sum -= int(row["조정수량"])
                    
        curr_stock = init_qty + in_sum - auto_out_sum - manual_out_sum + adj_sum
        
        sub_subul.append({
            "재료명": item, "단위": unit, "기월이월": init_qty, "금월입고": in_sum,
            "생산출고(자동)": auto_out_sum, "수기출고": manual_out_sum, "재고조정": adj_sum,
            "현재재고": curr_stock, "안전재고": safe_qty
        })

    st.markdown("### 📦 부재료 수불부")
    df_sub_calc = pd.DataFrame(sub_subul)
    st.dataframe(
        df_sub_calc.style.format({
            "기월이월": "{:,d}", "금월입고": "{:,d}", "생산출고(자동)": "{:,d}",
            "수기출고": "{:,d}", "재고조정": "{:,d}", "현재재고": "{:,d}", "안전재고": "{:,d}"
        }),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 6: 거래처별 입고 현황
# ---------------------------------------------------------
with tab6:
    st.subheader("🏪 거래처별 구매/입고 현황")
    df_in = load_data("입고기록")
    
    amount_col = "공급가액(VAT별도)" if "공급가액(VAT별도)" in df_in.columns else ("총금액" if "총금액" in df_in.columns else "")
    
    if not df_in.empty and "거래처명" in df_in.columns and amount_col:
        v_summary = df_in.groupby("거래처명")[amount_col].sum().reset_index()
        cols = st.columns(len(v_summary) if len(v_summary) > 0 else 1)
        for idx, row in v_summary.iterrows():
            with cols[idx % len(cols)]:
                st.metric(f"{row['거래처명']} 누적 공급가액", f"{row[amount_col]:,d} 원")
        
        st.divider()
        st.markdown("### 🔍 거래처별 상세 입고 내역")
        selected_v = st.selectbox("조회할 거래처 선택", ["전체 거래처"] + list(df_in["거래처명"].unique()))
        
        if selected_v != "전체 거래처":
            df_filtered = df_in[df_in["거래처명"] == selected_v]
        else:
            df_filtered = df_in
            
        show_cols = [c for c in df_filtered.columns if c not in ["DB환산수량", "DB환산단위"]]
        df_v_display = df_filtered[show_cols]
        
        format_dict = {"입고수량": "{:,d}"}
        for c in ["공급가액(VAT별도)", "VAT(10%)", "총합계금액", "개당단가", "총금액", "단가"]:
            if c in df_v_display.columns:
                format_dict[c] = "{:,d}"
                
        st.dataframe(
            df_v_display.style.format(format_dict),
            use_container_width=True
        )
    else:
        st.info("거래처 입고 기록이 없습니다.")
