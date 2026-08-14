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

# --- 复习提醒模块 ---
elif st.session_state['menu_choice'] == "提醒":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("选择提醒日期", datetime.date.today())
        target_s = st.selectbox("指定学员", ["全部学生"] + sorted(r_df['姓名'].unique().tolist()))
        reminders = {}
        for _, row in r_df.iterrows():
            if row['学习内容'] in WORD_ONLY_CONTENTS:
                diff = (q_date - row['dt']).days + 1
                if diff in REVIEW_DAYS:
                    n = row['姓名']
                    if target_s != "全部学生" and n != target_s: continue
                    if n not in reminders: reminders[n] = []
                    reminders[n].append(row['dt'].strftime("%Y-%m-%d"))
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **{name}**"); st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("今日该学生无复习任务")

# ==========【账目&明细｜顶部总指标+下方左右分栏】==========
elif st.session_state['menu_choice'] == "account":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if r_df.empty:
        st.info("暂无上课记录")
    else:
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        r_df['日期文字'] = r_df['dt_obj'].dt.strftime('%Y-%m-%d')

        target_m = st.selectbox("📅 选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']

        col_metric_1, col_metric_2 = st.columns(2)
        with col_metric_1:
            st.metric("💰 本月总薪资", f"¥{m_df['小计'].sum():,.0f}")
        with col_metric_2:
            st.metric("⌛ 本月总课时", f"{m_df['课时'].sum():.1f} h")

        st.divider()
        col_stat, col_log = st.columns([5,5])

        with col_stat:
            st.subheader("📋 学生月度统计")
            def merge_c(c):
                if c in ["单词", "旧数据补录", "导入", "大学单词", "雅思单词"]: return "单词课(合并)"
                return c
            m_df['统计课型'] = m_df['学习内容'].apply(merge_c)
            s_sum = m_df.groupby(['姓名', '统计课型']).agg({'课时': 'sum', '小计': 'sum'}).reset_index()
            s_order = s_sum.groupby('姓名')['课时'].sum().reset_index().sort_values('课时', ascending=False)
            final = pd.merge(s_order[['姓名']], s_sum, on='姓名', how='left')
            final.insert(0, '序号', final['姓名'].map({n: i+1 for i, n in enumerate(s_order['姓名'].unique())}))
            st.dataframe(final, use_container_width=True, hide_index=True, height=340)

            st.write("---")
            search_n = st.selectbox("🔍 选择学生查看当月明细", ["请选择"] + final['姓名'].unique().tolist())
            if search_n != "请选择":
                detail = m_df[m_df['姓名'] == search_n].sort_values(by='日期文字', ascending=False)
                st.dataframe(detail[['日期文字', '学习内容', '课时', '小计']], use_container_width=True, hide_index=True)

        with col_log:
            st.subheader("📜 全部流水记录（可删除）")
            show_df = m_df.copy()
            st.dataframe(show_df[["姓名","日期文字","学习内容","课时"]], use_container_width=True, hide_index=True, height=480)

            st.divider()
            st.subheader("🗑️ 删除上课记录")
            target_row = None
            del_student = st.selectbox("1.选择学生", ["请选择学生"] + sorted(show_df['姓名'].unique().tolist()))
            if del_student != "请选择学生":
                student_records = show_df[show_df["姓名"] == del_student].sort_values("日期文字", ascending=False)
                date_options = student_records["日期文字"].tolist()
                del_date = st.selectbox("2.选择上课日期", ["请选择日期"] + date_options)
                if del_date != "请选择日期":
                    target_row = show_df[(show_df["姓名"] == del_student) & (show_df["日期文字"] == del_date)].iloc[0]
                    st.info(f"待删除：{del_student}｜{del_date}｜{target_row['学习内容']}｜{target_row['课时']}h")

            confirm_check = st.checkbox("确认要删除这条记录", disabled=(target_row is None))
            if confirm_check and st.button("执行删除"):
                st.session_state["undo_cache"] = {
                    "action":"delete",
                    "table_id":TABLE_ID_RECORDS,
                    "record_id":target_row["record_id"],
                    "origin_fields": target_row.to_dict()
                }
                delete_feishu_record(TABLE_ID_RECORDS, target_row["record_id"])
                st.toast("🗑️ 记录已删除，下方可执行撤销", icon="⚠️")
                time.sleep(1)
                st.rerun()

        st.divider()
        st.subheader("↩️ 撤销上一步操作")
        cache_exist = isinstance(st.session_state.get("undo_cache"), dict)
        if cache_exist:
            st.success(f"✅ 存在待撤销操作：{st.session_state['undo_cache']['action']}")
        else:
            st.warning("⚠️ 无待撤销缓存")
        chk_undo_enable = st.checkbox("启用撤销操作", disabled=not cache_exist, key="chk_undo_enable_acc")
        chk_undo_confirm = st.checkbox("确认执行撤销", disabled=not chk_undo_enable, key="chk_undo_confirm_acc")

        if st.button("✅ 执行撤销", disabled= not (chk_undo_enable and chk_undo_confirm)):
            ok, msg = execute_undo()
            if ok:
                st.toast(f"✅ {msg}", icon="✅")
            else:
                st.toast(f"❌ {msg}", icon="❌")
            st.session_state["undo_cache"] = None
            time.sleep(0.8)
            st.rerun()

# --- 快速录课模块（已修复录入成功误报失败、移除录入撤销、新增页面内删除功能）---
elif st.session_state['menu_choice'] == "录入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())

    with st.form("in"):
        name = st.selectbox("学生姓名", active_s)
        date = st.date_input("上课日期")
        content = st.selectbox("内容", LEARN_CONTENTS)
        hour = st.selectbox("课时", HOURS_OPTIONS, index=1)
        submit = st.form_submit_button("确认录入")

        if submit:
            real_time_record_df = fetch_feishu_data(TABLE_ID_RECORDS)
            duplicate = False
            if not real_time_record_df.empty:
                real_time_record_df["parse_date"] = pd.to_datetime(real_time_record_df["学习日期"], unit="ms", errors="coerce").dt.date
                filter_cond = (real_time_record_df["姓名"] == name) & (real_time_record_df["parse_date"] == date)
                if real_time_record_df[filter_cond].shape[0] > 0:
                    duplicate = True

            if duplicate:
                st.toast(f"⚠️ 重复录入：{name} 在 {date} 已经存在一节课！同一天只能录入1节课", icon="⚠️")
            else:
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                new_fields = {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour}
                resp = add_feishu_record(TABLE_ID_RECORDS, new_fields)
                # 修复Bug：优先判断code=0代表真实入库成功，兼容双层record_id结构
                if resp.get("code") != 0:
                    st.toast(f"❌ 录入接口报错：{resp.get('msg','未知错误')}", icon="❌")
                else:
                    data = resp.get("data", {})
                    record_id = data.get("record_id")
                    if not record_id and "record" in data:
                        record_id = data["record"].get("record_id")
                    # 快速录课录入成功不写入撤销缓存，无法撤销
                    emoji = random.choice(ANIMAL_EMOJIS)
                    st.toast(f"{emoji} 同步成功", icon="✅")
                    time.sleep(1)
                    st.rerun()

    # 快速录课页面新增删除上课记录区域
    st.divider()
    st.subheader("🗑️ 删除上课记录")
    r_df_del = fetch_feishu_data(TABLE_ID_RECORDS)
    if r_df_del.empty:
        st.info("暂无上课记录")
    else:
        r_df_del['dt_obj'] = pd.to_datetime(r_df_del['学习日期'], unit='ms', errors='coerce')
        r_df_del['日期文字'] = r_df_del['dt_obj'].dt.strftime('%Y-%m-%d')
        target_row_del = None
        del_stu = st.selectbox("1.选择学生", ["请选择学生"] + sorted(r_df_del['姓名'].unique().tolist()), key="del_in_stu")
        if del_stu != "请选择学生":
            stu_rec = r_df_del[r_df_del["姓名"] == del_stu].sort_values("日期文字", ascending=False)
            date_opt = stu_rec["日期文字"].tolist()
            del_dt = st.selectbox("2.选择上课日期", ["请选择日期"] + date_opt, key="del_in_date")
            if del_dt != "请选择日期":
                target_row_del = r_df_del[(r_df_del["姓名"] == del_stu) & (r_df_del["日期文字"] == del_dt)].iloc[0]
                st.info(f"待删除：{del_stu}｜{del_dt}｜{target_row_del['学习内容']}｜{target_row_del['课时']}h")

        confirm_del_check = st.checkbox("确认删除本条上课记录", disabled=(target_row_del is None), key="chk_del_in")
        if confirm_del_check and st.button("执行删除", key="btn_del_in"):
            st.session_state["undo_cache"] = {
                "action":"delete",
                "table_id":TABLE_ID_RECORDS,
                "record_id":target_row_del["record_id"],
                "origin_fields": target_row_del.to_dict()
            }
            delete_feishu_record(TABLE_ID_RECORDS, target_row_del["record_id"])
            st.toast("🗑️ 记录已删除，前往账目页面执行撤销恢复", icon="⚠️")
            time.sleep(1)
            st.rerun()

# --- 学生档案模块【新增年级字段】 ---
elif st.session_state['menu_choice'] == "名册":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    with st.expander("➕ 添加新学员", expanded=True):
        with st.form("add"):
            n = st.text_input("姓名")
            grade = st.selectbox("年级", GRADE_OPTIONS)
            s = st.selectbox("状态", STATUS_OPTIONS)
            info = st.text_area("基础档案信息")
            if st.form_submit_button("确认入库"):
                if n:
                    fresh_student_df = fetch_feishu_data(TABLE_ID_STUDENTS)
                    if not fresh_student_df.empty and n in fresh_student_df['姓名'].tolist():
                        st.toast(f"⚠️ 学生【{n}】档案已存在，不可重复新建！", icon="⚠️")
                    else:
                        new_stu_fields = {"姓名": n, "年级": grade, "状态": s, "基础信息": info}
                        resp = add_feishu_record(TABLE_ID_STUDENTS, new_stu_fields)
                        record_id = resp.get("data",{}).get("record_id")
                        st.session_state["undo_cache"] = {
                            "action":"add",
                            "table_id":TABLE_ID_STUDENTS,
                            "record_id": record_id,
                            "origin_fields": new_stu_fields
                        }
                        emoji = random.choice(ANIMAL_EMOJIS)
                        st.toast(f"{emoji} 学员入库成功，下方可执行撤销", icon="✅")
                        time.sleep(1)
                        st.rerun()
    if not s_df.empty:
        ts = st.selectbox("📂 编辑/查看学生档案", ["未选择"] + sorted(s_df['姓名'].tolist()))
        if ts != "未选择":
            data = s_df[s_df['姓名'] == ts].iloc[0]
            with st.container(border=True):
                current_grade = data.get("年级", "未填写")
                idx_g = GRADE_OPTIONS.index(current_grade) if current_grade in GRADE_OPTIONS else 0
                ng = st.selectbox("年级", GRADE_OPTIONS, index=idx_g)
                ns = st.selectbox("状态", STATUS_OPTIONS, index=STATUS_OPTIONS.index(data['状态']) if data['状态'] in STATUS_OPTIONS else 0)
                ni = st.text_area("信息文本框", value=data.get('基础信息', ""), height=200)
                c1, c2 = st.columns(2)
                if c1.button("💾 保存档案内容"):
                    update_feishu_record(TABLE_ID_STUDENTS, data['record_id'], {"年级": ng, "状态": ns, "基础信息": ni})
                    emoji = random.choice(ANIMAL_EMOJIS)
                    st.toast(f"{emoji} 档案已更新", icon="✅")
                    time.sleep(1); st.rerun()
                if c2.button("🗑️ 彻底删除学生"):
                    if st.checkbox("确认删除"):
                        st.session_state["undo_cache"] = {
                            "action":"delete",
                            "table_id":TABLE_ID_STUDENTS,
                            "record_id":data["record_id"],
                            "origin_fields": data.to_dict()
                        }
                        delete_feishu_record(TABLE_ID_STUDENTS, data['record_id'])
                        st.toast("⚠️ 学员已删除，下方可执行撤销", icon="⚠️")
                        time.sleep(1); st.rerun()

    st.divider()
    st.subheader("↩️ 撤销上一步操作")
    cache_exist = isinstance(st.session_state.get("undo_cache"), dict)
    if cache_exist:
        st.success(f"✅ 当前可撤销：{st.session_state['undo_cache']['action']}")
    else:
        st.warning("⚠️ 暂无待撤销操作")
    chk_undo_enable = st.checkbox("启用撤销操作", disabled=not cache_exist, key="chk_undo_enable_stu")
    chk_undo_confirm = st.checkbox("确认执行撤销", disabled=not chk_undo_enable, key="chk_undo_confirm_stu")

    if st.button("✅ 执行撤销", disabled= not (chk_undo_enable and chk_undo_confirm)):
        ok, msg = execute_undo()
        if ok:
            st.toast(f"✅ {msg}", icon="✅")
        else:
            st.toast(f"❌ {msg}", icon="❌")
        st.session_state["undo_cache"] = None
        time.sleep(0.8)
        st.rerun()

# --- 导出21天表模块【课时矩阵表格增加预览，其他全部逻辑不变】---
elif st.session_state['menu_choice'] == "导出":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if r_all.empty:
        st.info("暂无上课记录，无法导出")
    else:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        r_all['ym_str'] = r_all['dt'].apply(lambda x:x.strftime("%Y-%m") if pd.notna(x) else None)

        tab1, tab2 = st.tabs(["📄 导出21天抗遗忘表","📊 导出本月课时表格(行学生，列日期)"])

        with tab1:
            target = st.selectbox("学员", sorted(r_all['姓名'].unique().tolist()))
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']; rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            preview_df = pd.DataFrame(output[2:])
            st.subheader("👁️ 表格预览")
            st.dataframe(preview_df, use_container_width=True, hide_index=True, height=350)

            if st.button("生成21天表格"):
                buf = io.StringIO(); pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
                st.download_button(f"📥 下载 {target}_21天表.csv", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")
                emoji = random.choice(ANIMAL_EMOJIS)
                st.toast(f"{emoji} 21天表格已生成，请下载", icon="✅")

        with tab2:
            ym_list = sorted([x for x in r_all['ym_str'].unique() if x is not None], reverse=True)
            sel_month = st.selectbox("选择要导出的月份", ym_list)

            # 构建课时矩阵，新增预览
            df_month = r_all[r_all['ym_str'] == sel_month].copy()
            df_month["date_short"] = df_month["dt"].apply(lambda d:d.strftime("%m.%d"))
            stu_date_h = defaultdict(lambda:defaultdict(float))
            stu_total = defaultdict(float)
            all_dates = set()
            all_stus = set()
            for _,row in df_month.iterrows():
                sname = row["姓名"]
                dshort = row["date_short"]
                h = float(row["课时"])
                stu_date_h[sname][dshort] += h
                stu_total[sname] += h
                all_dates.add(dshort)
                all_stus.add(sname)
            sorted_stu = sorted(all_stus)
            sorted_date = sorted(all_dates, key=lambda x:(int(x.split(".")[0]), int(x.split(".")[1])))
            csv_rows = []
            header_row = ["姓名","总课时"] + sorted_date
            csv_rows.append(header_row)
            for s in sorted_stu:
                row_data = [s, round(stu_total[s],1)]
                for d in sorted_date:
                    row_data.append(round(stu_date_h[s].get(d,0.0),1))
                csv_rows.append(row_data)

            # 预览表格
            st.subheader("👁️ 课时矩阵预览")
            preview_matrix = pd.DataFrame(csv_rows[1:], columns=csv_rows[0])
            st.dataframe(preview_matrix, use_container_width=True, hide_index=True, height=380)

            if st.button("生成课时矩阵表格"):
                buf2 = io.StringIO()
                pd.DataFrame(csv_rows).to_csv(buf2, index=False, header=False, encoding="utf-8-sig")
                st.download_button(f"📥 下载 {sel_month}_课时矩阵表.csv", buf2.getvalue().encode("utf-8-sig"), f"{sel_month}_课时矩阵表.csv", "text/csv")
                emoji = random.choice(ANIMAL_EMOJIS)
                st.toast(f"{emoji} 课时矩阵表格已生成，请下载", icon="✅")

# --- 批量导入模块【兼容年级列】 ---
elif st.session_state['menu_choice'] == "导入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f); bar = st.progress(0)
        if st.button("启动同步"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS); names_in = s_now['姓名'].tolist() if not s_now.empty else []
            for i, row in df.iterrows():
                name = str(row['姓名'])
                grade_val = str(row.get("年级","未填写")) if "年级" in df.columns else "未填写"
                if name not in names_in:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "年级":grade_val, "状态": "在读/上课"})
                    names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date(); ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                except: pass
                bar.progress((i+1)/len(df))
            emoji = random.choice(ANIMAL_EMOJIS)
            st.toast(f"{emoji} 批量导入完成", icon="✅")
            time.sleep(1.2)
            st.rerun()
