import streamlit as st
import pandas as pd
import datetime
import math

# ---------------------------------------------------------
# 0. 페이지 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="당근라페 원부재료 수불부", layout="wide")
st.title("🥕 당근라페 원부재료 수불 및 생산 관리 시스템")

# ---------------------------------------------------------
# 1. 원부재료 및 거래처 표준 목록 정의
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
# TAB 1: 입고 등록 (+ 최근 입력 내역 8개 표 / 원 단위 정수 표기)
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
    
    # 단위 자동 환산 및 총액 연산
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
            st.success(f"✅ **[{in_date}]** 거래처 **[{vendor_name}]** / **{item_name}** {input_qty}{unit_type} ({total_amount:,.0f}원) 입고 완료!")

    st.divider()

    # 📋 최근 입고 내역 (8개 - 금액 소수점 없는 원 단위 서식 적용)
    st.markdown("### 🕒 최근 입고 내역 (최신 8건)")
    recent_in_data = {
        "입고일자": ["2026-09-16", "2026-09-15", "2026-09-12", "2026-09-10", "2026-09-08", "2026-09-05", "2026-09-03", "2026-09-01"],
        "거래처명": ["제이원글로벌", "케이앤에스", "은성특수산업", "제이원글로벌", "케이앤에스", "제이원글로벌", "은성특수산업", "케이앤에스"],
        "구분": ["원재료", "부재료", "부재료", "원재료", "부재료", "원재료", "부재료", "부재료"],
        "재료명": ["소금 (백설 꽃소금)", "당근200트레이", "카톤박스(소)", "시타 프리올리바 올리브 오일", "당근200탑실링지", "라임 주스(레이지)", "파우치(200*250)", "당근 400 스티커"],
        "입고수량": [20.00, 1000.00, 200.00, 30.00, 1000.00, 10.00, 500.00, 500.00],
        "단위": ["kg", "개", "개", "L", "개", "L", "개", "개"],
        "단가(원)": [1500, 150, 800, 25000, 100, 15000, 250, 80],
        "총금액(원)": [30000, 150000, 160000, 750000, 100000, 150000, 125000, 40000]
    }
    df_recent_in = pd.DataFrame(recent_in_data)
    st.dataframe(
        df_recent_in.style.format({
            "입고수량": "{:,.2f}",
            "단가(원)": "{:,d}",
            "총금액(원)": "{:,d}"
        }),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 2: 당근라페 완제품 생산 (+ 최근 생산 내역 8개 표)
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
    st.table(pd.DataFrame(preview_data))
    
    if st.button("생산 실적 저장 및 레시피 자동 출고"):
        st.success(f"🎉 **[{prod_date}]** **{product}** {count}개 생산 등록 완료!")

    st.divider()

    # 📋 최근 생산 내역 (8개)
    st.markdown("### 🥣 최근 생산 내역 (최신 8건)")
    recent_prod_data = {
        "생산일자": ["2026-09-16", "2026-09-15", "2026-09-14", "2026-09-12", "2026-09-11", "2026-09-09", "2026-09-07", "2026-09-05"],
        "생산제품": ["당근라페 200g", "당근라페 400g", "당근라페 200g", "당근라페 400g", "당근라페 200g", "당근라페 200g", "당근라페 400g", "당근라페 200g"],
        "생산수량(개)": [24, 16, 48, 24, 36, 12, 16, 24],
        "박스 포장 수": ["4 박스(특소)", "2 박스(소)", "8 박스(특소)", "3 박스(소)", "6 박스(특소)", "2 박스(특소)", "2 박스(소)", "4 박스(특소)"],
        "상태": ["출고 완료", "출고 완료", "출고 완료", "출고 완료", "출고 완료", "출고 완료", "출고 완료", "출고 완료"]
    }
    st.dataframe(pd.DataFrame(recent_prod_data), use_container_width=True)

# ---------------------------------------------------------
# TAB 3: 수기 출고 (+ 최근 수기 출고 내역 8개 표)
# ---------------------------------------------------------
with tab3:
    st.subheader("수기 출고 등록 (타 용도 사용)")
    out_date = st.date_input("출고 일자", datetime.date.today(), key="out_date")
    
    col_out1, col_out2 = st.columns(2)
    with col_out1:
        target_item_out = st.selectbox("출고 원부재료 선택", RAW_MATERIALS + SUB_MATERIALS, key="out_item")
        out_reason = st.selectbox("출고 목적", ["타 제품 제조 사용", "샘플/테스트 출고", "이벤트/증정용 사용", "기타 수기 출고"])
    with col_out2:
        out_qty = st.number_input("출고 수량", min_value=0.01, step=1.0, key="out_qty")
        out_note = st.text_input("상세 비고 (선택사항)", placeholder="예: B제품 포장용 카톤박스 10개 사용", key="out_note")
        
    if st.button("수기 출고 저장"):
        if out_qty <= 0:
            st.warning("출고 수량을 입력해주세요.")
        else:
            st.success(f"📤 **[{out_date}]** **[{target_item_out}]** {out_qty} 출고 완료!")

    st.divider()

    # 📋 최근 수기 출고 내역 (8개)
    st.markdown("### 📤 최근 수기 출고 내역 (최신 8건)")
    recent_out_data = {
        "출고일자": ["2026-09-15", "2026-09-14", "2026-09-11", "2026-09-08", "2026-09-06", "2026-09-04", "2026-09-02", "2026-08-30"],
        "재료명": ["카톤박스(소)", "당근 400 스티커", "파우치(200*160)", "시타 프리올리바 올리브 오일", "설탕(백설)", "카톤박스(특소)", "당근200트레이", "소금 (백설 꽃소금)"],
        "출고수량": [5.00, 10.00, 20.00, 500.00, 1000.00, 6.00, 10.00, 200.00],
        "단위": ["개", "개", "개", "ml", "g", "개", "개", "g"],
        "출고목적": ["타 제품 제조 사용", "샘플/테스트 출고", "타 제품 제조 사용", "샘플/테스트 출고", "타 제품 제조 사용", "이벤트/증정용 사용", "샘플/테스트 출고", "타 제품 제조 사용"],
        "비고": ["B제품 세트 포장용", "촬영용 샘플 사용", "C라인 파우치 테스트", "신제품 드레싱 연구용", "레시피 테스트용", "이벤트 증정 포장", "신규 마켓 샘플", "기타 소스 제조"]
    }
    df_recent_out = pd.DataFrame(recent_out_data)
    st.dataframe(
        df_recent_out.style.format({"출고수량": "{:,.2f}"}),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 4: 재고 조정 (+ 최근 재고 조정 내역 8개 표)
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
        adj_qty = st.number_input("조정 수량", min_value=0.01, step=1.0, key="adj_qty")
        adj_note = st.text_input("상세 비고", placeholder="예: 창고 이동 중 스티커 오염 손실 발생", key="adj_note")
        
    if st.button("재고 조정 저장"):
        if adj_qty <= 0:
            st.warning("조정 수량을 입력해주세요.")
        else:
            st.success(f"🛠️ **[{adj_date}]** **[{target_item_adj}]** {adj_qty} 재고 조정 완료!")

    st.divider()

    # 📋 최근 재고 조정 내역 (8개)
    st.markdown("### 🛠️ 최근 재고 조정 내역 (최신 8건)")
    recent_adj_data = {
        "조정일자": ["2026-09-14", "2026-09-10", "2026-09-07", "2026-09-03", "2026-08-31", "2026-08-28", "2026-08-25", "2026-08-20"],
        "재료명": ["당근200표시사항 스티커", "카톤박스(특소)", "라임 주스(레이지)", "당근200탑실링지", "후추(오뚜기)", "파우치(200*250)", "홀그레인 머스타드(르네디종)", "카톤박스(소)"],
        "조정구분": ["파손/불량 손실 (-)", "실사 재고 감소 (-)", "유통기한 경과 소진 (-)", "파손/불량 손실 (-)", "실사 재고 증가 (+)", "파손/불량 손실 (-)", "실사 재고 감소 (-)", "실사 재고 증가 (+)"],
        "조정수량": [5.00, 2.00, 200.00, 15.00, 50.00, 8.00, 120.00, 5.00],
        "단위": ["장", "개", "ml", "개", "g", "개", "개", "g"],
        "조정사유": ["보관 중 파손/불량", "재고 실사 차이 반영", "유통기한 경과 소진", "보관 중 파손/불량", "재고 실사 차이 반영", "보관 중 파손/불량", "재고 실사 차이 반영", "재고 실사 차이 반영"],
        "상세비고": ["인쇄 오염으로 인한 폐기", "창고 실사 2개 부족", "유통기한 도래 폐기", "실링 작업 중 찢어짐", "실사 결과 50g 초과 발견", "운송 과정 찌그러짐", "측정 오차 실사 차감", "실사 결과 5개 추가 발굴"]
    }
    df_recent_adj = pd.DataFrame(recent_adj_data)
    st.dataframe(
        df_recent_adj.style.format({"조정수량": "{:,.2f}"}),
        use_container_width=True
    )

# ---------------------------------------------------------
# TAB 5: 수불부 현황판
# ---------------------------------------------------------
with tab5:
    st.subheader("📋 원부재료 수불현황판")
    
    search_mode = st.radio(
        "조회 방식 선택", 
        ["📅 월별 통합 조회 (1방식)", "📆 기간 지정 조회 (2방식)"], 
        horizontal=True
    )
    st.divider()
    
    if search_mode == "📅 월별 통합 조회 (1방식)":
        col_m1, col_m2 = st.columns([1, 2])
        with col_m1:
            today = datetime.date.today()
            selected_year = st.selectbox("조회 연도", range(today.year - 2, today.year + 3), index=2)
            selected_month = st.selectbox("조회 월", range(1, 13), index=today.month - 1)
        with col_m2:
            st.info(f"💡 **{selected_year}년 {selected_month:02d}월**의 기월이월 및 월간 입출고 누적 수불 데이터를 조회합니다.")
    else:
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("시작일", datetime.date.today() - datetime.timedelta(days=7))
        with col_d2:
            end_date = st.date_input("종료일", datetime.date.today())
        st.info(f"💡 **{start_date} ~ {end_date}** 기간 동안 발생한 입출고 현황을 조회합니다.")

    # 1. 원재료 수불부
    st.markdown("### 🥕 원재료 수불부")
    raw_material_data = {
        "재료명": RAW_MATERIALS,
        "단위": ["g", "ml", "g", "g", "ml", "g", "g"],
        "기월이월": [10000.00, 15000.00, 3000.00, 3000.00, 2000.00, 5000.00, 500.00],
        "금월입고": [20000.00, 30000.00, 5000.00, 5000.00, 3000.00, 10000.00, 0.00],
        "생산출고(자동)": [520.00, 4776.00, 2036.00, 2036.00, 672.00, 672.00, 16.00],
        "수기출고": [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        "재고조정": [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
        "현재재고": [29480.00, 40224.00, 5964.00, 5964.00, 4328.00, 14328.00, 484.00],
        "안전재고": [5000.00, 10000.00, 2000.00, 2000.00, 1000.00, 2000.00, 100.00]
    }
    df_raw = pd.DataFrame(raw_material_data)
    st.dataframe(
        df_raw.style.format({
            "기월이월": "{:,.2f}", "금월입고": "{:,.2f}", "생산출고(자동)": "{:,.2f}",
            "수기출고": "{:,.2f}", "재고조정": "{:,.2f}", "현재재고": "{:,.2f}", "안전재고": "{:,.2f}"
        }),
        use_container_width=True
    )

    st.divider()

    # 2. 부재료 수불부
    st.markdown("### 📦 부재료 수불부")
    sub_material_data = {
        "재료명": SUB_MATERIALS,
        "단위": ["개", "개", "장", "개", "개", "개", "개", "개"],
        "기월이월": [1000, 1000, 500, 100, 1000, 500, 100, 500],
        "금월입고": [0, 0, 0, 200, 0, 0, 200, 0],
        "생산출고(자동)": [240, 240, 48, 40, 160, 160, 20, 0],
        "수기출고": [0, 0, 0, 10, 0, 0, 5, 0],
        "재고조정": [0, 0, -5, -2, 0, 0, 0, 0],
        "현재재고": [760, 760, 447, 248, 840, 340, 275, 500],
        "안전재고": [200, 200, 100, 50, 200, 100, 50, 100]
    }
    df_sub = pd.DataFrame(sub_material_data)
    st.dataframe(
        df_sub.style.format({
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
    st.caption("어느 거래처에서 무슨 원부재료를 얼마만큼 구매했는지 집계 현황을 확인합니다.")
    
    col_v1, col_v2, col_v3 = st.columns(3)
    with col_v1:
        st.metric("케이앤에스 누적 구매액", "1,250,000 원", "입고 5건")
    with col_v2:
        st.metric("은성특수산업 누적 구매액", "840,000 원", "입고 3건")
    with col_v3:
        st.metric("제이원글로벌 누적 구매액", "2,100,000 원", "입고 8건")
        
    st.divider()
    
    st.markdown("### 🔍 거래처별 상세 입고 내역")
    selected_v_filter = st.selectbox("조회할 거래처 선택", ["전체 거래처"] + VENDORS[:3])
    
    vendor_sample_data = {
        "입고일자": ["2026-09-02", "2026-09-05", "2026-09-10", "2026-09-12", "2026-09-15"],
        "거래처명": ["케이앤에스", "제이원글로벌", "은성특수산업", "케이앤에스", "제이원글로벌"],
        "구분": ["부재료", "원재료", "부재료", "부재료", "원재료"],
        "입고재료명": ["당근200트레이", "시타 프리올리바 올리브 오일", "카톤박스(소)", "당근200탑실링지", "라임 주스(레이지)"],
        "입고수량": [2000.0, 50.0, 500.0, 2000.0, 30.0],
        "단위": ["개", "L", "개", "개", "L"],
        "단가(원)": [150, 25000, 800, 100, 15000],
        "총 구매금액(원)": [300000, 1250000, 400000, 200000, 450000]
    }
    df_vendor = pd.DataFrame(vendor_sample_data)
    
    if selected_v_filter != "전체 거래처":
        df_vendor = df_vendor[df_vendor["거래처명"] == selected_v_filter]
        
    st.dataframe(
        df_vendor.style.format({
            "입고수량": "{:,.1f}",
            "단가(원)": "{:,d}",
            "총 구매금액(원)": "{:,d}"
        }),
        use_container_width=True
    )
