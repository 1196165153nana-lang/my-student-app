# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time
import random

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务规则配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
WORD_DIFFICULTY = ["简单", "中等", "困难"]
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

ANIMAL_EMOJIS = ["🐱", "🐶", "🦊", "🐼", "🐨", "🐯", "🐰", "🦆", "🐸", "🦁"]

# 初始化状态
if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "首页"
# undo_cache：{"op_type":"add_record|del_record", "table":"xxx", "record_id":"xxx", "data":{}}
if 'undo_cache' not in st.session_state:
    st.session_state['undo_cache'] = None
if "undo_input" not in st.session_state:
    st.session_state["undo_input"] = 0

# -------------------------- 工具函数 --------------------------
def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        return r.json().get("tenant_access_token")
    except Exception:
        return None

def fetch_feishu_data(table_id):
    token = get_tenant_access_token()
    if not token:
        return pd.DataFrame()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    res = requests.get(url, headers=headers, timeout=15)
    items = res.json().get("data", {}).get("items", [])
    rows = []
    for item in items:
        row = item["fields"]
        row["record_id"] = item["record_id"]
        rows.append(row)
    return pd.DataFrame(rows)

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type":"application/json"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    payload = {"fields": fields}
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    return resp.json()

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    resp = requests.delete(url, headers=headers, timeout=15)
    return resp.json()

def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]:
        return 45
    if content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]:
        return 50
    return 40

def generate_wechat_msg(name, review_date, learn_list):
    date_str = review_date.strftime("%m月%d日")
    items = "\n".join([f"{d.strftime('%m月%d日')}单词学习内容" for d in learn_list])
    return f"""【21天抗遗忘单词复习提醒】

{date_str}复习内容：

{items}

请{name}抽出时间复习，巩固记忆💪"""

def do_undo():
    cache = st.session_state.get("undo_cache")
    if not cache:
        st.warning("没有可撤销的操作")
        return
    op_type = cache["op_type"]
    table = cache["table"]
    if op_type == "del_record":
        # 删除操作撤销：重新新增这条记录
        add_feishu_record(table, cache["data"])
    elif op_type == "add_record":
        # 新增操作撤销：删除这条记录
        rid = cache["record_id"]
        delete_feishu_record(table, rid)
    st.session_state["undo_cache"] = None
    emoji = random.choice(ANIMAL_EMOJIS)
    st.toast(f"{emoji} 已撤销上次操作！", icon="✅")
    time.sleep(1)
    st.rerun()

