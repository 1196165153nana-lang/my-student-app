# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time
import random
from collections import defaultdict

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
WORD_ONLY_CONTENTS = ["单词", "旧数据补录", "导入"]
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)] # 0.5 到 10.0 小时
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]
GRADE_OPTIONS = ["未填写", "小学", "初一", "初二", "初三", "高一", "高二", "高三", "大学", "成人"]

ANIMAL_EMOJIS = ["🐱", "🐶", "🦊", "🐼", "🐨", "🐯", "🐰", "🦆", "🐸", "🦁"]

# 初始化状态
if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "首页"
if "undo_cache" not in st.session_state:
    st.session_state["undo_cache"] = None

# -------------------------- 2. 核心工具函数 --------------------------
def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        return r.json().get("tenant_access_token")
    except Exception as e:
        print(f"获取token失败:{e}")
        return None

def fetch_feishu_data(table_id):
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        items = r.json().get("data", {}).get("items", [])
        if not items: return pd.DataFrame()
        data = []
        for item in items:
            f = item["fields"]
            f["record_id"] = item["record_id"]
            data.append(f)
        return pd.DataFrame(data)
    except Exception as e:
        print(f"拉取数据异常:{e}")
        return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    forbidden = ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt", "dt_obj", "统计课型", "序号", "总课时(h)", "上课日期", "日期文字"]
    clean_f = {k: v for k, v in fields.items() if k not in forbidden}
    payload = {"fields": clean_f}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=12)
        resp = r.json()
        print(f"【新增记录完整API返回】{resp}")
        return resp
    except Exception as e:
        print(f"新增记录异常:{e}")
        return {"code": -1}

def update_feishu_record(table_id, record_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.put(url, headers=headers, json={"fields": fields}, timeout=12)
        return r.json()
    except: return {"code": -1}

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.delete(url, headers=headers, timeout=12)
        resp = r.json()
        print(f"【删除记录API返回】{resp}")
        return resp
    except Exception as e:
        print(f"删除异常:{e}")
        return {"code":-1}

def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]: return 45
    if content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]: return 50
    return 40

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日单词学习内容") for d in sorted_ln])
    return f"【21天抗遗忘单词复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦"

# --------------------------【撤销函数】--------------------------
def execute_undo():
    cache = st.session_state.get("undo_cache")
    if not (isinstance(cache, dict) and "action" in cache):
        return False, "无缓存操作"
    action = cache["action"]
    table_id = cache["table_id"]
    record_id = cache.get("record_id")
    origin_fields = cache.get("origin_fields")

    forbidden_undo_keys = ["record_id","dt_obj","月份","日期文字","小计","单价","统计课型","序号"]
    if origin_fields:
        origin_fields = {k:v for k,v in origin_fields.items() if k not in forbidden_undo_keys}

    if action == "add":
        if not record_id:
            return False, "add操作无record_id"
        res = delete_feishu_record(table_id, record_id)
        if res.get("code") ==0:
            return True, "撤销新增成功，已删除记录"
        else:
            return False, f"删除失败:{res}"
    elif action == "delete":
        if not origin_fields:
            return False, "delete操作缺少原始字段"
        res = add_feishu_record(table_id, origin_fields)
        if res.get("code") ==0:
            return True, "撤销删除成功，已恢复记录"
        else:
            return False, f"恢复新增失败:{res}"
    return False, "未知操作类型"

# -------------------------- 3. 全局页面样式 --------------------------
st.set_page_config(page_title="FishTeacher", layout="wide", page_icon="🐟")
st.markdown("""
<style>
.block-container { max-width: 1400px !important; padding-top: 1rem !important; padding-left:2rem; padding-right:2rem; }
@media (max-width: 768px) {
[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }
}
div.stButton > button {
    width: 330px !important;
    height: 100px !important;
    margin: 0 auto 15px auto !important;
    font-size: 22px !important;
    font-weight: bold !important;
    color: #FFFFFF !important;
    background-color: #21242c !important;
    border: 2px solid #5289f7 !important;
    border-radius: 20px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    padding-left: 25px !important;
    box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.3) !important;
}
div.stButton > button:active { background-color: #5289f7 !important; }

.brand-title {font-size: 32px;font-weight: bold;text-align: center;margin-bottom: 10px; }
.brand-subtitle { font-size: 30px; color:#444444;text-align: center;margin-bottom: 10px;}
.brand-desc {font-size: 10px;color:#666666;text-align: center;margin-bottom: 15px;}

.back-btn-box div.stButton > button {
height: 55px !important; font-size: 16px !important; width: 300px !important;
background-color: transparent !important; border: 1px solid #555 !important;
justify-content: center !important; padding-left: 0 !important;
}

div[data-baseweb="popover"] ul li {
        min-height: 100px !important;
        font-size: 22px !important;
        padding: 12px 20px !important;
    }
div[data-baseweb="popover"] ul {
        background-color: #1c1e24 !important;
        border-radius: 16px !important;
    }
div[data-baseweb="popover"] ul li:hover {
        background-color: #333640 !important;
    }
div[data-baseweb="popover"] ul li[aria-selected="true"] {
        background-color: #2a3142 !important;
    }

div[data-testid="stToast"] {
    position: fixed !important;
    top: 45vh !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    width: 360px !important;
    font-size: 22px !important;
    font-weight:bold !important;
    padding:26px !important;
    border-radius:20px !important;
    z-index: 9999 !important;
    animation: toastBounce 0.4s ease-out;
}

@keyframes toastBounce {
    0% { transform: translate(-50%, -50%) scale(0.6); opacity:0; }
    60% { transform: translate(-50%, -50%) scale(1.1); }
    100% { transform: translate(-50%, -50%) scale(1); opacity:1; }
}

footer {visibility: hidden;}

/* 全部DataFrame表格强制白色背景，黑色文字 */
div[data-testid="stDataFrame"] {
    background-color: #ffffff !important;
}
div[data-testid="stDataFrame"] table {
    background-color: #ffffff !important;
}
div[data-testid="stDataFrame"] th {
    background-color: #f7f9fc !important;
    color: #000000 !important;
}
div[data-testid="stDataFrame"] td {
    background-color: #ffffff !important;
    color: #000000 !important;
}

</style>
""", unsafe_allow_html=True)