# -------------------------- 页面配置与样式 --------------------------
st.set_page_config(page_title="FishTeacher", layout="centered", page_icon="🐟")
st.markdown("""
<style>
.block-container {
max-width: 850px !important;
padding-top: 1rem !important;
}
@media (max-width: 600px) {
[data-testid="column"] {
width:100% !important;
flex:1 1 100% !important;
min-width:100% !important;
}
}
div.stButton > button {
width: 100% !important;
height: 100px !important;
font-size: 22px !important;
font-weight: bold !important;
color:#FFFFFF !important;
background-color:#21242c !important;
border:2px solid #5294ff !important;
border-radius: 20px !important;
box-shadow:0 4px 10px rgba(0,0,0,0.3) !important;
}
div.stButton > button:active {
background-color:#5289ff !important;
}
.brand-title {font-size:32px;font-weight:bold;text-align:center;margin-bottom:10px;}
.brand-subtitle {font-size:20px;color:#444;text-align:center;margin-bottom:15px;}
.back-btn-box div.stButton > button{
height:55px !important;
font-size:16px !important;
width:300px !important;
background:transparent !important;
border:1px solid #555 !important;
justify-content:center !important;
padding-left:0 !important;
}
div[data-testid="stToast"]{
position:fixed;
top:45vh !important;
left:50%;
transform:translate(-50%, -50%);
width:360px;
font-size:22px;
font-weight:bold;
padding:26px;
border-radius:20px;
z-index:9999;
animation:toastPop 0.4s ease-out;
}
@keyframes toastPop {
0% {transform:translate(-50%,-50%) scale(0.6);opacity:0;}
60% {transform:translate(-50%,-50%) scale(1.1);}
100% {transform:translate(-50%,-50%) scale(1);opacity:1;}
}
footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
st.markdown('<p class="brand-subtitle"><strong>高效学员管理 & 21天抗遗忘系统</strong></p>', unsafe_allow_html=True)

def go_home():
    st.session_state["menu_choice"] = "首页"
    st.rerun()

# ==================== 首页 ====================
if st.session_state["menu_choice"] == "首页":
    c1,c2 = st.columns(2)
    with c1:
        if st.button("🔍 复习提醒"):
            st.session_state["menu_choice"] = "提醒"
            st.rerun()
        if st.button("📊 账目&明细"):
            st.session_state["menu_choice"] = "account"
            st.rerun()
        if st.button("👥 学生档案"):
            st.session_state["menu_choice"] = "student"
            st.rerun()
    with c2:
        if st.button("📝 快速录课"):
            st.session_state["menu_choice"] = "record"
            st.rerun()
        if st.button("📄 导出21天表格"):
            st.session_state["menu_choice"] = "export"
            st.rerun()
        if st.button("📥 批量导入"):
            st.session_state["menu_choice"] = "import"
            st.rerun()

# ==================== 复习提醒页面 ====================
elif st.session_state["menu_choice"] == "提醒":
    st.markdown('<div class="back-btn-box">',unsafe_allow_html=True)
    st.button("🏠 返回主页", on_click=go_home)
    st.markdown("</div>",unsafe_allow_html=True)
    df_records = fetch_feishu_data(TABLE_ID_RECORDS)
    sel_date = st.date_input("选择提醒日期", value=datetime.date.today())
    st.divider()
    st.info("此页面无撤销操作")

# ==================== 快速录课页面【增加撤销输入框】 ====================
elif st.session_state["menu_choice"] == "record":
    st.markdown('<div class="back-btn-box">',unsafe_allow_html=True)
    st.button("🏠 返回主页", on_click=go_home)
    st.markdown("</div>",unsafe_allow_html=True)

    # 仅当存在可撤销记录，才渲染输入框
    if st.session_state["undo_cache"] is not None:
        undo_num = st.number_input("输入数字1，撤销上一步操作", min_value=0, max_value=1, step=1, key="undo_record")
        if undo_num == 1:
            do_undo()

    st.divider()
    df_stu = fetch_feishu_data(TABLE_ID_STUDENTS)
    stu_list = df_stu["姓名"].dropna().unique().tolist()
    sel_stu = st.selectbox("选择学生", stu_list)
    sel_day = st.date_input("上课日期", value=datetime.date.today())
    sel_content = st.selectbox("学习内容", LEARN_CONTENTS)
    sel_hour = st.selectbox("课时", HOURS_OPTIONS)
    submit = st.button("✅确认录入本节课")

    if submit:
        df_check = fetch_feishu_data(TABLE_ID_RECORDS)
        dup = df_check[(df_check.get("学生","")==sel_stu) & (pd.to_datetime(df_check.get("上课日期",""),errors="coerce").dt.date == sel_day)]
        if len(dup) > 0:
            st.warning(f"{sel_stu} 今日已经录入课程，禁止重复录入！")
        else:
            payload = {
                "学生": sel_stu,
                "上课日期": sel_day.isoformat(),
                "学习内容": sel_content,
                "课时": sel_hour
            }
            resp = add_feishu_record(TABLE_ID_RECORDS, payload)
            rid = resp.get("data",{}).get("record_id")
            st.session_state["undo_cache"] = {
                "op_type":"add_record",
                "table":TABLE_ID_RECORDS,
                "record_id": rid,
                "data": payload
            }
            st.success("课程录入成功！如需撤销请输入数字1")
            time.sleep(1)
            st.rerun()

# ==================== 账目明细页面【增加撤销输入框】 ====================
elif st.session_state["menu_choice"] == "account":
    st.markdown('<div class="back-btn-box">',unsafe_allow_html=True)
    st.button("🏠 返回主页", on_click=go_home)
    st.markdown("</div>",unsafe_allow_html=True)

    if st.session_state["undo_cache"] is not None:
        undo_num = st.number_input("输入数字1，撤销上一步操作", min_value=0, max_value=1, step=1, key="undo_account")
        if undo_num == 1:
            do_undo()

    st.divider()
    df_rec = fetch_feishu_data(TABLE_ID_RECORDS)
    df_rec["上课日期_dt"] = pd.to_datetime(df_rec["上课日期"], errors="coerce")
    df_rec["月份"] = df_rec["上课日期_dt"].dt.strftime("%Y-%m")
    month_list = sorted(df_rec["月份"].dropna().unique().tolist(), reverse=True)
    sel_month = st.selectbox("选择月份", month_list)
    df_month = df_rec[df_rec["月份"] == sel_month].copy()
    df_month["单价"] = df_month["学习内容"].apply(get_unit_price)
    df_month["薪资"] = df_month["课时"] * df_month["单价"]

    total_hour = df_month["课时"].sum()
    total_salary = df_month["薪资"].sum()
    st.markdown(f"### 📌本月总课时：{total_hour:.1f} ｜总薪资：{total_salary:.0f}元")
    st.divider()
    col_left, col_right = st.columns([5,5])
    with col_left:
        st.subheader("📋统计汇总")
        stat_df = df_month.groupby("学生").agg({"课时":"sum","薪资":"sum"}).reset_index()
        st.dataframe(stat_df, use_container_width=True)
    with col_right:
        st.subheader("📜流水明细")
        show_df = df_month[["学生","上课日期","学习内容","课时","单价","薪资"]].copy()
        st.dataframe(show_df, use_container_width=True)
        st.divider()
        st.subheader("🗑 删除课程记录")
        name_opt = ["--选择学生--"] + sorted(df_month["学生"].dropna().unique())
        del_name = st.selectbox("选择学生", name_opt)
        if del_name != "--选择学生--":
            rows_del = df_month[df_month["学生"] == del_name]
            date_opt = ["--选择日期--"] + sorted(rows_del["上课日期"].dropna().unique(), reverse=True)
            del_date = st.selectbox("选择要删除的上课日期", date_opt)
            if del_date != "--选择日期--":
                target = rows_del[rows_del["上课日期"] == del_date].iloc[0]
                st.info(f"待删除：{del_name}｜{del_date}｜{target['学习内容']}｜课时{target['课时']}")
                confirm_del = st.checkbox("确认删除该条记录")
                if confirm_del and st.button("执行删除"):
                    st.session_state["undo_cache"] = {
                        "op_type":"del_record",
                        "table":TABLE_ID_RECORDS,
                        "data": target.to_dict()
                    }
                    delete_feishu_record(TABLE_ID_RECORDS, target["record_id"])
                    st.success("删除完成，输入数字1可以撤销")
                    time.sleep(1)
                    st.rerun()

# ==================== 学生档案页面【增加撤销输入框】 ====================
elif st.session_state["menu_choice"] == "student":
    st.markdown('<div class="back-btn-box">',unsafe_allow_html=True)
    st.button("🏠 返回主页", on_click=go_home)
    st.markdown("</div>",unsafe_allow_html=True)

    if st.session_state["undo_cache"] is not None:
        undo_num = st.number_input("输入数字1，撤销上一步操作", min_value=0, max_value=1, step=1, key="undo_student")
        if undo_num == 1:
            do_undo()

    st.divider()
    df_stu = fetch_feishu_data(TABLE_ID_STUDENTS)
    with st.expander("➕ 添加新学员", expanded=True):
        with st.form("add_stu_form"):
            new_name = st.text_input("学员姓名")
            new_status = st.selectbox("学员状态", STATUS_OPTIONS)
            new_note = st.text_area("备注信息")
            sub_add = st.form_submit_button("确认入库")
            if sub_add:
                if not new_name.strip():
                    st.warning("姓名不能为空")
                else:
                    exist = df_stu[df_stu["姓名"] == new_name.strip()]
                    if len(exist) > 0:
                        st.warning("该学员档案已存在，请勿重复添加")
                    else:
                        payload = {"姓名":new_name.strip(), "状态":new_status, "备注":new_note}
                        resp = add_feishu_record(TABLE_ID_STUDENTS, payload)
                        rid = resp.get("data",{}).get("record_id")
                        st.session_state["undo_cache"] = {
                            "op_type":"add_record",
                            "table":TABLE_ID_STUDENTS,
                            "record_id":rid,
                            "data":payload
                        }
                        st.success("学员档案新建完成，输入数字1可撤销")
                        time.sleep(1)
                        st.rerun()
    st.divider()
    sel_stu_edit = st.selectbox("📂编辑/删除学员", ["--请选择学员--"] + sorted(df_stu["姓名"].dropna().unique()))
    if sel_stu_edit != "--请选择学员--":
        row = df_stu[df_stu["姓名"] == sel_stu_edit].iloc[0]
        with st.container(border=True):
            edit_status = st.selectbox("修改状态", STATUS_OPTIONS, index=STATUS_OPTIONS.index(row.get("状态","在读/上课")) if row.get("状态") in STATUS_OPTIONS else 0)
            edit_note = st.text_area("修改备注", value=row.get("备注",""))
            c_a,c_b = st.columns(2)
            with c_a:
                if st.button("💾保存修改"):
                    token = get_tenant_access_token()
                    headers = {"Authorization":f"Bearer {token}","Content-Type":"application/json"}
                    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID_STUDENTS}/records/{row['record_id']}"
                    requests.patch(url, headers=headers, json={"fields":{"状态":edit_status,"备注":edit_note}})
                    st.success("档案已更新")
                    time.sleep(1)
                    st.rerun()
            with c_b:
                if st.button("🗑彻底删除该学员"):
                    if st.checkbox("⚠确认删除，删除后可以输入数字1撤销"):
                        st.session_state["undo_cache"] = {
                            "op_type":"del_record",
                            "table":TABLE_ID_STUDENTS,
                            "data":row.to_dict()
                        }
                        delete_feishu_record(TABLE_ID_STUDENTS, row["record_id"])
                        st.success("学员档案已删除，输入数字1恢复")
                        time.sleep(1)
                        st.rerun()

# ==================== 导出页面 ====================
elif st.session_state["menu_choice"] == "export":
    st.markdown('<div class="back-btn-box">',unsafe_allow_html=True)
    st.button("🏠 返回主页", on_click=go_home)
    st.markdown("</div>",unsafe_allow_html=True)
    st.info("此页面无撤销操作")

# ==================== 批量导入页面 ====================
elif st.session_state["menu_choice"] == "import":
    st.markdown('<div class="back-btn-box">',unsafe_allow_html=True)
    st.button("🏠 返回主页", on_click=go_home)
    st.markdown("</div>",unsafe_allow_html=True)
    st.info("此页面无撤销操作")