st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
st.markdown('<p class="brand-subtitle"><strong>🐟 FishTeacher</strong></p>', unsafe_allow_html=True)
st.markdown('<p class="brand-desc">掌上拇指便捷管理</p>', unsafe_allow_html=True)

# -------------------------- 4. 页面路由分发 --------------------------
def back_home():
    st.session_state['menu_choice'] = "首页"
    st.rerun()

# --- 首页菜单 ---
if st.session_state['menu_choice'] == "首页":
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 复习提醒"): st.session_state['menu_choice'] = "提醒"; st.rerun()
        if st.button("📊 账目&明细"): st.session_state['menu_choice'] = "account"; st.rerun()
        if st.button("👥 学生档案"): st.session_state['menu_choice'] = "名册"; st.rerun()
    with col2:
        if st.button("📝 快速录课"): st.session_state['menu_choice'] = "录入"; st.rerun()
        if st.button("📄 导出21天"): st.session_state['menu_choice'] = "导出"; st.rerun()
        if st.button("📥 批量数据导入"): st.session_state['menu_choice'] = "导入"; st.rerun()


elif st.session_state['menu_choice'] == "account":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回首页"):
        back_home()
    st.markdown('</div>', unsafe_allow_html=True)

    df_rec = fetch_feishu_data(TABLE_ID_RECORDS)
    df_stu = fetch_feishu_data(TABLE_ID_STUDENTS)

    # 构建学生姓名‑状态映射
    stu_status_map = {}
    if not df_stu.empty:
        for _,row in df_stu.iterrows():
            s_name = row.get("学生姓名","")
            s_status = row.get("状态","")
            if s_name:
                stu_status_map[s_name] = s_status

    if df_rec.empty:
        st.info("暂无上课记录")
    else:
        df_rec["上课日期"] = pd.to_datetime(df_rec["上课日期"], errors="coerce")
        min_dt = df_rec["上课日期"].min().date()
        max_dt = df_rec["上课日期"].max().date()
        select_month = st.date_input("选择结算月份", value=max_dt, min_value=min_dt, max_value=max_dt)
        sel_year = select_month.year
        sel_month = select_month.month

        df_month = df_rec[(df_rec["上课日期"].dt.year==sel_year) & (df_rec["上课日期"].dt.month==sel_month)].copy()

        if df_month.empty:
            st.warning("所选月份没有课时记录")
        else:
            # 计算统计
            total_hour = df_month["课时(h)"].sum()
            total_fee = 0
            for _,r in df_month.iterrows():
                total_fee += r["课时(h)"] * get_unit_price(r["学习内容"])

            st.subheader(f"📅 {sel_year}年{sel_month}月汇总｜总课时:{total_hour:.1f}h｜总薪资:{total_fee}元")

            # 电脑大屏左右分栏，手机自动上下
            col_left, col_right = st.columns([1,1])
            with col_left:
                st.markdown("### 📈学生月度统计")
                group_df = df_month.groupby("学生姓名").agg(
                    课时总小时=("课时(h)","sum")
                ).reset_index()
                # 【核心改动：结课学生名字后面加上(结课)】
                def label_student_name(n):
                    stat = stu_status_map.get(n,"")
                    if stat == "结课/毕业":
                        return f"{n}(结课)"
                    return n
                group_df["学生姓名"] = group_df["学生姓名"].apply(label_student_name)
                st.dataframe(group_df, use_container_width=True)

                # 导出月度结算csv
                buf = io.StringIO()
                group_df.to_csv(buf, index=False, encoding="utf‑8‑sig")
                csv_bytes = buf.getvalue().encode("utf‑8‑sig")
                st.download_button(
                    label="📥导出本月结算表格(CSV)",
                    data=csv_bytes,
                    file_name=f"{sel_year}_{sel_month}_月度结算.csv",
                    mime="text/csv"
                )

            with col_right:
                st.markdown("### 📒当月流水明细")
                detail_df = df_month[["上课日期","学生姓名","学习内容","课时(h)"]].copy()
                detail_df["上课日期"] = detail_df["上课日期"].dt.strftime("%Y‑%m‑%d")
                # 明细表格同样加上(结课)标记
                detail_df["学生姓名"] = detail_df["学生姓名"].apply(label_student_name)
                st.dataframe(detail_df, use_container_width=True)


elif st.session_state['menu_choice'] == "提醒":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回首页"):
        back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.info("复习提醒模块，你原有代码粘贴此处")

elif st.session_state['menu_choice'] == "名册":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回首页"):
        back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.info("学生档案模块，原有代码粘贴此处")

elif st.session_state['menu_choice'] == "录入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回首页"):
        back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.info("快速录课模块，原有代码粘贴此处")

elif st.session_state['menu_choice'] == "导出":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回首页"):
        back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.info("21天导出模块，原有代码粘贴此处")

elif st.session_state['menu_choice'] == "导入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回首页"):
        back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.info("批量导入模块，原有代码粘贴此处")
